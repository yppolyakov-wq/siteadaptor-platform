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
from django.contrib.auth.decorators import login_required
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
    # Ревью D3.0: мусор в предоплате не отменяет остальные правки — предоплата остаётся
    # прежней (ошибка сказана), прочие поля сохраняются.
    deposit = _deposit_or_error(request, request.POST.get("deposit_eur"))
    resource.require_manual_confirm = bool(request.POST.get("require_manual_confirm"))
    resource.counts_party_size = bool(request.POST.get("counts_party_size"))
    fields = ["require_manual_confirm", "counts_party_size", "updated_at"]
    if deposit is not None:
        resource.deposit_cents = deposit
        fields.append("deposit_cents")
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
    if deposit is not None:
        messages.success(request, _("Deposit settings saved."))
    else:
        messages.info(request, _("Die übrigen Änderungen sind gespeichert."))
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


# --- UX-D D3.1: страница ресурса ----------------------------------------------------
#
# Вкладки рисует сервер (`?tab=`, белый список); «tisch» есть только у стола, «profil» —
# только у мастера. Всё редактируемое о ресурсе — ОДНА форма `resource_update` (инвариант
# W0: старые `resource_settings`/`resource_profile` писали поля безусловно, форма по
# вкладке обнулила бы соседние поля). Сначала проверка всего, потом одна запись.
# Мини-формы страницы (правила часов, комбинация, вкл/выкл) — прежние действия модуля.

PAGE_ACTIONS = frozenset(
    {"resource_update", "rule", "rules_from_hours", "rule_delete", "toggle", "resource_parts"}
)


def tabs_for(resource) -> tuple[str, ...]:
    """Вкладки ресурса по типу (у не-стола нет «tisch», у не-мастера — «profil»)."""
    return tuple(
        t
        for t in RESOURCE_TABS
        if (t != "tisch" or resource.type == Resource.TYPE_TABLE)
        and (t != "profil" or resource.type == Resource.TYPE_STAFF)
    )


def page_url(resource, tab: str | None = None) -> str:
    from django.urls import reverse

    url = reverse("booking:resource-edit", args=[resource.pk])
    if tab in tabs_for(resource) and tab != RESOURCE_TABS[0]:
        url += f"?tab={tab}"
    return url


class _Invalid(Exception):
    def __init__(self, tab: str, message: str):
        super().__init__(message)
        self.tab = tab
        self.message = message


def _update(request, resource):
    """Сохранить единую форму страницы ресурса: всё или ничего (под блокировкой строки)."""
    from apps.booking import occupancy
    from apps.core.permissions import has_perm

    from . import views

    post = request.POST
    tenant = getattr(request, "tenant", None)
    with transaction.atomic():
        resource = Resource.objects.select_for_update().get(pk=resource.pk)
        fields = ["updated_at"]
        if post.get("basis_present"):
            name = (post.get("name") or "").strip()[:120]
            if not name:
                raise _Invalid("basis", _("Bitte einen Namen angeben."))
            resource.name = name
            resource.sort_order = views._bounded_int(
                post.get("sort_order"), resource.sort_order, 0, 999
            )
            fields += ["name", "sort_order"]
        if post.get("buchung_present"):
            resource.capacity = views._bounded_int(post.get("capacity"), resource.capacity, 1, 100)
            resource.counts_party_size = bool(post.get("counts_party_size"))
            resource.bookable_online = bool(post.get("bookable_online"))
            fields += ["capacity", "counts_party_size", "bookable_online"]
            # Решение D3: предоплата и ручная проверка — по праву цен (как у услуги, D2).
            if has_perm(request.user, "preise.edit"):
                cents = views._deposit_cents_or_none(post.get("deposit_eur"))
                if cents is None:
                    raise _Invalid("buchung", _("Bitte einen Betrag wie 25,00 angeben."))
                resource.deposit_cents = cents
                resource.require_manual_confirm = bool(post.get("require_manual_confirm"))
                fields += ["deposit_cents", "require_manual_confirm"]
        if post.get("tisch_present") and resource.type == Resource.TYPE_TABLE:
            resource.seats = views._seats_or_none(post.get("seats"), resource.seats)
            resource.zone = (post.get("zone") or "").strip()[:40]
            fields += ["seats", "zone"]
        if post.get("buchung_present") and resource.type == Resource.TYPE_TABLE:
            # GA-4: «ab N Personen» онлайн; не больше мест (иначе стол пропал бы из подбора).
            resource.min_seats = min(
                views._bounded_int(post.get("min_seats"), resource.min_seats, 1, 99),
                resource.seats or 99,
            )
            fields.append("min_seats")
        if post.get("profil_present") and resource.type == Resource.TYPE_STAFF:
            resource.title = (post.get("title") or "").strip()[:120]
            resource.bio = (post.get("bio") or "").strip()[:2000]
            fields += ["title", "bio"]
            new_photo = views._uploaded_image_ref(request, "photo", "staff")
            if new_photo or post.get("remove_photo"):
                resource.photo = new_photo or {}
                fields.append("photo")
        # GA-5: стол в комбинации обязан остаться «1 бронь = 1 стол».
        if (
            resource.parts.exists() or resource.combinations.exists()
        ) and not occupancy._combinable(resource):
            raise _Invalid(
                "buchung",
                _(
                    "Dieser Tisch gehört zu einer Kombination: Kapazität 1 und "
                    "kein Platz-Pool sind nötig. Bitte zuerst die Kombination auflösen."
                ),
            )
        i18n_fields = (
            ("name", "title", "bio") if resource.type == Resource.TYPE_STAFF else ("name",)
        )
        fields += apply_i18n_overlay(resource, post, tenant, i18n_fields)
        resource.save(update_fields=list(dict.fromkeys(fields)))
    messages.success(request, _("Saved."))


@login_required
def resource_edit(request, pk):
    """UX-D D3.1: страница ресурса — шапка со сводкой и вкладки."""
    from django.shortcuts import render

    from apps.core.i18n_input import i18n_inputs_for
    from apps.core.permissions import has_perm

    from . import hours_summary, views
    from .models import Service

    resource = get_object_or_404(Resource.objects.prefetch_related("rules", "parts"), pk=pk)
    tabs = tabs_for(resource)
    if request.method == "POST":
        action = request.POST.get("action", "")
        tab = request.POST.get("tab")
        # Страница правит только СВОЙ ресурс: чужой pk в POST — 404, не тихая правка.
        if action not in PAGE_ACTIONS or request.POST.get("resource") != str(resource.pk):
            raise Http404
        if action == "resource_update":
            try:
                _update(request, resource)
            except _Invalid as exc:
                messages.error(request, exc.message)
                tab = exc.tab
        else:
            response = dispatch(request, action)
            if response is not None:  # отказ комбинации и т.п. — обратно на свою вкладку
                tab = ACTION_TAB.get(action)
        if tab not in tabs:
            tab = ACTION_TAB.get(action)
        return redirect(page_url(resource, tab))

    tab = request.GET.get("tab")
    rule_groups = hours_summary.rule_groups(resource.rules.all())
    single_tables = []
    if resource.type == Resource.TYPE_TABLE:
        single_tables = [
            t
            for t in Resource.objects.filter(
                is_active=True,
                type=Resource.TYPE_TABLE,
                counts_party_size=False,
                capacity=1,
                parts__isnull=True,
            ).order_by("sort_order", "name")
            if t.pk != resource.pk
        ]
    tenant = getattr(request, "tenant", None)
    return render(
        request,
        "booking/resource_page.html",
        {
            "nav": "booking-resources",
            "r": resource,
            "tabs": tabs,
            "active_tab": tab if tab in tabs else tabs[0],
            "rule_groups": rule_groups,
            "hours_summary": hours_summary.summary(rule_groups),
            "business_hours": views._business_hours_of(tenant),
            "weekdays": AvailabilityRule.WEEKDAYS,
            "single_tables": single_tables,
            "part_ids": {p.pk for p in resource.parts.all()},
            "offered": Service.objects.filter(resources=resource).order_by("name")
            if resource.type == Resource.TYPE_STAFF
            else [],
            "i18n_inputs": i18n_inputs_for(
                resource,
                tenant,
                ("name", "title", "bio") if resource.type == Resource.TYPE_STAFF else ("name",),
            ),
            "can_edit_prices": has_perm(request.user, "preise.edit"),
        },
    )
