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
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.aggregator.stock_sync import touch_promotion
from apps.notifications.services import tenant_locale

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
        touch_promotion(promotion.id)  # T-8.26 п.3: «Ausverkauft» в каталоге города
    elif promotion.status != "active":
        raise OutOfStock()


def return_units(promotion_id, quantity: int) -> None:
    """Вернуть лимит кампании (отмена сделки). Идемпотентность — на вызывающем
    FSM (терминальный статус не перезаходится); waitlist — как у резервов."""
    from .services import notify_waitlist_available

    Promotion.objects.filter(id=promotion_id, available_quantity__isnull=False).update(
        available_quantity=F("available_quantity") + quantity
    )
    touch_promotion(promotion_id)  # T-8.26 п.3
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


def deal_counts(promotion) -> dict:
    """P7: сделки акции на новых рельсах — заказы (маркер {"promo": id} в
    OrderItem.modifiers), брони услуг и номеров (FK). Отменённые не считаем
    (им возвращён лимит кампании) — конверсия честная."""
    from apps.booking.models import Booking
    from apps.orders.models import OrderItem
    from apps.stays.models import StayBooking

    orders = (
        OrderItem.objects.filter(modifiers__contains=[{"promo": str(promotion.pk)}])
        .exclude(order__status="cancelled")
        .values("order_id")
        .distinct()
        .count()
    )
    bookings = (
        Booking.objects.filter(promotion=promotion).exclude(status=Booking.STATUS_CANCELLED).count()
    )
    stays = (
        StayBooking.objects.filter(promotion=promotion)
        .exclude(status=StayBooking.STATUS_CANCELLED)
        .count()
    )
    return {
        "orders": orders,
        "bookings": bookings,
        "stays": stays,
        "total": orders + bookings + stays,
    }


def promo_line_price(promo, product, variant=None):
    """SF-4b (вариант A владельца): промо-цена СТРОКИ корзины/заказа или None.

    Применимость: промо действует только на строку, чья база = base_price
    товара (без варианта или вариант без своей цены) — `new_price` выводится
    из базовой цены, вариант с собственной ценой едет по полной. Дельты
    модификаторов добавляются ПОВЕРХ снаружи."""
    if promo is None or product is None or promo.product_id != product.pk:
        return None
    if variant is not None and getattr(variant, "price", None) is not None:
        return None
    return promo.new_price


def attach_promos(products, *, with_lowest=True):
    """SF-4b: bulk-атрибуты промо для карточных поверхностей (каталог/главная/
    related/upsell/wishlist/quick-add): `promo`, `promo_price` (None у товара
    с вариантами — «from …» с промо врал бы), `promo_badge`, `promo_lowest`
    (§11 PAngV: карточка с промо-ценой анонсирует снижение — референс рядом).

    Один запрос акций + один батч PriceLog; без акций — ноль лишних запросов."""
    products = list(products)
    pmap = product_promo_map([p.pk for p in products])
    if pmap:
        # SF-7: цена сравнения (30 дней до старта + прошлые акции) — батчем на
        # страницу; нужна и без `with_lowest` — `has_discount` читает её всегда.
        from . import reference_price

        reference_price.attach(list(pmap.values()))
    for p in products:
        promo = pmap.get(p.pk)
        p.promo = promo
        p.promo_price = None if getattr(p, "has_variants", False) else promo_line_price(promo, p)
        # SF-7 (§11 PAngV): объявлять снижение — только от цены сравнения. Акция,
        # чья цена не ниже минимума 30 дней, продаёт по своей цене, но без
        # зачёркнутой цены, процента и «Sie sparen».
        announce = bool(promo and p.promo_price is not None and promo.has_discount)
        pct = promo.discount_percent_display if announce else None
        # festpreis без процента раньше вырождался в одинокий «%» — человеческая
        # подпись честнее (находка сверки Sparfuchs-ТЗ).
        p.promo_badge = f"−{pct} %" if pct else (_("Aktion") if promo else "")
        p.promo_old = promo.old_price if announce else None
        p.promo_lowest = promo.lowest_30d_display if announce and with_lowest else None
        # DL-19: выгода в евро — формам «Regal»/«Deal-Kachel» она нужна строкой
        # («Sie sparen 0,50 €»); в шаблоне вычесть нельзя, а второй запрос ради
        # этого не нужен — обе цены уже здесь.
        p.promo_savings = (p.promo_old - p.promo_price) if p.promo_old is not None else None
    return products


def promo_for_product(product):
    """P6: активная акция на товар → Promotion | None (для показа на витрине;
    чекаут по промо-цене живёт на детали АКЦИИ — /p/<uuid>/kaufen/).

    При нескольких — максимальная выгода клиенту (минимальная new_price)."""
    if product is None:
        return None
    best = None
    # SF-9: mystery-акция — не часть цены товара (секрет раскрывается и продаётся
    # только на странице акции); иначе баннер/корзина раскрыли бы цену.
    now = timezone.now()
    for promo in (
        Promotion.objects.filter(Promotion.on_sale_q(), product=product)
        .exclude(discount_style="mystery")
        .order_by("created_at", "pk")
    ):
        if not promo.lowers_price or not rules_match(promo.target_rules, now):
            continue
        if best is None or promo.new_price < best.new_price:
            best = promo
    return best


def product_promo_map(product_ids, *, now=None, timeless_only=False):
    """P6: bulk-версия для карточек листинга — {product_id: Promotion} одним
    запросом (без N+1 на странице каталога).

    KA-12 E3.6: акция с окном (`target_rules` дни/часы) действует только внутри
    окна — та же проверка у карточки, корзины и create_order («показано =
    списано»; момент — время ЗАКАЗА). `timeless_only` — для внешних фидов (Google
    не знает часовых окон): акции с правилами туда не уходят вовсе."""
    now = now or timezone.now()
    out = {}
    # Стабильный порядок: при равной цене побеждает более ранняя акция — иначе выбор
    # (и вместе с ним фид Merchant: mystery исключает товар) зависел бы от порядка строк.
    # SF-9: без mystery — см. `promo_for_product`.
    for promo in (
        Promotion.objects.filter(Promotion.on_sale_q(), product_id__in=list(product_ids))
        .exclude(discount_style="mystery")
        .select_related("product")
        .order_by("created_at", "pk")
    ):
        if not promo.lowers_price:
            continue
        if timeless_only and promo.target_rules:
            continue
        if not rules_match(promo.target_rules, now):
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
        for p in Promotion.objects.filter(Promotion.on_sale_q(), service=service).exclude(
            discount_style="mystery"
        )
        if p.new_price is not None and not p.price_condition
    ]


def promo_for_service(service, start, resource_id=None, promos=None):
    """Активная акция на услугу, действующая в момент `start` у мастера.

    → (promotion, price_cents) или None. При нескольких — максимальная выгода
    клиенту (минимальная цена), как «не суммируем, берём лучшее» у stays.
    `promos` — предзагруженный `service_promos()` (сетка слотов, без N+1)."""
    if service is None:
        return None
    if promos is None:
        promos = Promotion.objects.filter(Promotion.on_sale_q(), service=service)
    best = None
    for promo in promos:
        if promo.discount_style == "mystery":
            continue  # SF-9: сетка слотов/форма раскрыли бы секрет
        if promo.price_condition:
            continue  # В2: условие не применяется к одиночной записи
        if not rules_match(promo.target_rules, start, resource_id):
            continue
        price = promo.new_price
        if price is None:
            continue
        cents = int(round(float(price) * 100))
        if best is None or cents < best[1]:
            best = (promo, cents)
    return best


# KA-12 E6.4c: публичного вызова нет. Подключая к витрине — пропустить через
# booking.public_views._no_show_gate (правило «Anzahlung nach Nichterscheinen»).
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
    if promotion.price_condition:
        raise ValueError("conditional promotion is not sold online")  # В2
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
    # SF-9: mystery — не часть цены номера (quote/«ab …»/бейдж раскрыли бы секрет).
    for promo in Promotion.objects.filter(Promotion.on_sale_q(), stay_unit=unit).exclude(
        discount_style="mystery"
    ):
        if promo.price_condition:
            continue  # В2: условие не применяется ко всей брони
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
            # I18N-13: метка попадает в снимок брони — язык БИЗНЕСА.
            with translation.override(tenant_locale()):
                label = _("Aktion −%(pct)s%% · %(title)s") % {"pct": percent, "title": title}
            best = (promo, percent, label[:80])
    return best


def mystery_promo_for_product(product):
    """SF-9: активная акция-сюрприз на товар — только для нейтрального баннера
    «Überraschungsaktion» на детали товара (без цены и процента)."""
    if product is None:
        return None
    return (
        Promotion.objects.filter(Promotion.on_sale_q(), product=product, discount_style="mystery")
        .order_by("created_at", "pk")
        .first()
    )
