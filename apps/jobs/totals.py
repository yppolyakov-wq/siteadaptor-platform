"""VAT-1: итоги сметы с разбивкой НДС по ставкам (фидбэк владельца 2026-08-26).

Цены сметы — НЕТТО (в отличие от заказа, где цены брутто по PAngV), поэтому НДС
начисляется СВЕРХУ: vat = netto × ставка / 100. Ставка берётся из строки
(`JobLine.vat_rate`), а если у строки её нет — из документа (`Job.vat_rate`):
так существующие сметы считаются ровно как раньше.

Округляем ПО ГРУППЕ СТАВКИ, а не по строке: построчное округление с последующим
суммированием расходится с прежним расчётом на копейку, а смету уже видел клиент.

Одна функция на все поверхности сметы — карточка кабинета, PDF, публичная
страница принятия и счёт. Иначе клиент примет один итог, а получит другой (тот
же приём, что спас заказы в волне SH).
"""

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")
ZERO = Decimal("0")


def _q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def _dec(value, default="0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    return Decimal(str(value))


def line_rate(line, document_rate) -> Decimal:
    """Ставка строки: своя, иначе ставка документа.

    Работает и с моделью JobLine, и со словарём (`set_lines` считает по dict'ам
    ещё до записи в базу).
    """
    if isinstance(line, dict):
        own = line.get("vat_rate")
    else:
        own = getattr(line, "vat_rate", None)
    return _dec(document_rate) if own in (None, "") else _dec(own)


def quote_totals(lines, document_rate, *, small_business=False) -> dict:
    """Итоги сметы: {"rows", "net", "vat", "gross"}.

    rows = [{"rate", "net", "vat", "gross"}] по убыванию ставки — то же поле, что
    у заказа (`order_totals`), поэтому карточка печатает разбивку общим партиалом.
    §19 Kleinunternehmer обнуляет ставку целиком.
    """
    by_rate: dict[Decimal, Decimal] = {}
    for line in lines:
        if isinstance(line, dict):
            qty = _dec(line.get("qty", 1), "1")
            price = _dec(line.get("unit_price"))
        else:
            qty = _dec(getattr(line, "qty", 1), "1")
            price = _dec(getattr(line, "unit_price", 0))
        rate = ZERO if small_business else line_rate(line, document_rate)
        by_rate[rate] = by_rate.get(rate, ZERO) + price * qty

    rows = []
    for rate in sorted(by_rate, reverse=True):
        net = _q(by_rate[rate])
        vat = _q(net * rate / Decimal("100"))
        if not net and not vat:
            continue
        rows.append({"rate": rate, "net": net, "vat": vat, "gross": net + vat})

    net_total = _q(sum((r["net"] for r in rows), ZERO))
    vat_total = _q(sum((r["vat"] for r in rows), ZERO))
    return {
        "rows": rows,
        "net": net_total,
        "vat": vat_total,
        "gross": net_total + vat_total,
    }
