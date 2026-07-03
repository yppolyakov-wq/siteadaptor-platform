"""Сервисы резервирования (anti-oversell).

Списание остатка — одним атомарным conditional UPDATE с F() (см.
docs/references/patterns/anti-oversell.md). Смена статусов — через
ReservationSM. Возврат остатка при отмене/истечении — в on_transition.
"""

import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

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


class VoucherError(Exception):
    """Ваучер нельзя погасить. reason: not_found/inactive/expired/used_up."""

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
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            # дозаполняем пустые контакты, имя не перетираем
            updates = []
            if not customer.phone and phone:
                customer.phone = phone
                updates.append("phone")
            if updates:
                customer.save(update_fields=[*updates, "updated_at"])
            return customer
    return Customer.objects.create(name=name, email=email, phone=phone)


@transaction.atomic
def reserve(promotion, *, name, email="", phone="", quantity=1, note="", source_channel=""):
    """Создать бронь, атомарно списав остаток акции.

    Бросает OutOfStock, если остатка не хватило/акция не active, и
    ReservationLimitReached при превышении max_per_customer.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    promo_id = getattr(promotion, "id", promotion)
    promotion = Promotion.objects.get(id=promo_id)

    customer = _get_or_create_customer(name=name, email=email, phone=phone)

    # лимит на клиента по этой акции (по сумме активных броней)
    if promotion.max_per_customer:
        active_qty = (
            Reservation.objects.filter(
                promotion=promotion,
                customer=customer,
                status__in=["pending", "confirmed"],
            ).aggregate(n=Sum("quantity"))["n"]
            or 0
        )
        if active_qty + quantity > promotion.max_per_customer:
            raise ReservationLimitReached()

    # атомарное условное списание остатка
    if promotion.available_quantity is not None:
        rows = Promotion.objects.filter(
            id=promotion.id,
            status="active",
            available_quantity__gte=quantity,
        ).update(available_quantity=F("available_quantity") - quantity)
        if rows == 0:
            raise OutOfStock()
    elif promotion.status != "active":
        # без лимита остатка, но акция должна быть активной
        raise OutOfStock()

    initial_status = "confirmed" if promotion.auto_confirm else "pending"
    now = timezone.now()
    reservation = Reservation.objects.create(
        promotion=promotion,
        customer=customer,
        reference_code=_unique_reference_code(),
        quantity=quantity,
        status=initial_status,
        expires_at=now + timedelta(hours=promotion.reservation_ttl_hours),
        confirmed_at=now if initial_status == "confirmed" else None,
        note=note,
        source_channel=(source_channel or "")[:50],
    )
    # письмо клиенту/владельцу — после коммита транзакции
    enqueue_reservation_email(reservation, "created")
    return reservation


def confirm(reservation, *, actor=None):
    """pending → confirmed (ручное подтверждение владельцем)."""
    with transaction.atomic():
        if reservation.status == "pending":
            reservation.confirmed_at = timezone.now()
            reservation.save(update_fields=["confirmed_at", "updated_at"])
        return ReservationSM().apply(reservation, "confirmed", actor=actor)


def fulfill(reservation, *, actor=None):
    """confirmed → fulfilled (бронь выдана клиенту)."""
    with transaction.atomic():
        if reservation.status != "fulfilled":
            reservation.fulfilled_at = timezone.now()
            reservation.save(update_fields=["fulfilled_at", "updated_at"])
        return ReservationSM().apply(reservation, "fulfilled", actor=actor)


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


def _unique_voucher_code() -> str:
    for _ in range(10):
        code = "V-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
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


@transaction.atomic
def redeem_voucher(code):
    """Погасить ваучер (одно использование). Бросает VoucherError с reason."""
    code = (code or "").strip().upper()
    voucher = Voucher.objects.select_for_update().filter(code=code).first()
    if voucher is None:
        raise VoucherError("not_found")
    if not voucher.is_active:
        raise VoucherError("inactive")
    if voucher.expires_at and voucher.expires_at < timezone.now():
        raise VoucherError("expired")
    if voucher.max_uses and voucher.used_count >= voucher.max_uses:
        raise VoucherError("used_up")
    Voucher.objects.filter(pk=voucher.pk).update(used_count=F("used_count") + 1)
    voucher.refresh_from_db(fields=["used_count"])
    return voucher


def _voucher_cap_percent() -> int:
    """B1.7(в): потолок промокода из настроек тенанта текущей схемы (0 = нет)."""
    try:
        from django.db import connection
        from django_tenants.utils import get_tenant_model, schema_context

        with schema_context("public"):
            tenant = (
                get_tenant_model()
                .objects.filter(schema_name=connection.schema_name)
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
    voucher = Voucher.objects.select_for_update().filter(code=code).first()
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
