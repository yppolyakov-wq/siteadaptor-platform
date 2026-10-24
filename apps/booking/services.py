"""Создание записи с анти-двойным-бронированием (Track D / D3a).

Аналог anti-oversell, но по интервалам: внутри транзакции блокируем строку
ресурса (select_for_update — все брони одного ресурса сериализуются), считаем
активные пересечения [start, end) и пускаем только если их меньше capacity.
Customer переиспользуется по email (как в promotions/orders).
"""

import re
import secrets
import string
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.promotions.models import Customer

from .models import MAX_BUFFER_MINUTES, Booking, ClosedDate, Pass, Resource

_ALPHABET = string.ascii_uppercase + string.digits


class PassInvalid(Exception):
    """Mehrfachkarte недействительна: аннулирована, просрочена или исчерпана."""


class SlotTaken(Exception):
    """Интервал на ресурсе уже занят (по capacity)."""


class ResourceClosed(Exception):
    """На эту дату ресурс/бизнес закрыт (ClosedDate)."""


class OutsideHours(Exception):
    """KA-12 E4.3 (О-4b): интервал вне рабочих часов ресурса/бизнеса — только с
    подтверждением владельца («Trotzdem eintragen»); закрытый день — жёстко."""


class NotMovable(Exception):
    """KA-12 E4.2b: двигать можно только действующую запись (не выполненную/отменённую)."""


class ResourceInactive(Exception):
    """KA-12 E4.2b: перенос на выключенный ресурс (мастер/стол)."""


def _unique_booking_code() -> str:
    for _ in range(10):
        code = "T-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Booking.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique booking reference code")


class PromoInvalid(Exception):
    """B1.2: промокод/Gutschein задан, но не применим (нет/исчерпан/минимум)."""


def _apply_voucher(code, base_cents):
    """(discount_cents, code_snapshot) для кода. Пусто → (0, "").
    Код задан, но не применим → PromoInvalid. Зеркало events._apply_voucher;
    гасит атомарно (used_count += 1) — откатится вместе с транзакцией book."""
    code = (code or "").strip().upper()
    if not code:
        return 0, "", 0
    from apps.promotions.services import VoucherError, spend_voucher

    # B1.5: расчёт+списание атомарно (единая точка; balance-сертификат — частично).
    try:
        discount, voucher = spend_voucher(code, base_cents)
    except VoucherError as exc:
        raise PromoInvalid() from exc
    # KA-12 B2-1: сертификат с остатком — оплата (третий элемент), промокод — Rabatt.
    paid = discount if getattr(voucher, "balance_cents", None) is not None else 0
    return discount, code, paid


def _get_or_create_customer(*, name, email, phone, match_by_phone=False) -> Customer:
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            if not customer.phone and phone:
                customer.phone = phone
                customer.save(update_fields=["phone", "updated_at"])
            return customer
    elif phone and match_by_phone:
        # KA-H7: запись по телефону из КАБИНЕТА (владелец знает клиента) не плодит
        # клиента заново. Только доверенный путь: на витрине телефон и имя легко
        # подставить чужие, и бронь попала бы в историю/письма другого человека.
        # Склеиваем только при совпадении непустого имени: общий номер семьи не
        # сливает двух людей; найденную запись не переименовываем.
        raw = phone.strip()
        wanted = (name or "").strip().lower()
        variants = {raw, re.sub(r"[\s\-/().]", "", raw)} - {""}
        if wanted:
            for customer in Customer.objects.filter(phone__in=variants).order_by("created_at"):
                if (customer.name or "").strip().lower() == wanted:
                    return customer
    return Customer.objects.create(name=name, email=email, phone=phone)


def _fresh_buffer(service) -> int:
    """Буфер из СВЕЖЕЙ строки услуги (читать под блокировкой ресурса): объект во
    вьюхе мог быть загружен до смены буфера владельцем — иначе гонка с
    `resync_occupancy` оставила бы новую запись со старой занятостью."""
    pk = getattr(service, "pk", None)
    if not pk:
        return 0
    from .models import Service

    value = Service.objects.filter(pk=pk).values_list("buffer_after_minutes", flat=True).first()
    return min(int(value or 0), MAX_BUFFER_MINUTES)


def occupied_end(service, end, *, fresh=False):
    """KA-12 E4.4a: конец занятости ресурса с буфером услуги (None — буфера нет)."""
    if fresh:
        buffer = _fresh_buffer(service)
    else:
        buffer = min(int(getattr(service, "buffer_after_minutes", 0) or 0), MAX_BUFFER_MINUTES)
    return end + timedelta(minutes=buffer) if buffer else None


@transaction.atomic
def resync_occupancy(service) -> int:
    """KA-12 E4.4a: буфер услуги поменяли — будущие активные записи держат ресурс
    по новому буферу (иначе старые брони остаются со старой занятостью).

    Под блокировкой затронутых ресурсов (порядок по pk, как у `book`): новая
    запись либо уже видна апдейту, либо создаётся после и читает свежий буфер.
    Возвращает число записей, которые после смены буфера легли внахлёст."""
    from django.db.models import F

    from apps.core import status_registry

    buffer = _fresh_buffer(service)
    future = Booking.objects.filter(
        service=service,
        end__gte=timezone.now(),
        status__in=status_registry.active_statuses_for("booking"),
    )
    resource_ids = sorted(set(future.values_list("resource_id", flat=True)))
    list(Resource.objects.select_for_update().filter(pk__in=resource_ids).order_by("pk"))
    now = timezone.now()
    if buffer:
        future.update(occupied_until=F("end") + timedelta(minutes=buffer), updated_at=now)
    else:
        future.update(occupied_until=None, updated_at=now)
    return sum(
        1
        for b in future.select_related("resource")
        if _would_overfill(
            b.resource,
            overlapping(b.resource, b.start, b.occupied_until or b.end).exclude(pk=b.pk),
            b.party_size,
        )
    )


def overlapping(resource, start, end):
    """Активные записи ресурса, пересекающие интервал [start, end).

    KA-12 E4.4a: чужая запись держит ресурс до `occupied_until` (с буфером её
    услуги); NULL — до `end`, как раньше."""
    from django.db.models.functions import Coalesce

    from apps.core import status_registry

    return (
        Booking.objects.filter(
            resource=resource,
            # FB-3 Вариант B: built-in ∪ кастом-active тенанта (кастом-статус держит слот).
            status__in=status_registry.active_statuses_for("booking"),
            start__lt=end,
            end__gt=start - timedelta(minutes=MAX_BUFFER_MINUTES),
        )
        .annotate(busy_until=Coalesce("occupied_until", "end"))
        .filter(busy_until__gt=start)
    )


def _would_overfill(resource, qs, party_size) -> bool:
    """G9: превысит ли capacity добавление брони на party_size. При
    counts_party_size считаем по сумме party_size (групповой курс), иначе — по
    числу броней (стол/мастер/зал = 1 единица на бронь)."""
    if resource.counts_party_size:
        from django.db.models import Sum

        current = qs.aggregate(s=Sum("party_size"))["s"] or 0
        return current + party_size > resource.capacity
    return qs.count() >= resource.capacity


@transaction.atomic
def book(
    resource,
    *,
    start,
    end,
    name,
    email="",
    phone="",
    party_size=1,
    note="",
    source_channel="",
    auto_confirm=False,
    service=None,
    price_cents=0,
    extras=None,
    voucher_code="",
    group_code="",
    notify=True,
    promotion=None,
    payment_method="",
    customer_type="private",
    billing_company="",
    billing_vat_id="",
    billing_address="",
    payment_due_at=None,
    match_by_phone=False,
    variant=None,
    variant_label="",
):
    """Создать запись, атомарно проверив пересечения. Бросает SlotTaken /
    ResourceClosed / ValueError (кривой интервал) / PromoInvalid (B1.2).
    service/price_cents — G10. extras (#7) — снимок доп-услуг
    [{label, price_cents}], сумма идёт в выручку. voucher_code —
    промокод/Gutschein: скидка на услугу+Extras, гасится атомарно.
    group_code/notify (HF-6) — принадлежность к мультислот-брони: письмо о такой
    брони шлёт `book_many` ОДНО на всю группу, а не N штук клиенту.
    promotion (P5 «ценовой слой») — бронь по акции: лимит кампании списывается
    В ЭТОЙ ЖЕ транзакции (SlotTaken откатывает и его), FK для возврата при
    отмене; промо-цена приходит уже готовой в price_cents."""
    if end <= start:
        raise ValueError("end must be after start")
    # KA-12 E4.4b: вариант обязан принадлежать услуге брони (кросс-таблица в БД не выразима).
    if variant is not None and variant.service_id != getattr(service, "pk", None):
        raise ValueError("variant does not belong to service")

    resource_id = getattr(resource, "id", resource)
    # Блокировка строки ресурса сериализует конкурентные брони этого ресурса.
    resource = Resource.objects.select_for_update().get(id=resource_id, is_active=True)

    # Точечные исключения: выходной ресурса или всего бизнеса (resource=None).
    closed = ClosedDate.objects.filter(date=start.date()).filter(
        Q(resource=resource) | Q(resource__isnull=True)
    )
    if closed.exists():
        raise ResourceClosed()

    busy_until = occupied_end(service, end, fresh=True)
    if _would_overfill(resource, overlapping(resource, start, busy_until or end), party_size):
        raise SlotTaken()

    # B1.2: скидка на полную стоимость (услуга + Extras); снимок кода/суммы.
    base_cents = int(price_cents or 0) + sum(int(e.get("price_cents", 0)) for e in (extras or []))
    discount_cents, voucher_snap, voucher_paid = _apply_voucher(voucher_code, base_cents)

    # P5: акция — списание лимита кампании внутри той же atomic (OutOfStock →
    # откат брони целиком, фантомного списания нет).
    if promotion is not None:
        from apps.promotions.price_layer import claim_units

        claim_units(promotion, 1)
    customer = _get_or_create_customer(
        name=name, email=email, phone=phone, match_by_phone=match_by_phone
    )
    booking = Booking.objects.create(
        resource=resource,
        service=service,
        variant=variant,
        variant_label=(variant_label or "")[:100],
        promotion=promotion,
        price_cents=int(price_cents or 0),
        # DC-8: снимок ставки НДС услуги (у записи без услуги — общая 19 %).
        vat_rate=(
            Decimal("19.00")
            if getattr(service, "vat_rate", None) is None
            else service.vat_rate  # KA-H7: 0 % — законная ставка, не «пусто»
        ),
        extras=list(extras or []),
        voucher_code=voucher_snap,
        discount_cents=discount_cents,
        voucher_paid_cents=voucher_paid,
        customer=customer,
        reference_code=_unique_booking_code(),
        group_code=group_code or "",
        start=start,
        end=end,
        occupied_until=busy_until,
        party_size=party_size,
        status=Booking.STATUS_CONFIRMED if auto_confirm else Booking.STATUS_PENDING,
        note=note,
        source_channel=(source_channel or "")[:50],
        # SH-23c: способ оплаты, тип покупателя и срок оплаты — снимком
        # (общий реестр `apps.core.payment_methods`; пусто = единственный способ).
        payment_method=payment_method or "",
        customer_type=customer_type or "private",
        billing_company=(billing_company or "").strip()[:200],
        billing_vat_id=(billing_vat_id or "").strip()[:30],
        billing_address=(billing_address or "").strip()[:1000],
        payment_due_at=payment_due_at,
    )
    from apps.crm.companies import link_deal

    link_deal(booking)  # CO-2c: фирма → справочник по USt-IdNr
    if booking.status == "confirmed":  # автоподтверждение — счёт сразу (CO-2d)
        from apps.finance.auto_invoice import on_confirmed

        on_confirmed("booking", booking)
    # MX-2e: трекеры опций записи (пул/склад) — в той же atomic; book_many
    # проходит здесь же (extras несёт только первая бронь группы).
    from apps.core import option_trackers

    option_trackers.commit_options(booking.extras, kind="booking", deal=booking)
    # письмо «заявка принята» — Notification в этой же транзакции (D3c)
    if notify:
        from .notifications import enqueue_booking_email

        enqueue_booking_email(booking, "created")
    # C2: «спросил с сайта → записался» — одна беседа (fail-soft, однозначность).
    from apps.inbox.deal_threads import adopt_open_thread, deal_ref_label

    adopt_open_thread(
        booking.customer,
        ref_kind="booking",
        ref_id=booking.reference_code,
        ref_label=deal_ref_label("booking", booking.reference_code),
    )
    return booking


MAX_GROUP_SLOTS = 6  # больше периодов за раз — уже не бронь, а расписание


@transaction.atomic
def book_many(starts, **kwargs):
    """HF-6: несколько периодов ОДНОЙ броней — N записей с общим group_code.

    Всё в одной транзакции: если хотя бы один период занят, не создаётся НИ ОДНОЙ
    брони (гость не получает половину заказа). Anti-oversell не дублируем — каждый
    период идёт через обычный `book`. Один период → обычная одиночная бронь с
    пустым group_code, то есть прежнее поведение байт-в-байт.

    `starts` — [(resource, start, end, price_cents)]: ресурс на КАЖДЫЙ период свой
    (разные периоды может обслуживать разный мастер — назначает вызывающая сторона
    через availability.assign_resource), цена — на дату периода (apps.booking.pricing).
    Остальные поля брони (имя/почта/услуга/…) — общие, приходят в kwargs.
    Возвращает список созданных броней в порядке периодов.
    """
    slots = list(starts)
    if not slots:
        raise ValueError("no slots given")
    if len(slots) > MAX_GROUP_SLOTS:
        raise ValueError("too many slots")
    single = len(slots) == 1
    code = "" if single else _unique_group_code()
    # Ревью 2026-07-31: промокод и Extras — ОДИН РАЗ на заказ, не на каждый период.
    # Раньше они уезжали в каждый `book` через **kwargs: одноразовый Gutschein
    # гасился первой бронью и ронял всю транзакцию («код недействителен» при
    # валидном коде), многоразовый давал N-кратную скидку, Extras оплачивались N раз.
    once = {
        "voucher_code": kwargs.pop("voucher_code", ""),
        "extras": kwargs.pop("extras", None),
    }
    created = []
    for resource, start, end, price_cents in slots:
        created.append(
            book(
                resource,
                start=start,
                end=end,
                price_cents=price_cents,
                group_code=code,
                # Одно письмо на всю группу — шлём после успешного создания всех.
                notify=single,
                **(once if not created else {}),
                **kwargs,
            )
        )
    if not single:
        from .notifications import enqueue_booking_email

        enqueue_booking_email(created[0], "created")
    return created


def _unique_group_code() -> str:
    for _ in range(10):
        code = "G-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Booking.objects.filter(group_code=code).exists():
            return code
    raise RuntimeError("could not generate unique booking group code")


def _unique_pass_code() -> str:
    for _ in range(10):
        code = "K-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Pass.objects.filter(code=code).exists():
            return code
    raise RuntimeError("could not generate unique pass code")


def issue_pass(
    *,
    name,
    email="",
    phone="",
    label="Mehrfachkarte",
    credits=10,
    valid_until=None,
    service=None,
    stripe_payment_intent="",
):
    """G9/A3: выпустить Mehrfachkarte клиенту (Customer переиспользуется по email).

    service — привязка к услуге/курсу (None = универсальная карта)."""
    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    return Pass.objects.create(
        customer=customer,
        code=_unique_pass_code(),
        label=(label or "Mehrfachkarte").strip()[:120] or "Mehrfachkarte",
        credits_total=max(1, int(credits or 1)),
        valid_until=valid_until,
        service=service,
        stripe_payment_intent=stripe_payment_intent or "",
    )


@transaction.atomic
def redeem_pass(card, *, booking=None):
    """G9: атомарно списать один визит с карты. PassInvalid — карта недействительна.

    Блокируем строку карты (select_for_update), перепроверяем валидность, списываем
    кредит; при booking — привязываем визит к карте (booking.card)."""
    locked = Pass.objects.select_for_update().get(pk=card.pk)
    if not locked.is_valid:
        raise PassInvalid()
    # A3: карта, привязанная к услуге, гасит только бронь этой услуги.
    if locked.service_id and booking is not None and booking.service_id != locked.service_id:
        raise PassInvalid()
    locked.credits_used += 1
    locked.save(update_fields=["credits_used", "updated_at"])
    if booking is not None:
        booking.card = locked
        booking.save(update_fields=["card", "updated_at"])
    return locked


@transaction.atomic
def move(booking, *, start, end, resource=None, override_hours=False):
    """Перенос записи на новый интервал с той же anti-double-book проверкой.

    KA-12 E4.3: закрытый день (ClosedDate ресурса или всего бизнеса) → ResourceClosed;
    вне часов → OutsideHours, если владелец не подтвердил. Новое время = новое
    напоминание и письмо клиенту «verschoben» (после коммита).
    KA-12 E4.2b: `resource` — перенос к другому мастеру/столу; все проверки — по
    ЦЕЛЕВОМУ ресурсу; двигается только действующая запись; блокируются оба ресурса
    в порядке pk (как `resync_occupancy` — без встречного дедлока)."""
    from apps.core import status_registry

    from . import availability

    if end <= start:
        raise ValueError("end must be after start")
    if booking.status not in status_registry.active_statuses_for("booking"):
        raise NotMovable()
    target_id = resource.pk if resource is not None else booking.resource_id
    locked = {
        r.pk: r
        for r in Resource.objects.select_for_update()
        .filter(pk__in={booking.resource_id, target_id})
        .order_by("pk")
    }
    target = locked[target_id]
    if not target.is_active:
        raise ResourceInactive()
    if availability.is_closed(target, timezone.localtime(start).date()):
        raise ResourceClosed()
    if not override_hours and not availability.within_hours(target, start, end):
        raise OutsideHours()
    busy_until = occupied_end(booking.service, end, fresh=True)
    overlaps = overlapping(target, start, busy_until or end).exclude(pk=booking.pk)
    if _would_overfill(target, overlaps, booking.party_size):
        raise SlotTaken()
    moved = booking.start != start
    booking.start = start
    booking.end = end
    booking.occupied_until = busy_until
    fields = ["start", "end", "occupied_until", "updated_at"]
    if target.pk != booking.resource_id:
        booking.resource = target
        fields.append("resource")
    if moved:
        booking.reminder_sent_at = None
        fields.append("reminder_sent_at")
    booking.save(update_fields=fields)
    if moved and booking.status in (Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED):
        from .notifications import enqueue_booking_email

        transaction.on_commit(lambda: enqueue_booking_email(booking, "moved"))
    return booking
