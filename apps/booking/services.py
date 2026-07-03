"""Создание записи с анти-двойным-бронированием (Track D / D3a).

Аналог anti-oversell, но по интервалам: внутри транзакции блокируем строку
ресурса (select_for_update — все брони одного ресурса сериализуются), считаем
активные пересечения [start, end) и пускаем только если их меньше capacity.
Customer переиспользуется по email (как в promotions/orders).
"""

import secrets
import string

from django.db import transaction
from django.db.models import Q

from apps.promotions.models import Customer

from .models import Booking, ClosedDate, Pass, Resource

_ALPHABET = string.ascii_uppercase + string.digits


class PassInvalid(Exception):
    """Mehrfachkarte недействительна: аннулирована, просрочена или исчерпана."""


class SlotTaken(Exception):
    """Интервал на ресурсе уже занят (по capacity)."""


class ResourceClosed(Exception):
    """На эту дату ресурс/бизнес закрыт (ClosedDate)."""


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
        return 0, ""
    from apps.loyalty.models import Voucher
    from apps.promotions.services import VoucherError, redeem_voucher

    voucher = Voucher.objects.filter(code=code).first()
    discount = voucher.discount_for(base_cents) if voucher else 0
    if not voucher or discount <= 0:
        raise PromoInvalid()
    try:
        redeem_voucher(code)
    except VoucherError as exc:
        raise PromoInvalid() from exc
    return discount, code


def _get_or_create_customer(*, name, email, phone) -> Customer:
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            if not customer.phone and phone:
                customer.phone = phone
                customer.save(update_fields=["phone", "updated_at"])
            return customer
    return Customer.objects.create(name=name, email=email, phone=phone)


def overlapping(resource, start, end):
    """Активные записи ресурса, пересекающие интервал [start, end)."""
    return Booking.objects.filter(
        resource=resource,
        status__in=Booking.ACTIVE_STATUSES,
        start__lt=end,
        end__gt=start,
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
):
    """Создать запись, атомарно проверив пересечения. Бросает SlotTaken /
    ResourceClosed / ValueError (кривой интервал) / PromoInvalid (B1.2).
    service/price_cents — G10. extras (#7) — снимок доп-услуг
    [{label, price_cents}], сумма идёт в выручку. voucher_code —
    промокод/Gutschein: скидка на услугу+Extras, гасится атомарно."""
    if end <= start:
        raise ValueError("end must be after start")

    resource_id = getattr(resource, "id", resource)
    # Блокировка строки ресурса сериализует конкурентные брони этого ресурса.
    resource = Resource.objects.select_for_update().get(id=resource_id, is_active=True)

    # Точечные исключения: выходной ресурса или всего бизнеса (resource=None).
    closed = ClosedDate.objects.filter(date=start.date()).filter(
        Q(resource=resource) | Q(resource__isnull=True)
    )
    if closed.exists():
        raise ResourceClosed()

    if _would_overfill(resource, overlapping(resource, start, end), party_size):
        raise SlotTaken()

    # B1.2: скидка на полную стоимость (услуга + Extras); снимок кода/суммы.
    base_cents = int(price_cents or 0) + sum(int(e.get("price_cents", 0)) for e in (extras or []))
    discount_cents, voucher_snap = _apply_voucher(voucher_code, base_cents)

    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    booking = Booking.objects.create(
        resource=resource,
        service=service,
        price_cents=int(price_cents or 0),
        extras=list(extras or []),
        voucher_code=voucher_snap,
        discount_cents=discount_cents,
        customer=customer,
        reference_code=_unique_booking_code(),
        start=start,
        end=end,
        party_size=party_size,
        status=Booking.STATUS_CONFIRMED if auto_confirm else Booking.STATUS_PENDING,
        note=note,
        source_channel=(source_channel or "")[:50],
    )
    # письмо «заявка принята» — Notification в этой же транзакции (D3c)
    from .notifications import enqueue_booking_email

    enqueue_booking_email(booking, "created")
    return booking


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
def move(booking, *, start, end):
    """Перенос записи на новый интервал с той же anti-double-book проверкой."""
    if end <= start:
        raise ValueError("end must be after start")
    resource = Resource.objects.select_for_update().get(id=booking.resource_id)
    overlaps = overlapping(resource, start, end).exclude(pk=booking.pk)
    if _would_overfill(resource, overlaps, booking.party_size):
        raise SlotTaken()
    booking.start = start
    booking.end = end
    booking.save(update_fields=["start", "end", "updated_at"])
    return booking
