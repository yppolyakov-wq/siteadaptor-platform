"""Письма по сообщениям inbox (M22b) — через apps.notifications.

Дедуп по сообщению (`inbox:msg:{id}:{role}`) — одно письмо на сообщение. Ответ
владельца → письмо клиенту со ссылкой на публичный тред; вопрос клиента → письмо
владельцу. Рендер в схеме арендатора (контекст под рукой), доставка после коммита.
"""

from django.db import connection
from django.urls import reverse

from apps.notifications.services import notify
from apps.promotions.notifications import _base_url, _owner_email, _render, _tenant

from .models import Message


def enqueue_message_email(message):
    """Письмо по новому сообщению: клиенту (ответ владельца) или владельцу (вопрос)."""
    conversation = message.conversation
    schema = connection.schema_name
    tenant = _tenant(schema)
    base = _base_url(schema)
    thread_url = (
        f"{base}{reverse('storefront-message-thread', args=[conversation.public_token])}"
        if base
        else ""
    )
    ctx = {
        "conversation": conversation,
        "message": message,
        "thread_url": thread_url,
        "business": tenant.name if tenant else "",
        "unsubscribe_url": "",
    }

    if message.author_role == Message.AUTHOR_STAFF:
        customer = conversation.customer
        if customer and customer.email:
            subject, body, html = _render("inbox_customer", ctx)
            notify(
                dedupe_key=f"inbox:msg:{message.id}:customer",
                type="inbox_reply",
                recipient=customer.email,
                subject=subject,
                body=body,
                html=html,
            )
    elif message.author_role == Message.AUTHOR_CUSTOMER:
        owner = _owner_email(tenant)
        if owner:
            subject, body, html = _render("inbox_owner", ctx)
            notify(
                dedupe_key=f"inbox:msg:{message.id}:owner",
                type="inbox_question",
                recipient=owner,
                subject=subject,
                body=body,
                html=html,
            )
