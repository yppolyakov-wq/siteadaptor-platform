"""T-8.1b: карточка «So finden Sie uns» на странице акции (план
docs/t8-1-aktion-demos-plan-2026-10-09.md §3).

Для локального бизнеса после цены главное — где это, открыто ли сейчас и как
связаться. Карточка собирается из полей тенанта; нет ни адреса, ни телефона →
None (страница без карточки, как раньше).
"""

from __future__ import annotations

from urllib.parse import quote

from apps.core.whatsapp import wa_link

_ROUTE_BASE = "https://www.google.com/maps/dir/?api=1&destination="


def route_url(tenant) -> str:
    """Ссылка «Route planen»: координаты точнее адреса, иначе адрес, иначе ""."""
    lat = getattr(tenant, "latitude", None)
    lng = getattr(tenant, "longitude", None)
    if lat is not None and lng is not None:
        return f"{_ROUTE_BASE}{lat},{lng}"
    address = (getattr(tenant, "address", "") or "").strip()
    if address:
        return _ROUTE_BASE + quote(address.replace("\n", ", "))
    return ""


def card_context(tenant, *, subject: str = "") -> dict | None:
    """Данные карточки или None. `subject` — тема WhatsApp-сообщения (акция)."""
    if tenant is None:
        return None
    address = (getattr(tenant, "address", "") or "").strip()
    phone = (getattr(tenant, "public_phone", "") or "").strip()
    if not address and not phone:
        return None
    text = ""
    if subject:
        from django.utils.translation import gettext as _

        text = _("Hallo, ich interessiere mich für: %(subject)s") % {"subject": subject}
    return {
        "name": getattr(tenant, "name", ""),
        "address": address,
        "phone": phone,
        "route_url": route_url(tenant),
        "whatsapp_url": wa_link(getattr(tenant, "whatsapp_number", "") or "", text),
    }
