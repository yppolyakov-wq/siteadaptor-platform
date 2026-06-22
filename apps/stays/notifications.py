"""Письма по date-range-броням (Track E / E3) — через apps.notifications.

Механика как у броней/записей: рендер в схеме арендатора, БД-дедуп
`stay:{id}:{event}:{role}`, доставка после коммита. Переиспуем хелперы
apps.promotions.notifications (_render/_base_url/_owner_email/_tenant).
"""

from django.db import connection
from django.urls import reverse

from apps.notifications.services import notify
from apps.promotions.notifications import _base_url, _owner_email, _render, _tenant

# событие -> базовое имя шаблона письма клиенту
_CUSTOMER_TEMPLATES = {
    "created": "stay_created",
    "confirmed": "stay_confirmed",
    "cancelled": "stay_cancelled",
    "reminder": "stay_reminder",
    "post_stay": "stay_post_stay",  # G2: благодарность + запрос отзыва после выезда
}


def _review_url(schema):
    """G2: ссылка на страницу бизнеса в hotel-портале для отзыва (best-effort).

    Портал/тенант — SHARED (public), поэтому читаем под schema_context('public').
    Нет портала/слага → пусто (письмо уйдёт без ссылки на отзыв)."""
    try:
        from django_tenants.utils import schema_context

        from apps.aggregator.models import AggregatorPortal
        from apps.tenants.models import Tenant

        with schema_context("public"):
            portal = AggregatorPortal.objects.filter(is_active=True, business_type="hotel").first()
            if portal is None:
                return ""
            slug = Tenant.objects.filter(schema_name=schema).values_list("slug", flat=True).first()
        return f"https://{portal.host}/unternehmen/{slug}/" if slug else ""
    except Exception:  # noqa: BLE001 — письмо не должно падать из-за ссылки
        return ""


def enqueue_stay_email(booking, event):
    """Создать Notification(ы) события брони (БД-дедуп) и поставить доставку."""
    schema = connection.schema_name
    customer = booking.customer
    ctx = {"booking": booking, "customer": customer, "unit": booking.unit}

    template_base = _CUSTOMER_TEMPLATES.get(event)
    if template_base and customer.email and not customer.unsubscribed:
        base = _base_url(schema)
        unsub = (
            f"{base}{reverse('storefront-unsubscribe', args=[customer.unsubscribe_token])}"
            if base
            else ""
        )
        # H4b: ссылка на самоотмену в письмах о брони (created/confirmed).
        cancel_link = ""
        if base and event in ("created", "confirmed"):
            from .public_views import cancel_token

            cancel_link = f"{base}{reverse('storefront-stay-cancel', args=[cancel_token(booking)])}"
        review_link = _review_url(schema) if event == "post_stay" else ""
        subject, body, html = _render(
            template_base,
            {**ctx, "unsubscribe_url": unsub, "cancel_url": cancel_link, "review_url": review_link},
        )
        headers = None
        if unsub:
            headers = {
                "List-Unsubscribe": f"<{unsub}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        notify(
            dedupe_key=f"stay:{booking.id}:{event}:customer",
            type=f"stay_{event}",
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
            type=f"stay_{event}",
            dedupe_key=f"stay:{booking.id}:{event}:tg",
            text=subject_tg or body_tg,
        )

    # владельцу — только при новой заявке
    if event == "created":
        owner = _owner_email(_tenant(schema))
        if owner:
            subject, body, html = _render("stay_owner", {**ctx, "unsubscribe_url": ""})
            notify(
                dedupe_key=f"stay:{booking.id}:created:owner",
                type="stay_created_owner",
                recipient=owner,
                subject=subject,
                body=body,
                html=html,
            )
