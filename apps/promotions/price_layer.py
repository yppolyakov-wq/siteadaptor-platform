"""P3 «ценовой слой»: акции на УСЛУГИ — правила применения и чекаут (2026-08-03).

План promo-price-layer-plan-2026-08-03 §3. Акция с целью-услугой действует
только в рамках `target_rules` (дни недели / окно часов / конкретный мастер —
«счастливые часы»); чекаут — штатный `booking.services.book` с промо-ценой
снаружи (anti-double-book цел), лимит кампании списывается в ТОЙ ЖЕ транзакции
(conditional UPDATE — тот же приём, что у reserve/purchase). Занятый слот
откатывает и лимит — фантомного списания нет.
"""

from django.db import transaction
from django.db.models import F

from .models import Promotion
from .services import OutOfStock


def claim_units(promotion, quantity: int) -> None:
    """Списать лимит кампании (None = без лимита, но акция обязана быть active).

    Единственная гарантия «не в минус» без блокировки строки — conditional
    UPDATE с F() (замок конкуренции: test_concurrency). Бросает OutOfStock."""
    if promotion.available_quantity is not None:
        rows = Promotion.objects.filter(
            id=promotion.id,
            status="active",
            available_quantity__gte=quantity,
        ).update(available_quantity=F("available_quantity") - quantity)
        if rows == 0:
            raise OutOfStock()
    elif promotion.status != "active":
        raise OutOfStock()


def return_units(promotion_id, quantity: int) -> None:
    """Вернуть лимит кампании (отмена сделки). Идемпотентность — на вызывающем
    FSM (терминальный статус не перезаходится); waitlist — как у резервов."""
    from .services import notify_waitlist_available

    Promotion.objects.filter(id=promotion_id, available_quantity__isnull=False).update(
        available_quantity=F("available_quantity") + quantity
    )
    promo = Promotion.objects.filter(id=promotion_id).first()
    if promo is not None:
        notify_waitlist_available(promo)


def rules_match(rules, start, resource_id=None) -> bool:
    """Проверка `target_rules` для момента `start` (aware local) и мастера.

    Ключи (все опциональны; пустые правила = всегда действует):
    weekdays: [0..6] (Mo=0) · hour_from/hour_to: int (окно [from, to),
    to может быть меньше from — «через полночь») · resource_id: str.
    Мусор в правилах трактуем консервативно: непонятное ограничение = НЕ
    совпало (fail-closed — промо-цену нельзя раздать по ошибке разметки)."""
    if not isinstance(rules, dict) or not rules:
        return True
    from django.utils import timezone

    local = timezone.localtime(start)
    weekdays = rules.get("weekdays")
    if weekdays is not None:
        if not isinstance(weekdays, list) or local.weekday() not in weekdays:
            return False
    hour_from, hour_to = rules.get("hour_from"), rules.get("hour_to")
    if hour_from is not None or hour_to is not None:
        try:
            lo = int(hour_from) if hour_from is not None else 0
            hi = int(hour_to) if hour_to is not None else 24
        except (TypeError, ValueError):
            return False
        h = local.hour
        inside = lo <= h < hi if lo <= hi else (h >= lo or h < hi)
        if not inside:
            return False
    want_resource = rules.get("resource_id")
    if want_resource:
        if resource_id is None or str(resource_id) != str(want_resource):
            return False
    return True


def promo_for_product(product):
    """P6: активная акция на товар → Promotion | None (для показа на витрине;
    чекаут по промо-цене живёт на детали АКЦИИ — /p/<uuid>/kaufen/).

    При нескольких — максимальная выгода клиенту (минимальная new_price)."""
    if product is None:
        return None
    best = None
    for promo in Promotion.objects.filter(product=product, status="active"):
        if not promo.has_discount:
            continue
        if best is None or promo.new_price < best.new_price:
            best = promo
    return best


def product_promo_map(product_ids):
    """P6: bulk-версия для карточек листинга — {product_id: Promotion} одним
    запросом (без N+1 на странице каталога)."""
    out = {}
    for promo in Promotion.objects.filter(product_id__in=list(product_ids), status="active"):
        if not promo.has_discount:
            continue
        cur = out.get(promo.product_id)
        if cur is None or promo.new_price < cur.new_price:
            out[promo.product_id] = promo
    return out


def service_promos(service):
    """P6: активные акции услуги с ценой (материализованный список — сетка слотов
    зовёт матчер десятки раз, запрос к БД нужен один)."""
    if service is None:
        return []
    return [
        p
        for p in Promotion.objects.filter(service=service, status="active")
        if p.new_price is not None
    ]


def promo_for_service(service, start, resource_id=None, promos=None):
    """Активная акция на услугу, действующая в момент `start` у мастера.

    → (promotion, price_cents) или None. При нескольких — максимальная выгода
    клиенту (минимальная цена), как «не суммируем, берём лучшее» у stays.
    `promos` — предзагруженный `service_promos()` (сетка слотов, без N+1)."""
    if service is None:
        return None
    if promos is None:
        promos = Promotion.objects.filter(service=service, status="active")
    best = None
    for promo in promos:
        if not rules_match(promo.target_rules, start, resource_id):
            continue
        price = promo.new_price
        if price is None:
            continue
        cents = int(round(float(price) * 100))
        if best is None or cents < best[1]:
            best = (promo, cents)
    return best


@transaction.atomic
def purchase_service(
    promotion,
    *,
    resource,
    start,
    end,
    name,
    email="",
    phone="",
    note="",
    source_channel="",
):
    """Чекаут акции-услуги СТАНДАРТНОЙ бронью (двойное списание в одной
    транзакции): лимит кампании + слот мастера (anti-double-book штатный).
    SlotTaken/ResourceClosed откатывают и лимит. Правила времени/мастера
    проверяются здесь же — API нельзя обойти хитрым POST'ом."""
    from apps.booking import services as booking_services

    if promotion.service_id is None:
        raise ValueError("promotion has no service target")
    if not rules_match(promotion.target_rules, start, resource.pk):
        raise OutOfStock()  # вне окна акции — по промо-цене не продаём
    price = promotion.new_price
    return booking_services.book(
        resource,
        start=start,
        end=end,
        name=name,
        email=email,
        phone=phone,
        note=note,
        source_channel=source_channel or "promo",
        service=promotion.service,
        price_cents=int(round(float(price) * 100)) if price is not None else 0,
        promotion=promotion,  # лимит кампании — внутри atomic book()
    )


def stay_promo(unit, arrival=None):
    """P4: активная акция на номер → (promotion, percent, label) | None.

    Скидка задаётся процентом (`discount_percent`); правило окна проживания —
    `target_rules {"stay_from","stay_to"}` (ISO-даты, проверяется ЗАЕЗД;
    мусор = fail-closed). При нескольких — максимальный процент (норма G4)."""
    from datetime import date

    if unit is None:
        return None
    best = None
    for promo in Promotion.objects.filter(stay_unit=unit, status="active"):
        percent = promo.discount_percent or 0
        if not percent:
            continue
        rules = promo.target_rules if isinstance(promo.target_rules, dict) else {}
        frm, to = rules.get("stay_from"), rules.get("stay_to")
        if (frm or to) and arrival is not None:
            try:
                if frm and arrival < date.fromisoformat(frm):
                    continue
                if to and arrival > date.fromisoformat(to):
                    continue
            except (TypeError, ValueError):
                continue  # кривые правила = акция не действует
        if best is None or percent > best[1]:
            title = promo.title.get("de") or next(iter(promo.title.values()), "Aktion")
            best = (promo, percent, f"Aktion −{percent}% · {title}"[:80])
    return best
