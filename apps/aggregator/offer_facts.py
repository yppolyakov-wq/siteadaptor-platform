"""PH-13f (макет M8): факты страницы предложения — только из данных листинга.

Правило волны: нет данных — нет строки. Способ получения берём из отклика акции
(`AggregatorListing.action`, PH-9), остаток — из снимка `remaining`. Способа оплаты
(наличные/карта) в данных нет, поэтому «Bezahlung: Vor Ort» пишем только там, где оплата
на месте следует из самого отклика (отложить, купон). Признака НДС у листинга нет —
«inkl. MwSt.» не выводим (решение В-12 плана).
"""

from __future__ import annotations

from django.utils.translation import gettext as _

#: способы, где покупатель платит в магазине при выдаче
_PAY_ON_SITE = {"reserve", "coupon"}


def _how(action: str) -> str:
    return {
        "reserve": _("Zurücklegen, im Geschäft abholen"),
        "coupon": _("Coupon holen, im Geschäft einlösen"),
        "booking": _("Termin online buchen"),
        "inquire": _("Anfrage an das Geschäft senden"),
        "buy": _("Beim Geschäft bestellen"),
    }.get(action, "")


def facts(listing) -> list[dict]:
    """[{key, label, value}] — в порядке макета; пусто, если сказать нечего."""
    out = []
    action = (getattr(listing, "action", "") or "").strip()
    how = _how(action)
    if how:
        out.append({"key": "how", "label": _("So bekommen Sie es"), "value": how})
    if action in _PAY_ON_SITE:
        out.append({"key": "payment", "label": _("Bezahlung"), "value": _("Vor Ort")})
    if getattr(listing, "availability", "") == "sold_out":
        out.append({"key": "stock", "label": _("Verfügbar"), "value": _("Ausverkauft")})
    else:
        remaining = getattr(listing, "remaining", None)
        if remaining:
            out.append(
                {
                    "key": "stock",
                    "label": _("Verfügbar"),
                    "value": _("Noch %(n)s") % {"n": remaining},
                }
            )
    return out
