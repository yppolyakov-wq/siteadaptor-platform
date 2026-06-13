"""Кабинет заказов Click & Collect (Track D / D2b): /dashboard/orders/.

Список входящих с фильтром по статусу, карточка заказа, действия по FSM
(confirm/ready/picked_up/cancel — каждое шлёт письмо клиенту через OrderSM)
и ручная отметка оплаты (v1 — оплата в магазине). Гейтинг модуля «orders» —
ModuleGatingMiddleware по префиксу из реестра.
"""

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.billing import connect
from apps.core.fsm import IllegalTransition

from .models import Order
from .state_machine import OrderSM


def _refund_order(request, order):
    """Анти-фрод: вернуть оплату при отмене оплаченного заказа (Stripe Connect)."""
    try:
        connect.refund(
            connect_id=request.tenant.stripe_connect_id,
            payment_intent=order.stripe_payment_intent,
        )
        order.payment_state = Order.PAYMENT_REFUNDED
        order.save(update_fields=["payment_state", "updated_at"])
        messages.success(request, _("Payment refunded."))
    except stripe.error.StripeError:
        messages.error(request, _("Refund failed — please check Stripe."))


@login_required
def order_list(request):
    qs = Order.objects.select_related("customer").prefetch_related("items")
    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)
    tenant = getattr(request, "tenant", None)
    return render(
        request,
        "orders/order_list.html",
        {
            "orders": qs[:200],
            "statuses": Order.STATUSES,
            "status": status,
            "orders_prepay": getattr(tenant, "orders_prepay", False),
            "payments_enabled": getattr(tenant, "payments_enabled", False),
            "nav": "orders",
        },
    )


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    sm = OrderSM()
    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "items": order.items.all(),
            "allowed_targets": sm.allowed_targets(order.status),
            "nav": "orders",
        },
    )


@login_required
@require_POST
def order_action(request, pk):
    order = get_object_or_404(Order, pk=pk)
    action = request.POST.get("action", "")
    if action == "mark_paid":
        order.payment_state = Order.PAYMENT_PAID
        order.save(update_fields=["payment_state", "updated_at"])
        messages.success(request, _("Marked as paid."))
    elif action in ("confirmed", "ready", "picked_up", "cancelled"):
        try:
            OrderSM().apply(order, action, actor=request.user)
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
            return redirect("orders:order-detail", pk=order.pk)
        messages.success(request, _("Order updated."))
        # анти-фрод: отмена оплаченного заказа возвращает оплату
        if (
            action == "cancelled"
            and order.payment_state == Order.PAYMENT_PAID
            and order.stripe_payment_intent
        ):
            _refund_order(request, order)
    else:
        messages.error(request, _("Unknown action."))
    return redirect("orders:order-detail", pk=order.pk)


@login_required
@require_POST
def order_settings(request):
    """Тумблер онлайн-предоплаты Click&Collect (P2.5c)."""
    request.tenant.orders_prepay = bool(request.POST.get("orders_prepay"))
    request.tenant.save(update_fields=["orders_prepay", "updated_at"])
    messages.success(request, _("Settings saved."))
    return redirect("orders:order-list")
