"""Письма по билетам (A6c) — через apps.notifications.

Механика как у stays/booking: рендер в схеме арендатора, БД-дедуп
`ticket:{id}:{event}:{role}`, доставка после коммита. Хелперы рендера/доменов —
из promotions.notifications. + Telegram (TG3) клиенту, если привязан.
"""

from django.db import connection
from django.urls import reverse

from apps.notifications.services import notify
from apps.promotions.notifications import _base_url, _owner_email, _render, _tenant

_CUSTOMER_TEMPLATES = {
    "created": "ticket_created",
    "confirmed": "ticket_confirmed",
    "cancelled": "ticket_cancelled",
    "reminder": "ticket_reminder",  # R9 за N дней до события
    "post_event": "ticket_post_event",  # R9 после события (отзыв/возврат)
    "payment_reminder": "ticket_payment_reminder",  # B2: незавершённая оплата
}


def enqueue_ticket_email(ticket, event):
    """Создать Notification(ы) события билета (БД-дедуп) и поставить доставку."""
    schema = connection.schema_name
    customer = ticket.customer
    ctx = {"ticket": ticket, "customer": customer, "event": ticket.event}

    template_base = _CUSTOMER_TEMPLATES.get(event)
    if template_base and customer.email and not customer.unsubscribed:
        base = _base_url(schema)
        # B2: ссылка на подтверждение (там кнопка «Jetzt bezahlen»).
        if event == "payment_reminder":
            ctx["pay_url"] = (
                f"{base}{reverse('storefront-ticket-ok', args=[ticket.reference_code])}"
                if base
                else ""
            )
        unsub = (
            f"{base}{reverse('storefront-unsubscribe', args=[customer.unsubscribe_token])}"
            if base
            else ""
        )
        # R9: drip-письма несут ссылку на памятку и на витрину.
        ctx["memo_url"] = (
            f"{base}{reverse('storefront-ticket-memo', args=[ticket.reference_code])}"
            if base
            else ""
        )
        ctx["website_url"] = base or ""
        # UA4-4b wiring: post-event ведёт на форму отзыва о событии (generic
        # reviews, GET → деталь с формой). Нет домена → письмо без ссылки.
        if event == "post_event":
            ctx["review_url"] = (
                f"{base}{reverse('storefront-event-review', args=[ticket.event_id])}"
                if base
                else ""
            )
        # R12: ссылка на самостоятельную отмену билета (политика — на событии).
        if base and event in ("created", "confirmed"):
            from .public_views import cancel_url

            ctx["cancel_url"] = f"{base}{cancel_url(ticket)}"
        subject, body, html = _render(template_base, {**ctx, "unsubscribe_url": unsub})
        headers = None
        if unsub:
            headers = {
                "List-Unsubscribe": f"<{unsub}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        notify(
            dedupe_key=f"ticket:{ticket.id}:{event}:customer",
            type=f"ticket_{event}",
            recipient=customer.email,
            subject=subject,
            body=body,
            html=html,
            headers=headers,
        )

    if template_base and customer:
        from apps.telegram.notify import send_to_customer

        subject_tg, body_tg, _html = _render(template_base, {**ctx, "unsubscribe_url": ""})
        send_to_customer(
            customer,
            type=f"ticket_{event}",
            dedupe_key=f"ticket:{ticket.id}:{event}:tg",
            text=subject_tg or body_tg,
        )

    # владельцу — на новую покупку
    if event == "created":
        owner = _owner_email(_tenant(schema))
        if owner:
            subject, body, html = _render("ticket_owner", {**ctx, "unsubscribe_url": ""})
            notify(
                dedupe_key=f"ticket:{ticket.id}:created:owner",
                type="ticket_created_owner",
                recipient=owner,
                subject=subject,
                body=body,
                html=html,
            )


def enqueue_installment_failed(charge, *, escalate=False):
    """R10c: письмо о неудачном списании доли рассрочки.

    Клиенту — «оплата не прошла» со ссылкой на билет (повтор/связь); владельцу —
    эскалация, если исчерпаны попытки (план failed). Дедуп по charge+попытке."""
    from decimal import Decimal

    schema = connection.schema_name
    plan = charge.plan
    ticket = plan.ticket
    customer = ticket.customer
    base = _base_url(schema)
    ticket_url = (
        f"{base}{reverse('storefront-ticket-ok', args=[ticket.reference_code])}" if base else ""
    )
    ctx = {
        "charge": charge,
        "plan": plan,
        "ticket": ticket,
        "event": ticket.event,
        "customer": customer,
        "amount_eur": Decimal(charge.amount_cents) / 100,
        "ticket_url": ticket_url,
        "attempt": charge.attempts,
        "final": escalate,
    }
    if customer.email and not customer.unsubscribed:
        subject, body, html = _render("installment_failed", {**ctx, "unsubscribe_url": ""})
        notify(
            dedupe_key=f"installment:{charge.id}:failed:{charge.attempts}:customer",
            type="installment_failed",
            recipient=customer.email,
            subject=subject,
            body=body,
            html=html,
        )
    if escalate:
        owner = _owner_email(_tenant(schema))
        if owner:
            subject, body, html = _render(
                "installment_failed_owner", {**ctx, "unsubscribe_url": ""}
            )
            notify(
                dedupe_key=f"installment:{charge.id}:failed:owner",
                type="installment_failed_owner",
                recipient=owner,
                subject=subject,
                body=body,
                html=html,
            )


def enqueue_event_waitlist_available(entry):
    """Письмо «снова frei» записи листа ожидания события (одно на запись, R1)."""
    schema = connection.schema_name
    base = _base_url(schema)
    event_url = f"{base}{reverse('storefront-event', args=[entry.event_id])}" if base else ""
    ctx = {"entry": entry, "event": entry.event, "event_url": event_url}
    subject, body, html = _render("event_waitlist_available", ctx)
    notify(
        dedupe_key=f"event_waitlist:{entry.id}:available",
        type="event_waitlist_available",
        recipient=entry.email,
        subject=subject,
        body=body,
        html=html,
    )
