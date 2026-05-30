"""CRUD товаров в кабинете арендатора (HTMX).

Список с live-search и фильтрами; create/edit/delete; загрузка/удаление картинок.
Все вьюхи требуют логина владельца (логин на субдомене своей схемы).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProductForm
from .images import delete_stored_image, save_product_image
from .models import Category, Product


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
        {"form": form, "is_create": False, "product": product, "nav": "catalog"},
    )


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
