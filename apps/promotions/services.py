"""Сервисы резервирования (anti-oversell).

Списание остатка — одним атомарным conditional UPDATE с F() (см.
docs/references/patterns/anti-oversell.md). Смена статусов — через
ReservationSM. Возврат остатка при отмене/истечении — в on_transition.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.aggregator.stock_sync import touch_promotion
from apps.loyalty.models import Voucher

from .models import Customer, Promotion, Reservation, WaitlistEntry
from .notifications import enqueue_reservation_email, enqueue_waitlist_available
from .state_machine import ReservationSM

# алфавит без похожих символов (0/O, 1/I) — код диктуется голосом на выдаче
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class OutOfStock(Exception):
    """Недостаточно доступного количества (или акция не active)."""


class ReservationLimitReached(Exception):
    """Превышен Promotion.max_per_customer для этого клиента."""


class ContactHoldLimit(Exception):
    """KA-12 E6.6: у контакта уже слишком много неподтверждённых резервов в бизнесе."""


class VoucherError(Exception):
    """Ваучер нельзя погасить. reason: not_found/inactive/expired/used_up/stale;
    KA-H9: needs_amount (сертификат с остатком — только с суммой), insufficient,
    invalid_amount, promotion_ended (купон остановленной/закончившейся акции)."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _unique_reference_code() -> str:
    for _ in range(10):
        code = "R-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Reservation.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique reservation reference code")


def _get_or_create_customer(*, name, email, phone) -> Customer:
    customer = None
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
    elif phone and phone.strip():
        # T-8.2: «отложить» принимает телефон без почты — иначе каждый повтор создавал
        # нового клиента и лимит «N pro Kunde» не работал. KA-12 E6.6: «0171 …» и
        # «+49 171 …» — один человек (сравнение по ключу из цифр).
        from apps.core.contacts import find_by_phone

        matches = find_by_phone(Customer.objects.order_by("created_at"), phone)
        customer = matches[0] if matches else None
        if customer is None:  # короткий/нестандартный номер — точное совпадение, как раньше
            customer = Customer.objects.filter(phone=phone.strip()).order_by("created_at").first()
    if customer is not None:
        # дозаполняем пустые контакты, имя не перетираем
        updates = []
        if not customer.phone and phone:
            customer.phone = phone
            updates.append("phone")
        if updates:
            customer.save(update_fields=[*updates, "updated_at"])
        return customer
    return Customer.objects.create(name=name, email=email, phone=(phone or "").strip())


@transaction.atomic
def reserve(
    promotion,
    *,
    name,
    email="",
    phone="",
    quantity=1,
    note="",
    source_channel="",
    open_cap=None,
):
    """ЛЕГАСИ-рельсы (P5/P7 «ценовой слой»): витрина с P5 резервы НЕ порождает —
    новые акции закрываются стандартными сделками (`purchase`/`book`/`book_stay`).
    Функция и /r/<code>/ живут, пока открытые резервы не иссякнут (история цела).

    Создать бронь, атомарно списав остаток акции. Бросает OutOfStock, если
    остатка не хватило/акция не active, и ReservationLimitReached при
    превышении max_per_customer.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    promo_id = getattr(promotion, "id", promotion)
    promotion = Promotion.objects.get(id=promo_id)
    if promotion.scope_kind:  # KA-12 PR-1: резервировать нечего — акция действует в корзине
        raise ValueError("scope promotion cannot be reserved")

    # KA-12 E6.6: один человек — по очереди (поиск клиента, лимит на клиента, бронь).
    # Advisory по контакту, а не строка клиента: UPDATE остатка акции не блокируется,
    # anti-oversell между РАЗНЫМИ людьми идёт параллельно, как раньше.
    from apps.core.contacts import advisory_lock, contact_lock_key

    # Ключ — на весь бизнес (не на акцию): потолок «открытых на контакт» (open_cap,
    # витрина) считается под той же блокировкой — параллельные POST его не обходят.
    advisory_lock(contact_lock_key("resv", email, phone))
    if open_cap is not None and open_reservations_for_contact(email, phone) >= open_cap:
        raise ContactHoldLimit()
    customer = _get_or_create_customer(name=name, email=email, phone=phone)

    # лимит на клиента по этой акции (по сумме активных броней)
    if promotion.max_per_customer:
        # SM-3: «активные» через реестр — резерв в кастом-active статусе владельца
        # тоже считается (литерал позволял обойти лимит на клиента).
        from apps.core import status_registry

        active_qty = (
            Reservation.objects.filter(
                promotion=promotion,
                customer=customer,
                status__in=status_registry.active_statuses_for("reservation"),
            ).aggregate(n=Sum("quantity"))["n"]
            or 0
        )
        if active_qty + quantity > promotion.max_per_customer:
            raise ReservationLimitReached()

    with transaction.atomic():
        reservation = _reserve_locked(
            promotion,
            customer=customer,
            quantity=quantity,
            note=note,
            source_channel=source_channel,
        )
    # письмо клиенту/владельцу — после коммита транзакции
    enqueue_reservation_email(reservation, "created")
    return reservation


def _reserve_locked(promotion, *, customer, quantity, note, source_channel):
    """Счётчик акции + (T-8.23f) склад товара + бронь — одной транзакцией: нехватка
    на складе откатывает и списание лимита акции."""
    # атомарное условное списание остатка
    if promotion.available_quantity is not None:
        rows = Promotion.objects.filter(
            id=promotion.id,
            status="active",
            available_quantity__gte=quantity,
        ).update(available_quantity=F("available_quantity") - quantity)
        if rows == 0:
            raise OutOfStock()
        touch_promotion(promotion.id)  # T-8.26 п.3
    elif promotion.status != "active":
        # без лимита остатка, но акция должна быть активной
        raise OutOfStock()

    initial_status = "confirmed" if promotion.auto_confirm else "pending"
    now = timezone.now()
    expires_at = full_hold_until(promotion, now)
    if initial_status == "pending":
        # KA-12 E6.6 (Р-2): неподтверждённый резерв держит товар недолго — выдуманные
        # контакты не «выкупят витрину» на сутки; подтверждение продлевает до полного срока.
        expires_at = min(expires_at, now + timedelta(hours=pending_hold_hours()))
    reservation = Reservation.objects.create(
        promotion=promotion,
        customer=customer,
        reference_code=_unique_reference_code(),
        quantity=quantity,
        status=initial_status,
        expires_at=expires_at,
        confirmed_at=now if initial_status == "confirmed" else None,
        note=note,
        source_channel=(source_channel or "")[:50],
    )
    hold_product_stock(reservation)
    return reservation


def open_reservations_for_contact(email="", phone="") -> int:
    """KA-12 E6.6 (Р-4): сколько НЕПОДТВЕРЖДЁННЫХ резервов у контакта по всему бизнесу.

    Только pending: подтверждённые владелец уже видел; чужой человек, вписав адрес
    жертвы, держит её «заблокированной» лишь на короткий срок неподтверждённого."""
    from django.db.models import Q

    from apps.core import status_registry
    from apps.core.contacts import phone_candidates_regex, phone_key

    email, phone = (email or "").strip(), (phone or "").strip()
    key = phone_key(phone)
    who = Q()
    if email:
        who |= Q(customer__email__iexact=email)
    regex = phone_candidates_regex(phone) if key else ""
    if regex:
        who |= Q(customer__phone__regex=regex)
    if not who:
        return 0
    pending = [
        code for code in status_registry.active_statuses_for("reservation") if code != "confirmed"
    ]
    rows = Reservation.objects.filter(who, status__in=pending).values_list(
        "customer__email", "customer__phone"
    )
    return sum(
        1
        for row_email, row_phone in rows
        if (email and (row_email or "").lower() == email.lower())
        or (key and phone_key(row_phone) == key)
    )


def coupon_by_email_only(promotion) -> bool:
    """KA-12 E6.6 (Р-3): код купона — только письмом (проверка владения адресом)."""
    return (getattr(promotion, "metadata", None) or {}).get("coupon_delivery") == "email"


def pending_hold_hours() -> int:
    return int(getattr(settings, "PROMO_PENDING_HOLD_HOURS", 4) or 4)


def full_hold_until(promotion, start):
    """Полный срок резерва от ``start``: TTL акции, но не дольше самой акции (T-8.2)."""
    until = start + timedelta(hours=promotion.reservation_ttl_hours)
    if promotion.ends_at and start < promotion.ends_at < until:
        until = promotion.ends_at
    return until


def _stock_target(promotion):
    """T-8.23f: товар акции, у которого ведётся остаток (без вариантов), иначе None.

    Решение владельца S2 (2026-10-11): при включённом учёте склада резерв ограничен
    складом. Товар с вариантами — резерв не знает варианта, склад не трогаем.
    """
    product = getattr(promotion, "product", None)
    if product is None or product.stock_quantity is None or product.has_variants:
        return None
    return product


def hold_product_stock(reservation) -> None:
    """Держим остаток товара под резерв (в транзакции резерва). Нехватка → OutOfStock.

    Списываем СРАЗУ при резерве, а не при выдаче: иначе двое отложили бы последнюю
    штуку. Выдача на кассе склад больше не трогает; отмена/истечение — возврат.
    """
    from apps.catalog.models import Product

    target = _stock_target(reservation.promotion)
    if target is None:
        return
    row = Product.objects.select_for_update().get(pk=target.pk)
    if row.stock_quantity is None:
        return
    if row.stock_quantity < reservation.quantity:
        raise OutOfStock()
    row.stock_quantity -= reservation.quantity
    row.save(update_fields=["stock_quantity", "updated_at"])
    from apps.inventory.services import consume_fefo, has_lots, record_movement

    record_movement(
        product=row,
        kind="sale",
        delta=-reservation.quantity,
        source="reservation",
        source_ref=str(reservation.pk),
        note=reservation.reference_code,
    )
    if has_lots(row, None):
        consume_fefo(row, None, qty=reservation.quantity)


def release_product_stock(reservation) -> None:
    """Вернуть удержанный остаток (отмена/истечение). Ровно один раз: возврат пишется
    в леджер идемпотентно, счётчик растёт только если движение действительно создано
    и было удержание (sale-движение этого резерва)."""
    from django.db.models import F

    from apps.catalog.models import Product
    from apps.inventory.models import StockMovement
    from apps.inventory.services import has_lots, record_movement, restore_fefo

    ref = str(reservation.pk)
    held = StockMovement.objects.filter(source="reservation", source_ref=ref, kind="sale").first()
    if held is None:
        return
    with transaction.atomic():
        moved = record_movement(
            product=held.product,
            kind="return",
            delta=-held.delta,
            source="reservation",
            source_ref=ref,
            note=reservation.reference_code,
        )
        if moved is None:
            return  # уже вернули
        Product.objects.filter(pk=held.product_id, stock_quantity__isnull=False).update(
            stock_quantity=F("stock_quantity") - held.delta
        )
        if has_lots(held.product, None):
            restore_fefo(held.product, None, qty=-held.delta)


@transaction.atomic
def purchase(
    promotion,
    *,
    quantity=1,
    name,
    email="",
    phone="",
    note="",
    source_channel="",
    fulfillment="",
    shipping_cents=0,
    shipping_address="",
    payment_method="",
    customer_type="private",
    billing_company="",
    billing_vat_id="",
    payment_due_at=None,
    pickup_slot=None,
    pickup_capacity=0,
):
    """P2 «ценовой слой»: чекаут акции СТАНДАРТНЫМ заказом (план
    promo-price-layer-plan-2026-08-03).

    Двойное списание в ОДНОЙ транзакции: (1) лимит кампании — тот же
    conditional UPDATE, что у reserve (rows==0 → OutOfStock, замок конкуренции
    прежний); (2) физический склад товара — штатный anti-oversell
    `create_order` (custom-строка с product). OutOfStock склада откатывает и
    лимит кампании — atomic. Маркер {"promo": id} в modifiers строки — по нему
    `_restore_promo_limits` возвращает лимит при отмене/возврате заказа.
    Цели v1: product и «свободная» акция (без цели — строка без склада);
    service/stay идут своими рельсами (P3/P4)."""
    if promotion.price_condition:
        # В2: условная акция онлайн не продаётся — гард в сервисе, не только во вьюхе
        # (будущие каналы: бот, MCP).
        raise ValueError("conditional promotion is not sold online")
    if promotion.scope_kind:
        # KA-12 PR-1 (ревью): акция на категорию/магазин действует в корзине на товары —
        # своей цены у неё нет (кастом-строка с ценой None уронила бы create_order).
        raise ValueError("scope promotion is applied in the cart, not sold itself")
    from . import gifts

    if gifts.is_gift(promotion):
        raise ValueError("gift promotion is added to qualifying orders, not sold")
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    # KA-12 PR-5 (ревью): прямая покупка акции — то же правило клиента, что корзина.
    from . import eligibility

    eligibility.check([promotion], email=email, phone=phone)
    # (1) лимит кампании (None = без лимита; но акция обязана быть active)
    if promotion.available_quantity is not None:
        rows = Promotion.objects.filter(
            id=promotion.id,
            status="active",
            available_quantity__gte=quantity,
        ).update(available_quantity=F("available_quantity") - quantity)
        if rows == 0:
            raise OutOfStock()
        touch_promotion(promotion.id)  # T-8.26 п.3
    elif promotion.status != "active":
        raise OutOfStock()

    # (2) стандартный заказ с замороженной промо-ценой; склад — штатно.
    from apps.orders import services as order_services

    title = promotion.title.get("de") or next(iter(promotion.title.values()), "Aktion")
    # SH-22: в строке заказа печатается ТОВАР, а название акции едет снимком
    # рядом со скидкой — иначе владелец видел в составе «Sommer-Deal» и не мог
    # понять, что именно продано. Свободная акция (без товара) остаётся собой.
    line_title = str(promotion.product) if promotion.product_id else title
    order = order_services.create_order(
        items=[],
        name=name,
        email=email,
        phone=phone,
        note=note,
        source_channel=source_channel or "promo",
        # SH-24: покупка по акции знает способ получения (раньше форсила
        # самовывоз — у бизнеса с доставкой заказ по акции молча ехал «на вынос»).
        fulfillment=fulfillment or "pickup",
        shipping_cents=shipping_cents,
        shipping_address=shipping_address,
        # SH-23d: способ оплаты и покупатель — как у обычного чекаута.
        payment_method=payment_method,
        customer_type=customer_type,
        billing_company=billing_company,
        billing_vat_id=billing_vat_id,
        payment_due_at=payment_due_at,
        # KA-12 E2.7: время самовывоза — та же ёмкость окна, что у корзины.
        pickup_slot=pickup_slot,
        pickup_capacity=pickup_capacity,
        custom_lines=[
            (
                line_title,
                promotion.new_price,
                quantity,
                promotion.product,
                None,
                [{"promo": str(promotion.pk), "label": "Aktion"}],
                None,
                # SH-22: обе цены известны здесь — снимок листовой и кампании.
                {
                    # SF-7: «Listenpreis» в заказе = объявленная цена сравнения;
                    # снижение не объявлено — разницу не выдумываем.
                    "list_price": promotion.old_price if promotion.has_discount else None,
                    "promotion": promotion,
                },
            )
        ],
    )
    return order


def confirm(reservation, *, actor=None):
    """pending → confirmed (ручное подтверждение владельцем)."""
    with transaction.atomic():
        # T-8.30g (ревью): строка под блокировкой — параллельная отмена/выдача не
        # перезапишет статус устаревшим объектом (как cancel/expire).
        res = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if res.status == "pending":
            res.confirmed_at = timezone.now()
            res.save(update_fields=["confirmed_at", "updated_at"])
        return ReservationSM().apply(res, "confirmed", actor=actor)


def fulfill(reservation, *, actor=None):
    """confirmed → fulfilled (бронь выдана клиенту).

    T-8.2: неподтверждённую бронь (pending) сначала подтверждаем — клиент с кодом стоит
    у кассы, а кнопка «Ausgeben» иначе падала (перехода pending → fulfilled нет).
    Письмо «подтверждено» в этот момент не шлём: клиент уже получает товар.
    """
    with transaction.atomic():
        # T-8.30g (ревью): двойной тап у прилавка и гонка «выдача ↔ отмена» —
        # решение по статусу принимается на заблокированной строке.
        res = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if res.status == "pending":
            from apps.notifications import prefs

            with prefs.muted(customer=True):
                res = confirm(res, actor=actor)
        if res.status != "fulfilled":
            res.fulfilled_at = timezone.now()
            res.save(update_fields=["fulfilled_at", "updated_at"])
        return ReservationSM().apply(res, "fulfilled", actor=actor)


def cancel(reservation, *, actor=None):
    """Отмена брони с возвратом остатка. Идемпотентно (защита от double-refund)."""
    with transaction.atomic():
        res = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if res.status not in ("pending", "confirmed"):
            return res  # уже терминальная — no-op
        res.cancelled_at = timezone.now()
        res.save(update_fields=["cancelled_at", "updated_at"])
        return ReservationSM().apply(res, "cancelled", actor=actor)


def expire(reservation, *, actor=None):
    """Просрочка брони (по TTL) с возвратом остатка. Идемпотентно."""
    with transaction.atomic():
        res = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if res.status not in ("pending", "confirmed"):
            return res
        return ReservationSM().apply(res, "expired", actor=actor)


# ---------------------------------------------------------------------------
# Ваучеры / промокоды
# ---------------------------------------------------------------------------


def _unique_voucher_code(prefix: str = "V-") -> str:
    for _ in range(10):
        code = prefix + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Voucher.objects.filter(code=code).exists():
            return code
    raise RuntimeError("could not generate unique voucher code")


def generate_vouchers(
    *,
    label,
    count=1,
    max_uses=1,
    expires_at=None,
    customer=None,
    discount_percent=None,
    discount_cents=None,
    min_order_cents=0,
):
    """Сгенерировать count ваучеров с уникальными кодами. Вернуть список.

    customer (D1): опц. привязка к клиенту — ваучер появится в карточке 360° CRM.
    discount_percent/discount_cents (A4): структурная скидка для онлайн-заказа
    (промокод на чекауте); оба пустые = ручной ваучер-метка как раньше."""
    count = max(1, min(int(count), 200))  # разумный потолок на пачку
    created = []
    for _ in range(count):
        created.append(
            Voucher.objects.create(
                code=_unique_voucher_code(),
                label=label,
                max_uses=max_uses,
                expires_at=expires_at,
                customer=customer,
                discount_percent=discount_percent or None,
                discount_cents=discount_cents or None,
                min_order_cents=min_order_cents or 0,
            )
        )
    return created


# ---------------------------------------------------------------------------
# T-8.3: купон акции («Coupon holen») — план docs/t8-3-coupon-plan-2026-10-10.md
# ---------------------------------------------------------------------------


class CouponUnavailable(Exception):
    """Купон не выдан: акция не активна или все купоны розданы."""


def find_coupon(promotion, code) -> Voucher | None:
    code = (code or "").strip().upper()
    if not code:
        return None
    return Voucher.objects.filter(code=code, promotion=promotion).first()


class CouponExists(Exception):
    """KA-H9: купон по этим контактам уже выдан — код в браузер не раскрываем."""

    def __init__(self, voucher):
        super().__init__(voucher.code)
        self.voucher = voucher


def issue_coupon(
    promotion,
    *,
    name="",
    email="",
    phone="",
    existing_code="",
    source_channel="",
    reveal_existing=True,
):
    """Выдать купон акции → (voucher, created).

    «1 на человека»: код из куки этого браузера (``existing_code``) или тот же
    e-mail/телефон возвращают уже выданный купон — лимит не тронут. Лимит акции
    (``available_quantity``) списывается тем же conditional UPDATE, что резерв.
    Контакт необязателен; клиент заводится, только если он оставлен."""
    existing = find_coupon(promotion, existing_code)
    if existing is not None:
        return existing, False
    email = (email or "").strip()
    phone = (phone or "").strip()
    # KA-12 E6.6: два параллельных запроса одного человека не выпускают два купона —
    # поиск выданного и выпуск под одной блокировкой по контакту.
    with transaction.atomic():
        from apps.core.contacts import advisory_lock, contact_lock_key

        advisory_lock(contact_lock_key(f"coupon:{promotion.id}", email, phone))
        return _issue_coupon_locked(
            promotion,
            name=name,
            email=email,
            phone=phone,
            source_channel=source_channel,
            reveal_existing=reveal_existing,
        )


def _issue_coupon_locked(promotion, *, name, email, phone, source_channel, reveal_existing):
    customer = None
    if email or phone:
        customer = _get_or_create_customer(
            name=(name or "").strip() or email or phone, email=email, phone=phone
        )
        existing = Voucher.objects.filter(promotion=promotion, customer=customer).first()
        if existing is not None:
            # KA-H9: на витрине контакт — не доказательство владения: кто знает чужой
            # e-mail, получил бы чужой код. reveal_existing=False → вызывающий шлёт
            # код на адрес из карточки клиента, а не показывает его.
            if not reveal_existing:
                raise CouponExists(existing)
            return existing, False
    with transaction.atomic():
        active = Promotion.objects.filter(id=promotion.id, status="active")
        if promotion.available_quantity is None:
            if not active.exists():
                raise CouponUnavailable
        elif not active.filter(available_quantity__gte=1).update(
            available_quantity=F("available_quantity") - 1
        ):
            raise CouponUnavailable
        else:
            touch_promotion(promotion.id)  # T-8.26 п.3
        voucher = Voucher.objects.create(
            code=_unique_voucher_code("C-"),
            label=(promotion.title_text or "Coupon")[:120],
            max_uses=1,
            expires_at=promotion.ends_at,
            customer=customer,
            promotion=promotion,
            source_channel=(source_channel or "")[:30],
        )
    return voucher, True


def _promotion_ended(voucher) -> bool:
    """KA-H9: купон акции живёт, пока жива акция (снимок expires_at этого не видит).
    Распроданный лимит — НЕ конец: выданные купоны сами его и выбрали."""
    if not voucher.promotion_id:
        return False
    promo = voucher.promotion
    if promo is None or promo.status != "active":
        return True
    return bool(promo.ends_at and promo.ends_at < timezone.now())


def _locked_voucher(code):
    """Ваучер под блокировкой + общие проверки (найден/активен/срок/акция)."""
    voucher = (
        Voucher.objects.select_for_update(of=("self",))
        .select_related("promotion")
        .filter(code=code)
        .first()
    )
    if voucher is None:
        raise VoucherError("not_found")
    if not voucher.is_active:
        raise VoucherError("inactive")
    if voucher.expires_at and voucher.expires_at < timezone.now():
        raise VoucherError("expired")
    if _promotion_ended(voucher):
        raise VoucherError("promotion_ended")
    return voucher


@transaction.atomic
def redeem_balance(code, amount_cents, *, expect_used=None):
    """KA-H9: списать сумму с сертификата у кассы. Отказ, а не урезание: «на кассе
    приняли 30 €, а списали 20 €» хуже ошибки. Двойной тап — через expect_used."""
    code = (code or "").strip().upper()
    voucher = _locked_voucher(code)
    if voucher.balance_cents is None:
        raise VoucherError("not_found")
    amount = int(amount_cents or 0)
    if amount <= 0:
        raise VoucherError("invalid_amount")
    if voucher.balance_cents <= 0:
        raise VoucherError("used_up")
    if expect_used is not None and voucher.used_count != expect_used:
        raise VoucherError("stale")
    if amount > voucher.balance_cents:
        raise VoucherError("insufficient")
    updated = Voucher.objects.filter(pk=voucher.pk, balance_cents__gte=amount).update(
        balance_cents=F("balance_cents") - amount,
        used_count=F("used_count") + 1,
        updated_at=timezone.now(),
    )
    if not updated:
        raise VoucherError("insufficient")
    voucher.refresh_from_db(fields=["balance_cents", "used_count", "updated_at"])
    return voucher


@transaction.atomic
def redeem_voucher(code, *, expect_used=None):
    """Погасить ваучер (одно использование). Бросает VoucherError с reason.

    ``expect_used`` — счётчик, который видел подтверждающий (T-8.30g): если ваучер уже
    погасили после этого, повтор (двойной тап) не списывает второй раз."""
    code = (code or "").strip().upper()
    voucher = _locked_voucher(code)
    if voucher.balance_cents is not None:
        # KA-H9: сертификат с остатком гасится только с суммой (redeem_balance) —
        # иначе счётчик рос, а остаток нет: «погашать» можно было бесконечно.
        raise VoucherError("needs_amount")
    if voucher.max_uses and voucher.used_count >= voucher.max_uses:
        raise VoucherError("used_up")
    if expect_used is not None and voucher.used_count != expect_used:
        raise VoucherError("stale")  # погасили после того, как владелец открыл страницу
    # Г4-1: `.update()` не трогает auto_now — штамп ставим явно: у купона акции
    # (max_uses=1) это и есть момент погашения для недельной сводки владельцу.
    Voucher.objects.filter(pk=voucher.pk).update(
        used_count=F("used_count") + 1, updated_at=timezone.now()
    )
    voucher.refresh_from_db(fields=["used_count", "updated_at"])
    return voucher


def _voucher_cap_percent() -> int:
    """B1.7(в): потолок промокода из настроек тенанта текущей схемы (0 = нет)."""
    try:
        from django.db import connection
        from django_tenants.utils import get_tenant_model, schema_context

        # P0-4 (аудит 2026-09-03): имя схемы снимаем ДО входа в контекст — внутри
        # `schema_context("public")` оно уже "public", и настройка владельца не
        # применялась никогда (потолок читался у public-тенанта, у него 0).
        schema = connection.schema_name
        with schema_context("public"):
            tenant = (
                get_tenant_model()
                .objects.filter(schema_name=schema)
                .only("voucher_max_percent")
                .first()
            )
        return min(100, int(getattr(tenant, "voucher_max_percent", 0) or 0))
    except Exception:  # noqa: BLE001 — сбой настройки не валит чекаут (без капа)
        return 0


def _capped(voucher, discount: int, base_cents: int) -> int:
    """Кап промокода потолком тенанта. Balance-сертификаты НЕ капаются (B1.7в)."""
    if discount <= 0 or voucher.balance_cents is not None:
        return discount
    cap_pct = _voucher_cap_percent()
    if not cap_pct:
        return discount
    return min(discount, int(base_cents) * cap_pct // 100)


def preview_discount(voucher, base_cents: int) -> int:
    """Скидка кода для превью (корзина/quote) — ta же логика, что spend_voucher,
    но read-only: с потолком тенанта, без списания."""
    return _capped(voucher, voucher.discount_for(int(base_cents)), base_cents)


def spend_voucher(code, base_cents: int):
    """B1.5: атомарно рассчитать И списать скидку кода для суммы base_cents.

    ЕДИНАЯ точка чекаутов (orders/booking/stays/events): расчёт и списание под
    одной блокировкой (закрывает гонку «прочитал → списал»). Возвращает
    (discount_cents > 0, voucher) или бросает VoucherError. Balance-сертификат
    (B1.5) списывает остаток частично (кап суммой), обычный промокод —
    used_count += 1 в пределах max_uses."""
    code = (code or "").strip().upper()
    # T-8.3: купон акции живёт только на кассе — онлайн-чекаут его не видит
    # (иначе код без скидки «сгорел» бы на любом заказе).
    voucher = Voucher.objects.select_for_update().filter(code=code, promotion__isnull=True).first()
    if voucher is None:
        raise VoucherError("not_found")
    if not voucher.is_active:
        raise VoucherError("inactive")
    if voucher.expires_at and voucher.expires_at < timezone.now():
        raise VoucherError("expired")
    if voucher.balance_cents is not None:
        if voucher.balance_cents <= 0:
            raise VoucherError("used_up")
        discount = voucher.discount_for(int(base_cents))
        if discount <= 0:
            raise VoucherError("not_applicable")
        Voucher.objects.filter(pk=voucher.pk).update(
            used_count=F("used_count") + 1,
            balance_cents=F("balance_cents") - discount,
        )
    else:
        if voucher.max_uses and voucher.used_count >= voucher.max_uses:
            raise VoucherError("used_up")
        # B1.7(в): промокод капается потолком тенанта (сертификаты — нет).
        discount = _capped(voucher, voucher.discount_for(int(base_cents)), base_cents)
        if discount <= 0:
            raise VoucherError("not_applicable")
        Voucher.objects.filter(pk=voucher.pk).update(used_count=F("used_count") + 1)
    voucher.refresh_from_db(fields=["used_count", "balance_cents"])
    return discount, voucher


def voucher_return_cents(deal) -> int:
    """KA-12 B2-7a: сколько вернуть balance-сертификату при отмене/возврате сделки —
    ровно списанное с него (`voucher_paid_cents`, B2-1). `discount_cents` после DC-5 и
    Minderung несёт и скидку владельца, и уступку — вернуть его = подарить разницу.
    Легаси-сделка без точного поля — прежнее правило."""
    exact = int(getattr(deal, "voucher_paid_cents", 0) or 0)
    if exact:
        return exact
    return int(getattr(deal, "discount_cents", 0) or 0)


def unredeem_voucher(code, amount_cents=0) -> bool:
    """B1.4: вернуть ОДНО использование кода при отмене брони/заказа/билета.

    Идемпотентность — на вызывающем: FSM-переход в cancelled срабатывает один
    раз (двойная отмена = IllegalTransition). Условный декремент (used_count>0)
    гонко-безопасен; неизвестный/неиспользованный код — no-op (False).
    amount_cents (B1.5) — снимок скидки: balance-сертификату возвращается."""
    code = (code or "").strip().upper()
    if not code:
        return False
    updated = Voucher.objects.filter(code=code, used_count__gt=0).update(
        used_count=F("used_count") - 1
    )
    if updated:
        # B1.5: balance-сертификату возвращаем и списанную сумму (снимок скидки).
        amount = max(0, int(amount_cents or 0))
        if amount:
            Voucher.objects.filter(code=code, balance_cents__isnull=False).update(
                balance_cents=F("balance_cents") + amount
            )
    return bool(updated)


# ---------------------------------------------------------------------------
# Лояльность (штампы)
# ---------------------------------------------------------------------------

STAMP_COOLDOWN_SECONDS = 30  # анти-дабл: не чаще одного штампа за это время


class LoyaltyError(Exception):
    """Штамп нельзя начислить. reason: cooldown."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def get_or_create_card(program, customer):
    from apps.loyalty.models import LoyaltyCard

    card, _ = LoyaltyCard.objects.get_or_create(program=program, customer=customer)
    return card


@transaction.atomic
def add_stamp(card, *, cooldown_seconds=STAMP_COOLDOWN_SECONDS):
    """Начислить штамп. При достижении порога — награда (Voucher) + сброс.

    Возвращает (card, reward_voucher|None). Бросает LoyaltyError('cooldown')
    при слишком частом начислении (анти-дабл).
    """
    from apps.loyalty.models import LoyaltyCard, StampEvent

    card = LoyaltyCard.objects.select_for_update().select_related("program").get(pk=card.pk)

    last = card.events.order_by("-created_at").first()
    if last and (timezone.now() - last.created_at).total_seconds() < cooldown_seconds:
        raise LoyaltyError("cooldown")

    StampEvent.objects.create(card=card)
    card.stamps += 1

    reward = None
    required = card.program.stamps_required
    if required and card.stamps >= required:
        card.stamps -= required
        card.rewards_earned += 1
        reward = generate_vouchers(label=card.program.reward_label, count=1, max_uses=1)[0]

    card.save(update_fields=["stamps", "rewards_earned", "updated_at"])
    return card, reward


def notify_waitlist_available(promotion) -> int:
    """Уведомить лист ожидания о возврате остатка (S6.4).

    Каждая запись получает РОВНО одно письмо: флаг notified + unique dedupe_key
    в Notification. Уведомляем не больше, чем доступно сейчас (по очереди
    created_at), и только для активной акции. Вызывается из ReservationSM после
    возврата остатка (cancelled/expired).
    """
    if promotion.status != "active":
        return 0
    promotion.refresh_from_db(fields=["available_quantity"])
    available = promotion.available_quantity or 0
    if available <= 0:
        return 0

    count = 0
    pending = WaitlistEntry.objects.filter(promotion=promotion, notified=False).order_by(
        "created_at"
    )[:available]
    for entry in pending:
        enqueue_waitlist_available(entry)
        entry.notified = True
        entry.save(update_fields=["notified", "updated_at"])
        count += 1
    return count
