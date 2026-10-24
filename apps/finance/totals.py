"""Суммы счёта по группам ставок — ОДНА функция на счёт, PDF, журнал и вычеты.

Два режима (`Invoice.price_basis`):
- `net` — строки несут нетто за штуку (`unit_price`), налог = round(нетто группы × r).
  Ручной счёт и сметы заявок; все счета, выставленные до Bruttomethode.
- `gross` — строки несут брутто за штуку (`unit_gross`, цены сделок «inkl. MwSt.»);
  брутто группы делится на нетто и налог тем же `split_gross`, что считает сделка
  (`orders/totals.py`). Иначе часть брутто-сумм недостижима: 45,00 € @19 % «от
  нетто в центах» = 45,01 € (план `docs/ka-12-bruttomethode-plan-2026-10-24.md`).
"""

from decimal import ROUND_HALF_UP, Decimal

BASIS_NET = "net"
BASIS_GROSS = "gross"
_CENT = Decimal("0.01")


def _dec(value, default="0") -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except ArithmeticError:
        return Decimal(default)


def line_rate(line, vat_rate, small_business=False) -> Decimal:
    if small_business:
        return Decimal("0")
    own = line.get("vat_rate")
    return _dec(vat_rate) if own in (None, "") else _dec(own)


def line_gross(line, rate) -> Decimal:
    """Брутто строки (за все штуки). Строка без `unit_gross` (старый/смешанный
    снимок) — из нетто по ставке."""
    qty = _dec(line.get("qty", 1), "1")
    if line.get("unit_gross") not in (None, ""):
        return _dec(line["unit_gross"]) * qty
    return _dec(line.get("unit_price")) * qty * (1 + rate / Decimal("100"))


def rate_groups(lines, vat_rate, *, small_business=False, basis=BASIS_NET) -> list:
    """[(ставка, нетто, налог, брутто)] по убыванию ставки. Кривая строка (KeyError/
    TypeError) поднимается наверх — вызывающий решает, какой фолбэк ему честен."""
    from apps.orders.totals import split_gross

    sums: dict[Decimal, Decimal] = {}
    for line in lines or []:
        rate = line_rate(line, vat_rate, small_business)
        if basis == BASIS_GROSS:
            amount = line_gross(line, rate)
        else:
            amount = _dec(line["unit_price"]) * _dec(line.get("qty", 1), "1")
        sums[rate] = sums.get(rate, Decimal("0")) + amount
    rows = []
    for rate in sorted(sums, reverse=True):
        if basis == BASIS_GROSS:
            gross = sums[rate].quantize(_CENT, rounding=ROUND_HALF_UP)
            net, vat = split_gross(gross, rate)
        else:
            net = sums[rate].quantize(_CENT, rounding=ROUND_HALF_UP)
            vat = (net * rate / Decimal("100")).quantize(_CENT, rounding=ROUND_HALF_UP)
            gross = net + vat
        rows.append((rate, net, vat, gross))
    return rows


def gross_line(text, qty, unit_gross, rate, **extra) -> dict:
    """Строка gross-счёта: `unit_gross` — истина, `unit_price` — производное нетто
    (4 знака; его читают экран счёта и старые потребители)."""
    unit_gross = _dec(unit_gross)
    rate = _dec(rate)
    net = (unit_gross / (1 + rate / Decimal("100"))).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    return {
        "text": str(text)[:200],
        "qty": qty,
        "unit_gross": str(unit_gross),
        "unit_price": str(net),
        "vat_rate": str(rate),
        **extra,
    }
