"""UX-D D4.3: «Unterkunft» — общие настройки размещения в Einstellungen › Zimmer.

Kurtaxe и Hausordnung, часы заезда/выезда, удобства на карточке номера. Раньше —
под-вкладка «Kurtaxe & Hausordnung» во вкладке «Einstellungen» списка номеров (план
`docs/ux-d4-rooms-prices-plan-2026-11-03.md`, П4). Обработчики прежние
(`settings_actions`). Права: экран — `einstellungen.view/edit`; Kurtaxe и часы пишут
цену и момент признания выручки → ещё `preise.edit` (как гейт `RATE_EDIT_ACTIONS`).
Kurtaxe и Hausordnung — одна форма (одно действие пишет оба поля; W0).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.core.permissions import has_perm
from apps.core.templatetags.cabinet import can_open

from . import settings_actions
from .models import AMENITIES, StaySettings

ACTIONS = ("kurtaxe", "stay_hours", "card_amenities")
PRICE_ACTIONS = ("kurtaxe", "stay_hours")


@login_required
def stay_settings(request):
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action not in ACTIONS:
            return HttpResponseBadRequest()
        if action in PRICE_ACTIONS and not has_perm(request.user, "preise.edit"):
            messages.error(request, _("Preise und Tarife ändern nur Inhaber und Admins."))
        else:
            settings_actions.handle(request, action)
        return redirect(settings_actions.home_url(action))
    tenant = getattr(request, "tenant", None)
    config = getattr(tenant, "site_config", None) or {}
    return render(
        request,
        "stays/stay_settings.html",
        {
            "nav": "stay-settings",
            "stay_settings": StaySettings.load(),
            "can_edit_prices": has_perm(request.user, "preise.edit"),
            "hour_choices": range(24),
            "amenities": AMENITIES,
            "card_amenities": set(
                config.get("stay_card_amenities", []) if isinstance(config, dict) else []
            ),
            "can_kurtaxe_report": can_open("stays:kurtaxe", request),
            "can_checkins": can_open("stays:checkins", request),
        },
    )
