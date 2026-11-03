"""UX-D D4.1: «Tarife» — свой экран со списком, созданием в шторке и правкой.

Раньше тарифы жили карточкой во вкладке «Einstellungen» списка номеров, и тариф
нельзя было изменить — только создать, вкл/выкл, удалить (план
`docs/ux-d4-rooms-prices-plan-2026-11-03.md`). Права — `preise.view/edit`
(view_perms: GET читает, POST пишет). Правка безопасна для старых броней: у брони
снимок тарифа (`rate_snapshot`), перенос считает по снимку.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import drawer as drawer_mod
from apps.core.i18n_input import i18n_inputs_for
from apps.core.owner_login import local_next
from apps.core.permissions import has_perm

from . import settings_actions
from .models import RatePlan, StayUnit

LIST_ACTIONS = ("rateplan_toggle", "rateplan_delete")


def _category_choices():
    return list(StayUnit.objects.only("pk", "name").order_by("name"))


def _form_ctx(rp=None, values=None, errors=None, scope_err=None):
    """Значения полей формы: введённое (после ошибки) → тариф → пустые дефолты."""
    if values is None:
        values = {
            "name": rp.name if rp else "",
            "description": rp.description if rp else "",
            "percent_adjust": rp.percent_adjust if rp else 0,
            "surcharge_eur": f"{rp.surcharge_cents / 100:.2f}" if rp else "0",
            "meal_plan": rp.meal_plan if rp else RatePlan.MEAL_NONE,
            "cancellation": rp.cancellation if rp else RatePlan.CANCEL_FLEXIBLE,
            "free_cancel_days": rp.free_cancel_days if rp else 0,
            "prepayment_percent": rp.prepayment_percent if rp else 0,
            "sort_order": rp.sort_order if rp else 0,
        }
    return {
        "rv": values,
        "rv_errors": errors or {},
        "scope_error": scope_err,
        "meals": RatePlan.MEALS,
        "cancellations": RatePlan.CANCELLATIONS,
        "category_choices": _category_choices(),
    }


def _posted_values(post) -> dict:
    """Введённое как есть — для повторного показа формы после ошибки."""
    keys = (
        "name",
        "description",
        "percent_adjust",
        "surcharge_eur",
        "meal_plan",
        "cancellation",
        "free_cancel_days",
        "prepayment_percent",
        "sort_order",
    )
    return {k: (post.get(k) or "")[:300] for k in keys}


@login_required
def rate_plans(request):
    """Список тарифов строками; в строке — только статус-переключатель (hidden-поля)."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action not in LIST_ACTIONS:
            return HttpResponseBadRequest()
        settings_actions.handle(request, action)
        return redirect("stays:rate-plans")
    plans = list(RatePlan.objects.prefetch_related("units").order_by("sort_order", "name"))
    return render(
        request,
        "stays/rate_plans.html",
        {
            "nav": "rate-plans",
            "plans": plans,
            "can_edit_prices": has_perm(request.user, "preise.edit"),
        },
    )


@login_required
@drawer_mod.drawer_aware
def rate_plan_new(request):
    """«＋ Tarif»: шторка в кабинете, без JS — обычная страница. После создания —
    страница тарифа (там переводы и всё остальное)."""

    def render_form(values=None, errors=None, scope_err=None, rp=None):
        ctx = {
            "nav": "rate-plans",
            "rp": None,
            "next_url": drawer_mod.drawer_next(request, reverse("stays:rate-plans")),
            **_form_ctx(rp, values, errors, scope_err),
        }
        if request.method == "POST":
            ctx["next_url"] = local_next(request) or ctx["next_url"]
        if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
            return drawer_mod.fragment(render(request, "stays/_rate_plan_new_drawer.html", ctx))
        return render(request, "stays/rate_plan_new.html", ctx)

    if request.method == "POST":
        values, errors = settings_actions.parse_rate_plan(request.POST)
        scope, scope_err = settings_actions.scope_error(request.POST)
        if errors or scope_err:
            if drawer_mod.is_drawer(request):  # шторка показывает его в role=alert
                messages.error(request, scope_err or next(iter(errors.values())))
            return render_form(_posted_values(request.POST), errors, scope_err)
        rp = settings_actions.save_rate_plan(None, values, scope, request)
        messages.success(request, _("Rate plan added."))
        return redirect(reverse("stays:rate-plan-edit", args=[rp.pk]))
    return render_form()


@login_required
def rate_plan_edit(request, pk):
    """Страница тарифа: одна форма со всеми полями, охватом и переводами."""
    rp = get_object_or_404(RatePlan.objects.prefetch_related("units"), pk=pk)
    values = errors = scope_err = None
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "update":
            values, errors = settings_actions.parse_rate_plan(request.POST)
            scope, scope_err = settings_actions.scope_error(request.POST)
            if not errors and not scope_err:
                settings_actions.save_rate_plan(rp, values, scope, request)
                messages.success(request, _("Settings saved."))
                return redirect("stays:rate-plan-edit", pk=rp.pk)
            messages.error(request, scope_err or next(iter(errors.values())))
            values = _posted_values(request.POST)
        elif action in LIST_ACTIONS:
            # ревью D4.1 (F2): страница действует только на СВОЙ тариф, а не на pk из формы
            post = request.POST.copy()
            post["rateplan"] = str(rp.pk)
            request.POST = post
            settings_actions.handle(request, action)
            if action == "rateplan_delete":
                return redirect("stays:rate-plans")
            return redirect("stays:rate-plan-edit", pk=rp.pk)
        else:
            return HttpResponseBadRequest()
    return render(
        request,
        "stays/rate_plan_edit.html",
        {
            "nav": "rate-plans",
            "rp": rp,
            "can_edit_prices": has_perm(request.user, "preise.edit"),
            "i18n_inputs": i18n_inputs_for(
                rp, getattr(request, "tenant", None), fields=settings_actions.RATE_PLAN_TEXT_FIELDS
            ),
            **_form_ctx(rp, values, errors, scope_err),
        },
    )
