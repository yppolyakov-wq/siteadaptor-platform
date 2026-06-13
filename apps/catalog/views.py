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

from .forms import CategoryForm, ProductForm
from .images import delete_stored_image, save_product_image
from .models import Category, Product, ProductVariant


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
    form = ProductForm(request.POST or None)
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
    form = ProductForm(request.POST or None, instance=product)
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
    variant.is_active = bool(request.POST.get("is_active"))
    variant.save(
        update_fields=[
            "price",
            "content_amount",
            "stock_quantity",
            "sort_order",
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
    form = CategoryForm(request.POST or None)
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
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("catalog:category-list")
    return render(
        request,
        "catalog/category_form.html",
        {"form": form, "is_create": False, "category": category, "nav": "categories"},
    )


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
