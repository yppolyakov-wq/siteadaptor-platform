"""CM-6.4: post-purchase просьба об отзыве о товарах — beat раз в сутки.

Паттерн booking.send_booking_post_visits: окно подхвата [N+7 … N дней назад]
по updated_at терминального статуса (picked_up/shipped ставят updated_at в
момент перехода), дедуп post_purchase_sent_at + БД-дедуп notify.
"""

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from .models import Order
from .notifications import enqueue_order_email


def _iter_tenant_schemas():
    with schema_context("public"):
        return list(
            get_tenant_model()
            .objects.exclude(schema_name="public")
            .values_list("schema_name", flat=True)
        )


def send_due_post_purchases(now=None) -> int:
    """Ровно одно письмо на выданный/отправленный заказ с товарами."""
    now = now or timezone.now()
    days = getattr(settings, "ORDERS_POSTPURCHASE_DAYS", 2)
    upper = now - timezone.timedelta(days=days)
    lower = upper - timezone.timedelta(days=7)  # окно подхвата пропусков
    due = Order.objects.filter(
        status__in=(Order.STATUS_PICKED_UP, Order.STATUS_SHIPPED),
        post_purchase_sent_at__isnull=True,
        updated_at__gte=lower,
        updated_at__lte=upper,
    )
    sent = 0
    for order in due:
        enqueue_order_email(order, "post_purchase")
        order.post_purchase_sent_at = timezone.now()
        order.save(update_fields=["post_purchase_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_order_post_purchases():
    """Beat (раз в сутки): post-purchase письма по всем схемам арендаторов."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_post_purchases()
    return total


def send_due_payment_reminders(now=None) -> int:
    """B2.1: заказ создан с онлайн-оплатой, но не оплачен N часов — одно
    напоминание (transactional, Vertragsanbahnung: гейт email+unsubscribed
    в enqueue, без opt-in). on_site/vorkasse не трогаем (unpaid — норма)."""
    now = now or timezone.now()
    hours = getattr(settings, "ORDERS_PAYREMIND_HOURS", 24)
    upper = now - timezone.timedelta(hours=hours)
    lower = upper - timezone.timedelta(days=7)  # окно подхвата пропусков
    due = Order.objects.filter(
        payment_method=Order.METHOD_STRIPE,
        payment_state=Order.PAYMENT_UNPAID,
        status=Order.STATUS_NEW,
        payment_reminder_sent_at__isnull=True,
        created_at__gte=lower,
        created_at__lte=upper,
    )
    sent = 0
    for order in due:
        enqueue_order_email(order, "payment_reminder")
        order.payment_reminder_sent_at = timezone.now()
        order.save(update_fields=["payment_reminder_sent_at", "updated_at"])
        sent += 1
    return sent


@shared_task
def send_order_payment_reminders():
    """Beat (раз в час): напоминания о незавершённой оплате по всем схемам."""
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += send_due_payment_reminders()
    return total
