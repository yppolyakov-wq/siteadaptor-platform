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
        stripe_payment_intent="",  # M2i-7.1: оплата «в пути» (SEPA) — не напоминаем
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


#: Заказов в одной выборке и выборок за проход схемы; остаток подберёт следующий проход.
ABANDONED_BATCH = 500
ABANDONED_MAX_BATCHES = 10


def _abandoned_pks(now, exclude=()) -> list:
    """Кандидаты автоотмены: заказ не подтверждён и не оплачен, писать клиенту некуда,
    срок вышел (`payments.abandon_deadline`, здесь — то же условие в SQL): оплата не начата
    — `ORDERS_ABANDONED_HOURS`; платёж «в пути» без исхода — `processing_hold()`; срок
    оплаты заказа (`payment_due_at`) ещё не прошёл — ждём его. `exclude` — заказы, не
    отменившиеся в этом проходе."""
    from django.db.models import Q

    from .payments import abandoned_hours, no_contact_email_q, processing_hold

    idle = Q(stripe_payment_intent="") & Q(
        created_at__lte=now - timezone.timedelta(hours=abandoned_hours())
    )
    stuck = ~Q(stripe_payment_intent="") & Q(created_at__lte=now - processing_hold())
    return list(
        Order.objects.filter(
            payment_method=Order.METHOD_STRIPE,
            payment_state=Order.PAYMENT_UNPAID,
            status=Order.STATUS_NEW,
        )
        .filter(idle | stuck)
        .filter(no_contact_email_q())
        .filter(Q(payment_due_at__isnull=True) | Q(payment_due_at__lte=now))
        .exclude(pk__in=list(exclude))
        .order_by("created_at")
        .values_list("pk", flat=True)[:ABANDONED_BATCH]
    )


def _still_abandoned(order, now) -> bool:
    """Повторная проверка под блокировкой строки — те же условия, что в выборке."""
    from .payments import abandon_deadline, has_contact_email

    return (
        order.payment_method == Order.METHOD_STRIPE
        and order.payment_state == Order.PAYMENT_UNPAID
        and order.status == Order.STATUS_NEW
        and abandon_deadline(order) <= now
        and not has_contact_email(order)
    )


def expire_abandoned_online(now=None, *, expire_run=None) -> int:
    """FB-33 M2i-7.1: отменить брошенные онлайн-заказы текущей схемы.

    Заказ корзины ушёл на оплату без e-mail (M2i-7), гость оплату бросил: напоминание
    слать некуда, а заказ держит склад и лимит акции. Через `ORDERS_ABANDONED_HOURS`
    такой заказ отменяется штатным переходом FSM (склад, лимит акции, промокод
    возвращают эффекты перехода). Заказы с e-mail, Vorkasse/счёт, оплата на месте,
    оплаченные и подтверждённые не трогаются; платёж «в пути» ждём до `processing_hold()`.

    Блокировка строки и повторная проверка под ней — как у `expire_due_anprobe`: вебхук
    оплаты (`payments.mark_order_paid`) берёт ту же блокировку. Идемпотентно: отменённый
    заказ из выборки выпадает. Заказ, который отменить не удалось, исключается до конца
    прохода — очередь за ним идёт дальше; итог прохода — в логе (без PII)."""
    from django.db import connection, transaction

    from apps.orders.state_machine import OrderSM

    from .payments import ABANDONED_ACTOR

    now = now or timezone.now()
    schema = connection.schema_name
    cancelled = 0
    cancelled_pks: list = []
    failed: list = []
    full = True
    for _batch in range(ABANDONED_MAX_BATCHES):
        pks = _abandoned_pks(now, exclude=failed)
        for pk in pks:
            try:
                with transaction.atomic():
                    order = Order.objects.select_for_update().filter(pk=pk).first()
                    if order is None or not _still_abandoned(order, now):
                        continue  # оплатили/подтвердили/появился адрес — не трогаем
                    OrderSM().apply(order, "cancelled", actor=ABANDONED_ACTOR)
                    cancelled += 1
                    cancelled_pks.append(pk)
            except Exception:  # noqa: BLE001 — один заказ не роняет проход; в лог без PII
                failed.append(pk)
                logger.exception("abandoned-online %s: заказ %s не отменён", schema, pk)
        if len(pks) < ABANDONED_BATCH:
            full = False
            break
    if cancelled or failed:
        logger.info("abandoned-online %s: cancelled=%s failed=%s", schema, cancelled, len(failed))
    if failed:
        tenant_iter._tag_sentry(schema, "expire_abandoned_online_orders")
        logger.error(
            "abandoned-online %s: не отменены заказы (%s): %s",
            schema,
            len(failed),
            ", ".join(str(pk) for pk in failed[:50]),
        )
    if full:
        logger.warning("abandoned-online %s: batch full — остаток уйдёт в следующий проход", schema)
    if cancelled_pks:
        _expire_sessions(schema, cancelled_pks, expire_run)
    return cancelled


def _expire_sessions(schema: str, pks, run=None) -> None:
    """FB-33 D4a: закрыть сессии Stripe отменённых заказов — ПОСЛЕ транзакций отмены
    (вызов Stripe не держит блокировку строки). Тенант — один раз на проход. Сбой не
    роняет проход: сессия закроется своим сроком, поздняя оплата вернётся."""
    from django_tenants.utils import get_tenant_model

    from .payments import expire_open_sessions

    tenant = get_tenant_model().objects.filter(schema_name=schema).first()
    connect_id = (getattr(tenant, "stripe_connect_id", "") or "").strip()
    if not connect_id:
        return
    try:
        closed = expire_open_sessions(pks, connect_id=connect_id, run=run)
    except Exception:  # noqa: BLE001 — отмена уже записана
        logger.exception("abandoned-online %s: checkout sessions not expired", schema)
        return
    if closed:
        logger.info("abandoned-online %s: checkout sessions closed=%s", schema, closed)


#: Повторы возврата поздней оплаты: сколько раз и за какой срок после платежа.
REFUND_RETRY_MAX = 4
REFUND_RETRY_DAYS = 3
_REFUND_RETRY_STEP = timezone.timedelta(minutes=15)


def _refund_retry_due(schema: str, pk, now) -> bool:
    """Пора ли повторить возврат: не больше `REFUND_RETRY_MAX` раз, с растущей паузой
    (15 мин · 2ⁿ). Счётчик — в кэше; кэш недоступен — не повторяем (иначе повторы и
    письма владельцу о сбое шли бы без предела)."""
    from django.core.cache import cache

    key = f"order-refund-retry:{schema}:{pk}"
    try:
        state = cache.get(key) or {"n": 0, "next": 0}
        if state["n"] >= REFUND_RETRY_MAX or now.timestamp() < state["next"]:
            return False
        pause = _REFUND_RETRY_STEP * (2 ** state["n"])
        cache.set(
            key,
            {"n": state["n"] + 1, "next": (now + pause).timestamp()},
            (REFUND_RETRY_DAYS + 1) * 86400,
        )
    except Exception:  # noqa: BLE001
        logger.warning("refund-retry %s: счётчик недоступен — заказ %s пропущен", schema, pk)
        return False
    return True


def retry_late_refunds(now=None) -> int:
    """FB-33 M2i-7.1 (ревью): повторить возврат оплаты отменённых заказов текущей схемы.

    Оплата пришла к отменённому заказу, а возврат не прошёл (сбой Stripe) — заказ остался
    «отменён · оплачен» (`payments.refund_open`). Отмена заказа всегда возвращает оплату,
    поэтому такое сочетание — незавершённый возврат; повтор безопасен: Stripe узнаёт его
    по ключу идемпотентности. Только свежие платежи (`REFUND_RETRY_DAYS`), ограниченное
    число попыток — дальше владелец возвращает сам (письмо о сбое и пометка в карточке).
    → сколько заказов стало «возвращено»."""
    from django.db import connection
    from django.db.models import F
    from django_tenants.utils import get_tenant_model

    from apps.core import payment_holds, refunds
    from apps.core.models import DealPayment

    now = now or timezone.now()
    schema = connection.schema_name
    fresh = (
        DealPayment.objects.filter(
            deal_kind="order",
            created_at__gte=now - timezone.timedelta(days=REFUND_RETRY_DAYS),
            refunded_cents__lt=F("amount_cents"),
        )
        .exclude(stripe_payment_intent="")
        .values_list("deal_id", flat=True)
    )
    due = list(
        Order.objects.filter(
            pk__in=fresh,
            status=Order.STATUS_CANCELLED,
            payment_state=Order.PAYMENT_PAID,
            payment_method=Order.METHOD_STRIPE,
        )
        .exclude(stripe_payment_intent="")
        .order_by("created_at")[:ABANDONED_BATCH]
    )
    # FB-33 D4a: повтор возврата второго платежа — общий для видов сделок, в ядре
    done = payment_holds.retry_extra_refunds(now)  # все виды с книгой (EXTRA_RETRY_KINDS)
    if not due:
        return done
    tenant = get_tenant_model().objects.filter(schema_name=schema).first()
    for order in due:
        if not _refund_retry_due(schema, order.pk, now):
            continue
        try:
            result = refunds.refund_payment("order", order, tenant)
        except Exception:  # noqa: BLE001 — один заказ не роняет проход
            logger.exception("refund-retry %s: заказ %s — сбой", schema, order.pk)
            continue
        logger.warning("refund-retry %s: заказ %s → %s", schema, order.pk, result)
        if result in (refunds.RefundResult.REFUNDED, refunds.RefundResult.ALREADY):
            done += 1
    return done


@shared_task
def expire_abandoned_online_orders():
    """Beat (15 мин): автоотмена брошенных онлайн-заказов без e-mail по всем схемам и
    повтор несостоявшихся возвратов поздней оплаты. Шаги изолированы друг от друга."""
    from .payments import ExpirePass

    now = timezone.now()
    total = 0
    refunded = 0
    expire_run = ExpirePass()  # FB-33 D4a: бюджет закрытия сессий Stripe — на весь проход
    for schema in _iter_tenant_schemas():
        with tenant_iter.isolated(schema, "expire_abandoned_online_orders"):
            total += expire_abandoned_online(now, expire_run=expire_run)
        with tenant_iter.isolated(schema, "retry_late_order_refunds"):
            refunded += retry_late_refunds(now)
    return {"expired": total, "refunds_retried": refunded}
