"""Витрина Click & Collect (Track D / D2a): корзина-сессия + оформление самовывоза.

Корзина — dict {product_id: qty} в сессии (без аккаунта, как бронь акций).
Защита формы — как у брони: honeypot (website) + rate-limit по IP
(apps.core.ratelimit). Если модуль orders у бизнеса выключен — всех страниц
просто нет (404), кнопка на витрине тоже скрыта.
"""

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import ratelimit

from .models import Order
from .services import EmptyOrder, create_order

CART_SESSION_KEY = "cart"
RL_LIMIT = 5  # оформлений на IP
RL_WINDOW = 600  # за 10 минут
MAX_QTY = 50  # на позицию — защита от мусора


def _require_orders_active(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("orders"):
        raise Http404


def _cart(request) -> dict:
    cart = request.session.get(CART_SESSION_KEY)
    return cart if isinstance(cart, dict) else {}


def _cart_items(request):
    """[(product, qty), …] по корзине; исчезнувшие/неактивные товары отбрасываем."""
    from apps.catalog.models import Product

    cart = _cart(request)
    products = {str(p.pk): p for p in Product.objects.filter(pk__in=cart.keys(), is_active=True)}
    return [(products[pid], qty) for pid, qty in cart.items() if pid in products]


@require_POST
def cart_add(request):
    _require_orders_active(request)
    from apps.catalog.models import Product

    product = get_object_or_404(Product, pk=request.POST.get("product"), is_active=True)
    try:
        qty = max(1, min(int(request.POST.get("qty", "1")), MAX_QTY))
    except (TypeError, ValueError):
        qty = 1
    cart = _cart(request)
    cart[str(product.pk)] = min(cart.get(str(product.pk), 0) + qty, MAX_QTY)
    request.session[CART_SESSION_KEY] = cart
    messages.success(request, _("Added to your order."))
    return redirect("storefront-cart")


@require_POST
def cart_remove(request):
    _require_orders_active(request)
    cart = _cart(request)
    cart.pop(str(request.POST.get("product", "")), None)
    request.session[CART_SESSION_KEY] = cart
    return redirect("storefront-cart")


def cart_view(request):
    _require_orders_active(request)
    items = _cart_items(request)
    total = sum((product.base_price * qty for product, qty in items), start=0)
    return render(
        request,
        "storefront/cart.html",
        {"items": items, "total": total, "currency": items[0][0].currency if items else "EUR"},
    )


@require_POST
def checkout(request):
    _require_orders_active(request)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-cart")
    # hit() == True → лимит превышен (см. apps.core.ratelimit)
    if ratelimit.hit("order", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Please tell us your name."))
        return redirect("storefront-cart")
    try:
        order = create_order(
            items=_cart_items(request),
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            note=request.POST.get("note", "").strip()[:2000],
            source_channel=(request.GET.get("ch") or "")[:50],
        )
    except EmptyOrder:
        messages.error(request, _("Your order is empty."))
        return redirect("storefront-cart")
    request.session[CART_SESSION_KEY] = {}
    return redirect("storefront-order", code=order.reference_code)


def order_confirmation(request, code):
    _require_orders_active(request)
    order = get_object_or_404(Order, reference_code=code)
    return render(request, "storefront/order_confirmation.html", {"order": order})
