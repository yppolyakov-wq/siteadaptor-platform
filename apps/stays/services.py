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
from django.db.models import Q
from django.utils import translation
from django.utils.translation import gettext as _

from apps.promotions.models import Customer

from . import availability, pricing
from .models import RatePlan, StayBooking, StaySettings, StayUnit
from .rate_plans import RatePlanInvalid  # noqa: F401 — реэкспорт для вызывающих (Z-4)

_ALPHABET = string.ascii_uppercase + string.digits


class StayUnavailable(Exception):
    """На запрошенный диапазон нет свободного юнита (занятость/блок)."""


class MinStay(Exception):
    """Диапазон короче минимального числа ночей юнита (min_nights)."""


class MaxGuests(Exception):
    """Гостей больше вместимости юнита (max_guests)."""


class PromoInvalid(Exception):
    """Промокод указан, но не применим (нет такого/просрочен/исчерпан/не достигнут мин)."""


class RestrictionViolated(Exception):
    """G12: бронь нарушает правила онлайн-продаж (Verkaufsregeln). Держит код
    причины и число для текста (см. restrictions.violation)."""

    def __init__(self, code: str, n=None):
        super().__init__(code)
        self.code = code
        self.n = n


def _unique_stay_code() -> str:
    for _attempt in range(10):
        code = "S-" + "".join(secrets.choice(_ALPHABET) for _i in range(6))
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


def _apply_voucher(code, base_cents):
    """(discount_cents, code_snapshot) для промокода (H4a). Пусто → (0, "").
    Код задан, но не применим (нет/просрочен/исчерпан/не достигнут мин) → PromoInvalid.
    Гасит ваучер атомарно (used_count += 1) — откатится, если транзакция упадёт."""
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


class RoomConflict(Exception):
    """PMS-R2: на выбранной комнате уже есть пересекающаяся активная бронь."""


class GuestCheckedInMove(Exception):
    """KA-12 Z-5: перенос дат заселённого гостя (заезд в будущее / выезд в прошлое)."""


class NoCapacity(Exception):
    """KA-12 E4.10a: блок комнаты на ночи, где категория уже продана целиком."""


def free_rooms_for(booking):
    """PMS-R2: активные комнаты категории брони, свободные на её диапазон
    (для селекта назначения; своя комната включена). Пусто, если комнат нет."""
    from apps.core import status_registry

    from .models import Room, StayBooking, UnitBlock

    rooms = list(Room.objects.filter(unit_id=booking.unit_id, is_active=True))
    if not rooms:
        return []
    overlapping = StayBooking.objects.filter(
        status__in=status_registry.active_statuses_for("stay"),
        arrival__lt=booking.departure,
        departure__gt=booking.arrival,
    ).exclude(pk=booking.pk)
    busy = set(overlapping.filter(room__in=rooms).values_list("room_id", flat=True))
    # KA-12 E4.10b: доп. номера мультиномерных броней тоже заняты.
    busy |= set(
        StayBooking.extra_rooms.through.objects.filter(
            staybooking__in=overlapping, room__in=rooms
        ).values_list("room_id", flat=True)
    )
    # KA-12 E4.10a: блок комнаты занимает ночи [start_date, end_date] включительно.
    busy |= set(
        UnitBlock.objects.filter(
            room__in=rooms,
            start_date__lt=booking.departure,
            end_date__gte=booking.arrival,
        ).values_list("room_id", flat=True)
    )
    return [r for r in rooms if r.id not in busy]


def assign_room(booking, room) -> None:
    """PMS-R2: назначить/снять физический номер. room=None — снять; комната
    чужой категории или занятая на диапазон → RoomConflict."""
    if room is None:
        if booking.room_id:
            # KA-12 E4.10b: первым становится следующий назначенный номер — иначе
            # бронь с доп. номерами считалась бы «ohne Zimmer».
            extras = list(booking.extra_rooms.all())
            booking.room = extras[0] if extras else None
            booking.save(update_fields=["room", "updated_at"])
            if extras:
                booking.extra_rooms.remove(extras[0])
        return
    if room.unit_id != booking.unit_id:
        raise RoomConflict()
    from .models import Room

    with transaction.atomic():
        # KA-12 E4.10a: блокировка строки комнаты — два одновременных назначения (или
        # назначение и блок ремонта) одной комнаты не проходят оба.
        Room.objects.select_for_update().filter(pk=room.pk).first()
        if room.id not in {r.id for r in free_rooms_for(booking)}:
            raise RoomConflict()
        booking.room = room
        booking.save(update_fields=["room", "updated_at"])
        # Комната не может стоять и первой, и дополнительной.
        booking.extra_rooms.remove(room)


def assigned_rooms(booking) -> list:
    """KA-12 E4.10b: все назначенные номера брони (первый — `room`)."""
    out = [booking.room] if booking.room_id else []
    out += [r for r in booking.extra_rooms.all() if r.id != booking.room_id]
    return out


def assign_rooms(booking, rooms) -> None:
    """KA-12 E4.10b: назначить номера мультиномерной брони одним действием.

    Порядок значим: первый → `room`, остальные → `extra_rooms`. Пустые и дубли
    отбрасываются; больше, чем `booking.rooms`, — RoomConflict; каждая комната —
    своей категории и свободна на диапазон (блокировки комнат в порядке pk)."""
    from .models import Room

    picked = []
    for room in rooms:
        if room is not None and room.id not in {r.id for r in picked}:
            picked.append(room)
    if len(picked) > max(1, booking.rooms or 1):
        raise RoomConflict()
    if any(r.unit_id != booking.unit_id for r in picked):
        raise RoomConflict()
    with transaction.atomic():
        for pk in sorted(r.pk for r in picked):
            Room.objects.select_for_update().filter(pk=pk).first()
        free = {r.id for r in free_rooms_for(booking)}
        if any(r.id not in free for r in picked):
            raise RoomConflict()
        booking.room = picked[0] if picked else None
        booking.save(update_fields=["room", "updated_at"])
        booking.extra_rooms.set(picked[1:])


def extra_room_slots(booking) -> list[dict]:
    """Селекты «Zimmer 2…N» формы правки: номер слота и уже назначенная комната."""
    if not booking or (booking.rooms or 1) <= 1:
        return []
    extras = [r.id for r in booking.extra_rooms.all() if r.id != booking.room_id]
    return [
        {"n": i + 2, "room_id": extras[i] if i < len(extras) else None}
        for i in range(booking.rooms - 1)
    ]


def drop_conflicting_rooms(booking) -> None:
    """После переноса дат: снять назначенные номера, которые на новые даты заняты."""
    free = {r.id for r in free_rooms_for(booking)}
    current = assigned_rooms(booking)
    keep = [r for r in current if r.id in free]
    if len(keep) == len(current):
        return
    try:
        assign_rooms(booking, keep)
    except RoomConflict:
        # Гонка: и оставшиеся номера только что заняли — снимаем все (номера
        # назначит стойка), лишь бы не держать один номер за двумя гостями.
        booking.room = None
        booking.save(update_fields=["room", "updated_at"])
        booking.extra_rooms.clear()


def create_block(unit, start_date, end_date, reason="", *, room=None):
    """KA-12 E4.10a: блок дат категории (room=None) или конкретной комнаты.

    Комната — только своей категории; если на неё на эти ночи уже назначен гость —
    RoomConflict («сначала переназначьте гостя»), молча комнату у брони не снимаем."""
    from datetime import timedelta

    from apps.core import status_registry

    from .availability import range_available
    from .models import Room, StayBooking, StayUnit, UnitBlock

    if end_date < start_date:
        raise ValueError("end before start")
    if room is not None and (room.unit_id != unit.id or not room.is_active):
        raise RoomConflict()
    with transaction.atomic():
        # Порядок блокировок как у book_stay/move_stay: категория, затем комната.
        StayUnit.objects.select_for_update().filter(pk=unit.pk).first()
        # Ревью E4.10a / Z-5 Р-4: блок (категории или комнаты) отнимает номер у
        # продажи — на ночах, где категория уже продана целиком, он дал бы овербукинг.
        # Внешние факты (iCal/OTA) пишут UnitBlock напрямую — отказать им нельзя.
        if not range_available(unit, start_date, end_date + timedelta(days=1)):
            raise NoCapacity()
        if room is None:
            return UnitBlock.objects.create(
                unit=unit, start_date=start_date, end_date=end_date, reason=reason[:120]
            )
        Room.objects.select_for_update().filter(pk=room.pk).first()
        occupied = (
            StayBooking.objects.filter(
                Q(room=room) | Q(extra_rooms=room),
                status__in=status_registry.active_statuses_for("stay"),
                arrival__lte=end_date,
                departure__gt=start_date,
            )
            .distinct()
            .exists()
        )
        if occupied:
            raise RoomConflict()
        return UnitBlock.objects.create(
            unit=unit, room=room, start_date=start_date, end_date=end_date, reason=reason[:120]
        )


def sync_room_quantity(unit) -> None:
    """PMS-R1: при заведённых физических комнатах quantity = число активных.

    Счётчик остаётся единственным источником ёмкости для anti-oversell/цен;
    комнаты — разбивка поверх (Вариант A). Без комнат — ничего не трогаем."""
    if not unit.rooms.exists():
        return
    count = unit.rooms.filter(is_active=True).count()
    if unit.quantity != count:
        unit.quantity = count
        unit.save(update_fields=["quantity", "updated_at"])


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
    voucher_code="",
    rooms=1,
    enforce_restrictions=False,
    dynamic_pricing=False,
    payment_method="",
    customer_type="private",
    billing_company="",
    billing_vat_id="",
    billing_address="",
    payment_due_at=None,
    apply_auto_discount=True,
):
    """Создать бронь по датам, атомарно проверив занятость по ночам. Бросает
    ValueError (кривой диапазон), MinStay, MaxGuests, StayUnavailable, PromoInvalid.
    extras (#7) — снимок выбранных доп-услуг [{label, price_cents}]; сумма в total.
    rate_plan (H1) — выбранный тариф (RatePlan|None): модификатор цены + снимок.
    adults/children (H5) — разбивка гостей; guests = adults + children (если задан
    adults). Kurtaxe (H9) считается по adults и включается в total.
    voucher_code (H4a) — промокод (Voucher): скидка на проживание+услуги (не на
    Kurtaxe), атомарно гасится; задан, но не применим → PromoInvalid.
    rooms (G5) — число номеров этого типа в одной брони (семьи/группы): занимает
    ``rooms`` из quantity, вместимость и цена проживания × rooms."""
    if departure <= arrival:
        raise ValueError("departure must be after arrival")
    rooms = max(1, int(rooms))
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

    # Z-4 (E4.6c): тариф перепроверяется под локом юнита (деактивирован/сужен между
    # формой и POST, или вызывающий передал чужой) — и берётся ПЕРЕЧИТАННЫМ, чтобы цена
    # и снимок считались по актуальным модификаторам, а не по объекту из формы.
    if rate_plan is not None:
        rate_plan = RatePlan.objects.for_unit(unit).filter(pk=rate_plan.pk, is_active=True).first()
        if rate_plan is None:
            raise RatePlanInvalid()

    if (departure - arrival).days < unit.min_nights:
        raise MinStay()
    # G12: правила онлайн-продаж — ре-валидация ТОЛЬКО для витрины
    # (enforce_restrictions=True из unterkunft_book); кабинет/walk-in — без гейта.
    if enforce_restrictions:
        from . import restrictions

        hit = restrictions.violation(unit, arrival, departure)
        if hit:
            raise RestrictionViolated(*hit)
    if guests > unit.max_guests * rooms:  # G5: вместимость × число номеров
        raise MaxGuests()
    if not availability.range_available(unit, arrival, departure, needed=rooms):
        raise StayUnavailable()

    from apps.core import extras as extras_engine

    extras_snap = list(extras or [])
    nights = (departure - arrival).days
    kurtaxe = pricing.kurtaxe_total_cents(adults, nights, children=children)  # H9, Z-6
    # G4: авто-скидка (LOS/Frühbucher/Last-Minute) — на проживание (без Extras/Kurtaxe).
    # G5: проживание × число номеров.
    # PMS-D: динамическая цена — ТОЛЬКО витрина (dynamic_pricing=True из
    # unterkunft_book); занятость считается под локом юнита, без новой брони.
    occ_kwargs = {}
    if dynamic_pricing:
        rules = StaySettings.load().clean_occupancy_rules()
        if rules:
            occ_kwargs = {
                "occupancy_rules": rules,
                "occupancy_by_day": availability.occupancy_by_day(unit, arrival, departure),
            }
    room_cents = (
        pricing.quote_total_cents(unit, arrival, departure, rate_plan=rate_plan, **occ_kwargs)
        * rooms
    )
    # P4 «ценовой слой»: акция на номер — обычный кандидат авто-скидки (max,
    # не суммируем); победа акции списывает лимит кампании в ЭТОЙ же транзакции.
    from apps.promotions import price_layer as promo_layer

    # Z-5 Р-1: стойка может выключить авто-скидки (G4/Lücken/акция) — тогда и лимит
    # акции не списывается; ваучер — явный ввод сотрудника, его тумблер не трогает.
    promo_hit = promo_layer.stay_promo(unit, arrival) if apply_auto_discount else None
    extra = [(promo_hit[1], promo_hit[2])] if promo_hit else None
    auto_discount_cents, auto_discount_label = (
        pricing.auto_discount(
            room_cents, nights, arrival, unit=unit, departure=departure, extra=extra
        )
        if apply_auto_discount
        else (0, "")
    )
    booked_promo = None
    if promo_hit and auto_discount_label == promo_hit[2]:
        promo_layer.claim_units(promo_hit[0], 1)  # OutOfStock → откат всей брони
        booked_promo = promo_hit[0]
    # H4a: промокод применяется к проживанию (после авто-скидки) + услугам, не к Kurtaxe.
    lodging_cents = room_cents - auto_discount_cents + extras_engine.total_cents(extras_snap)
    discount_cents, voucher_code_snap, voucher_paid = _apply_voucher(voucher_code, lodging_cents)
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
        rooms=rooms,
        price_cents=unit.price_cents,
        # DC-8: снимок ставки НДС номера (смена ставки в каталоге не переписывает
        # прошлые брони — GoBD).
        vat_rate=unit.vat_rate,
        # A5a сезон/выходные + H1 тариф + #7 Extras − H4a скидка + H9 Kurtaxe.
        total_cents=lodging_cents - discount_cents + kurtaxe,
        kurtaxe_cents=kurtaxe,
        discount_cents=discount_cents,
        voucher_code=voucher_code_snap,
        voucher_paid_cents=voucher_paid,
        auto_discount_cents=auto_discount_cents,
        auto_discount_label=auto_discount_label,
        extras=extras_snap,
        rate_plan=rate_plan,
        rate_snapshot=_rate_snapshot(rate_plan),
        # KA-12 Z-1: цены ночей на момент брони (те же аргументы, что room_cents).
        night_prices=pricing.night_snapshot(
            unit, arrival, departure, rate_plan=rate_plan, **occ_kwargs
        ),
        status=StayBooking.STATUS_CONFIRMED if auto_confirm else StayBooking.STATUS_PENDING,
        note=note,
        source_channel=(source_channel or "")[:50],
        promotion=booked_promo,
        # SH-23c: способ оплаты, тип покупателя и срок оплаты — снимком
        # (Р-5: 100 % предоплаты допускает и банковский перевод, не только карту).
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

        on_confirmed("stay", booking)
    # MX-2e: трекеры опций — пул проверяется, склад списывается; исключение
    # откатывает всю бронь (паттерн OutOfStock).
    from apps.core import option_trackers

    option_trackers.commit_options(extras_snap, kind="stay", deal=booking)
    # письмо «Anfrage erhalten» — Notification в этой же транзакции (E3)
    from .notifications import enqueue_stay_email

    enqueue_stay_email(booking, "created")
    # C2: «спросил с сайта → забронировал» — одна беседа (fail-soft, однозначность).
    from apps.inbox.deal_threads import adopt_open_thread, deal_ref_label

    adopt_open_thread(
        booking.customer,
        ref_kind="stay",
        ref_id=booking.reference_code,
        ref_label=deal_ref_label("stay", booking.reference_code),
    )
    return booking


def _move_keep_rate(booking, old_nights: int):
    """KA-12 E4.7a: перенос без «Neu berechnen» — держим СОГЛАСОВАННУЮ цену за ночь.

    Проживание (после скидок) масштабируется по числу ночей, per-night допы
    пересчитываются, Kurtaxe — всегда свежая (налог общины по adults × ночи, не
    предмет договорённости). Drag с тем же числом ночей и гостей — итог прежний.
    Скидку промокода/сертификата не трогаем (снимок)."""
    from apps.core import extras as extras_engine

    nights = (booking.departure - booking.arrival).days
    extras_old = extras_engine.total_cents(booking.extras)
    kurtaxe_old = booking.kurtaxe_cents or 0
    # База проживания = итог − Kurtaxe − допы + скидка (обратная формула reprice-ветки).
    base = max(0, booking.total_cents - kurtaxe_old - extras_old + (booking.discount_cents or 0))
    if nights != old_nights:
        base = round(base * nights / old_nights)
    booking.extras = extras_engine.retotal(booking.extras, nights=nights)
    booking.kurtaxe_cents = pricing.kurtaxe_total_cents(
        booking.adults, nights, children=booking.children
    )
    booking.total_cents = (
        max(0, base + extras_engine.total_cents(booking.extras) - (booking.discount_cents or 0))
        + booking.kurtaxe_cents
    )
    # Z-1: согласованные цены ночей едут вместе с бронью (разбивка = итог).
    booking.night_prices = pricing.shift_snapshot(
        booking.night_prices, booking.arrival, booking.departure
    )
    update_fields = [
        "unit",
        "room",
        "arrival",
        "departure",
        "total_cents",
        "kurtaxe_cents",
        "extras",
        "night_prices",
        "updated_at",
    ]
    if booking.payment_state == StayBooking.PAYMENT_PENDING and booking.deposit_cents:
        prepay = pricing.prepayment_cents(booking.total_cents, _rate_for_booking(booking))
        if prepay > 0:
            booking.deposit_cents = prepay
            update_fields.append("deposit_cents")
    booking.save(update_fields=update_fields)
    return booking


class SeasonOverlap(Exception):
    """Z-4: новый сезон пересекается с сезоном той же категории (``conflict``)."""

    def __init__(self, conflict):
        super().__init__(conflict)
        self.conflict = conflict


@transaction.atomic
def add_season_rate(unit, *, label, start_date, end_date, price_cents):
    """Z-4 (E4.6c): сезонная цена категории без пересечений. Границы включительные
    (резолвер цены: ``start ≤ ночь ≤ end``) — [1–10] и [10–20] пересекаются по 10-й.
    Лок строки категории сериализует две параллельные вставки. Уже существующие
    пересечения (до Z-4) не чиним — кабинет помечает их бейджем."""
    from .models import SeasonRate

    if end_date < start_date:
        raise ValueError("end before start")
    unit = StayUnit.objects.select_for_update().get(pk=getattr(unit, "pk", unit))
    conflict = (
        SeasonRate.objects.filter(unit=unit, start_date__lte=end_date, end_date__gte=start_date)
        .order_by("start_date")
        .first()
    )
    if conflict is not None:
        raise SeasonOverlap(conflict)
    return SeasonRate.objects.create(
        unit=unit,
        label=label,
        start_date=start_date,
        end_date=end_date,
        price_cents=price_cents,
    )


@transaction.atomic
def move_stay(booking, *, arrival, departure, unit=None, reprice=True):
    """Перенос брони на новый диапазон (и опц. в другой юнит) с той же
    anti-overbook-проверкой.

    Батч C (Belegungsplan): ``unit`` — целевой юнит (drag по вертикали);
    ``reprice=False`` — цена/суммы СОХРАНЯЮТСЯ (решение владельца: PMS-стандарт,
    гость уже согласился на цену; drag держит число ночей → Kurtaxe валидна).
    Обе блокировки строк берём в стабильном порядке pk (без дедлоков)."""
    if departure <= arrival:
        raise ValueError("departure must be after arrival")
    # KA-12 Z-5 (Р-6, ревью §9.7): гость уже заселён — заезд не переносится в
    # будущее, выезд — в прошлое (все поверхности: форма, кнопка, drag).
    if getattr(booking, "checked_in_at", None):
        from django.utils import timezone

        today = timezone.localdate()
        if arrival > today or departure < today:
            raise GuestCheckedInMove()
    ids = {booking.unit_id}
    if unit is not None:
        ids.add(unit.pk)
    locked = {
        u.pk: u for u in StayUnit.objects.select_for_update().filter(id__in=ids).order_by("id")
    }
    dest = locked[unit.pk] if unit is not None else locked[booking.unit_id]
    if (departure - arrival).days < dest.min_nights:
        raise MinStay()
    if booking.guests > dest.max_guests * booking.rooms:
        raise MaxGuests()
    # G5: бронь занимает свои rooms; при переносе в ТОТ ЖЕ юнит исключаем её же
    # из подсчёта; в другой юнит — она там ещё не занимает ничего.
    exclude = booking.pk if dest.pk == booking.unit_id else None
    if not availability.range_available(
        dest, arrival, departure, exclude_pk=exclude, needed=booking.rooms
    ):
        raise StayUnavailable()
    from apps.core import extras as extras_engine

    if dest.pk != booking.unit_id:
        booking.unit = dest
        # PMS-R2: физический номер принадлежит категории — при смене сбрасываем.
        booking.room = None
        # KA-12 E4.10b: и доп. номера мультиномерной брони.
        booking.extra_rooms.clear()
    unit = dest
    old_nights = max(1, (booking.departure - booking.arrival).days)
    booking.arrival = arrival
    booking.departure = departure
    if not reprice:
        return _move_keep_rate(booking, old_nights)
    # A5a база + H1 тариф (снимок) + #7 Extras (пересчёт per-night, MX-0) − H4a
    # скидка + H9 Kurtaxe. Промокод не перегашиваем — держим снимок скидки.
    nights = (departure - arrival).days
    rate_plan = _rate_for_booking(booking)
    booking.kurtaxe_cents = pricing.kurtaxe_total_cents(
        booking.adults, nights, children=booking.children
    )
    room_cents = (
        pricing.quote_total_cents(unit, arrival, departure, rate_plan=rate_plan) * booking.rooms
    )
    booking.night_prices = pricing.night_snapshot(unit, arrival, departure, rate_plan=rate_plan)
    # G4 + MX-0: авто-скидка ТЕМИ ЖЕ аргументами, что book_stay — без unit/departure
    # правка молча теряла Lücken-Deal; без extra — скидку акции при живом FK
    # StayBooking.promotion (итог и причина расходились).
    from apps.promotions import price_layer as promo_layer

    promo_hit = promo_layer.stay_promo(unit, arrival)
    promo_extra = [(promo_hit[1], promo_hit[2])] if promo_hit else None
    booking.auto_discount_cents, booking.auto_discount_label = pricing.auto_discount(
        room_cents, nights, arrival, unit=unit, departure=departure, extra=promo_extra
    )
    # MX-0: per-night допы следуют за новым числом ночей (завтрак ×2 ночи при
    # продлении до 5 недосчитывал 45 € — доказано тестом). Легаси-снимки без
    # unit_cents не трогаем.
    booking.extras = extras_engine.retotal(booking.extras, nights=nights)
    lodging_cents = (
        room_cents - booking.auto_discount_cents + extras_engine.total_cents(booking.extras)
    )
    booking.total_cents = max(0, lodging_cents - booking.discount_cents) + booking.kurtaxe_cents
    update_fields = [
        # PMS-R2 (фикс латентного бага): смена юнита раньше НЕ сохранялась
        # в reprice-ветке — "unit" отсутствовал в update_fields (путь был
        # недостижим: кнопка Move юнит не передавала; форма правки — передаёт).
        "unit",
        "room",
        "arrival",
        "departure",
        "total_cents",
        "kurtaxe_cents",
        "auto_discount_cents",
        "auto_discount_label",
        "extras",
        "night_prices",
        "updated_at",
    ]
    # MX-0: неоплаченная процентная предоплата (G7) следует за новым итогом —
    # гость ждёт ссылку на старую сумму при изменившейся цене. Оплаченный депозит
    # не трогаем (доплата/возврат — MX-3).
    if booking.payment_state == StayBooking.PAYMENT_PENDING and booking.deposit_cents:
        prepay = pricing.prepayment_cents(booking.total_cents, rate_plan)
        if prepay > 0:
            booking.deposit_cents = prepay
            update_fields.append("deposit_cents")
    booking.save(update_fields=update_fields)
    return booking


def _import_over_ical_block(unit, kwargs):
    """Снять iCal-блоки, накрывающие [заезд, последняя ночь], и повторить бронь
    в точке сохранения: неудача откатывает удаление блоков."""
    import datetime

    from .models import UnitBlock

    last_night = kwargs["departure"] - datetime.timedelta(days=1)
    # Только блок iCal РОВНО на даты брони — это та же бронь, пришедшая фидом.
    # Длинный «nicht verfügbar»-блок или блок другого канала не снимаем: иначе
    # даты открылись бы для продажи до следующего синка.
    covering = UnitBlock.objects.filter(
        unit=unit, start_date=kwargs["arrival"], end_date=last_night
    ).exclude(source_id_ref="")
    if not covering.exists():
        raise StayUnavailable()
    with transaction.atomic():
        covering.delete()
        return book_stay(unit, **kwargs)


@transaction.atomic
def import_external_booking(
    *, kind, unit, arrival, departure, name, external_ref="", email="", guests=1
):
    """G11: занести бронь из внешнего канала (Booking/Airbnb…) в наш календарь.

    Идемпотентно по (kind, external_ref): повторный импорт той же брони вернёт её.
    Успех → StayBooking (source_channel=kind, auto_confirm). Конфликт/невалидные
    даты (овербукинг между каналами) → не теряем: ставим UnitBlock на диапазон и
    возвращаем None (сигнал «разобрать вручную»)."""
    external_ref = (external_ref or "").strip()[:120]
    if external_ref:
        existing = StayBooking.objects.filter(
            source_channel=kind, external_ref=external_ref
        ).first()
        if existing is not None:
            return existing
    kwargs = {
        "arrival": arrival,
        "departure": departure,
        "name": name or kind,
        "email": email,
        "guests": guests,
        "source_channel": kind,
        "auto_confirm": True,
    }
    try:
        try:
            booking = book_stay(unit, **kwargs)
        except StayUnavailable:
            # KA-H6: часто «занято» — это iCal-блок ТОГО ЖЕ канала на эти даты. Снимаем
            # блоки iCal, целиком накрывающие бронь, и пробуем ещё раз; не вышло —
            # откат (блоки вернутся) и прежний путь «Import-Konflikt».
            booking = _import_over_ical_block(unit, kwargs)
    except (StayUnavailable, MinStay, MaxGuests, ValueError):
        import datetime

        from .models import UnitBlock

        last_night = departure - datetime.timedelta(days=1)
        if last_night >= arrival:
            UnitBlock.objects.create(
                unit=unit,
                start_date=arrival,
                end_date=last_night,
                reason=f"{kind}: Import-Konflikt {external_ref or name}"[:120],
            )
            transaction.on_commit(
                lambda: _notify_overbooking(
                    unit,
                    [
                        arrival + datetime.timedelta(days=i)
                        for i in range((departure - arrival).days)
                    ],
                    kind,
                )
            )
        return None
    if external_ref:
        booking.external_ref = external_ref
        booking.save(update_fields=["external_ref", "updated_at"])
    return booking


def cancellation_state(booking, today=None) -> dict:
    """Политика отмены брони по снимку тарифа H1 (H4b): {can_cancel, free}.

    Активная бронь (pending/confirmed) отменяема всегда; «free» (без штрафа/с
    возвратом депозита) — для flexible до ``free_cancel_days`` дней до заезда;
    non_refundable → отмена без возврата. fulfilled/cancelled — нельзя."""
    from datetime import timedelta

    from django.utils import timezone

    if today is None:
        today = timezone.localdate()
    from apps.core import status_registry

    if booking.status not in status_registry.active_statuses_for("stay"):
        return {"can_cancel": False, "free": False}
    snap = booking.rate_snapshot or {}
    if snap.get("cancellation") == "non_refundable":
        return {"can_cancel": True, "free": False}
    days = int(snap.get("free_cancel_days", 0) or 0)
    return {"can_cancel": True, "free": today <= booking.arrival - timedelta(days=days)}


def sync_ical_source(source) -> int:
    """Стянуть внешний iCal и пересоздать блоки этого источника (A5b).

    Идемпотентно: удаляем прежние блоки source_id_ref=source.pk и заводим заново
    по событиям фида (DTEND эксклюзивно → end_date = DTEND-1, наш включительный
    формат). Возвращает число заведённых блоков. Сетевые/парс-ошибки —
    last_status, блоки не трогаем.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.ssrf import safe_get

    from . import ical
    from .models import UnitBlock

    src = str(source.pk)
    try:
        # safe_get: egress-фильтр (без loopback/приватных/метаданных облака) + лимит
        # размера. source.url задаёт владелец — иначе SSRF на внутренние сервисы.
        text = safe_get(source.url, timeout=20)
        events = ical.parse_events(text)
    except Exception as exc:  # noqa: BLE001 — сбой фида не должен ронять синк
        source.last_status = str(exc)[:120]
        source.last_synced_at = timezone.now()
        source.save(update_fields=["last_status", "last_synced_at", "updated_at"])
        return 0

    from apps.core import status_registry

    from .availability import overbooked_nights
    from .models import StayBooking

    with transaction.atomic():
        UnitBlock.objects.filter(unit=source.unit, source_id_ref=src).delete()
        # KA-H6: бронь, уже импортированная из канала (G11) на те же даты, — это
        # та же занятость; второй блок задвоил бы её.
        imported = set(
            StayBooking.objects.filter(
                unit=source.unit,
                status__in=status_registry.active_statuses_for("stay"),
            )
            .exclude(external_ref="")
            .values_list("arrival", "departure")
        )
        created = 0
        window = []
        for _uid, start, end in events:
            last_night = end - timedelta(days=1)  # DTEND эксклюзивно → включительно
            if last_night < start:
                continue
            if (start, end) in imported:
                continue
            window.append((start, end))
            UnitBlock.objects.create(
                unit=source.unit,
                start_date=start,
                end_date=last_night,
                reason=f"iCal: {source.label or 'extern'}"[:120],
                source_id_ref=src,
            )
            created += 1
        # KA-H6: данные канала — правда (блок остаётся), но овербукинг больше не
        # молчит: статус источника + письмо владельцу (один раз на набор ночей).
        conflict = []
        if window:
            first = min(s for s, _e in window)
            last = max(e for _s, e in window)
            conflict = overbooked_nights(source.unit, first, last)
        source.last_status = f"OK: {created}"
        if conflict:
            dates = ", ".join(d.strftime("%d.%m.") for d in conflict[:10])
            source.last_status = f"OK: {created} · Konflikt: {dates}"[:120]
            transaction.on_commit(lambda: _notify_overbooking(source.unit, conflict, src))
        source.last_synced_at = timezone.now()
        source.save(update_fields=["last_status", "last_synced_at", "updated_at"])
    return created


def _notify_overbooking(unit, nights, origin: str) -> None:
    """KA-H6: письмо владельцу «Überbuchung» (дедуп по юниту и набору ночей)."""
    import hashlib
    import logging

    from apps.booking.revenue import _tenant
    from apps.notifications.services import email_locale, notify

    log = logging.getLogger(__name__)
    tenant = _tenant(None)
    recipient = (getattr(tenant, "owner_email", "") or "").strip()
    if not nights:
        return
    if not recipient:
        log.warning("overbooking on unit %s, but no owner e-mail (%s)", unit.pk, origin)
        return
    dates = ", ".join(d.strftime("%d.%m.%Y") for d in nights[:20])
    digest = hashlib.sha256(dates.encode()).hexdigest()[:12]
    with translation.override(email_locale()):
        subject = _("Überbuchung: %(unit)s") % {"unit": unit.name}
        body = _(
            "Für %(unit)s sind an diesen Nächten mehr Buchungen und Sperren als Zimmer "
            "vorhanden: %(dates)s. Der externe Kalender wurde trotzdem übernommen — "
            "bitte klären Sie die Belegung im Belegungsplan."
        ) % {"unit": unit.name, "dates": dates}
    try:
        notify(
            dedupe_key=f"stay:overbooking:{getattr(tenant, 'schema_name', '')}:{unit.pk}:{digest}",
            type="stay_overbooking_owner",
            recipient=recipient,
            subject=subject,
            body=body,
        )
    except Exception:  # noqa: BLE001 — синк не падает из-за письма
        log.warning("overbooking mail not sent (%s)", origin, exc_info=True)
