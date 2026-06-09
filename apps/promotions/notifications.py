"""Письма по броням — через apps.notifications (Sprint 6).

Рендер происходит при создании уведомления (мы в схеме арендатора, весь контекст
под рукой); тело и заголовки хранятся в Notification.payload. Гарантия без
дублей — unique dedupe_key в БД (`resv:{id}:{event}:{role}`), см.
patterns/notification-dedupe.md; Redis-lock задачи доставки — оптимизация.
Вызывается из ReservationSM.on_transition и services.reserve (внутри транзакции:
строка Notification атомарна с событием, доставка — после коммита).
"""

from django.db import connection
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.urls import reverse
from django_tenants.utils import get_tenant_model, schema_context

from apps.notifications.services import notify

# событие -> базовое имя шаблона письма клиенту
_CUSTOMER_TEMPLATES = {
    "created": "reservation_created",
    "confirmed": "reservation_confirmed",
    "cancelled": "reservation_cancelled",
    "expired": "reservation_expired",
}


def _tenant(schema_name):
    with schema_context("public"):
        return get_tenant_model().objects.filter(schema_name=schema_name).first()


def _owner_email(tenant) -> str:
    return tenant.owner_email if tenant else ""


def _base_url(schema_name) -> str:
    """Абсолютный URL витрины арендатора (для ссылки отписки в письме)."""
    try:
        from apps.tenants.models import Domain

        with schema_context("public"):
            domain = (
                Domain.objects.filter(tenant__schema_name=schema_name, is_primary=True).first()
                or Domain.objects.filter(tenant__schema_name=schema_name).first()
            )
        return f"https://{domain.domain}" if domain else ""
    except Exception:  # noqa: BLE001
        return ""


def _render(template_base, ctx) -> tuple[str, str, str]:
    """Рендер subject + text + (опц.) HTML-альтернативы письма."""
    subject = render_to_string(f"emails/{template_base}_subject.txt", ctx).strip()
    body = render_to_string(f"emails/{template_base}.txt", ctx)
    try:
        html = render_to_string(f"emails/{template_base}.html", ctx)
    except TemplateDoesNotExist:
        html = ""
    return subject, body, html


def enqueue_reservation_email(reservation, event):
    """Создать Notification(ы) события брони (БД-дедуп) и поставить доставку."""
    schema = connection.schema_name
    customer = reservation.customer
    ctx = {"reservation": reservation, "promotion": reservation.promotion, "customer": customer}

    template_base = _CUSTOMER_TEMPLATES.get(event)
    # клиенту — если есть email и он не отписался
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
            # one-click отписка (RFC 8058)
            headers = {
                "List-Unsubscribe": f"<{unsub}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        notify(
            dedupe_key=f"resv:{reservation.id}:{event}:customer",
            type=f"reservation_{event}",
            recipient=customer.email,
            subject=subject,
            body=body,
            html=html,
            headers=headers,
        )

    # владельцу — только при создании брони
    if event == "created":
        owner = _owner_email(_tenant(schema))
        if owner:
            subject, body, html = _render("reservation_owner", {**ctx, "unsubscribe_url": ""})
            notify(
                dedupe_key=f"resv:{reservation.id}:created:owner",
                type="reservation_created_owner",
                recipient=owner,
                subject=subject,
                body=body,
                html=html,
            )


def enqueue_waitlist_available(entry):
    """Письмо «снова в наличии» записи листа ожидания (одно на запись, S6.4)."""
    schema = connection.schema_name
    base = _base_url(schema)
    promo_url = (
        f"{base}{reverse('storefront-promotion', args=[entry.promotion_id])}" if base else ""
    )
    ctx = {"entry": entry, "promotion": entry.promotion, "promo_url": promo_url}
    subject, body, html = _render("waitlist_available", ctx)
    notify(
        dedupe_key=f"waitlist:{entry.id}:available",
        type="waitlist_available",
        recipient=entry.email,
        subject=subject,
        body=body,
        html=html,
    )
