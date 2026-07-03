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
