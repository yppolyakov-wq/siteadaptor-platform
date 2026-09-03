"""Сервис создания заказа Click & Collect (Track D / D2a).

Зеркало promotions.services.reserve по работе с Customer (переиспользование по
email), но клиент из заказа помечается created_source="order". Остаток v1 не
списываем (решение ТЗ: предзаказ без жёсткого лимита; stock — отдельный
инкремент D2c).
"""

import re
import secrets
import string
from decimal import Decimal

from django.db import transaction

from apps.inventory.services import record_movement
from apps.promotions.models import Customer

from .models import Order, OrderItem

_ALPHABET = string.ascii_uppercase + string.digits


class EmptyOrder(Exception):
    """Оформление пустой корзины."""


class OutOfStock(Exception):
    """Не хватает остатка на товар/вариант (R3)."""

    def __init__(self, title="", available=0):
        self.title = title
        self.available = available
        super().__init__(f"out of stock: {title} (available {available})")


def _reserve_stock(norm):
    """Атомарно списать остаток по позициям (R3, паттерн anti-oversell).

    Блокируем строку товара/варианта (select_for_update), проверяем и списываем.
    null = без учёта (не трогаем). Вызывается внутри транзакции create_order;
    при нехватке бросает OutOfStock → заказ не создаётся (откат).
    """
    from apps.catalog.models import Product, ProductVariant

    # Стабильный порядок блокировок — меньше шанс дедлока при конкуренции.
    for product, variant, qty, _options in sorted(
        norm, key=lambda i: str(i[1].pk if i[1] else i[0].pk)
    ):
        if variant is not None:
            row = ProductVariant.objects.select_for_update().get(pk=variant.pk)
            title = f"{product} · {variant.label}"
        else:
            row = Product.objects.select_for_update().get(pk=product.pk)
            title = str(product)
        if row.stock_quantity is None:
            continue  # без учёта остатка
        if row.stock_quantity < qty:
            raise OutOfStock(title=title, available=row.stock_quantity)
        row.stock_quantity -= qty
        row.save(update_fields=["stock_quantity", "updated_at"])
        # Склад-2 E1.5: если сущность ведётся по партиям — гасим FEFO (ближайший MHD
        # первым) в той же atomic. No-op для товаров без партий → поведение прежнее.
        from apps.inventory.services import consume_fefo, has_lots

        if has_lots(product, variant):
            consume_fefo(product, variant, qty=qty)


def _plz_prefixes(raw) -> list[str]:
    """«40, 41 235» → ['40','41235'] (только цифры, по запятым/пробелам)."""
    parts = re.split(r"[,\s]+", str(raw or "").strip())
    return [d for d in (re.sub(r"\D", "", p) for p in parts) if d]


def _zone_for_plz(tenant, plz):
    """Зона доставки с самым длинным совпавшим PLZ-префиксом (или None)."""
    digits = re.sub(r"\D", "", str(plz or ""))
    best, best_len = None, -1
    for zone in getattr(tenant, "delivery_zones", None) or []:
        if not isinstance(zone, dict):
            continue
        for prefix in _plz_prefixes(zone.get("plz", "")):
            if digits and digits.startswith(prefix) and len(prefix) > best_len:
                best, best_len = zone, len(prefix)
    return best


def delivery_quote(tenant, subtotal_cents: int, plz: str = "") -> dict:
    """Доставка для (суммы, PLZ): {deliverable, fee_cents, min_cents, free_cents}.

    Зона с самым длинным совпавшим PLZ-префиксом переопределяет плоский тариф/
    порог/Mindestbestellwert. При delivery_restrict_to_zones и непустом списке
    зон без совпадения — не доставляем. Бесплатно при subtotal ≥ free.
    """
    none = {"deliverable": False, "fee_cents": 0, "min_cents": 0, "free_cents": 0}
    if not getattr(tenant, "delivery_enabled", False):
        return none
    zones = getattr(tenant, "delivery_zones", None) or []
    zone = _zone_for_plz(tenant, plz)
    if zone is None and zones and getattr(tenant, "delivery_restrict_to_zones", False):
        return none

    def _from(key, fallback):
        if zone is not None and zone.get(key) not in (None, ""):
            try:
                return max(0, int(zone[key]))
            except (TypeError, ValueError):
                return fallback
        return fallback

    fee = _from("fee_cents", getattr(tenant, "delivery_fee_cents", 0) or 0)
    free = _from("free_cents", getattr(tenant, "delivery_free_cents", 0) or 0)
    min_c = _from("min_cents", getattr(tenant, "delivery_min_cents", 0) or 0)
    if free and subtotal_cents >= free:
        fee = 0
    return {"deliverable": True, "fee_cents": fee, "min_cents": min_c, "free_cents": free}


def shipping_cost(tenant, subtotal_cents: int, plz: str = "") -> int:
    """Стоимость доставки в центах — обёртка над delivery_quote (0, если недоступна)."""
    return delivery_quote(tenant, subtotal_cents, plz)["fee_cents"]


def _unique_order_code() -> str:
    for _ in range(10):
        code = "O-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Order.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique order reference code")


def _get_or_create_customer(*, name, email, phone) -> Customer:
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            if not customer.phone and phone:
                customer.phone = phone
                customer.save(update_fields=["phone", "updated_at"])
            return customer
    return Customer.objects.create(
        name=name, email=email, phone=phone, created_source=Customer.SOURCE_ORDER
    )


def _promo_title(promo) -> str:
    """SH-22: название акции снимком (немецкое → любое → пусто).

    Снимок, а не FK-чтение при показе: кампанию переименовывают и удаляют, а
    уже проданная строка обязана печатать то, что видел клиент.
    """
    if promo is None:
        return ""
    title = getattr(promo, "title", None) or {}
    if isinstance(title, dict):
        return (title.get("de") or next(iter(title.values()), ""))[:200]
    return str(title)[:200]


@transaction.atomic
def create_order(
    *,
    items,
    name,
    email="",
    phone="",
    note="",
    table_number="",
    pickup_location="",
    pickup_slot=None,
    source_channel="",
    fulfillment=Order.FULFILLMENT_PICKUP,
    shipping_address="",
    shipping_cents=0,
    combos=(),
    voucher_code="",
    payment_method="",
    custom_lines=(),
    reserve_expires_at=None,
    apply_promotions=True,
):
    """Создать заказ из позиций со снимками цены/названия.

    items — кортежи (product, qty) ИЛИ (product, variant, qty) ИЛИ
    (product, variant, qty, options); variant=None = товар без вариантов,
    options — список ModifierOption (A4b, надбавка к цене позиции). Для доставки
    (fulfillment=delivery) total включает shipping_cents. Бросает EmptyOrder без
    позиций и ValueError при qty < 1.

    custom_lines (LS-3 Sofort-Angebot) — кортежи (title, unit_price, qty[,
    product[, variant[, modifiers[, vat_rate]]]]): позиции с ЗАМОРОЖЕННОЙ
    ценой/названием (из строки, не из каталога). product/variant переданы → складской учёт как у обычных
    позиций (anti-oversell + леджер); None → свободная строка, склад не тронут.
    """
    norm = []
    for item in items:
        if len(item) == 4:
            product, variant, qty, options = item
        elif len(item) == 3:
            product, variant, qty, options = item[0], item[1], item[2], []
        else:
            product, variant, qty, options = item[0], None, item[1], []
        norm.append((product, variant, int(qty), list(options)))
    # Комбо-набор (A4): (combo, [options], qty). Снимок состава — в modifiers.
    combo_norm = [(c, list(opts), int(q)) for c, opts, q in combos]
    custom_norm = []
    for line in custom_lines:
        title, unit_price, qty = line[0], line[1], line[2]
        product = line[3] if len(line) > 3 else None
        variant = line[4] if len(line) > 4 else None
        # P2 «ценовой слой»: 6-й элемент — снимок modifiers (напр. маркер
        # {"promo": id} — по нему возврат лимита кампании при отмене).
        mods = list(line[5]) if len(line) > 5 else []
        # VAT-2: 7-й элемент — ставка НДС строки (услуга/блюдо из свободной сборки
        # несут свою). None → снимок берётся из товара, иначе дефолт модели.
        vat = line[6] if len(line) > 6 else None
        # SH-22: 8-й элемент — снимок скидки акции {"list_price", "promotion"}
        # (промо-чекаут /p/<uuid>/kaufen/ знает обе цены; свободная строка — None).
        promo_snap = line[7] if len(line) > 7 else None
        custom_norm.append(
            (
                str(title),
                Decimal(str(unit_price)),
                int(qty),
                product,
                variant,
                mods,
                vat,
                promo_snap,
            )
        )
    if not norm and not combo_norm and not custom_norm:
        raise EmptyOrder()
    if (
        any(qty < 1 for _p, _v, qty, _o in norm)
        or any(q < 1 for _c, _o, q in combo_norm)
        or any(q < 1 for _t, _u, q, _p, _v, _m, _r, _ps in custom_norm)
    ):
        raise ValueError("qty must be >= 1")

    # SF-4b (вариант A владельца): корзина/любой items-путь продаёт товар с
    # активной акцией-целью по ПРОМО-ЦЕНЕ. Лимит кампании списывается ЗДЕСЬ,
    # в той же atomic (conditional UPDATE claim_units; исчерпан → промо-
    # OutOfStock, checkout показывает «Aktionslimit erreicht»). Маркер
    # {"promo": id} едет в OrderItem.modifiers — возврат лимита при отмене
    # (_restore_promo_limits) и аналитика (deal_counts) читают его без правок.
    # custom_lines не трогаем (promotions.purchase кладёт маркер сам).
    line_promos: dict[int, tuple] = {}
    if apply_promotions and norm:
        from apps.promotions.price_layer import (
            claim_units,
            product_promo_map,
            promo_line_price,
        )

        promo_by_product = product_promo_map({p.pk for p, _v, _q, _o in norm})
        claim_totals: dict = {}
        for idx, (product, variant, qty, _options) in enumerate(norm):
            promo = promo_by_product.get(product.pk)
            promo_base = promo_line_price(promo, product, variant)
            if promo_base is None:
                continue
            line_promos[idx] = (promo, Decimal(str(promo_base)))
            prev = claim_totals.get(promo.pk)
            claim_totals[promo.pk] = (promo, (prev[1] if prev else 0) + qty)
        for promo, total_qty in claim_totals.values():
            claim_units(promo, total_qty)
    # R3: атомарное списание; OutOfStock → откат, заказа нет. Custom-строки с
    # привязкой к товару резервируют сток тем же путём (цена всё равно из строки).
    custom_reserve = [
        (p, v, q, []) for _t, _u, q, p, v, _m, _r, _ps in custom_norm if p is not None
    ]
    _reserve_stock(norm + custom_reserve)
    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    delivery = fulfillment == Order.FULFILLMENT_DELIVERY
    shipping = int(shipping_cents) if delivery else 0
    if norm:
        currency = norm[0][0].currency
    elif combo_norm:
        currency = combo_norm[0][0].currency or "EUR"
    else:
        currency = "EUR"
    order = Order.objects.create(
        customer=customer,
        reference_code=_unique_order_code(),
        note=note,
        table_number=(table_number or "").strip()[:20],
        pickup_location="" if delivery else (pickup_location or "").strip()[:200],
        pickup_slot=pickup_slot,
        source_channel=(source_channel or "")[:50],
        total=Decimal("0"),
        currency=currency,
        fulfillment=Order.FULFILLMENT_DELIVERY if delivery else Order.FULFILLMENT_PICKUP,
        shipping_address=(shipping_address or "").strip()[:1000] if delivery else "",
        shipping_cents=shipping,
        # E-7: способ оплаты известен ДО создания (пикер checkout) — письмо
        # `created` рендерится внутри этой функции и должно его видеть.
        payment_method=payment_method,
        # M3 Boutique: дедлайн Anprobe-резерва задаётся ДО письма `created` —
        # enqueue_order_email ремапит его на unverbindlich-текст.
        reserve_expires_at=reserve_expires_at,
    )
    total = Decimal("0")
    for idx, (product, variant, qty, options) in enumerate(norm):
        # DecimalField не приводит атрибут у не перезагруженных из БД
        # инстансов — нормализуем явно. Цена варианта: своя или base_price.
        base = variant.price_value if variant is not None else product.base_price
        # A4b: надбавки модификаторов входят в unit_price; снимок — отдельно.
        deltas = sum((Decimal(str(o.price_delta)) for o in options), Decimal("0"))
        # SF-4b: применимая акция заменяет БАЗУ строки (дельты опций — поверх).
        line_promo = line_promos.get(idx)
        list_price = None
        if line_promo is not None:
            unit_price = line_promo[1] + deltas
            # SH-22: листовая цена той же строки (база каталога + те же опции) —
            # снимком, иначе показать выгоду позже нечем: цены акции живые.
            list_price = Decimal(str(base)) + deltas
        else:
            unit_price = Decimal(str(base)) + deltas
        # Фидбэк 2026-08-04: артикул опции — в снимок (печать в заказе/PDF).
        # MX-0: id опции в снимке — сводный учёт доп-продаж и агрегаты «сколько
        # продано опции X» (немецкая метка — не ключ: переименование рвало историю).
        modifiers = [
            {
                "id": str(o.pk),
                "label": o.label,
                "delta": str(o.price_delta),
                **({"sku": o.sku} if o.sku else {}),
            }
            for o in options
        ]
        if line_promo is not None:
            # тот же dict-элемент, что кладёт promotions.services.purchase —
            # modifiers__contains матчит частично, возврат/аналитика едины.
            modifiers.append({"promo": str(line_promo[0].pk), "label": "Aktion"})
        label = variant.label if variant is not None else ""
        title = f"{product} · {label}" if label else str(product)
        item = OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,
            variant_label=label,
            # «везде артикул»: снимок Art.-Nr. (вариантный приоритетнее товарного).
            sku=(variant.sku if variant is not None and variant.sku else product.sku),
            qty=qty,
            unit_price=unit_price,
            title_snapshot=title[:200],
            modifiers=modifiers,
            # SH-4: снимок ставки НДС товара (документ не переписывается, если
            # ставку в каталоге потом поменяли).
            vat_rate=product.vat_rate,
            # ERP-1: снимок EK — маржа истории больше не дрейфует с ценой закупки.
            cost_price=(variant.cost_value if variant is not None else product.cost_price),
            # SH-22: снимок скидки акции (листовая цена + кампания + её название).
            list_price=list_price,
            promotion=(line_promo[0] if line_promo is not None else None),
            promo_label=(_promo_title(line_promo[0]) if line_promo is not None else ""),
        )
        # U-D3: залогировать списание в склад-леджер (append-only, в той же atomic
        # create_order, что и декремент _reserve_stock). Только учитываемый остаток
        # (stock_quantity != None); идемпотентно по позиции (source_ref=item.pk).
        tracked = variant if variant is not None else product
        if tracked.stock_quantity is not None:
            record_movement(
                product=product,
                variant=variant,
                kind="sale",
                delta=-qty,
                source="order",
                source_ref=str(item.pk),
                note=order.reference_code,
            )
        total += unit_price * qty
    # Комбо-позиции (A4): одна OrderItem на набор, product=None, состав в modifiers.
    if combo_norm:
        from apps.catalog.combos import combo_price, combo_snapshot

        for combo, options, qty in combo_norm:
            unit_price = combo_price(combo, options)
            OrderItem.objects.create(
                order=order,
                product=None,
                combo=combo,
                qty=qty,
                unit_price=unit_price,
                title_snapshot=str(combo.name)[:200],
                modifiers=combo_snapshot(combo, options),
                # VAT-2: ставка набора снимком — меню-сет гастро уходил в документ
                # по 19 %, потому что у комбо ставки не было вовсе.
                vat_rate=combo.vat_rate,
            )
            total += unit_price * qty
    # LS-3: custom-строки — цена/название заморожены (персональное предложение);
    # позиции с товаром логируют списание в леджер (как обычные), свободные — нет.
    for title, unit_price, qty, product, variant, mods, line_vat, promo_snap in custom_norm:
        label = variant.label if variant is not None else ""
        _sku = ""
        if variant is not None and variant.sku:
            _sku = variant.sku
        elif product is not None:
            _sku = product.sku
        item = OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,
            variant_label=label,
            sku=_sku,
            qty=qty,
            unit_price=unit_price,
            title_snapshot=title[:200],
            modifiers=mods,
            # SH-4/VAT-2: у строки с товаром — его ставка; у свободной строки —
            # переданная явно (блюдо, услуга), иначе дефолт модели.
            **(
                {"vat_rate": product.vat_rate}
                if product is not None
                else ({"vat_rate": line_vat} if line_vat is not None else {})
            ),
            # ERP-1: EK-снимок у складских custom-строк (свободные — без).
            cost_price=(
                variant.cost_value
                if variant is not None
                else (product.cost_price if product is not None else None)
            ),
            # SH-22: снимок скидки акции для промо-чекаута (см. 8-й слот).
            list_price=(promo_snap or {}).get("list_price"),
            promotion=(promo_snap or {}).get("promotion"),
            promo_label=_promo_title((promo_snap or {}).get("promotion")),
        )
        tracked = variant if variant is not None else product
        if tracked is not None and tracked.stock_quantity is not None:
            record_movement(
                product=product,
                variant=variant,
                kind="sale",
                delta=-qty,
                source="order",
                source_ref=str(item.pk),
                note=order.reference_code,
            )
        total += unit_price * qty
    # Промокод (A4): скидка на сумму товаров+комбо (до доставки). Гашение под
    # блокировкой (redeem_voucher) — анти-двойное-списание; сбой → без скидки.
    discount = Decimal("0")
    if voucher_code:
        from apps.promotions.services import VoucherError, spend_voucher

        # B1.5: расчёт+списание атомарно (единая точка; balance — частично).
        try:
            disc_cents, _voucher = spend_voucher(voucher_code, int(total * 100))
            discount = Decimal(disc_cents) / 100
            order.voucher_code = voucher_code[:12]
            order.discount_cents = disc_cents
        except VoucherError:
            discount = Decimal("0")
    order.total = total - discount + Decimal(shipping) / 100  # G4: доставка в итог
    order.save(update_fields=["total", "voucher_code", "discount_cents", "updated_at"])
    # письма клиенту/владельцу — Notification в этой же транзакции,
    # доставка после коммита (D2b)
    from .notifications import enqueue_order_email

    enqueue_order_email(order, "created")
    # C2: «спросил с сайта → купил» остаётся ОДНОЙ беседой (fail-soft, только при
    # ровно одном открытом треде клиента без привязки).
    from apps.inbox.deal_threads import adopt_open_thread, deal_ref_label

    adopt_open_thread(
        order.customer,
        ref_kind="order",
        ref_id=order.reference_code,
        ref_label=deal_ref_label("order", order.reference_code),
    )
    return order
