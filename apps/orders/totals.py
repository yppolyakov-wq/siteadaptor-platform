"""SH-3/4: итоги заказа с разбивкой НДС (фидбэк владельца 2026-08-20).

Цены в проекте — БРУТТО (PAngV «inkl. MwSt.», витрина показывает конечную цену),
поэтому НДС не доначисляется, а ВЫДЕЛЯЕТСЯ из суммы: netto = brutto / (1 + r),
mwst = brutto − netto. Ставка берётся из СНИМКА позиции (`OrderItem.vat_rate`),
у доставки — максимальная ставка позиций (правило DACH для Nebenleistung), а
§19 Kleinunternehmer обнуляет всё.

Один хелпер на все поверхности (карточка заказа, письма, PDF) — иначе цифры
разъедутся, как это уже было со скидкой.
"""

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def split_gross(gross: Decimal, rate: Decimal) -> tuple[Decimal, Decimal]:
    """Брутто → (нетто, НДС) для ставки `rate` в процентах."""
    gross = Decimal(str(gross))
    rate = Decimal(str(rate or 0))
    if rate <= 0:
        return _q(gross), Decimal("0.00")
    net = _q(gross / (Decimal("1") + rate / Decimal("100")))
    return net, _q(gross - net)


def order_totals(order, *, small_business=False) -> dict:
    """Итоги заказа: позиции, скидка, доставка, разбивка НДС по ставкам.

    Скидка уменьшает базу пропорционально долям ставок — иначе при двух ставках
    НДС посчитался бы с суммы, которую клиент не платил.
    Возвращает {"items", "discount", "shipping", "gross", "net", "vat", "rows"},
    где rows = [{"rate", "gross", "net", "vat"}] по убыванию ставки.

    SH-22 добавляет два ключа показа: "list_items" (сумма по ЛИСТОВЫМ ценам, то
    есть до скидок акций) и "promo_rows" ([{"label", "amount"}] по акциям, сумма
    по убыванию). Инвариант: list_items − Σpromo_rows − discount + shipping ==
    gross. Существующие ключи не меняются — их читают счёт и карточка сделки.
    """
    items = list(order.items.all())
    gross_items = sum((i.line_total for i in items), Decimal("0"))
    list_items = sum((i.list_total for i in items), Decimal("0"))
    # Скидки акций — по КАМПАНИИ (в заказе их может быть несколько): ключ =
    # снимок названия, чтобы переименование кампании не переписало документ.
    promo_by_label: dict[str, Decimal] = {}
    for item in items:
        amount = item.discount_total
        if amount <= 0:
            continue
        label = item.promo_name
        promo_by_label[label] = promo_by_label.get(label, Decimal("0")) + amount
    promo_rows = [
        {"label": label, "amount": _q(amount)}
        for label, amount in sorted(promo_by_label.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    discount = Decimal(order.discount_cents) / 100
    shipping = Decimal(order.shipping_cents) / 100 if order.is_delivery else Decimal("0")
    by_rate: dict[Decimal, Decimal] = {}
    for item in items:
        rate = Decimal("0") if small_business else Decimal(str(item.vat_rate or 0))
        by_rate[rate] = by_rate.get(rate, Decimal("0")) + item.line_total
    # Доставка — побочная услуга: ставка максимальной ставки товаров в заказе.
    if shipping:
        rate = max(by_rate) if by_rate else Decimal("0")
        if small_business:
            rate = Decimal("0")
        by_rate[rate] = by_rate.get(rate, Decimal("0")) + shipping
    # Скидка — пропорционально долям (база НДС уменьшается вместе с суммой).
    base = sum(by_rate.values(), Decimal("0"))
    if discount and base > 0:
        left = discount
        rates = sorted(by_rate, reverse=True)
        for idx, rate in enumerate(rates):
            share = left if idx == len(rates) - 1 else _q(discount * (by_rate[rate] / base))
            by_rate[rate] = max(by_rate[rate] - share, Decimal("0"))
            left -= share
    rows = []
    for rate in sorted(by_rate, reverse=True):
        gross = _q(by_rate[rate])
        if not gross:
            continue
        net, vat = split_gross(gross, rate)
        rows.append({"rate": rate, "gross": gross, "net": net, "vat": vat})
    return {
        "items": _q(gross_items),
        # SH-22: показные ключи (деньги не меняются — items остаётся нетто акций).
        "list_items": _q(list_items),
        "promo_rows": promo_rows,
        "promo_discount": _q(sum((r["amount"] for r in promo_rows), Decimal("0"))),
        "discount": _q(discount),
        "shipping": _q(shipping),
        "gross": _q(sum((r["gross"] for r in rows), Decimal("0"))),
        "net": _q(sum((r["net"] for r in rows), Decimal("0"))),
        "vat": _q(sum((r["vat"] for r in rows), Decimal("0"))),
        "rows": rows,
    }
