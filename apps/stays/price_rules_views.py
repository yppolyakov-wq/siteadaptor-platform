"""UX-D D4.2: «Preise & Regeln» — правила цены и продаж номеров в Einstellungen › Zimmer.

Раньше — четыре карточки во вкладке «Einstellungen» списка номеров (план
`docs/ux-d4-rooms-prices-plan-2026-11-03.md`, П4: «настройки — в Настройках»).
Вкладки — ссылки (`?tab=`), каждая карточка — свои мини-формы «список + добавить»;
обработчики — те же, что раньше (`settings_actions`), поэтому поведение прежнее.
Права: `preise.view/edit` (view_perms, как «Tarife»); проверка `preise.edit` во вьюхе
оставлена страховкой. Сотрудник с правом смотреть цены видит правила без форм.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.permissions import has_perm

from . import settings_actions
from .models import RatePlan, StaySettings, StayUnit

# вкладка → действия, которые она принимает (порядок = порядок вкладок)
TABS = {
    "rabatte": ("autodiscount_add", "autodiscount_delete"),
    "dynamik": ("occupancy_add", "occupancy_delete"),
    "luecken": ("gap_deal",),
    "regeln": ("booking_window", "restriction_add", "restriction_delete"),
}
ACTION_TAB = {action: tab for tab, actions in TABS.items() for action in actions}


def weekdays():
    return [
        (0, _("Mo")),
        (1, _("Tu")),
        (2, _("We")),
        (3, _("Th")),
        (4, _("Fr")),
        (5, _("Sa")),
        (6, _("Su")),
    ]


def rules_context() -> dict:
    """Правила цены и продаж с подписями для кабинета (то, что раньше строил units())."""
    stay_settings = StaySettings.load()
    unit_names = {
        str(pk): name
        for pk, name in StayUnit.objects.order_by("-is_active", "name").values_list("pk", "name")
    }
    kind_labels = dict(StaySettings.AUTO_DISCOUNT_KINDS)
    return {
        "stay_settings": stay_settings,
        "auto_rules": [
            {
                "index": i,
                "kind": r["kind"],
                "kind_label": kind_labels.get(r["kind"], r["kind"]),
                "threshold": r["threshold"],
                "percent": r["percent"],
            }
            for i, r in enumerate(stay_settings.clean_auto_rules())
        ],
        "auto_kinds": StaySettings.AUTO_DISCOUNT_KINDS,
        "occupancy_rules": [
            {**r, "index": i} for i, r in enumerate(stay_settings.clean_occupancy_rules())
        ],
        "restriction_rules": [
            {**r, "index": i, "unit_name": unit_names.get(r["unit"], "")}
            for i, r in enumerate(stay_settings.clean_restriction_rules())
        ],
        "unit_choices": list(unit_names.items()),
        "weekdays": weekdays(),
    }


@login_required
def price_rules(request):
    tab = request.GET.get("tab")
    if tab not in TABS:
        tab = next(iter(TABS))
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action not in ACTION_TAB:
            return HttpResponseBadRequest()
        # те же правила, что у units(): правила цены пишет только preise.edit
        if not has_perm(request.user, "preise.edit"):
            messages.error(request, _("Preise und Tarife ändern nur Inhaber und Admins."))
        else:
            settings_actions.handle(request, action)
        return redirect(reverse("stays:price-rules") + f"?tab={ACTION_TAB[action]}")
    return render(
        request,
        "stays/price_rules.html",
        {
            "nav": "price-rules",
            "tab": tab,
            "tabs": [
                ("rabatte", _("Automatic discounts")),
                ("dynamik", _("Dynamic prices")),
                ("luecken", _("Lücken-Deal")),
                ("regeln", _("Sales rules")),
            ],
            "can_edit_prices": has_perm(request.user, "preise.edit"),
            "rate_plans_count": RatePlan.objects.count(),
            **rules_context(),
        },
    )
