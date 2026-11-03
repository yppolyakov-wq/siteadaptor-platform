"""UX-D D4.0: настроечные действия кабинета номеров — тарифы, правила цен и продаж,
Kurtaxe, часы, подача карточки.

Раньше жили веткой в POST-диспетчере ``views.units()`` (список номеров + 10 разделов
настроек одной страницей). Обработчики перенесены 1:1 — поведение и сообщения прежние;
``units()`` по-прежнему принимает эти действия (старые формы и открытые вкладки браузера),
а экраны волны D4 («Tarife», «Preise & Regeln», «Unterkunft») принимают только свои.
``HOME`` — куда вернуть после сохранения без ``next``; меняется по мере переезда экранов.
"""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.i18n_input import apply_i18n_overlay

from .form_input import _eur_to_cents, _int, _parse_hour, _rateplan_pk, _rateplan_scope
from .models import RatePlan, StaySettings


def rateplan(request) -> None:
    """H1: тариф; Z-4 — для всех или выбранных категорий"""
    name = request.POST.get("name", "").strip()
    scope = _rateplan_scope(request.POST)
    if name and scope is not None and not scope[0] and not scope[1]:
        messages.error(request, _("Bitte mindestens eine Kategorie wählen."))
    elif name:
        rp = RatePlan.objects.create(
            name=name[:120],
            description=request.POST.get("description", "").strip()[:300],
            percent_adjust=_int(request.POST.get("percent_adjust", "0"), 0, -90, 200),
            surcharge_cents=_eur_to_cents(request.POST.get("surcharge_eur")),
            meal_plan=request.POST.get("meal_plan", RatePlan.MEAL_NONE),
            cancellation=request.POST.get("cancellation", RatePlan.CANCEL_FLEXIBLE),
            free_cancel_days=_int(request.POST.get("free_cancel_days", "0"), 0, 0, 365),
            prepayment_percent=_int(request.POST.get("prepayment_percent", "0"), 0, 0, 100),
            sort_order=_int(request.POST.get("sort_order", "0"), 0, 0, 999),
            applies_to_all=scope is None or scope[0],
        )
        if scope is not None and not scope[0]:
            rp.units.set(scope[1])
        messages.success(request, _("Rate plan added."))
    else:
        messages.error(request, _("Please enter a rate plan name."))


def rateplan_units(request) -> None:
    """Z-4: правка категорий тарифа"""
    rp = get_object_or_404(RatePlan, pk=_rateplan_pk(request.POST))
    scope = _rateplan_scope(request.POST)
    if scope is None:
        pass  # W0: формы без поля охвата набор не трогают
    elif not scope[0] and not scope[1]:
        messages.error(request, _("Bitte mindestens eine Kategorie wählen."))
    else:
        with transaction.atomic():
            rp.applies_to_all = scope[0]
            rp.save(update_fields=["applies_to_all", "updated_at"])
            rp.units.set([] if scope[0] else scope[1])
        messages.success(request, _("Settings saved."))


def rateplan_toggle(request) -> None:
    rp = get_object_or_404(RatePlan, pk=_rateplan_pk(request.POST))
    rp.is_active = not rp.is_active
    rp.save(update_fields=["is_active", "updated_at"])
    messages.success(request, _("Settings saved."))


def rateplan_delete(request) -> None:
    RatePlan.objects.filter(pk=_rateplan_pk(request.POST)).delete()
    messages.success(request, _("Settings saved."))


def card_amenities(request) -> None:
    """HF-2: пиктограммы удобств на карточке номера"""
    from apps.tenants import siteconfig

    tenant = request.tenant
    keys = siteconfig.normalize_card_amenities(request.POST.getlist("card_amenity"))
    # Targeted-write (как board_settings): прочие ключи site_config целы.
    cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
    if keys:
        cfg["stay_card_amenities"] = keys
    else:
        cfg.pop("stay_card_amenities", None)  # пусто = дефолт, ключ не храним
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
    messages.success(request, _("Settings saved."))


def kurtaxe(request) -> None:
    """H9 Kurtaxe + H6 Hausordnung"""
    settings_obj = StaySettings.load()
    settings_obj.kurtaxe_cents = _eur_to_cents(request.POST.get("kurtaxe_eur"))
    settings_obj.kurtaxe_label = request.POST.get("kurtaxe_label", "").strip()[:80] or "Kurtaxe"
    settings_obj.house_rules = request.POST.get("house_rules", "").strip()[:8000]
    fields = ["kurtaxe_cents", "kurtaxe_label", "house_rules", "updated_at"]
    # E9.10: переводы Hausordnung — в той же форме (выпадашка у заголовка).
    fields += apply_i18n_overlay(
        settings_obj, request.POST, getattr(request, "tenant", None), ("house_rules",)
    )
    # KA-12 Z-6: Kurtaxe детей — presence-guard (снятый чекбокс не приходит).
    if request.POST.get("kurtaxe_children_present"):
        settings_obj.kurtaxe_children_free = bool(request.POST.get("kurtaxe_children_free"))
        settings_obj.kurtaxe_child_cents = _eur_to_cents(request.POST.get("kurtaxe_child_eur"))
        fields += ["kurtaxe_children_free", "kurtaxe_child_cents"]
    settings_obj.save(update_fields=fields)
    messages.success(request, _("Settings saved."))


def stay_hours(request) -> None:
    """Z-5 Р-8: часы заезда/выезда"""
    checkin = _parse_hour(request.POST.get("checkin_hour"))
    checkout = _parse_hour(request.POST.get("checkout_hour"))
    if checkin is None or checkout is None:
        messages.error(request, _("Bitte eine Stunde von 0 bis 23 angeben."))
    else:
        settings_obj = StaySettings.load()
        settings_obj.checkin_hour, settings_obj.checkout_hour = checkin, checkout
        settings_obj.save(update_fields=["checkin_hour", "checkout_hour", "updated_at"])
        messages.success(request, _("Settings saved."))


def autodiscount_add(request) -> None:
    """G4: добавить правило авто-скидки"""
    settings_obj = StaySettings.load()
    kind = request.POST.get("kind", "")
    valid_kinds = {k for k, _ in StaySettings.AUTO_DISCOUNT_KINDS}
    threshold = _int(request.POST.get("threshold", "0"), 0, 1, 365)
    percent = _int(request.POST.get("percent", "0"), 0, 1, 90)
    if kind in valid_kinds and threshold and percent:
        rules = settings_obj.clean_auto_rules()
        rules.append({"kind": kind, "threshold": threshold, "percent": percent})
        settings_obj.auto_discount_rules = rules
        settings_obj.save(update_fields=["auto_discount_rules", "updated_at"])
        messages.success(request, _("Discount rule added."))
    else:
        messages.error(request, _("Please fill in the discount rule."))


def autodiscount_delete(request) -> None:
    """G4: удалить правило по индексу"""
    settings_obj = StaySettings.load()
    rules = settings_obj.clean_auto_rules()
    idx = _int(request.POST.get("index", "-1"), -1, 0, len(rules) - 1)
    if 0 <= idx < len(rules):
        rules.pop(idx)
        settings_obj.auto_discount_rules = rules
        settings_obj.save(update_fields=["auto_discount_rules", "updated_at"])
        messages.success(request, _("Settings saved."))


def booking_window(request) -> None:
    """G12: окно бронирования (глубина + мин. срок)"""
    settings_obj = StaySettings.load()
    settings_obj.max_advance_days = _int(request.POST.get("max_advance_days", "0"), 0, 0, 365)
    settings_obj.min_advance_days = _int(request.POST.get("min_advance_days", "0"), 0, 0, 90)
    settings_obj.save(update_fields=["max_advance_days", "min_advance_days", "updated_at"])
    messages.success(request, _("Settings saved."))


def restriction_add(request) -> None:
    """G12: правило продаж (Verkaufsregel)"""
    settings_obj = StaySettings.load()
    rule = {
        "start": request.POST.get("start", "").strip()[:10],
        "end": request.POST.get("end", "").strip()[:10],
        "unit": request.POST.get("unit", "").strip()[:40],
        "min_nights": _int(request.POST.get("min_nights", "0"), 0, 0, 365),
        "max_nights": _int(request.POST.get("max_nights", "0"), 0, 0, 365),
        "no_checkin": request.POST.getlist("no_checkin"),
        "no_checkout": request.POST.getlist("no_checkout"),
    }
    rules = settings_obj.clean_restriction_rules()
    rules.append(rule)
    settings_obj.restriction_rules = rules
    cleaned = settings_obj.clean_restriction_rules()
    if len(cleaned) > len(rules) - 1:  # правило не пустое → сохранилось
        settings_obj.restriction_rules = cleaned
        settings_obj.save(update_fields=["restriction_rules", "updated_at"])
        messages.success(request, _("Sales rule added."))
    else:
        messages.error(request, _("Please fill in at least one restriction."))


def restriction_delete(request) -> None:
    """G12: удалить правило по индексу"""
    settings_obj = StaySettings.load()
    rules = settings_obj.clean_restriction_rules()
    idx = _int(request.POST.get("index", "-1"), -1, 0, len(rules) - 1)
    if 0 <= idx < len(rules):
        rules.pop(idx)
        settings_obj.restriction_rules = rules
        settings_obj.save(update_fields=["restriction_rules", "updated_at"])
        messages.success(request, _("Settings saved."))


def occupancy_add(request) -> None:
    """PMS-D: правило «занятость ≥ X % → ±Y %»"""
    settings_obj = StaySettings.load()
    rules = settings_obj.clean_occupancy_rules()
    rules.append(
        {
            "occupancy": _int(request.POST.get("occupancy", "0"), 0, 0, 100),
            "percent": _int(request.POST.get("percent", "0"), 0, -50, 50),
        }
    )
    settings_obj.occupancy_rules = rules
    cleaned = settings_obj.clean_occupancy_rules()
    if len(cleaned) > len(rules) - 1:  # правило валидное → сохранилось
        settings_obj.occupancy_rules = cleaned
        settings_obj.save(update_fields=["occupancy_rules", "updated_at"])
        messages.success(request, _("Settings saved."))
    else:
        messages.error(request, _("Please fill in at least one restriction."))


def occupancy_delete(request) -> None:
    """PMS-D: удалить правило по индексу"""
    settings_obj = StaySettings.load()
    rules = settings_obj.clean_occupancy_rules()
    idx = _int(request.POST.get("index", "-1"), -1, 0, len(rules) - 1)
    if 0 <= idx < len(rules):
        rules.pop(idx)
        settings_obj.occupancy_rules = rules
        settings_obj.save(update_fields=["occupancy_rules", "updated_at"])
        messages.success(request, _("Settings saved."))


def gap_deal(request) -> None:
    """Lücken-Deal: скидка на короткие промежутки"""
    settings_obj = StaySettings.load()
    enabled = bool(request.POST.get("enabled"))
    settings_obj.gap_max_nights = (
        _int(request.POST.get("gap_max_nights", "3"), 3, 1, 14) if enabled else 0
    )
    settings_obj.gap_discount_percent = _int(
        request.POST.get("gap_discount_percent", "25"), 25, 1, 70
    )
    settings_obj.save(update_fields=["gap_max_nights", "gap_discount_percent", "updated_at"])
    messages.success(request, _("Settings saved."))


HANDLERS = {
    "rateplan": rateplan,
    "rateplan_units": rateplan_units,
    "rateplan_toggle": rateplan_toggle,
    "rateplan_delete": rateplan_delete,
    "autodiscount_add": autodiscount_add,
    "autodiscount_delete": autodiscount_delete,
    "occupancy_add": occupancy_add,
    "occupancy_delete": occupancy_delete,
    "gap_deal": gap_deal,
    "booking_window": booking_window,
    "restriction_add": restriction_add,
    "restriction_delete": restriction_delete,
    "kurtaxe": kurtaxe,
    "stay_hours": stay_hours,
    "card_amenities": card_amenities,
}
ACTIONS = frozenset(HANDLERS)

# Куда вернуть после сохранения (url_name, query). Пока экраны D4.1–D4.4 не готовы —
# прежний адрес: вкладка «Einstellungen» списка номеров и её под-вкладка.
HOME: dict[str, tuple[str, str]] = {
    "rateplan": ("stays:units", "tab=einstellungen&sec=preise"),
    "rateplan_units": ("stays:units", "tab=einstellungen&sec=preise"),
    "rateplan_toggle": ("stays:units", "tab=einstellungen&sec=preise"),
    "rateplan_delete": ("stays:units", "tab=einstellungen&sec=preise"),
    "autodiscount_add": ("stays:units", "tab=einstellungen&sec=preise"),
    "autodiscount_delete": ("stays:units", "tab=einstellungen&sec=preise"),
    "occupancy_add": ("stays:units", "tab=einstellungen&sec=preise"),
    "occupancy_delete": ("stays:units", "tab=einstellungen&sec=preise"),
    "gap_deal": ("stays:units", "tab=einstellungen&sec=preise"),
    "booking_window": ("stays:units", "tab=einstellungen&sec=regeln"),
    "restriction_add": ("stays:units", "tab=einstellungen&sec=regeln"),
    "restriction_delete": ("stays:units", "tab=einstellungen&sec=regeln"),
    "kurtaxe": ("stays:units", "tab=einstellungen&sec=kurtaxe"),
    "stay_hours": ("stays:units", "tab=einstellungen&sec=kurtaxe"),
    # HF-2: живёт рядом с прочей «подачей» номеров
    "card_amenities": ("stays:units", "tab=einstellungen&sec=kurtaxe"),
}


def home_url(action: str) -> str:
    """Адрес возврата после сохранения настроечного действия."""
    url_name, query = HOME[action]
    url = reverse(url_name)
    return f"{url}?{query}" if query else url


def handle(request, action: str) -> bool:
    """Выполнить настроечное действие; False — действие не настроечное."""
    handler = HANDLERS.get(action)
    if handler is None:
        return False
    handler(request)
    return True
