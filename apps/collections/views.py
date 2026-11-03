"""UB3-2: кабинет «Kollektionen» — CRUD подборок + привязка услуг/номеров.

Одна страница в стиле `booking.services_view` (простые POST-формы, без JS):
создание по имени (slug генерируется автоматически), переименование/порядок,
вкл/выкл, удаление и чекбоксы состава — услуги (при активном booking) и номера
(при активном stays) прямо в карточке подборки. Presence-guard: состав пишется
только если соответствующий список пришёл в POST — частичная форма не очищает
связи другого kind.
"""

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.utils.translation import gettext as _

from apps.core.i18n_input import apply_i18n_overlay, extra_locales

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


def _clean_pks(values) -> set:
    """Присланные pk → множество UUID-строк (мусор отбрасывается, не роняет запрос)."""
    out = set()
    for raw in values:
        try:
            out.add(str(uuid.UUID(str(raw))))
        except ValueError:
            continue
    return out


def _shown_queryset(model):
    """Что форма показывает для выбора состава (то же, что GET ниже)."""
    qs = model.objects.filter(is_active=True)
    if model._meta.model_name == "product":
        qs = qs.order_by("name")[:200]
    return qs


def _save_members(request, relation, field: str) -> None:
    """UX-D D6.0: новый состав = (отмеченные ∩ показанные) ∪ (текущие − показанные).

    Форма показывает не всё (неактивные товары, товары после 200-го) — раньше `.set()` из
    присланного молча стирал их членство. Отмеченное, но не показанное, тоже не берём:
    форма такого не рисовала."""
    model = relation.model
    shown = _clean_pks(request.POST.getlist(f"{field}_shown"))
    if not shown:
        # Старая вкладка (до D6.0) не присылает `*_shown` — считаем показанным то, что
        # рисует форма сейчас, иначе снятые галочки молча не сохранились бы.
        shown = {str(pk) for pk in _shown_queryset(model).values_list("pk", flat=True)}
    checked = _clean_pks(request.POST.getlist(field)) & shown
    current = {str(pk) for pk in relation.values_list("pk", flat=True)}
    keep = checked | (current - shown)
    relation.set(model.objects.filter(pk__in=keep))


@login_required
def collections_view(request):
    """Страница управления подборками. Доступна, когда активен booking ИЛИ stays
    (подборки группируют именно услуги/номера); иначе 404."""
    tenant = getattr(request, "tenant", None)
    has_booking = bool(tenant and tenant.is_module_active("booking"))
    has_stays = bool(tenant and tenant.is_module_active("stays"))
    # M4-B Lookbook: подборки теперь и для ТОВАРОВ (бутик: «Herbst-Looks»).
    # catalog — core-модуль, поэтому страница доступна всем; 404-гейт снят.
    has_catalog = bool(tenant and tenant.is_module_active("catalog"))
    if not (has_booking or has_stays or has_catalog):
        raise Http404

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create":
            name = request.POST.get("name", "").strip()
            if name:
                collection = Collection(name=name, slug=_unique_slug(name))
                # E9.10: переводы имени (выпадашка языка у заголовка страницы).
                apply_i18n_overlay(collection, request.POST, tenant, fields=("name",))
                collection.save()
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
            changed = apply_i18n_overlay(collection, request.POST, tenant, fields=("name",))
            collection.save(update_fields=["name", "sort_order", "updated_at", *changed])
            # Состав подборки: перезаписываем только присланные kind'ы (presence-guard).
            if has_booking and request.POST.get("services_present"):
                _save_members(request, collection.services, "services")
            if has_stays and request.POST.get("units_present"):
                _save_members(request, collection.stay_units, "units")
            if has_catalog and request.POST.get("products_present"):
                _save_members(request, collection.products, "products")
            messages.success(request, _("Collection saved."))
        elif action == "photo":  # M4-B: фото образа (лукбук) — добавить/удалить
            from apps.catalog.images import apply_gallery_op

            collection = get_object_or_404(Collection, pk=request.POST.get("collection"))
            try:
                collection.images = apply_gallery_op(
                    collection.images,
                    op="remove" if request.POST.get("remove") else "add",
                    image_id=request.POST.get("remove") or "",
                    uploaded=request.FILES.get("photo"),
                    folder="collections",
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                collection.save(update_fields=["images", "updated_at"])
                messages.success(request, _("Collection saved."))
        elif action == "toggle":
            collection = get_object_or_404(Collection, pk=request.POST.get("collection"))
            collection.is_active = not collection.is_active
            collection.save(update_fields=["is_active", "updated_at"])
        elif action == "delete":
            get_object_or_404(Collection, pk=request.POST.get("collection")).delete()
            messages.success(request, _("Collection deleted."))
        return redirect("collections:list")

    # GET: есть ли что группировать (подсказка внизу списка).
    has_entities = False
    if has_booking:
        from apps.booking.models import Service

        has_entities = has_entities or Service.objects.filter(is_active=True).exists()
    if has_stays:
        from apps.stays.models import StayUnit

        has_entities = has_entities or StayUnit.objects.filter(is_active=True).exists()
    if has_catalog:
        from apps.catalog.models import Product

        has_entities = has_entities or Product.objects.filter(is_active=True).exists()
    # UX-D D6.3: список — строки с количествами (один запрос), состав/фото/переводы — на
    # странице подборки (раньше 3 запроса и все чекбоксы на каждую подборку).
    from .pages import annotated

    collections = list(
        annotated(
            Collection.objects.all(),
            {"has_booking": has_booking, "has_stays": has_stays, "has_catalog": has_catalog},
        )
    )
    return render(
        request,
        "collections/list.html",
        {
            "nav": "collections",
            "collections": collections,
            "extra_locales": extra_locales(tenant),
            "has_booking": has_booking,
            "has_stays": has_stays,
            "has_catalog": has_catalog,
            "has_entities": has_entities,
        },
    )
