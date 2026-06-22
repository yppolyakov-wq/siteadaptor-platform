"""Создание брони по датам с анти-овербукингом (Track E / E1).

Зеркало apps.booking.services / anti-oversell, но по ночам: внутри транзакции
блокируем строку StayUnit (select_for_update — все брони юнита сериализуются),
пер-ночно считаем занятость (availability.range_available) и пускаем, только если
на КАЖДУЮ ночь есть свободный из quantity юнитов. Customer переиспользуется по
email (как promotions/orders/booking).
"""

import secrets
import string

from django.db import transaction

from apps.promotions.models import Customer

from . import availability, pricing
from .models import StayBooking, StayUnit

_ALPHABET = string.ascii_uppercase + string.digits


class StayUnavailable(Exception):
    """На запрошенный диапазон нет свободного юнита (занятость/блок)."""


class MinStay(Exception):
    """Диапазон короче минимального числа ночей юнита (min_nights)."""


class MaxGuests(Exception):
    """Гостей больше вместимости юнита (max_guests)."""


def _unique_stay_code() -> str:
    for _ in range(10):
        code = "S-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not StayBooking.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique stay reference code")


def _rate_snapshot(rate_plan) -> dict:
    """Снимок тарифа (H1) для брони: переживает удаление/правку RatePlan и несёт
    модификаторы для пересчёта при переносе."""
    if rate_plan is None:
        return {}
    return {
        "name": rate_plan.name,
        "meal_plan": rate_plan.meal_plan,
        "meal_label": rate_plan.get_meal_plan_display(),
        "cancellation": rate_plan.cancellation,
        "cancellation_label": rate_plan.get_cancellation_display(),
        "free_cancel_days": rate_plan.free_cancel_days,
        "percent_adjust": rate_plan.percent_adjust,
        "surcharge_cents": rate_plan.surcharge_cents,
    }


def _rate_for_booking(booking):
    """Тариф для пересчёта брони: живой RatePlan, иначе duck-объект из снимка."""
    if booking.rate_plan_id and booking.rate_plan:
        return booking.rate_plan
    snap = booking.rate_snapshot or {}
    if snap:
        from types import SimpleNamespace

        return SimpleNamespace(
            percent_adjust=snap.get("percent_adjust", 0),
            surcharge_cents=snap.get("surcharge_cents", 0),
        )
    return None


def _get_or_create_customer(*, name, email, phone) -> Customer:
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            if not customer.phone and phone:
                customer.phone = phone
                customer.save(update_fields=["phone", "updated_at"])
            return customer
    return Customer.objects.create(name=name, email=email, phone=phone)


@transaction.atomic
def book_stay(
    unit,
    *,
    arrival,
    departure,
    name,
    email="",
    phone="",
    guests=1,
    adults=None,
    children=0,
    note="",
    source_channel="",
    auto_confirm=False,
    extras=None,
    rate_plan=None,
):
    """Создать бронь по датам, атомарно проверив занятость по ночам. Бросает
    ValueError (кривой диапазон), MinStay, MaxGuests, StayUnavailable.
    extras (#7) — снимок выбранных доп-услуг [{label, price_cents}]; сумма в total.
    rate_plan (H1) — выбранный тариф (RatePlan|None): модификатор цены + снимок.
    adults/children (H5) — разбивка гостей; guests = adults + children (если задан
    adults). Kurtaxe (H9) считается по adults и включается в total."""
    if departure <= arrival:
        raise ValueError("departure must be after arrival")
    # H5: adults задан → guests = adults + children; иначе старый контракт (guests).
    if adults is not None:
        adults = max(1, int(adults))
        children = max(0, int(children))
        guests = adults + children
    else:
        adults, children = guests, 0
    if guests < 1:
        raise ValueError("guests must be >= 1")

    unit_id = getattr(unit, "id", unit)
    # Блокировка строки юнита сериализует конкурентные брони этого юнита.
    unit = StayUnit.objects.select_for_update().get(id=unit_id, is_active=True)

    if (departure - arrival).days < unit.min_nights:
        raise MinStay()
    if guests > unit.max_guests:
        raise MaxGuests()
    if not availability.range_available(unit, arrival, departure):
        raise StayUnavailable()

    from apps.core import extras as extras_engine

    extras_snap = list(extras or [])
    nights = (departure - arrival).days
    kurtaxe = pricing.kurtaxe_total_cents(adults, nights)  # H9
    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    booking = StayBooking.objects.create(
        unit=unit,
        customer=customer,
        reference_code=_unique_stay_code(),
        arrival=arrival,
        departure=departure,
        guests=guests,
        adults=adults,
        children=children,
        price_cents=unit.price_cents,
        # A5a сезон/выходные + H1 тариф + #7 Extras + H9 Kurtaxe (всё в итоге).
        total_cents=pricing.quote_total_cents(unit, arrival, departure, rate_plan=rate_plan)
        + extras_engine.total_cents(extras_snap)
        + kurtaxe,
        kurtaxe_cents=kurtaxe,
        extras=extras_snap,
        rate_plan=rate_plan,
        rate_snapshot=_rate_snapshot(rate_plan),
        status=StayBooking.STATUS_CONFIRMED if auto_confirm else StayBooking.STATUS_PENDING,
        note=note,
        source_channel=(source_channel or "")[:50],
    )
    # письмо «Anfrage erhalten» — Notification в этой же транзакции (E3)
    from .notifications import enqueue_stay_email

    enqueue_stay_email(booking, "created")
    return booking


@transaction.atomic
def move_stay(booking, *, arrival, departure):
    """Перенос брони на новый диапазон с той же anti-overbook-проверкой."""
    if departure <= arrival:
        raise ValueError("departure must be after arrival")
    unit = StayUnit.objects.select_for_update().get(id=booking.unit_id)
    if (departure - arrival).days < unit.min_nights:
        raise MinStay()
    if not availability.range_available(unit, arrival, departure, exclude_pk=booking.pk):
        raise StayUnavailable()
    from apps.core import extras as extras_engine

    booking.arrival = arrival
    booking.departure = departure
    # A5a база + H1 тариф (снимок) + #7 Extras (снимки) + H9 Kurtaxe (пересчёт по ночам).
    nights = (departure - arrival).days
    booking.kurtaxe_cents = pricing.kurtaxe_total_cents(booking.adults, nights)
    booking.total_cents = (
        pricing.quote_total_cents(unit, arrival, departure, rate_plan=_rate_for_booking(booking))
        + extras_engine.total_cents(booking.extras)
        + booking.kurtaxe_cents
    )
    booking.save(
        update_fields=["arrival", "departure", "total_cents", "kurtaxe_cents", "updated_at"]
    )
    return booking


def stay_to_invoice(booking, *, small_business=False):
    """Создать черновик Rechnung (finance.Invoice) из брони (A5, опц.).

    Цена брони — брутто (вкл. 7 % Beherbergung), поэтому нетто вычисляем обратным
    счётом, чтобы gross в счёте совпал с оплаченным. §19 → НДС 0 (gross == net).
    Идемпотентно: повторный вызов вернёт уже существующий счёт. Ставит
    booking.invoice_id; статус draft (выпуск/нумерация — в кабинете finance).
    """
    from decimal import ROUND_HALF_UP, Decimal

    from apps.finance.models import Invoice

    if booking.invoice_id:
        existing = Invoice.objects.filter(pk=booking.invoice_id).first()
        if existing is not None:
            return existing

    gross = Decimal(booking.total_cents) / 100
    # H9: Kurtaxe — durchlaufender Posten, отдельной строкой без 7 % Beherbergung-НДС;
    # из базы НДС её исключаем (gross_beh = итог − Kurtaxe).
    kurtaxe = Decimal(booking.kurtaxe_cents) / 100
    gross_beh = gross - kurtaxe
    rate = Decimal("0") if small_business else Decimal("7")
    if rate:
        net_beh = (gross_beh / (1 + rate / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        net_beh = gross_beh
    vat = gross_beh - net_beh
    net = net_beh + kurtaxe  # Kurtaxe без НДС → net == gross по этой строке
    lines = [
        {
            "text": (
                f"Übernachtung {booking.unit.name}: {booking.nights} "
                f"Nächte ({booking.arrival:%d.%m.%Y}–{booking.departure:%d.%m.%Y})"
            ),
            "qty": 1,
            "unit_price": str(net_beh),
        }
    ]
    if kurtaxe:
        lines.append({"text": "Kurtaxe (ohne USt.)", "qty": 1, "unit_price": str(kurtaxe)})
    invoice = Invoice.objects.create(
        customer=booking.customer,
        recipient=str(booking.customer)[:500],
        lines=lines,
        vat_rate=rate,
        net=net,
        vat_amount=vat,
        gross=gross,
        note=f"Buchung {booking.reference_code}"[:200],
    )
    booking.invoice_id = invoice.id
    booking.save(update_fields=["invoice_id", "updated_at"])
    return invoice


def sync_ical_source(source) -> int:
    """Стянуть внешний iCal и пересоздать блоки этого источника (A5b).

    Идемпотентно: удаляем прежние блоки source_id_ref=source.pk и заводим заново
    по событиям фида (DTEND эксклюзивно → end_date = DTEND-1, наш включительный
    формат). Возвращает число заведённых блоков. Сетевые/парс-ошибки —
    last_status, блоки не трогаем.
    """
    from datetime import timedelta

    import requests
    from django.utils import timezone

    from . import ical
    from .models import UnitBlock

    src = str(source.pk)
    try:
        resp = requests.get(source.url, timeout=20)
        resp.raise_for_status()
        events = ical.parse_events(resp.text)
    except Exception as exc:  # noqa: BLE001 — сбой фида не должен ронять синк
        source.last_status = str(exc)[:120]
        source.last_synced_at = timezone.now()
        source.save(update_fields=["last_status", "last_synced_at", "updated_at"])
        return 0

    with transaction.atomic():
        UnitBlock.objects.filter(unit=source.unit, source_id_ref=src).delete()
        created = 0
        for _uid, start, end in events:
            last_night = end - timedelta(days=1)  # DTEND эксклюзивно → включительно
            if last_night < start:
                continue
            UnitBlock.objects.create(
                unit=source.unit,
                start_date=start,
                end_date=last_night,
                reason=f"iCal: {source.label or 'extern'}"[:120],
                source_id_ref=src,
            )
            created += 1
        source.last_status = f"OK: {created}"
        source.last_synced_at = timezone.now()
        source.save(update_fields=["last_status", "last_synced_at", "updated_at"])
    return created
