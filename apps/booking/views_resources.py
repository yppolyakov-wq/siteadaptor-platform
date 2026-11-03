"""UX-D D3.0: действия экрана ресурсов («Öffnungszeiten & Ressourcen») — один модуль.

Раньше 10 действий жили веткой `if/elif` внутри `views.resources()`. Здесь они 1:1, плюс
карта `ACTION_TAB` — на какой вкладке будущей страницы ресурса (D3.1) живёт действие.
Перенос без изменения поведения, кроме двух правок:
  * предоплата разбирается строго (`parse_money`): мусор — ошибка, прежнее значение цело
    (раньше `_eur_to_cents` молча давал 0, а поле рисовалось округлённым до евро);
  * удаление правила часов — только правила присланного ресурса (раньше — по любому pk).
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _

from apps.core.i18n_input import apply_i18n_overlay, save_row_translations

from .models import AvailabilityRule, Resource

# Вкладки страницы ресурса (D3.1); здесь — только как адрес возврата действий.
RESOURCE_TABS = ("basis", "zeiten", "buchung", "tisch", "profil")


def _deposit_or_error(request, raw):
    """Предоплата в центах или None (ошибка уже показана; прежнее значение не трогаем)."""
    from . import views

    cents = views._deposit_cents_or_none(raw)
    if cents is None:
        messages.error(request, _("Bitte einen Betrag wie 25,00 angeben."))
    return cents


def _create(request):
    from . import views

    name = request.POST.get("name", "").strip()
    if not name:
        return None
    deposit = _deposit_or_error(request, request.POST.get("deposit_eur"))
    if deposit is None:
        return None
    resource = Resource(
        name=name,
        type=request.POST.get("type", Resource.TYPE_TABLE),
        capacity=views._bounded_int(request.POST.get("capacity"), 1, 1, 100),
        seats=views._seats_or_none(request.POST.get("seats")),
        zone=request.POST.get("zone", "").strip()[:40],
        counts_party_size=bool(request.POST.get("counts_party_size")),
        deposit_cents=deposit,
        require_manual_confirm=bool(request.POST.get("require_manual_confirm")),
    )
    # E9.10: переводы названия — до первого save, одной записью.
    apply_i18n_overlay(resource, request.POST, getattr(request, "tenant", None), ("name",))
    resource.save()
    messages.success(request, _("Resource created."))
    return None


def _i18n(request):  # E9.10: переводы названия стола/зала под строкой
    resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
    save_row_translations(resource, request.POST, getattr(request, "tenant", None), ("name",))
    messages.success(request, _("Saved."))
    return None


def _rule(request):
    resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
    try:
        AvailabilityRule.objects.create(
            resource=resource,
            weekday=int(request.POST.get("weekday", "0")),
            start_time=request.POST.get("start_time") or "09:00",
            end_time=request.POST.get("end_time") or "18:00",
            slot_minutes=max(5, min(int(request.POST.get("slot_minutes", "30")), 480)),
        )
        messages.success(request, _("Opening hours added."))
    except (TypeError, ValueError):
        messages.error(request, _("Invalid input."))
    return None


def _rules_from_hours(request):
    # KA-12 E4.1b: «Aus Öffnungszeiten übernehmen» — правила дня из часов бизнеса
    # (дни, где у ресурса уже есть правило, не трогаем).
    from apps.tenants import openinghours

    hours = openinghours.normalize(
        getattr(getattr(request, "tenant", None), "opening_hours_structured", None)
    )
    created = 0
    with transaction.atomic():  # двойной клик не плодит дубли правил
        try:
            resource = get_object_or_404(
                Resource.objects.select_for_update(), pk=request.POST.get("resource")
            )
        except (ValueError, ValidationError):  # кривой pk — 404, не 500
            raise Http404 from None
        have = set(resource.rules.values_list("weekday", flat=True))
        for wd, (o, c) in hours.items():
            if int(wd) not in have:
                AvailabilityRule.objects.create(
                    resource=resource, weekday=int(wd), start_time=o, end_time=c
                )
                created += 1
    if created:
        messages.success(request, _("Opening hours added."))
    else:
        messages.info(request, _("Keine Öffnungszeiten zum Übernehmen."))
    return None


def _rule_delete(request):
    # UX-D D3.0: только правило присланного ресурса (раньше — любое по pk).
    try:
        deleted, _detail = AvailabilityRule.objects.filter(
            pk=request.POST.get("rule"), resource_id=request.POST.get("resource")
        ).delete()
    except (ValueError, ValidationError):  # мусорный id — не 500 (ревью SP-3)
        deleted = -1
    if deleted < 0:
        messages.error(request, _("Invalid input."))
    elif not deleted:
        messages.error(request, _("Nicht gefunden."))
    return None


def _closed(request):
    from apps.core import closures

    from . import views

    day = views._parse_day_or_none(request.POST.get("date"))
    if not views._may_close_business(request):
        messages.error(request, views.CLOSE_BUSINESS_OWNER_ONLY)
    elif day is None:
        messages.error(request, _("Invalid date."))
    else:
        closures.set_range(day, day, reason=request.POST.get("reason", "").strip())
        messages.success(request, _("Closed date added."))
    return None


def _toggle(request):
    resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
    resource.is_active = not resource.is_active
    resource.save(update_fields=["is_active", "updated_at"])
    return None


def _settings(request):
    from apps.booking import occupancy

    from . import views

    resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
    deposit = _deposit_or_error(request, request.POST.get("deposit_eur"))
    if deposit is None:
        return None
    resource.deposit_cents = deposit
    resource.require_manual_confirm = bool(request.POST.get("require_manual_confirm"))
    resource.counts_party_size = bool(request.POST.get("counts_party_size"))
    fields = ["deposit_cents", "require_manual_confirm", "counts_party_size", "updated_at"]
    # KA-12 GA-3: вместимость/места/зона правятся здесь же (presence-guard W0:
    # старая форма без этих полей их не трогает).
    if request.POST.get("seats_present"):
        resource.capacity = views._bounded_int(
            request.POST.get("capacity"), resource.capacity, 1, 100
        )
        resource.seats = views._seats_or_none(request.POST.get("seats"), resource.seats)
        resource.zone = request.POST.get("zone", "").strip()[:40]
        resource.sort_order = views._bounded_int(request.POST.get("sort_order"), 0, 0, 999)
        # GA-4: «ab N Personen» онлайн; не больше мест (иначе стол молча
        # пропал бы из онлайн-подбора).
        resource.min_seats = min(
            views._bounded_int(request.POST.get("min_seats"), 1, 1, 99), resource.seats or 99
        )
        resource.bookable_online = bool(request.POST.get("bookable_online"))
        fields += ["capacity", "seats", "zone", "sort_order", "min_seats", "bookable_online"]
    # GA-5 (ревью): стол в комбинации обязан остаться «1 бронь = 1 стол» —
    # иначе область занятости стала бы несимметричной (продажа в одну сторону).
    if (resource.parts.exists() or resource.combinations.exists()) and not occupancy._combinable(
        resource
    ):
        messages.error(
            request,
            _(
                "Dieser Tisch gehört zu einer Kombination: Kapazität 1 und "
                "kein Platz-Pool sind nötig. Bitte zuerst die Kombination auflösen."
            ),
        )
        return redirect("booking:resources")
    resource.save(update_fields=fields)
    messages.success(request, _("Deposit settings saved."))
    return None


def _parts(request):
    # KA-12 GA-5: «Tisch 3+4» — из каких столов состоит комбинация.
    from apps.booking import occupancy

    resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
    try:
        with transaction.atomic():
            parts = occupancy.set_parts(resource, request.POST.getlist("part"))
    except occupancy.ComboInvalid as exc:
        messages.error(request, str(exc))
    except (ValueError, ValidationError):
        messages.error(request, _("Invalid input."))
    else:
        messages.success(
            request,
            _("Kombination gespeichert.") if parts else _("Kombination aufgelöst."),
        )
    return None


def _profile(request):
    # A3: профиль мастера — должность, био, фото (загрузка/удаление).
    from . import views

    resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
    resource.title = request.POST.get("title", "").strip()[:120]
    resource.bio = request.POST.get("bio", "").strip()[:2000]
    fields = ["title", "bio", "updated_at"]
    # E9.10: переводы имени/роли/био мастера — в той же форме профиля.
    fields += apply_i18n_overlay(
        resource, request.POST, getattr(request, "tenant", None), ("name", "title", "bio")
    )
    new_photo = views._uploaded_image_ref(request, "photo", "staff")
    if new_photo or request.POST.get("remove_photo"):
        resource.photo = new_photo or {}
        fields.append("photo")
    resource.save(update_fields=fields)
    messages.success(request, _("Profile saved."))
    return None


HANDLERS = {
    "resource": _create,
    "i18n": _i18n,
    "rule": _rule,
    "rules_from_hours": _rules_from_hours,
    "rule_delete": _rule_delete,
    "closed": _closed,
    "toggle": _toggle,
    "resource_settings": _settings,
    "resource_parts": _parts,
    "resource_profile": _profile,
}

# Вкладка страницы ресурса, где живёт действие (None — действие не про один ресурс).
ACTION_TAB = {
    "resource": "basis",
    "i18n": "basis",
    "toggle": "basis",
    "rule": "zeiten",
    "rules_from_hours": "zeiten",
    "rule_delete": "zeiten",
    "resource_settings": "buchung",
    "resource_parts": "tisch",
    "resource_profile": "profil",
    "closed": None,
}


def dispatch(request, action: str):
    """Выполнить действие; ответ — только если обработчик сам решил, куда вести."""
    handler = HANDLERS.get(action)
    return handler(request) if handler else None
