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
            "pickup_locations_text": "\n".join(
                f"{p['name']} | {p['address']}".rstrip(" |")
                for p in getattr(tenant, "pickup_points", [])
            ),
            "nav": "orders",
        },
    )


def _active_kitchen_orders():
    """Заказы в работе для KDS: принятые/новые, старые сверху (FIFO кухни)."""
    return (
        Order.objects.filter(status__in=(Order.STATUS_NEW, Order.STATUS_CONFIRMED))
        .select_related("customer")
        .prefetch_related("items")
        .order_by("created_at")
    )


@login_required
def kitchen(request):
    """Küchen-Display (KDS, A4): экран очереди заказов с авто-обновлением.

    Полная страница; доска заказов перезагружается HTMX-поллингом (_kitchen_board).
    Гейтинг модуля «orders» — ModuleGatingMiddleware по префиксу из реестра.
    """
    return render(
        request,
        "orders/kitchen.html",
        {"orders": _active_kitchen_orders(), "nav": "orders"},
    )


@login_required
def table_qr(request):
    """T2a: печатный лист QR-кодов столов. Каждый QR ведёт на витрину с
    ?tisch=N&ch=qr — гость сканирует, заказывает, заказ привязан к столу.

    Кабинет на домене арендатора → build_absolute_uri даёт верный хост витрины.
    Гейтинг модуля «orders» — ModuleGatingMiddleware.
    """
    import segno

    try:
        count = int(request.GET.get("count", "12"))
    except (TypeError, ValueError):
        count = 12
    count = max(1, min(count, 60))
    tables = []
    for n in range(1, count + 1):
        url = request.build_absolute_uri(f"/?tisch={n}&ch=qr")
        data_uri = segno.make(url, error="m").svg_data_uri(scale=4, border=2)
        tables.append({"n": n, "data_uri": data_uri})
    return render(
        request,
        "orders/table_qr.html",
        {"tables": tables, "count": count, "nav": "orders"},
    )


@login_required
def kitchen_board(request):
    """HTMX-партиал доски KDS (поллинг каждые несколько секунд)."""
    return render(request, "orders/_kitchen_board.html", {"orders": _active_kitchen_orders()})


@login_required
@require_POST
def kitchen_action(request, pk):
    """Действие с доски KDS (Annehmen new→confirmed / Fertig confirmed→ready).

    Возвращает обновлённый партиал доски для HTMX-swap (без перезагрузки экрана).
    """
    order = get_object_or_404(Order, pk=pk)
    action = request.POST.get("action", "")
    if action in ("confirmed", "ready"):
        try:
            OrderSM().apply(order, action, actor=request.user)
        except IllegalTransition:
            pass  # статус уже сменился (другой экран) — просто перерисуем доску
    return render(request, "orders/_kitchen_board.html", {"orders": _active_kitchen_orders()})


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


def _parse_pickup_locations(request) -> list[dict]:
    """Текст «Name | Adresse» построчно → [{name,address}] (только с name, до 10)."""
    out = []
    for line in (request.POST.get("pickup_locations", "") or "").splitlines():
        if not line.strip():
            continue
        name, _, address = line.partition("|")
        if name.strip():
            out.append({"name": name.strip()[:120], "address": address.strip()[:200]})
        if len(out) >= 10:
            break
    return out


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
        tenant.pickup_locations = _parse_pickup_locations(request)
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
                "pickup_locations",
                "updated_at",
            ]
        )
    else:
        tenant.orders_prepay = bool(request.POST.get("orders_prepay"))
        tenant.save(update_fields=["orders_prepay", "updated_at"])
    messages.success(request, _("Settings saved."))
    return redirect("orders:order-list")
