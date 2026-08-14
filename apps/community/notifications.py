"""Уведомления о жизни пространства поездки (MT-3).

Объявление гида — то, ради чего раньше держали Telegram-группу. Поэтому оно
уходит обоими каналами платформы (email + Telegram) с уважением к матрице
владельца (UD4-2). Реплики чата НЕ рассылаем: чат читают, находясь в нём,
иначе поездка утонет в письмах.
"""

from django.urls import reverse

from apps.core import status_registry

DOMAIN = "community"
EVENT_NEW_POST = "new_post"


def _participants(space):
    """Клиенты с действующим билетом на заезд (получатели уведомлений)."""
    if space.ref_kind != "event" or not space.ref_id:
        return []
    from apps.events.models import Ticket

    tickets = (
        Ticket.objects.filter(event_id=space.ref_id)
        .exclude(status__in=status_registry.cancelled_statuses_for("ticket"))
        .select_related("customer")
    )
    seen, out = set(), []
    for ticket in tickets:
        customer = ticket.customer
        if customer is None or customer.pk in seen:
            continue
        seen.add(customer.pk)
        out.append(customer)
    return out


def _tenant():
    from django.db import connection

    from apps.tenants.models import Tenant

    return Tenant.objects.filter(schema_name=connection.schema_name).first()


def notify_new_post(space, post) -> int:
    """Сообщить участникам о новой записи ленты. → сколько уведомлений поставлено.

    Молчим, когда это реплика чата, запись пришла ИЗ Telegram (там её уже видели)
    или автор — участник (адресат объявления — группа, а не гид).
    """
    from apps.notifications.models import Notification
    from apps.notifications.prefs import channel_enabled
    from apps.notifications.services import notify
    from apps.telegram.notify import send_to_customer

    if post.kind != post.KIND_POST or post.source == post.SOURCE_TELEGRAM:
        return 0
    if not post.by_staff:
        return 0
    tenant = _tenant()
    if tenant is None:
        return 0
    subject = space.title or str(space)
    url = reverse("community-space", args=[space.pk])
    text = f"{subject}: {post.body[:200]}\n{url}"
    sent = 0
    for customer in _participants(space):
        if customer.email and channel_enabled(
            tenant, "customer", DOMAIN, EVENT_NEW_POST, Notification.EMAIL
        ):
            notify(
                dedupe_key=f"community:{post.pk}:{customer.pk}:email",
                type="community_post",
                recipient=customer.email,
                subject=subject,
                body=text,
                channel=Notification.EMAIL,
            )
            sent += 1
        if channel_enabled(tenant, "customer", DOMAIN, EVENT_NEW_POST, Notification.TELEGRAM):
            # Хелпер сам молчит, если бот не подключён или клиент его не привязывал.
            send_to_customer(
                customer,
                type="community_post",
                dedupe_key=f"community:{post.pk}:{customer.pk}:tg",
                text=text,
            )
            sent += 1
    return sent
