"""Письма по заказам Click & Collect (Track D / D2b) — через apps.notifications.

Та же механика, что у броней (apps.promotions.notifications): рендер в схеме
арендатора, БД-дедуп по dedupe_key `order:{id}:{event}:{role}`, доставка после
коммита. Хелперы рендера/доменов переиспользуем из promotions.notifications.
"""

from django.db import connection
from django.urls import reverse

from apps.notifications.services import notify
from apps.promotions.notifications import _base_url, _owner_email, _render, _tenant

# событие -> базовое имя шаблона письма клиенту
_CUSTOMER_TEMPLATES = {
    "created": "order_created",
    "confirmed": "order_confirmed",
    "ready": "order_ready",
    "picked_up": "order_picked_up",
    "cancelled": "order_cancelled",
}


def enqueue_order_email(order, event):
    """Создать Notification(ы) события заказа (БД-дедуп) и поставить доставку."""
    schema = connection.schema_name
    customer = order.customer
    ctx = {"order": order, "customer": customer, "items": list(order.items.all())}

    template_base = _CUSTOMER_TEMPLATES.get(event)
    if template_base and customer.email and not customer.unsubscribed:
        base = _base_url(schema)
        unsub = (
            f"{base}{reverse('storefront-unsubscribe', args=[customer.unsubscribe_token])}"
            if base
            else ""
        )
        subject, body, html = _render(template_base, {**ctx, "unsubscribe_url": unsub})
        headers = None
        if unsub:
            headers = {
                "List-Unsubscribe": f"<{unsub}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        notify(
            dedupe_key=f"order:{order.id}:{event}:customer",
            type=f"order_{event}",
            recipient=customer.email,
            subject=subject,
            body=body,
            html=html,
            headers=headers,
        )

    # владельцу — только при новом заказе
    if event == "created":
        owner = _owner_email(_tenant(schema))
        if owner:
            subject, body, html = _render("order_owner", {**ctx, "unsubscribe_url": ""})
            notify(
                dedupe_key=f"order:{order.id}:created:owner",
                type="order_created_owner",
                recipient=owner,
                subject=subject,
                body=body,
                html=html,
            )
