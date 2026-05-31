"""Email-уведомления по броням.

Отправка — через idempotent_task с детерминированным dedupe_key (см.
patterns/notification-dedupe.md, уровень 2: Redis-лок как ранний отсев;
полноценная таблица Notification — Sprint 6).

Задача ставится в очередь ПОСЛЕ коммита транзакции (transaction.on_commit),
чтобы воркер гарантированно увидел сохранённую бронь. Письма уходят клиенту
(если есть email) и владельцу (на created).
"""

from django.conf import settings
from django.core.mail import send_mail
from django.db import connection, transaction
from django.template.loader import render_to_string
from django_tenants.utils import get_tenant_model, schema_context

from apps.core.jobs import idempotent_task

# событие -> базовое имя шаблона письма клиенту
_CUSTOMER_TEMPLATES = {
    "created": "reservation_created",
    "confirmed": "reservation_confirmed",
    "cancelled": "reservation_cancelled",
    "expired": "reservation_expired",
}


def enqueue_reservation_email(reservation, event):
    """Поставить письмо в очередь после коммита текущей транзакции."""
    schema = connection.schema_name
    rid = str(reservation.id)

    def _send():
        send_reservation_email.delay(
            dedupe_key=f"resv_email:{rid}:{event}",
            schema_name=schema,
            reservation_id=rid,
            event=event,
        )

    transaction.on_commit(_send)


def _owner_email(schema_name) -> str:
    """Email владельца бизнеса (Tenant живёт в public-схеме). Best-effort."""
    try:
        with schema_context("public"):
            tenant = get_tenant_model().objects.filter(schema_name=schema_name).first()
            return tenant.owner_email if tenant else ""
    except Exception:  # noqa: BLE001 — уведомления не критичны
        return ""


def _send(template_base, ctx, recipient) -> None:
    subject = render_to_string(f"emails/{template_base}_subject.txt", ctx).strip()
    body = render_to_string(f"emails/{template_base}.txt", ctx)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])


@idempotent_task()
def send_reservation_email(schema_name=None, reservation_id=None, event=None):
    from .models import Reservation

    with schema_context(schema_name):
        res = (
            Reservation.objects.select_related("promotion", "customer")
            .filter(id=reservation_id)
            .first()
        )
        if res is None:
            return {"skipped": "missing"}

        ctx = {"reservation": res, "promotion": res.promotion, "customer": res.customer}
        sent = 0

        template_base = _CUSTOMER_TEMPLATES.get(event)
        if template_base and res.customer.email:
            _send(template_base, ctx, res.customer.email)
            sent += 1

        if event == "created":
            owner = _owner_email(schema_name)
            if owner:
                _send("reservation_owner", ctx, owner)
                sent += 1

    return {"sent": sent}
