"""Кабинет заказов Click & Collect (Track D / D2b): /dashboard/orders/.

Список входящих с фильтром по статусу, карточка заказа, действия по FSM
(confirm/ready/picked_up/cancel — каждое шлёт письмо клиенту через OrderSM)
и ручная отметка оплаты (v1 — оплата в магазине). Гейтинг модуля «orders» —
ModuleGatingMiddleware по префиксу из реестра.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.fsm import IllegalTransition

from .models import Order
from .state_machine import OrderSM


@login_required
def order_list(request):
    qs = Order.objects.select_related("customer").prefetch_related("items")
    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)
    return render(
        request,
        "orders/order_list.html",
        {"orders": qs[:200], "statuses": Order.STATUSES, "status": status, "nav": "orders"},
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
            messages.success(request, _("Order updated."))
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
    else:
        messages.error(request, _("Unknown action."))
    return redirect("orders:order-detail", pk=order.pk)
