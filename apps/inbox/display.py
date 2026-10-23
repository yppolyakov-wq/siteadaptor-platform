"""Чат-фикс 2026-10-23: подписи авторов сообщений — кто и когда писал.

Одна точка для кабинета (тред, карточка сделки, поллинг) и витрины клиента.
"""

from django.utils.translation import gettext as _

from .models import Message


def author_label(message, conversation, *, viewer):
    """Подпись автора над пузырём. `viewer` — кто смотрит: "staff" (кабинет) или
    "customer" (витрина). Клиент видит свои сообщения как «Sie», ответы — именем
    сотрудника (только first_name: username бывает e-mail'ом) или названием бизнеса;
    кабинет — имя клиента и полное имя сотрудника."""
    role = message.author_role
    if role == Message.AUTHOR_SYSTEM:
        return _("System")
    if role == Message.AUTHOR_CUSTOMER:
        if viewer == Message.AUTHOR_CUSTOMER:
            return _("Sie")
        customer = conversation.customer
        return (getattr(customer, "name", "") or "").strip() or _("Guest")
    user = message.author_user
    if user is not None:
        if viewer == Message.AUTHOR_STAFF:
            name = (user.get_full_name() or "").strip() or user.username
        else:
            name = (user.first_name or "").strip()
        if name:
            return name
    from django.db import connection

    tenant = getattr(connection, "tenant", None)
    return getattr(tenant, "name", "") or _("Team")


def labelled_messages(conversation, *, viewer):
    msgs = list(conversation.messages.select_related("author_user"))
    for m in msgs:
        m.author_label = author_label(m, conversation, viewer=viewer)
    return msgs


def with_last_message(qs):
    """Чат-фикс 2026-10-23: в списке видно, ЧТО и КТО написал последним (а не только
    тему) — одним подзапросом на беседу, без N+1."""
    from django.db.models import OuterRef, Subquery

    last = Message.objects.filter(conversation=OuterRef("pk")).order_by("-created_at", "-pk")
    return qs.annotate(
        last_body=Subquery(last.values("body")[:1]),
        last_role=Subquery(last.values("author_role")[:1]),
    )
