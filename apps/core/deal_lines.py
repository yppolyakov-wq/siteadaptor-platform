"""DF-4: состав сделки СТРОКАМИ — как на утверждённом макете.

Сверка с макетом (`docs/design/deal-card-2026-08-25/Hotel.dc.html`) показала
расхождение: у брони номера, записи и билета блок «Positionen» рисовался парой
абзацев («3 Nächte · 2 Erw.»), тогда как макет требует таблицу — номер строки,
что продано, ставка НДС, цена за единицу, количество, сумма. У заказа и заявки
свои настоящие строки (OrderItem / смета), поэтому им этот модуль не нужен.

Источник данных — те же снимки, из которых считается налог (`core.vat`): ночи,
допы (unit_cents + per_night, MX-0), Kurtaxe, тариф билета. Ничего не считаем
заново — иначе показ разошёлся бы с деньгами.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import gettext_lazy as _

ZERO = Decimal("0")


def _money(cents) -> Decimal:
    return Decimal(int(cents or 0)) / 100


def _extras_rows(obj, nights: int, fallback_rate: Decimal) -> list[dict]:
    """Строки допов из снимка: цена за единицу × количество.

    Снимок несёт `unit_cents`/`per_night` (MX-0), поэтому количество честное:
    завтрак «pro Nacht» на трёхдневную бронь — это 3 единицы, а не одна."""
    rows = []
    for extra in getattr(obj, "extras", None) or []:
        if not isinstance(extra, dict):
            continue
        total = _money(extra.get("price_cents"))
        if not total:
            continue
        unit = _money(extra.get("unit_cents")) or total
        per_night = bool(extra.get("per_night"))
        qty = nights if per_night and nights else 1
        # Снимок мог прийти без unit_cents (старые брони) — тогда честнее
        # показать одну строку суммой, чем выдумывать деление.
        if unit * qty != total:
            unit, qty = total, 1
        raw = extra.get("vat_rate")
        rows.append(
            {
                "label": str(extra.get("label", "")),
                "note": str(_("pro Nacht")) if per_night else "",
                "rate": Decimal(str(raw)) if raw not in (None, "") else fallback_rate,
                "unit": unit,
                "qty": qty,
                "total": total,
            }
        )
    return rows


def deal_lines(kind: str, obj) -> list[dict]:
    """Строки состава для показа. Пустой список = у карточки свои строки."""
    rate = Decimal(str(getattr(obj, "vat_rate", 0) or 0))
    rows: list[dict] = []

    if kind == "stay":
        nights = int(getattr(obj, "nights", 0) or 0)
        extras_total = sum(
            (
                _money(e.get("price_cents"))
                for e in getattr(obj, "extras", None) or []
                if isinstance(e, dict)
            ),
            ZERO,
        )
        kurtaxe = _money(getattr(obj, "kurtaxe_cents", 0))
        total = _money(getattr(obj, "total_cents", 0))
        discount = _money(getattr(obj, "discount_cents", 0))
        lodging = max(total - extras_total - kurtaxe + discount, ZERO)
        unit = (lodging / nights) if nights else lodging
        unit_name = getattr(getattr(obj, "unit", None), "name", "") or str(_("Übernachtung"))
        rows.append(
            {
                "label": unit_name,
                "note": str(_("pro Nacht")),
                "rate": rate,
                "unit": unit,
                "qty": nights or 1,
                "total": lodging,
            }
        )
        rows += _extras_rows(obj, nights, rate)
        if kurtaxe:
            rows.append(
                {
                    "label": str(_("Kurtaxe")),
                    "note": str(_("ohne MwSt.")),
                    "rate": ZERO,
                    "unit": None,  # база (лица × ночи) в снимке не хранится
                    "qty": None,
                    "total": kurtaxe,
                }
            )
        return rows

    if kind == "booking":
        base = _money(getattr(obj, "price_cents", 0))
        service = getattr(obj, "service", None)
        label = getattr(service, "name", "") or str(_("Leistung"))
        party = int(getattr(obj, "party_size", 0) or 0)
        # MX-5: цена за человека — количество честное, иначе «1×».
        per_person = getattr(service, "pricing_mode", "") == "per_person" and party > 1
        rows.append(
            {
                "label": str(label),
                "note": str(_("pro Person")) if per_person else "",
                "rate": rate,
                "unit": (base / party) if per_person and party else base,
                "qty": party if per_person else 1,
                "total": base,
            }
        )
        rows += _extras_rows(obj, 0, rate)
        return rows

    if kind == "ticket":
        qty = int(getattr(obj, "quantity", 1) or 1)
        unit = _money(getattr(obj, "price_cents", 0))
        rows.append(
            {
                "label": getattr(obj, "tier_label", "") or str(_("Ticket")),
                "note": "",
                "rate": rate,
                "unit": unit,
                "qty": qty,
                "total": unit * qty,
            }
        )
        rows += _extras_rows(obj, 0, rate)
        accommodation = _money(getattr(obj, "accommodation_cents", 0))
        if accommodation:
            rows.append(
                {
                    "label": str(_("Übernachtung")),
                    "note": "",
                    "rate": rate,
                    "unit": accommodation,
                    "qty": 1,
                    "total": accommodation,
                }
            )
        return rows

    return rows
