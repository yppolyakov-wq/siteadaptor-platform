"""DC-8: честная разбивка НДС у брони номера, записи услуги и билета.

Решение владельца 2026-08-26. У заказа разбивка была всегда (`orders.totals`),
у остальных видов сделок налог не выделялся вовсе — счёт и карточка показывали
одну сумму. Здесь — общий калькулятор: он собирает компоненты сделки со ЗНИМКАМИ
ставок и раскладывает их по ставкам так же, как заказ.

Немецкие правила, из-за которых одной ставки на сделку мало: проживание — 7 %
(§12 Abs. 2 Nr. 11 UStG), завтрак и прочие допы — 19 % (Aufteilungsgebot),
Kurtaxe — вне НДС. Поэтому ставка живёт на позиции, а не на сделке.

Скидка уменьшает базу: `discount_scope="deal"` — пропорционально долям ставок
(иначе НДС считался бы с суммы, которую клиент не платил), `"position"` — из
базовой позиции, `"delivery"` — из доставки (DC-9). Итог сделки при этом НЕ
меняется — меняется только распределение базы и показ.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from apps.orders.totals import split_gross

ZERO = Decimal("0")


def _q(value: Decimal) -> Decimal:
    from decimal import ROUND_HALF_UP

    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _extras_components(obj, fallback_rate: Decimal) -> list[tuple[str, Decimal, Decimal]]:
    """Доп-услуги снимка: (метка, брутто, ставка).

    Старые снимки без `vat_rate` идут по ставке сделки — fail-safe, как в
    `extras.retotal` (снимки живут годами и переписывать их нельзя)."""
    out = []
    for extra in getattr(obj, "extras", None) or []:
        if not isinstance(extra, dict):
            continue
        gross = Decimal(int(extra.get("price_cents", 0) or 0)) / 100
        if not gross:
            continue
        raw = extra.get("vat_rate")
        rate = Decimal(str(raw)) if raw not in (None, "") else fallback_rate
        out.append((str(extra.get("label", "")), gross, rate))
    return out


def deal_components(kind: str, obj) -> list[tuple[str, Decimal, Decimal, bool]]:
    """Компоненты сделки: (метка, брутто, ставка, это базовая позиция).

    Базовая позиция — то, ЧТО продано (ночи, услуга, тариф билета): на неё
    ложится скидка со scope="position"."""
    rate = Decimal(str(getattr(obj, "vat_rate", 0) or 0))
    rows: list[tuple[str, Decimal, Decimal, bool]] = []
    if kind == "stay":
        extras = sum((c[1] for c in _extras_components(obj, rate)), ZERO)
        kurtaxe = Decimal(getattr(obj, "kurtaxe_cents", 0) or 0) / 100
        total = Decimal(getattr(obj, "total_cents", 0) or 0) / 100
        discount = Decimal(getattr(obj, "discount_cents", 0) or 0) / 100
        # Проживание = итог − допы − Kurtaxe + скидка (скидку раскладываем ниже).
        lodging = total - extras - kurtaxe + discount
        rows.append((str(_("Übernachtung")), max(lodging, ZERO), rate, True))
        rows += [(label, gross, r, False) for label, gross, r in _extras_components(obj, rate)]
        if kurtaxe:
            rows.append((str(_("Kurtaxe")), kurtaxe, ZERO, False))
        return rows
    if kind == "booking":
        base = Decimal(getattr(obj, "price_cents", 0) or 0) / 100
        rows.append((str(_("Leistung")), base, rate, True))
        rows += [(label, gross, r, False) for label, gross, r in _extras_components(obj, rate)]
        return rows
    if kind == "ticket":
        base = (
            Decimal(getattr(obj, "price_cents", 0) or 0)
            / 100
            * int(getattr(obj, "quantity", 1) or 1)
        )
        rows.append((getattr(obj, "tier_label", "") or str(_("Ticket")), base, rate, True))
        rows += [(label, gross, r, False) for label, gross, r in _extras_components(obj, rate)]
        accommodation = Decimal(getattr(obj, "accommodation_cents", 0) or 0) / 100
        if accommodation:
            rows.append((str(_("Übernachtung")), accommodation, rate, False))
        return rows
    return rows


def deal_vat(kind: str, obj, *, small_business: bool = False) -> dict:
    """{"rows": [{rate, gross, net, vat}], "gross", "net", "vat"} для сделки.

    Заказ идёт своим хелпером (его разбивка честная с волны SH) — так точка
    входа одна, а поведение заказа байт-в-байт прежнее."""
    if kind == "order":
        from apps.orders.totals import order_totals

        totals = order_totals(obj, small_business=small_business)
        return {
            "rows": totals["rows"],
            "gross": totals["gross"],
            "net": totals["net"],
            "vat": totals["vat"],
        }

    if kind == "job":
        # VAT-1 (2026-08-26): у сметы своя арифметика — цены НЕТТО, налог сверху,
        # и с этой волны ставка живёт на ПОЗИЦИИ. Разбивку считает тот же
        # quote_totals, что и set_lines/PDF/публичная страница — одна точка
        # истины, иначе документ разойдётся с карточкой.
        from apps.jobs.totals import quote_totals

        lines = list(getattr(obj, "lines", None).all()) if hasattr(obj, "lines") else []
        if lines:
            totals = quote_totals(lines, getattr(obj, "vat_rate", 0), small_business=small_business)
            return {
                "rows": totals["rows"],
                "gross": totals["gross"],
                "net": totals["net"],
                "vat": totals["vat"],
            }
        # Смета без строк (или стаб в тестах): берём снимок сделки.
        gross = Decimal(getattr(obj, "gross", 0) or 0)
        net = Decimal(getattr(obj, "net", 0) or 0)
        tax = Decimal(getattr(obj, "vat_amount", 0) or 0)
        rate = ZERO if small_business else Decimal(str(getattr(obj, "vat_rate", 0) or 0))
        rows = [{"rate": rate, "gross": gross, "net": net, "vat": tax}] if gross else []
        return {"rows": rows, "gross": gross, "net": net, "vat": tax}

    components = deal_components(kind, obj)
    if not components:
        return {"rows": [], "gross": ZERO, "net": ZERO, "vat": ZERO}

    by_rate: dict[Decimal, Decimal] = {}
    base_rate = None
    for _label, gross, rate, is_base in components:
        rate = ZERO if small_business else rate
        by_rate[rate] = by_rate.get(rate, ZERO) + gross
        if is_base and base_rate is None:
            base_rate = rate

    discount = Decimal(getattr(obj, "discount_cents", 0) or 0) / 100
    scope = getattr(obj, "discount_scope", "deal") or "deal"
    if discount:
        _apply_discount(by_rate, discount, scope=scope, base_rate=base_rate)

    rows = []
    for rate in sorted(by_rate, reverse=True):
        gross = _q(by_rate[rate])
        if gross <= 0:
            continue
        net, vat = split_gross(gross, rate)
        rows.append({"rate": rate, "gross": gross, "net": net, "vat": vat})
    return {
        "rows": rows,
        "gross": _q(sum((r["gross"] for r in rows), ZERO)),
        "net": _q(sum((r["net"] for r in rows), ZERO)),
        "vat": _q(sum((r["vat"] for r in rows), ZERO)),
    }


def _apply_discount(by_rate: dict, discount: Decimal, *, scope: str, base_rate) -> None:
    """Снять скидку с базы. `position` — с базовой ставки, иначе пропорционально."""
    if scope == "position" and base_rate is not None and by_rate.get(base_rate):
        take = min(discount, by_rate[base_rate])
        by_rate[base_rate] -= take
        discount -= take
        if discount <= 0:
            return
    base = sum(by_rate.values(), ZERO)
    if base <= 0:
        return
    left = discount
    rates = sorted(by_rate, reverse=True)
    for idx, rate in enumerate(rates):
        share = left if idx == len(rates) - 1 else _q(discount * (by_rate[rate] / base))
        by_rate[rate] = max(by_rate[rate] - share, ZERO)
        left -= share


# Ставки, доступные владельцу в кабинете (DE): обычная, льготная, без налога.
RATE_CHOICES = (Decimal("19.00"), Decimal("7.00"), Decimal("0.00"))


def parse_rate_optional(raw):
    """Ставка из формы, где пусто = «как у документа/сделки» (VAT-1).

    Отличается от `parse_rate` тем, что возвращает None вместо дефолта: у строки
    сметы и у доп-услуги пустое значение — законное состояние, оно означает
    наследование ставки, а не «19 %».
    """
    if raw in (None, ""):
        return None
    try:
        value = Decimal(str(raw).replace(",", ".").strip())
    except Exception:  # noqa: BLE001 — мусор из формы (как в parse_rate ниже)
        return None
    return value if value in RATE_CHOICES else None


def parse_rate(raw, default: Decimal) -> Decimal:
    """Ставка из формы кабинета. Чужое значение → прежнее (защита от подмены)."""
    try:
        value = Decimal(str(raw).replace(",", ".").strip())
    except Exception:  # noqa: BLE001 — пустое/мусор
        return default
    return value if value in RATE_CHOICES else default
