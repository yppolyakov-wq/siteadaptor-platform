"""Кабинет заказов Click & Collect (Track D / D2b): /dashboard/orders/.

Список входящих с фильтром по статусу, карточка заказа, действия по FSM
(confirm/ready/picked_up/cancel — каждое шлёт письмо клиенту через OrderSM)
и ручная отметка оплаты (v1 — оплата в магазине). Гейтинг модуля «orders» —
ModuleGatingMiddleware по префиксу из реестра.
"""

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
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
            "delivery_enabled": getattr(tenant, "delivery_enabled", False),
            "delivery_fee_eur": f"{getattr(tenant, 'delivery_fee_cents', 0) / 100:.2f}",
            "delivery_free_eur": f"{getattr(tenant, 'delivery_free_cents', 0) / 100:.2f}",
            "delivery_min_eur": f"{getattr(tenant, 'delivery_min_cents', 0) / 100:.2f}",
            "delivery_area": getattr(tenant, "delivery_area", ""),
            "pickup_min_eur": f"{getattr(tenant, 'pickup_min_cents', 0) / 100:.2f}",
            "delivery_restrict_to_zones": getattr(tenant, "delivery_restrict_to_zones", False),
            "delivery_zone_rows": _zone_rows(tenant),
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
    elif action in ("confirmed", "ready", "picked_up", "shipped", "cancelled", "returned"):
        if action == "shipped":  # G4: трек-номер до перехода (письмо его включает)
            from django.utils import timezone

            order.tracking_code = request.POST.get("tracking_code", "").strip()[:100]
            order.shipped_at = timezone.now()
            order.save(update_fields=["tracking_code", "shipped_at", "updated_at"])
        try:
            OrderSM().apply(order, action, actor=request.user)
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
            return redirect("orders:order-detail", pk=order.pk)
        messages.success(request, _("Order updated."))
        # Отмена/возврат оплаченного заказа возвращает оплату (Widerruf/анти-фрод).
        if (
            action in ("cancelled", "returned")
            and order.payment_state == Order.PAYMENT_PAID
            and order.stripe_payment_intent
        ):
            _refund_order(request, order)
    else:
        messages.error(request, _("Unknown action."))
    return redirect("orders:order-detail", pk=order.pk)


@login_required
def delivery_note_pdf(request, pk):
    """Lieferschein-PDF заказа (A2b) — накладная + адресная этикетка."""
    from .pdf import build_delivery_note_pdf

    order = get_object_or_404(
        Order.objects.select_related("customer").prefetch_related("items"), pk=pk
    )
    pdf = build_delivery_note_pdf(order, request.tenant)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="Lieferschein-{order.reference_code}.pdf"'
    return resp


def _eur_to_cents(raw) -> int:
    try:
        return max(0, round(float(str(raw or "0").replace(",", ".")) * 100))
    except (TypeError, ValueError):
        return 0


ZONE_ROWS = 6  # A2a: число строк-зон в форме доставки


def _parse_delivery_zones(request) -> list[dict]:
    """Собрать delivery_zones из строк формы (только непустые PLZ)."""
    zones = []
    for i in range(ZONE_ROWS):
        plz = request.POST.get(f"zone_plz_{i}", "").strip()[:120]
        if not plz:
            continue
        zones.append(
            {
                "plz": plz,
                "fee_cents": _eur_to_cents(request.POST.get(f"zone_fee_{i}")),
                "free_cents": _eur_to_cents(request.POST.get(f"zone_free_{i}")),
                "min_cents": _eur_to_cents(request.POST.get(f"zone_min_{i}")),
            }
        )
    return zones


def _zone_rows(tenant) -> list[dict]:
    """ZONE_ROWS строк для формы: существующие зоны (в €) + пустые добивки."""
    zones = list(getattr(tenant, "delivery_zones", None) or [])
    rows = []
    for i in range(ZONE_ROWS):
        z = zones[i] if i < len(zones) else None
        rows.append(
            {
                "i": i,
                "plz": z.get("plz", "") if z else "",
                "fee_eur": f"{(z.get('fee_cents') or 0) / 100:.2f}" if z else "",
                "free_eur": f"{(z.get('free_cents') or 0) / 100:.2f}" if z else "",
                "min_eur": f"{(z.get('min_cents') or 0) / 100:.2f}" if z else "",
            }
        )
    return rows


@login_required
@require_POST
def order_settings(request):
    """Настройки заказов: онлайн-предоплата (P2.5c) ИЛИ доставка/Versand (G4).

    Две независимые формы; различаем по hidden ``form`` — чтобы сохранение одной
    не сбрасывало другую."""
    tenant = request.tenant
    if request.POST.get("form") == "delivery":
        tenant.delivery_enabled = bool(request.POST.get("delivery_enabled"))
        tenant.delivery_fee_cents = _eur_to_cents(request.POST.get("delivery_fee_eur"))
        tenant.delivery_free_cents = _eur_to_cents(request.POST.get("delivery_free_eur"))
        tenant.delivery_min_cents = _eur_to_cents(request.POST.get("delivery_min_eur"))
        tenant.delivery_area = request.POST.get("delivery_area", "").strip()[:2000]
        tenant.pickup_min_cents = _eur_to_cents(request.POST.get("pickup_min_eur"))
        tenant.delivery_restrict_to_zones = bool(request.POST.get("delivery_restrict_to_zones"))
        tenant.delivery_zones = _parse_delivery_zones(request)
        tenant.save(
            update_fields=[
                "delivery_enabled",
                "delivery_fee_cents",
                "delivery_free_cents",
                "delivery_min_cents",
                "delivery_area",
                "pickup_min_cents",
                "delivery_restrict_to_zones",
                "delivery_zones",
                "updated_at",
            ]
        )
    else:
        tenant.orders_prepay = bool(request.POST.get("orders_prepay"))
        tenant.save(update_fields=["orders_prepay", "updated_at"])
    messages.success(request, _("Settings saved."))
    return redirect("orders:order-list")
