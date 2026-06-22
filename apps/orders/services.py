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
):
    """Создать заказ из позиций со снимками цены/названия.

    items — кортежи (product, qty) ИЛИ (product, variant, qty) ИЛИ
    (product, variant, qty, options); variant=None = товар без вариантов,
    options — список ModifierOption (A4b, надбавка к цене позиции). Для доставки
    (fulfillment=delivery) total включает shipping_cents. Бросает EmptyOrder без
    позиций и ValueError при qty < 1.
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
    if not norm and not combo_norm:
        raise EmptyOrder()
    if any(qty < 1 for _p, _v, qty, _o in norm) or any(q < 1 for _c, _o, q in combo_norm):
        raise ValueError("qty must be >= 1")

    _reserve_stock(norm)  # R3: атомарное списание; OutOfStock → откат, заказа нет
    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    delivery = fulfillment == Order.FULFILLMENT_DELIVERY
    shipping = int(shipping_cents) if delivery else 0
    currency = norm[0][0].currency if norm else (combo_norm[0][0].currency or "EUR")
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
    )
    total = Decimal("0")
    for product, variant, qty, options in norm:
        # DecimalField не приводит атрибут у не перезагруженных из БД
        # инстансов — нормализуем явно. Цена варианта: своя или base_price.
        base = variant.price_value if variant is not None else product.base_price
        # A4b: надбавки модификаторов входят в unit_price; снимок — отдельно.
        deltas = sum((Decimal(str(o.price_delta)) for o in options), Decimal("0"))
        unit_price = Decimal(str(base)) + deltas
        modifiers = [{"label": o.label, "delta": str(o.price_delta)} for o in options]
        label = variant.label if variant is not None else ""
        title = f"{product} · {label}" if label else str(product)
        OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,
            variant_label=label,
            qty=qty,
            unit_price=unit_price,
            title_snapshot=title[:200],
            modifiers=modifiers,
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
            )
            total += unit_price * qty
    # Промокод (A4): скидка на сумму товаров+комбо (до доставки). Гашение под
    # блокировкой (redeem_voucher) — анти-двойное-списание; сбой → без скидки.
    discount = Decimal("0")
    if voucher_code:
        from apps.loyalty.models import Voucher
        from apps.promotions.services import VoucherError, redeem_voucher

        voucher = Voucher.objects.filter(code=voucher_code).first()
        if voucher is not None and voucher.has_order_discount:
            disc_cents = voucher.discount_for(int(total * 100))
            if disc_cents > 0:
                try:
                    redeem_voucher(voucher_code)
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
    return order
