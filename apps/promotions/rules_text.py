"""DL-16.3 (AD2): условия акции человеческим языком — из полей, которые до сих пор
нигде не показывались (окно `target_rules`, лимит на клиента, срок резерва).

`conditions_for(promo)` → [{"icon", "text"}]; пусто → блок «Bedingungen» не рендерится.
Лимит/срок резерва — ТОЛЬКО у reservation-акций: на пути корзины `max_per_customer`
не enforce'ится (граница SF-4b), обещать его было бы ложью."""

from __future__ import annotations

from django.utils.dates import WEEKDAYS_ABBR
from django.utils.translation import gettext as _


def weekday_span(days) -> str:
    """[0, 1, 2, 4] → «Mo–Mi, Fr»; все семь → «täglich»; пусто → ''."""
    try:
        clean = sorted({int(d) for d in (days or []) if 0 <= int(d) <= 6})
    except (TypeError, ValueError):
        return ""
    if not clean:
        return ""
    if len(clean) == 7:
        return _("täglich")
    ranges, start, prev = [], clean[0], clean[0]
    for d in clean[1:]:
        if d == prev + 1:
            prev = d
            continue
        ranges.append((start, prev))
        start = prev = d
    ranges.append((start, prev))
    parts = []
    for a, b in ranges:
        if a == b:
            parts.append(str(WEEKDAYS_ABBR[a]))
        elif b == a + 1:
            parts.append(f"{WEEKDAYS_ABBR[a]}, {WEEKDAYS_ABBR[b]}")
        else:
            parts.append(f"{WEEKDAYS_ABBR[a]}–{WEEKDAYS_ABBR[b]}")
    return ", ".join(parts)


def conditions_for(promo) -> list[dict]:
    out: list[dict] = []
    rules = promo.target_rules if isinstance(promo.target_rules, dict) else {}
    days = weekday_span(rules.get("weekdays"))
    hf, ht = rules.get("hour_from"), rules.get("hour_to")
    hours = ""
    if isinstance(hf, int) and isinstance(ht, int) and not isinstance(hf, bool):
        hours = f"{hf}–{ht} " + _("Uhr")
    if days or hours:
        out.append({"icon": "🕒", "text": " ".join(x for x in (days, hours) if x)})
    if getattr(promo, "promo_type", "") == "reservation":
        if promo.max_per_customer:
            out.append(
                {"icon": "👤", "text": _("max. %(n)s pro Kunde") % {"n": promo.max_per_customer}}
            )
        if promo.reservation_ttl_hours:
            out.append(
                {
                    "icon": "📦",
                    "text": _("Reservierung %(h)s h gültig") % {"h": promo.reservation_ttl_hours},
                }
            )
    return out
