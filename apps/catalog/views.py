"""CRUD товаров в кабинете арендатора (HTMX).

Список с live-search и фильтрами; create/edit/delete. Все вьюхи требуют логина
владельца (логин на субдомене своей схемы).
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProductForm
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
        form.save()
        return redirect("catalog:product-list")
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
        form.save()
        return redirect("catalog:product-list")
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
