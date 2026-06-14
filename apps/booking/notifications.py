"""Письма по записям (Track D / D3c) — через apps.notifications.

Механика как у броней/заказов: рендер в схеме арендатора, БД-дедуп
`booking:{id}:{event}:{role}`, доставка после коммита.
"""

from django.db import connection
from django.urls import reverse

from apps.notifications.services import notify
from apps.promotions.notifications import _base_url, _owner_email, _render, _tenant

# событие -> базовое имя шаблона письма клиенту
_CUSTOMER_TEMPLATES = {
    "created": "booking_created",
    "confirmed": "booking_confirmed",
    "cancelled": "booking_cancelled",
    "reminder": "booking_reminder",
}


def enqueue_booking_email(booking, event):
    """Создать Notification(ы) события записи (БД-дедуп) и поставить доставку."""
    schema = connection.schema_name
    customer = booking.customer
    ctx = {"booking": booking, "customer": customer, "resource": booking.resource}

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
            dedupe_key=f"booking:{booking.id}:{event}:customer",
            type=f"booking_{event}",
            recipient=customer.email,
            subject=subject,
            body=body,
            html=html,
            headers=headers,
        )

    # TG3: то же событие — в Telegram, если клиент привязал бота (дополняет email).
    if template_base and customer:
        from apps.telegram.notify import send_to_customer

        subject_tg, body_tg, _html = _render(template_base, {**ctx, "unsubscribe_url": ""})
        send_to_customer(
            customer,
            type=f"booking_{event}",
            dedupe_key=f"booking:{booking.id}:{event}:tg",
            text=subject_tg or body_tg,
        )

    # владельцу — только при новой заявке
    if event == "created":
        owner = _owner_email(_tenant(schema))
        if owner:
            subject, body, html = _render("booking_owner", {**ctx, "unsubscribe_url": ""})
            notify(
                dedupe_key=f"booking:{booking.id}:created:owner",
                type="booking_created_owner",
                recipient=owner,
                subject=subject,
                body=body,
                html=html,
            )
