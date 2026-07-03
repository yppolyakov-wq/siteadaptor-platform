"""CRUD товаров в кабинете арендатора (HTMX).

Список с live-search и фильтрами; create/edit/delete; загрузка/удаление картинок.
Все вьюхи требуют логина владельца (логин на субдомене своей схемы).
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.i18n_input import apply_i18n_overlay, extra_locales, i18n_inputs_for

from .forms import CategoryForm, ProductForm
from .images import delete_stored_image, save_product_image
from .models import (
    Category,
    Combo,
    ComboGroup,
    ComboOption,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductVariant,
)


def _parse_price(raw):
    """«4,90» / «4.90» / пусто → Decimal или None (пусто/мусор/отрицательное)."""
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return value if value >= 0 else None


def _parse_int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _filtered_products(request):
    qs = Product.objects.select_related("category").all()
    q = (request.GET.get("q") or "").strip()
    if q:
        # Поиск по i18n-name (по ключам JSONField — icontains по jsonb не
        # поддерживается Postgres напрямую) и по sku.
        qs = qs.filter(Q(name__de__icontains=q) | Q(name__en__icontains=q) | Q(sku__icontains=q))
    category = request.GET.get("category")
    if category:
        qs = qs.filter(category_id=category)
    active = request.GET.get("active")
    if active == "1":
        qs = qs.filter(is_active=True)
    elif active == "0":
        qs = qs.filter(is_active=False)
    return qs


def _handle_uploads(request, product) -> None:
    """Сохраняет загруженные файлы в product.images (FileRef-envelope)."""
    files = request.FILES.getlist("images")
    if not files:
        return
    images = list(product.images or [])
    has_primary = any(img.get("is_primary") for img in images)
    for f in files:
        try:
            ref = save_product_image(f, is_primary=not has_primary, sort_order=len(images))
        except ValidationError as exc:
            messages.error(request, f"{f.name}: {'; '.join(exc.messages)}")
            continue
        has_primary = True
        images.append(ref)
    product.images = images
    product.save(update_fields=["images", "updated_at"])


@login_required
def product_list(request):
    products = _filtered_products(request)
    ctx = {
        "nav": "catalog",
        "products": products,
        "categories": Category.objects.all(),
        "q": request.GET.get("q", ""),
        "selected_category": request.GET.get("category", ""),
        "active": request.GET.get("active", ""),
    }
    # HTMX-запрос → только таблица (live-search без перезагрузки)
    if request.headers.get("HX-Request"):
        return render(request, "catalog/_product_rows.html", ctx)
    return render(request, "catalog/product_list.html", ctx)


@login_required
def product_create(request):
    form = ProductForm(request.POST or None, tenant=getattr(request, "tenant", None))
    if request.method == "POST" and form.is_valid():
        product = form.save()
        _handle_uploads(request, product)
        return redirect("catalog:product-edit", pk=product.pk)
    return render(
        request,
        "catalog/product_form.html",
        {"form": form, "is_create": True, "nav": "catalog"},
    )


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(
        request.POST or None, instance=product, tenant=getattr(request, "tenant", None)
    )
    if request.method == "POST" and form.is_valid():
        product = form.save()
        _handle_uploads(request, product)
        return redirect("catalog:product-edit", pk=product.pk)
    return render(
        request,
        "catalog/product_form.html",
        {
            "form": form,
            "is_create": False,
            "product": product,
            "variants": product.variants.all(),
            "modifier_groups": product.modifier_groups.prefetch_related("options"),
            "nav": "catalog",
        },
    )


# ---------------------------------------------------------------------------
# Варианты товара (R1): чай 100/250 г, размеры — CRUD на странице товара
# ---------------------------------------------------------------------------


@login_required
@require_POST
def variant_add(request, pk):
    product = get_object_or_404(Product, pk=pk)
    label = (request.POST.get("label") or "").strip()
    if not label:
        messages.error(request, _("Variant label is required."))
    elif ProductVariant.objects.filter(product=product, label=label).exists():
        messages.error(request, _("A variant with this label already exists."))
    else:
        ProductVariant.objects.create(
            product=product,
            label=label,
            sku=(request.POST.get("sku") or "").strip(),
            gtin=(request.POST.get("gtin") or "").strip(),
            price=_parse_price(request.POST.get("price")),
            content_amount=_parse_price(request.POST.get("content")),
            stock_quantity=_parse_int(request.POST.get("stock")),
            sort_order=_parse_int(request.POST.get("sort")) or 0,
        )
        messages.success(request, _("Variant added."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def variant_update(request, pk, vid):
    variant = get_object_or_404(ProductVariant, pk=vid, product_id=pk)
    variant.price = _parse_price(request.POST.get("price"))
    variant.content_amount = _parse_price(request.POST.get("content"))
    variant.stock_quantity = _parse_int(request.POST.get("stock"))
    variant.sort_order = _parse_int(request.POST.get("sort")) or 0
    variant.gtin = (request.POST.get("gtin") or "").strip()
    variant.is_active = bool(request.POST.get("is_active"))
    variant.save(
        update_fields=[
            "price",
            "content_amount",
            "stock_quantity",
            "sort_order",
            "gtin",
            "is_active",
            "updated_at",
        ]
    )
    messages.success(request, _("Variant updated."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def variant_delete(request, pk, vid):
    get_object_or_404(ProductVariant, pk=vid, product_id=pk).delete()
    messages.success(request, _("Variant removed."))
    return redirect("catalog:product-edit", pk=pk)


# ---------------------------------------------------------------------------
# Модификаторы / Extras блюда (A4 Gastro): группы + опции — CRUD на товаре
# ---------------------------------------------------------------------------


@login_required
@require_POST
def modifier_group_add(request, pk):
    product = get_object_or_404(Product, pk=pk)
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, _("Group name is required."))
    else:
        ModifierGroup.objects.create(
            product=product,
            name=name,
            min_select=_parse_int(request.POST.get("min")) or 0,
            max_select=_parse_int(request.POST.get("max")) or 0,
            sort_order=_parse_int(request.POST.get("sort")) or 0,
        )
        messages.success(request, _("Modifier group added."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_group_update(request, pk, gid):
    group = get_object_or_404(ModifierGroup, pk=gid, product_id=pk)
    group.name = (request.POST.get("name") or group.name).strip()
    group.min_select = _parse_int(request.POST.get("min")) or 0
    group.max_select = _parse_int(request.POST.get("max")) or 0
    group.sort_order = _parse_int(request.POST.get("sort")) or 0
    group.is_active = bool(request.POST.get("is_active"))
    group.save(
        update_fields=["name", "min_select", "max_select", "sort_order", "is_active", "updated_at"]
    )
    messages.success(request, _("Modifier group updated."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_group_delete(request, pk, gid):
    get_object_or_404(ModifierGroup, pk=gid, product_id=pk).delete()
    messages.success(request, _("Modifier group removed."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_option_add(request, pk, gid):
    group = get_object_or_404(ModifierGroup, pk=gid, product_id=pk)
    label = (request.POST.get("label") or "").strip()
    if not label:
        messages.error(request, _("Option label is required."))
    else:
        ModifierOption.objects.create(
            group=group,
            label=label,
            price_delta=_parse_price(request.POST.get("delta")) or Decimal("0"),
            sort_order=_parse_int(request.POST.get("sort")) or 0,
        )
        messages.success(request, _("Option added."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_option_update(request, pk, gid, oid):
    option = get_object_or_404(ModifierOption, pk=oid, group_id=gid, group__product_id=pk)
    option.label = (request.POST.get("label") or option.label).strip()
    option.price_delta = _parse_price(request.POST.get("delta")) or Decimal("0")
    option.sort_order = _parse_int(request.POST.get("sort")) or 0
    option.is_active = bool(request.POST.get("is_active"))
    option.save(update_fields=["label", "price_delta", "sort_order", "is_active", "updated_at"])
    messages.success(request, _("Option updated."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
@require_POST
def modifier_option_delete(request, pk, gid, oid):
    get_object_or_404(ModifierOption, pk=oid, group_id=gid, group__product_id=pk).delete()
    messages.success(request, _("Option removed."))
    return redirect("catalog:product-edit", pk=pk)


@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()  # soft-delete
        return redirect("catalog:product-list")
    return render(
        request,
        "catalog/product_confirm_delete.html",
        {"product": product, "nav": "catalog"},
    )


@login_required
def product_image_delete(request, pk, image_id):
    """Удаляет одну картинку товара (из списка и из storage)."""
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        images = list(product.images or [])
        kept, removed_primary = [], False
        for img in images:
            if img.get("id") == image_id:
                delete_stored_image(img)
                removed_primary = img.get("is_primary", False)
            else:
                kept.append(img)
        # если удалили главную — назначаем главной первую оставшуюся
        if removed_primary and kept:
            kept[0]["is_primary"] = True
        product.images = kept
        product.save(update_fields=["images", "updated_at"])
    return redirect("catalog:product-edit", pk=pk)


@login_required
def product_image_primary(request, pk, image_id):
    """Делает выбранную картинку главной."""
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        images = list(product.images or [])
        for img in images:
            img["is_primary"] = img.get("id") == image_id
        product.images = images
        product.save(update_fields=["images", "updated_at"])
    return redirect("catalog:product-edit", pk=pk)


# ---------------------------------------------------------------------------
# Категории (CRUD + иерархия)
# ---------------------------------------------------------------------------


def _category_tree() -> list:
    """Плоский список живых категорий в порядке дерева.

    Каждой записи проставляем .level (глубина) и .product_count. Категории,
    чей родитель удалён/отсутствует, показываем как корневые (не теряем их).
    """
    cats = list(Category.objects.all())
    alive_ids = {c.pk for c in cats}
    children_map: dict = {}
    for c in cats:
        key = c.parent_id if c.parent_id in alive_ids else None
        children_map.setdefault(key, []).append(c)

    counts = dict(
        Product.objects.values("category_id")
        .annotate(n=Count("id"))
        .values_list("category_id", "n")
    )

    rows: list = []

    def walk(parent_key, level):
        for c in sorted(children_map.get(parent_key, []), key=lambda x: (x.sort_order, x.slug)):
            c.level = level
            c.product_count = counts.get(c.pk, 0)
            rows.append(c)
            walk(c.pk, level + 1)

    walk(None, 0)
    return rows


def _descendants(category) -> list:
    """Все живые потомки категории (без неё самой)."""
    result: list = []
    stack = list(Category.objects.filter(parent=category))
    while stack:
        node = stack.pop()
        result.append(node)
        stack.extend(Category.objects.filter(parent=node))
    return result


@login_required
def category_list(request):
    return render(
        request,
        "catalog/category_list.html",
        {"nav": "categories", "categories": _category_tree()},
    )


@login_required
def category_create(request):
    form = CategoryForm(request.POST or None, tenant=getattr(request, "tenant", None))
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("catalog:category-list")
    return render(
        request,
        "catalog/category_form.html",
        {"form": form, "is_create": True, "nav": "categories"},
    )


@login_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(
        request.POST or None, instance=category, tenant=getattr(request, "tenant", None)
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("catalog:category-list")
    return render(
        request,
        "catalog/category_form.html",
        {"form": form, "is_create": False, "category": category, "nav": "categories"},
    )


@login_required
@require_POST
def category_inline_edit(request):
    """SE-2c-3: инлайн-правка имени категории прямо на канве витрины (?preview=1).

    JSON {category_pk, value} → пишет Category.name['de'] живой категории (AliveManager
    исключает удалённые). Только владелец (login_required на субдомене схемы). 204/400.
    """
    import json

    from django.http import HttpResponse, HttpResponseBadRequest

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return HttpResponseBadRequest()
    pk = data.get("category_pk")
    value = data.get("value", "")
    value = value.strip() if isinstance(value, str) else ""
    if not pk or not value:
        return HttpResponseBadRequest()
    try:
        category = Category.objects.get(pk=pk)
    except (Category.DoesNotExist, ValidationError, ValueError):
        return HttpResponseBadRequest()
    name = dict(category.name or {})
    name["de"] = value
    category.name = name
    category.save(update_fields=["name", "updated_at"])
    return HttpResponse(status=204)


@login_required
@require_POST
def product_inline_edit(request):
    """Инлайн-правка товара на канве — тонкий алиас единого диспетчера (UC2-4).

    Контракт/URL прежние: JSON {pk, field, value}; вайтлист/семантика полей —
    декларация INLINE_REGISTRY["product"] (apps/core/inline_edit.py):
    name/description → i18n['de'] (имя пустым не сохраняем), base_price —
    Decimal, только без вариантов; bump кэша — только на цене (как раньше)."""
    from apps.core.inline_edit import dispatch

    return dispatch(request, "product")


@login_required
@require_POST
def product_photo_edit(request):
    """M4 / пер-слайд: править галерею товара прямо на канве витрины (multipart).

    POST: pk, op ∈ {replace, add, remove}, image_id (для replace/remove), image
    (файл для replace/add). replace заменяет КОНКРЕТНЫЙ слайд по id в месте (одиночное
    фото → честная замена без дубля); add — добавляет; remove — удаляет. Реюз
    catalog.images.apply_gallery_op (валидация Pillow + storage + корректный primary).
    Сброс кэша витрины. Только владелец (login_required). 204/400.
    """
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.http import HttpResponse, HttpResponseBadRequest

    from apps.catalog.images import apply_gallery_op

    pk = request.POST.get("pk")
    op = request.POST.get("op", "replace")
    image_id = request.POST.get("image_id", "")
    uploaded = request.FILES.get("image")
    if not pk:
        return HttpResponseBadRequest()
    try:
        # Блокируем строку на время read-modify-write JSON-поля images — иначе две
        # параллельные правки (add+remove) затрут изменения друг друга (lost update).
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=pk)
            product.images = apply_gallery_op(
                product.images, op=op, image_id=image_id, uploaded=uploaded, folder="products"
            )
            product.save(update_fields=["images", "updated_at"])
    except (Product.DoesNotExist, ValueError):
        return HttpResponseBadRequest()
    except ValidationError as exc:
        return HttpResponseBadRequest("; ".join(exc.messages))
    schema = getattr(getattr(request, "tenant", None), "schema_name", None)
    if schema:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(schema)
    return HttpResponse(status=204)


@login_required
def category_delete(request, pk):
    """Удаление категории (soft).

    Если есть подкатегории или товары — даём выбрать стратегию:
    reparent (перевесить детей на родителя, товары отвязать), cascade
    (удалить ветку целиком, товары отвязать) или cancel.
    """
    category = get_object_or_404(Category, pk=pk)
    children = list(Category.objects.filter(parent=category))
    product_count = Product.objects.filter(category=category).count()
    descendants = _descendants(category)
    branch = [category, *descendants]
    descendant_product_count = Product.objects.filter(category__in=branch).count()
    has_dependencies = bool(children) or product_count > 0

    if request.method == "POST":
        strategy = request.POST.get("strategy", "")

        if not has_dependencies:
            category.delete()
            messages.success(request, _("Category deleted."))
            return redirect("catalog:category-list")

        if strategy == "reparent":
            Category.objects.filter(parent=category).update(parent=category.parent)
            Product.objects.filter(category=category).update(category=None)
            category.delete()
            messages.success(
                request, _("Category deleted; subcategories moved up and products detached.")
            )
            return redirect("catalog:category-list")

        if strategy == "cascade":
            Product.objects.filter(category__in=branch).update(category=None)
            Category.objects.filter(pk__in=[c.pk for c in branch]).delete()  # bulk soft-delete
            messages.success(request, _("Category and its subcategories deleted."))
            return redirect("catalog:category-list")

        # cancel / неизвестная стратегия — ничего не делаем
        return redirect("catalog:category-list")

    return render(
        request,
        "catalog/category_confirm_delete.html",
        {
            "category": category,
            "children": children,
            "product_count": product_count,
            "descendant_count": len(descendants),
            "descendant_product_count": descendant_product_count,
            "has_dependencies": has_dependencies,
            "nav": "categories",
        },
    )


# --- Combo-наборы (A4 Gastro): кабинет CRUD ----------------------------------------


@login_required
def combo_list(request):
    combos = Combo.objects.prefetch_related("groups__options").order_by("sort_order", "created_at")
    return render(request, "catalog/combo_list.html", {"combos": combos, "nav": "combos"})


@login_required
def combo_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        price = _parse_price(request.POST.get("price"))
        if not name or price is None:
            messages.error(request, _("Name and price are required."))
        else:
            combo = Combo(
                name=name,
                description=(request.POST.get("description") or "").strip(),
                price=price,
                sort_order=_parse_int(request.POST.get("sort")) or 0,
                is_active=bool(request.POST.get("is_active")),
            )
            apply_i18n_overlay(combo, request.POST, getattr(request, "tenant", None))  # L3d
            combo.save()
            return redirect("catalog:combo-edit", pk=combo.pk)
    return render(
        request,
        "catalog/combo_form.html",
        {
            "combo": None,
            "nav": "combos",
            "extra_locales": extra_locales(getattr(request, "tenant", None)),
        },
    )


@login_required
def combo_edit(request, pk):
    combo = get_object_or_404(Combo.objects.prefetch_related("groups__options"), pk=pk)
    if request.method == "POST":
        combo.name = (request.POST.get("name") or combo.name).strip()
        price = _parse_price(request.POST.get("price"))
        if price is not None:
            combo.price = price
        combo.description = (request.POST.get("description") or "").strip()
        combo.sort_order = _parse_int(request.POST.get("sort")) or 0
        combo.is_active = bool(request.POST.get("is_active"))
        _uf = ["name", "price", "description", "sort_order", "is_active", "updated_at"]
        _uf += apply_i18n_overlay(combo, request.POST, getattr(request, "tenant", None))  # L3d
        combo.save(update_fields=_uf)
        messages.success(request, _("Saved."))
        return redirect("catalog:combo-edit", pk=pk)
    products = Product.objects.filter(is_active=True).order_by("name")
    combo.i18n_inputs = i18n_inputs_for(combo, getattr(request, "tenant", None))  # L3d
    return render(
        request,
        "catalog/combo_form.html",
        {
            "combo": combo,
            "products": products,
            "nav": "combos",
            "extra_locales": extra_locales(getattr(request, "tenant", None)),
        },
    )


@login_required
def combo_delete(request, pk):
    combo = get_object_or_404(Combo, pk=pk)
    if request.method == "POST":
        combo.delete()  # soft-delete
        return redirect("catalog:combo-list")
    return render(request, "catalog/combo_confirm_delete.html", {"combo": combo, "nav": "combos"})


@login_required
@require_POST
def combo_group_add(request, pk):
    combo = get_object_or_404(Combo, pk=pk)
    label = (request.POST.get("label") or "").strip()
    if not label:
        messages.error(request, _("Group name is required."))
    else:
        ComboGroup.objects.create(
            combo=combo,
            label=label,
            min_select=_parse_int(request.POST.get("min")) or 0,
            max_select=_parse_int(request.POST.get("max")) or 0,
            sort_order=_parse_int(request.POST.get("sort")) or 0,
        )
        messages.success(request, _("Group added."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_group_update(request, pk, gid):
    group = get_object_or_404(ComboGroup, pk=gid, combo_id=pk)
    group.label = (request.POST.get("label") or group.label).strip()
    group.min_select = _parse_int(request.POST.get("min")) or 0
    group.max_select = _parse_int(request.POST.get("max")) or 0
    group.sort_order = _parse_int(request.POST.get("sort")) or 0
    group.is_active = bool(request.POST.get("is_active"))
    group.save(
        update_fields=["label", "min_select", "max_select", "sort_order", "is_active", "updated_at"]
    )
    messages.success(request, _("Group updated."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_group_delete(request, pk, gid):
    get_object_or_404(ComboGroup, pk=gid, combo_id=pk).delete()
    messages.success(request, _("Group removed."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_option_add(request, pk, gid):
    group = get_object_or_404(ComboGroup, pk=gid, combo_id=pk)
    product = Product.objects.filter(pk=request.POST.get("product"), is_active=True).first()
    if product is None:
        messages.error(request, _("Please choose a product."))
    else:
        ComboOption.objects.create(
            group=group,
            product=product,
            price_delta=_parse_price(request.POST.get("delta")) or Decimal("0"),
            sort_order=_parse_int(request.POST.get("sort")) or 0,
        )
        messages.success(request, _("Option added."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_option_update(request, pk, gid, oid):
    option = get_object_or_404(ComboOption, pk=oid, group_id=gid, group__combo_id=pk)
    option.price_delta = _parse_price(request.POST.get("delta")) or Decimal("0")
    option.sort_order = _parse_int(request.POST.get("sort")) or 0
    option.is_active = bool(request.POST.get("is_active"))
    option.save(update_fields=["price_delta", "sort_order", "is_active", "updated_at"])
    messages.success(request, _("Option updated."))
    return redirect("catalog:combo-edit", pk=pk)


@login_required
@require_POST
def combo_option_delete(request, pk, gid, oid):
    get_object_or_404(ComboOption, pk=oid, group_id=gid, group__combo_id=pk).delete()
    messages.success(request, _("Option removed."))
    return redirect("catalog:combo-edit", pk=pk)
