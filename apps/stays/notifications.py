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
    "payment_reminder": "stay_payment_reminder",  # B2: незавершённая оплата
}


def enqueue_stay_email(booking, event):
    """Создать Notification(ы) события брони (БД-дедуп) и поставить доставку."""
    schema = connection.schema_name
    customer = booking.customer
    ctx = {"booking": booking, "customer": customer, "unit": booking.unit}

    template_base = _CUSTOMER_TEMPLATES.get(event)
    if template_base and customer.email and not customer.unsubscribed:
        base = _base_url(schema)
        # B2: ссылка на подтверждение (там кнопка «Jetzt bezahlen»).
        if event == "payment_reminder":
            ctx["pay_url"] = (
                f"{base}{reverse('storefront-stay-ok', args=[booking.reference_code])}"
                if base
                else ""
            )
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
        # UA4-4b wiring: post-stay ведёт на форму отзыва о номере на витрине
        # (generic reviews, GET → деталь с формой) — раньше вёл в hotel-портал.
        # Нет домена → письмо без ссылки.
        review_link = (
            f"{base}{reverse('storefront-stay-review', args=[booking.unit_id])}"
            if base and event == "post_stay"
            else ""
        )
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
