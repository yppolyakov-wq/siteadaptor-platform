"""UB3-2: кабинет «Kollektionen» — CRUD подборок + привязка услуг/номеров.

Одна страница в стиле `booking.services_view` (простые POST-формы, без JS):
создание по имени (slug генерируется автоматически), переименование/порядок,
вкл/выкл, удаление и чекбоксы состава — услуги (при активном booking) и номера
(при активном stays) прямо в карточке подборки. Presence-guard: состав пишется
только если соответствующий список пришёл в POST — частичная форма не очищает
связи другого kind.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.utils.translation import gettext as _

from .models import Collection


def _unique_slug(name: str) -> str:
    """Слаг фасета из имени подборки; при коллизии — числовой суффикс
    («damen», «damen-2», …). Слаг стабилен после создания (не переписывается
    при переименовании — ссылки/фасет ?kollektion= не ломаются)."""
    base = slugify(name)[:130] or "kollektion"
    slug, n = base, 2
    while Collection.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


@login_required
def collections_view(request):
    """Страница управления подборками. Доступна, когда активен booking ИЛИ stays
    (подборки группируют именно услуги/номера); иначе 404."""
    tenant = getattr(request, "tenant", None)
    has_booking = bool(tenant and tenant.is_module_active("booking"))
    has_stays = bool(tenant and tenant.is_module_active("stays"))
    if not (has_booking or has_stays):
        raise Http404

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create":
            name = request.POST.get("name", "").strip()
            if name:
                Collection.objects.create(name=name, slug=_unique_slug(name))
                messages.success(request, _("Collection created."))
        elif action == "update":
            collection = get_object_or_404(Collection, pk=request.POST.get("collection"))
            name = request.POST.get("name", "").strip()
            if name:
                collection.name = name
            try:
                collection.sort_order = max(0, min(int(request.POST.get("sort_order", "0")), 999))
            except (TypeError, ValueError):
                pass
            collection.save(update_fields=["name", "sort_order", "updated_at"])
            # Состав подборки: перезаписываем только присланные kind'ы (presence-guard).
            if has_booking and request.POST.get("services_present"):
                from apps.booking.models import Service

                collection.services.set(
                    Service.objects.filter(pk__in=request.POST.getlist("services"))
                )
            if has_stays and request.POST.get("units_present"):
                from apps.stays.models import StayUnit

                collection.stay_units.set(
                    StayUnit.objects.filter(pk__in=request.POST.getlist("units"))
                )
            messages.success(request, _("Collection saved."))
        elif action == "toggle":
            collection = get_object_or_404(Collection, pk=request.POST.get("collection"))
            collection.is_active = not collection.is_active
            collection.save(update_fields=["is_active", "updated_at"])
        elif action == "delete":
            get_object_or_404(Collection, pk=request.POST.get("collection")).delete()
            messages.success(request, _("Collection deleted."))
        return redirect("collections:list")

    # GET: подборки + пары (сущность, входит?) для чекбоксов состава.
    services, units = [], []
    if has_booking:
        from apps.booking.models import Service

        services = list(Service.objects.filter(is_active=True))
    if has_stays:
        from apps.stays.models import StayUnit

        units = list(StayUnit.objects.filter(is_active=True))
    collections = list(Collection.objects.all())
    for collection in collections:
        svc_ids = set(collection.services.values_list("pk", flat=True))
        unit_ids = set(collection.stay_units.values_list("pk", flat=True))
        collection.svc_rows = [(s, s.pk in svc_ids) for s in services]
        collection.unit_rows = [(u, u.pk in unit_ids) for u in units]
    return render(
        request,
        "collections/list.html",
        {
            "nav": "collections",
            "collections": collections,
            "has_booking": has_booking,
            "has_stays": has_stays,
            "has_entities": bool(services or units),
        },
    )
