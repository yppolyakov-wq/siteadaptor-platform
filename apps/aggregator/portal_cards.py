"""PH-3: данные для карточки портала — «Endet in …» и статус «открыто сейчас».

Считается на сервере в момент рендера (главная кэшируется до 2 минут — устаревание
допустимо, JS дотикивает по `data-ends-at`)."""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

ENDS_WINDOW_DAYS = 7  # дальше — не срочно, строку не показываем


def ends_label(listing, now=None) -> tuple[str, str]:
    """(текст, ISO) для строки «Endet in …»; пусто — без строки."""
    ends = getattr(listing, "ends_at", None)
    if not ends:
        return "", ""
    now = now or timezone.now()
    left = (ends - now).total_seconds()
    if left <= 0 or left > ENDS_WINDOW_DAYS * 86400:
        return "", ""
    if left < 3600:
        minutes = max(1, int(left // 60))
        text = _("Endet in %(n)s Min.") % {"n": minutes}
    elif left < 86400:
        hours = int(left // 3600)
        text = _("Endet in %(n)s Std.") % {"n": hours}
    else:
        days = int(left // 86400)
        text = ngettext("Endet in %(n)s Tag", "Endet in %(n)s Tagen", days) % {"n": days}
    return text, ends.isoformat()


def prepare_cards(cards, snapshot=None, now=None):
    """Отсчёт и часы работы на карточках (часы — общим снимком, один запрос)."""
    from .views import _attach_open_status

    now = now or timezone.now()
    for card in cards:
        card.ends_text, card.ends_iso = ends_label(card, now)
        card.ends_soon = bool(card.ends_text) and (card.ends_at - now).total_seconds() < 86400
    _attach_open_status(cards, snapshot=snapshot)
    return cards


def action_label(kind: str) -> str:
    """Подпись пилюли действия по виду листинга (честно: без «Coupon» — отклика в листинге нет)."""
    return {
        "promotion": _("Zum Angebot"),
        "product": _("Ansehen"),
        "service": _("Termin"),
        "event": _("Tickets"),
        "stay": _("Verfügbarkeit"),
        "menu": _("Anfragen"),
        "business": _("Zum Geschäft"),
    }.get(kind, _("Ansehen"))
