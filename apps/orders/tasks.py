"""CM-6.4: post-purchase просьба об отзыве о товарах — beat раз в сутки.

Паттерн booking.send_booking_post_visits: окно подхвата [N+7 … N дней назад]
по updated_at терминального статуса (picked_up/shipped ставят updated_at в
момент перехода), дедуп post_purchase_sent_at + БД-дедуп notify.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core import tenant_iter

from .models import Order
from .notifications import enqueue_order_email

logger = logging.getLogger(__name__)


def _iter_tenant_schemas():
    return tenant_iter.schemas()


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
        with tenant_iter.isolated(schema, "send_order_post_purchases"):
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
        with tenant_iter.isolated(schema, "send_order_payment_reminders"):
            total += send_due_payment_reminders()
    return total


def expire_due_anprobe(now=None) -> int:
    """M3 Boutique: отменить просроченные Anprobe-резервы текущей схемы.

    Только неоплаченные new/confirmed с прошедшим reserve_expires_at; отмена —
    штатный FSM-путь cancelled (возврат стока + леджер), письмо ремапится на
    order_anprobe_cancelled в enqueue_order_email. Идемпотентно: отменённый
    заказ из фильтра выпадает."""
    from django.db import transaction

    from apps.orders.state_machine import OrderSM

    now = now or timezone.now()
    count = 0
    due_pks = list(
        Order.objects.filter(
            reserve_expires_at__lt=now,
            status__in=[Order.STATUS_NEW, Order.STATUS_CONFIRMED],
            payment_state=Order.PAYMENT_UNPAID,
        ).values_list("pk", flat=True)
    )
    for pk in due_pks:
        # Ревью M3 (HIGH): как в promotions.services.expire — блокировка строки
        # и ПОВТОРНАЯ проверка под локом. Иначе клиент, оплативший/забравший
        # вещь в последнюю минуту, получал отмену по устаревшему снапшоту
        # (статус затирался, сток возвращался у проданной вещи). atomic —
        # per-order: статус и restore коммитятся вместе.
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=pk)
                if (
                    order.status not in (Order.STATUS_NEW, Order.STATUS_CONFIRMED)
                    or order.payment_state != Order.PAYMENT_UNPAID
                    or not order.reserve_expires_at
                    or order.reserve_expires_at >= now
                ):
                    continue
                OrderSM().apply(order, "cancelled", actor="system:anprobe-ttl")
                count += 1
        except Exception:
            logger.exception("anprobe-ttl: не удалось отменить резерв %s", pk)
            continue
    return count


@shared_task
def expire_anprobe_reservations():
    """Beat (5 мин): просрочка Anprobe-резервов по всем схемам."""
    now = timezone.now()
    total = 0
    for schema in _iter_tenant_schemas():
        with tenant_iter.isolated(schema, "expire_anprobe_reservations"):
            total += expire_due_anprobe(now)
    return {"expired": total}


#: Заказов за один проход схемы: остальные подберёт следующий (15 минут).
ABANDONED_BATCH = 500


def _abandoned_pks(now) -> list:
    """Кандидаты автоотмены: онлайн-оплата не начата (нет платежа), заказ не подтверждён,
    писать клиенту некуда, срок вышел. Срок оплаты заказа (`payment_due_at`) ещё не
    прошёл — ждём его."""
    from django.db.models import Q

    from .payments import abandoned_hours

    cutoff = now - timezone.timedelta(hours=abandoned_hours())
    return list(
        Order.objects.filter(
            payment_method=Order.METHOD_STRIPE,
            payment_state=Order.PAYMENT_UNPAID,
            status=Order.STATUS_NEW,
            stripe_payment_intent="",
            customer__email="",
            created_at__lt=cutoff,
        )
        .filter(Q(payment_due_at__isnull=True) | Q(payment_due_at__lte=now))
        .order_by("created_at")
        .values_list("pk", flat=True)[:ABANDONED_BATCH]
    )


def _still_abandoned(order, now) -> bool:
    """Повторная проверка под блокировкой строки — те же условия, что в выборке."""
    from .payments import abandoned_hours, has_contact_email

    return (
        order.payment_method == Order.METHOD_STRIPE
        and order.payment_state == Order.PAYMENT_UNPAID
        and order.status == Order.STATUS_NEW
        and not order.stripe_payment_intent
        and order.created_at < now - timezone.timedelta(hours=abandoned_hours())
        and (order.payment_due_at is None or order.payment_due_at <= now)
        and not has_contact_email(order)
    )


def expire_abandoned_online(now=None) -> int:
    """FB-33 M2i-7.1: отменить брошенные онлайн-заказы текущей схемы.

    Заказ корзины ушёл на оплату без e-mail (M2i-7), гость оплату бросил: напоминание
    слать некуда, а заказ держит склад и лимит акции. Через `ORDERS_ABANDONED_HOURS`
    такой заказ отменяется штатным переходом FSM (склад, лимит акции, промокод
    возвращают эффекты перехода). Заказы с e-mail, Vorkasse/счёт, оплата на месте,
    оплаченные, подтверждённые и с начатым платежом не трогаются.

    Блокировка строки и повторная проверка под ней — как у `expire_due_anprobe`: вебхук
    оплаты (`payments.mark_order_paid`) берёт ту же блокировку. Идемпотентно: отменённый
    заказ из выборки выпадает."""
    from django.db import transaction

    from apps.orders.state_machine import OrderSM

    now = now or timezone.now()
    count = 0
    for pk in _abandoned_pks(now):
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().filter(pk=pk).first()
                if order is None or not _still_abandoned(order, now):
                    continue  # оплатили/подтвердили/появился адрес — не трогаем
                OrderSM().apply(order, "cancelled", actor="system:abandoned-online")
                count += 1
        except Exception:  # noqa: BLE001 — один заказ не роняет проход; в лог без PII
            logger.exception("abandoned-online: не удалось отменить заказ %s", pk)
            continue
    if count:
        logger.info("abandoned-online: отменено заказов — %s", count)
    return count


@shared_task
def expire_abandoned_online_orders():
    """Beat (15 мин): автоотмена брошенных онлайн-заказов без e-mail по всем схемам."""
    now = timezone.now()
    total = 0
    for schema in _iter_tenant_schemas():
        with tenant_iter.isolated(schema, "expire_abandoned_online_orders"):
            total += expire_abandoned_online(now)
    return {"expired": total}
