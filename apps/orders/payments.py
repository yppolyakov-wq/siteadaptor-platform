"""Онлайн-предоплата Click&Collect через Stripe Connect (P2.5c).

Checkout создаётся НА connected account бизнеса (деньги идут ему; вариант B —
application_fee=0). Подтверждение оплаты ставит вебхук на public-схеме
(apps.billing.webhooks → mark_order_paid), кросс-схемно через schema_context.
"""

import logging
import time

from apps.billing import connect

logger = logging.getLogger(__name__)

#: RFC 5321: адрес длиннее 254 знаков не доставляется (и не влезает в EmailField).
PAYER_EMAIL_MAX = 254


def available_methods(tenant, *, customer_type=None, shipping=None) -> list[str]:
    """E7-2: способы оплаты, доступные на checkout этого бизнеса.

    SH-23: правила переехали в ОБЩИЙ реестр `apps.core.payment_methods` (тот же
    порядок и те же guard'ы — stripe при prepay+Connect, vorkasse при IBAN,
    on_site всегда), потому что способ оплаты теперь есть у всех видов сделок.
    Новое здесь одно: фирме дополнительно предлагается счёт (решение Р-3), если
    бизнес включил `invoice_b2b_enabled`."""
    from apps.core import payment_methods as pm

    return pm.available(
        tenant, "order", customer_type=customer_type or pm.PRIVATE, shipping=shipping
    )


def picker_rows(methods: list[str], tenant) -> list[dict]:
    """FB-30.12: строки пикера оплаты заказа (подпись «Zahlung bei Abholung/Lieferung»)."""
    from apps.core import payment_methods as pm

    return pm.picker_rows(tenant, methods)


def abandoned_hours() -> int:
    """FB-33 M2i-7.1: через сколько часов брошенный онлайн-заказ без e-mail отменяется
    (`ORDERS_ABANDONED_HOURS`, по умолчанию 24; меньше часа не бывает)."""
    from django.conf import settings

    try:
        return max(1, int(getattr(settings, "ORDERS_ABANDONED_HOURS", 24)))
    except (TypeError, ValueError):
        return 24


def processing_hold():
    """Сколько заказ ждёт платёж «в пути» без исхода — как удержание брони (SEPA, 14 дней)."""
    from apps.core import payment_holds

    return payment_holds.PROCESSING_HOLD


def abandon_deadline(order):
    """FB-33 M2i-7.1: момент, с которого заказ без e-mail подлежит автоотмене, — один на
    выборку задачи, окно оплаты и срок сессии Stripe. Не раньше срока оплаты заказа
    (`payment_due_at`); при платеже «в пути» ждём его исхода до `processing_hold()`."""
    from datetime import timedelta

    wait = processing_hold() if order.stripe_payment_intent else timedelta(hours=abandoned_hours())
    return max(order.created_at + wait, order.payment_due_at or order.created_at)


def no_contact_email_q():
    """Условие «клиенту заказа некуда писать» — одно на выборку автоотмены и на проверки."""
    from django.db.models import Q

    return Q(customer__email="")


def has_contact_email(order) -> bool:
    """У клиента заказа есть e-mail (свежо из БД: адрес мог записать вебхук оплаты)."""
    from .models import Order

    return not Order.objects.filter(pk=order.pk).filter(no_contact_email_q()).exists()


def pay_window_closed(order, *, now=None) -> bool:
    """FB-33 M2i-7.1 (ревью): до автоотмены заказа без e-mail осталось меньше, чем Stripe
    даёт сессии со сроком (30 мин + запас) — новую ссылку оплаты не выдаём, иначе гость
    платит за минуты до отмены и получает возврат."""

    from django.utils import timezone

    from apps.core import payment_holds

    if not order.created_at or has_contact_email(order):
        return False
    now = now or timezone.now()
    return (
        abandon_deadline(order) - now
        < payment_holds.STRIPE_MIN_SESSION + payment_holds.SESSION_MARGIN
    )


def payment_processing(order) -> bool:
    """Оплата «в пути» (SEPA/Klarna): Checkout завершён, деньги ещё не зачислены —
    платёж привязан (`mark_order_processing`), а заказ ещё «не оплачен»."""
    from .models import Order

    return order.payment_state == Order.PAYMENT_UNPAID and bool(order.stripe_payment_intent)


def _late_refund_open(order) -> bool:
    """Отменённый заказ, оплаченный онлайн, деньги не возвращены: у заказа отмена всегда
    возвращает оплату, значит возврат не прошёл (сбой Stripe)."""
    from .models import Order

    return (
        order.status == Order.STATUS_CANCELLED
        and order.payment_state == Order.PAYMENT_PAID
        and order.payment_method == Order.METHOD_STRIPE
        and bool(order.stripe_payment_intent)
    )


def refund_open(order) -> bool:
    """Пометка «Rückerstattung offen» в карточке: возврат поздней оплаты отменённого заказа
    не прошёл ИЛИ (FB-33 D4a) у заказа есть платёж Stripe помимо главного с открытым
    остатком — второй платёж, возврат которого не состоялся (у заказа второй платёж
    всегда возвращается). +1 запрос, только у онлайн-заказа."""
    from apps.core import folio

    from .models import Order

    if _late_refund_open(order):
        return True
    if order.payment_method != Order.METHOD_STRIPE or not order.stripe_payment_intent:
        return False
    return folio.open_card_rows("order", order, exclude_intent=order.stripe_payment_intent).exists()


#: FB-33 D4a: состояния «Jetzt bezahlen» (`pay_state`).
PAY_OPEN = "open"
PAY_PROCESSING = "processing"
PAY_CLOSED = "closed"
PAY_UNAVAILABLE = "unavailable"
PAY_CANCELLED = "cancelled"


def pay_state(order, tenant) -> str:
    """FB-33 D4a: можно ли сейчас платить заказ онлайн — одно условие для `order_pay`,
    оплаты предложения и подтверждения. "open" — кнопка; "processing" — оплата «в пути»;
    "closed" — минуты до автоотмены; "unavailable" — онлайн-оплата у бизнеса выключена;
    "cancelled" — онлайн-заказ отменён; "" — не онлайн-заказ, уже оплачен или не «new»."""
    from .models import Order

    if order.payment_method != Order.METHOD_STRIPE:
        return ""
    if order.status == Order.STATUS_CANCELLED:
        return PAY_CANCELLED
    if (
        order.payment_state != Order.PAYMENT_UNPAID
        or order.status != Order.STATUS_NEW
        or order.total <= 0
    ):
        return ""
    if not getattr(tenant, "payments_enabled", False):
        return PAY_UNAVAILABLE
    if payment_processing(order):
        return PAY_PROCESSING
    if pay_window_closed(order):
        return PAY_CLOSED
    return PAY_OPEN


#: actor перехода FSM при автоотмене брошенного заказа (журнал audit, карточка).
ABANDONED_ACTOR = "system:abandoned-online"


def was_auto_cancelled(order) -> bool:
    """Заказ отменила автоотмена брошенных (по журналу переходов), а не человек."""
    from django.db import connection

    from apps.audit.models import AuditEvent

    from .models import Order

    if order.status != Order.STATUS_CANCELLED:
        return False
    schema = connection.schema_name
    return AuditEvent.objects.filter(
        tenant_schema="" if schema == "public" else schema,
        resource_type="order",
        resource_id=str(order.pk),
        action="order.cancelled",
        actor_display=ABANDONED_ACTOR,
    ).exists()


def _session_expires_at(order, *, now=None) -> int | None:
    """FB-33 M2i-7.1: срок сессии Stripe у заказа без e-mail — раньше автоотмены
    (`tasks.expire_abandoned_online`), чтобы оплата «в последнюю минуту» не пришла к уже
    отменённому заказу. Заказ с адресом не отменяется — сессия без своего срока. До отмены
    меньше минимума Stripe — тоже без срока: поздняя оплата вернётся (`mark_order_paid`)."""

    from django.utils import timezone

    from apps.core import payment_holds

    if has_contact_email(order) or not order.created_at:
        return None
    now = now or timezone.now()
    expires = (
        min(abandon_deadline(order), now + payment_holds.ONLINE_HOLD) - payment_holds.SESSION_MARGIN
    )
    if expires - now < payment_holds.STRIPE_MIN_SESSION:
        return None
    return int(expires.timestamp())


#: FB-33 D4a: сколько id сессий Checkout помнить на заказ (дальше — WARNING, сессия
#: закроется своим сроком, поздняя оплата вернётся).
ORDER_SESSIONS_MAX = 10
#: Потолок вызовов `Session.expire` и бюджет времени на проход автоотмены по схеме.
EXPIRE_CALLS_MAX = 50
EXPIRE_BUDGET_SECONDS = 60
_monotonic = time.monotonic


def _sessions_key(schema: str, pk) -> str:
    return f"order-sessions:{schema}:{pk}"


def _sessions_ttl() -> int:
    from datetime import timedelta

    from apps.core import payment_holds

    return int((payment_holds.ONLINE_HOLD + timedelta(hours=1)).total_seconds())


def _remember_session(order, session_id: str, connect_id: str, *, schema: str = "") -> None:
    """Запомнить id сессии Checkout заказа (кэш, не модель: сессия живёт ≤ 24 ч). Слот —
    атомарным `incr`: параллельные «Jetzt bezahlen» не затирают друг друга. Кэш недоступен
    или слоты кончились — WARNING: такую сессию закроет её срок."""
    from django.core.cache import cache
    from django.db import connection

    if not session_id:
        return
    key = _sessions_key(schema or connection.schema_name, order.pk)
    ttl = _sessions_ttl()
    try:
        cache.add(f"{key}:n", 0, ttl)
        slot = cache.incr(f"{key}:n")
        if slot > ORDER_SESSIONS_MAX:
            logger.warning(
                "order %s: more than %d checkout sessions — session not remembered",
                order.pk,
                ORDER_SESSIONS_MAX,
            )
            return
        cache.set(f"{key}:{slot}", {"id": session_id, "acct": connect_id}, ttl)
    except Exception:  # noqa: BLE001 — оплата важнее: сессия закроется своим сроком
        logger.warning("order %s: checkout session not remembered (cache)", order.pk)


def remembered_sessions(order_pk, *, schema: str = "") -> list[dict]:
    """Запомненные сессии заказа: [{"id", "acct", "key"}] (кэш недоступен — пусто)."""
    from django.core.cache import cache
    from django.db import connection

    key = _sessions_key(schema or connection.schema_name, order_pk)
    try:
        count = min(int(cache.get(f"{key}:n") or 0), ORDER_SESSIONS_MAX)
        slots = [f"{key}:{n}" for n in range(1, count + 1)]
        found = cache.get_many(slots) if slots else {}
    except Exception:  # noqa: BLE001
        logger.warning("order %s: checkout sessions unreadable (cache)", order_pk)
        return []
    return [
        {**found[slot], "key": slot}
        for slot in slots
        if isinstance(found.get(slot), dict) and found[slot].get("id")
    ]


def expire_open_sessions(order_pks, *, connect_id: str) -> int:
    """FB-33 D4a: после автоотмены закрыть открытые сессии Checkout отменённых заказов на
    connected account бизнеса (аккаунт — из `Tenant`, не из кэша). Звать ВНЕ транзакции.

    «Не ответил ≠ отказал»: первое `unknown` останавливает проход по схеме (WARNING) — id
    остаются, сессия закроется сроком, поздняя оплата вернётся прежним путём. Закрытые
    (`expired`/`closed`) id убираются. Потолок вызовов и бюджет времени — на проход.
    → сколько сессий закрыто."""
    from django.core.cache import cache

    if not connect_id:
        return 0
    started = _monotonic()
    calls = closed = 0
    for pk in order_pks:
        for item in remembered_sessions(pk):
            if calls >= EXPIRE_CALLS_MAX or _monotonic() - started > EXPIRE_BUDGET_SECONDS:
                logger.warning("expire sessions: pass budget exhausted after %d calls", calls)
                return closed
            if item.get("acct") != connect_id:
                logger.warning("order %s: checkout session of another account skipped", pk)
                continue
            calls += 1
            outcome = connect.expire_session(connect_id=connect_id, session_id=item["id"])
            if outcome == connect.UNKNOWN:
                logger.warning("expire sessions: Stripe did not answer — pass stopped")
                return closed
            closed += 1
            try:
                cache.delete(item["key"])
            except Exception:  # noqa: BLE001
                logger.warning("order %s: closed session not forgotten (cache)", pk)
    return closed


def order_checkout_url(order, tenant, *, success_url: str, cancel_url: str) -> str:
    """URL Stripe-оплаты заказа (на connected account бизнеса). FB-33 D4a: id сессии
    запоминается — автоотмена заказа закроет её (`expire_open_sessions`)."""
    url, session_id = connect.connected_checkout(
        connect_id=tenant.stripe_connect_id,
        amount_cents=int(round(order.total * 100)),
        product_name=f"Bestellung {order.reference_code}",
        metadata={
            "kind": "order_payment",
            "tenant_schema": tenant.schema_name,
            "order_id": str(order.id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
        business_type=getattr(tenant, "business_type", ""),
        payment_method_types=getattr(tenant, "stripe_payment_methods", None),
        currency=(order.currency or "EUR").lower(),
        expires_at=_session_expires_at(order),
    )
    _remember_session(order, session_id, tenant.stripe_connect_id)
    return url


def _clean_payer_email(raw) -> str:
    """FB-33 M2i-7: адрес плательщика из Stripe — строка, без управляющих знаков, ≤ 254,
    валидный по `validate_email`; иначе пусто. Адрес пишет отправитель — не верим."""
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    if not isinstance(raw, str):
        return ""
    email = raw.strip()
    if not email or len(email) > PAYER_EMAIL_MAX or any(ord(ch) < 32 for ch in email):
        return ""
    try:
        validate_email(email)
    except ValidationError:
        return ""
    return email


#: Статусы, в которых письма заказа уже не догоняют (отменён / возвращён).
_CLOSED = ("cancelled", "returned")


def _adopt_payer_email(order, raw) -> str:
    """FB-33 M2i-7 (решение владельца): заказ оформлен без e-mail — адрес плательщика из
    оплаченной сессии Stripe пишется клиенту заказа, только если у того адреса нет. Клиента
    не меняем и не ищем по адресу (заказ не перепривязывается), аккаунт не заводим.

    Возвращает причину для лога: "adopted" — записан сейчас; "same" — у клиента уже этот
    адрес (повтор вебхука после сбоя писем — письма догоняем снова, дедуп защищает);
    "own" — у клиента свой адрес; "no_payer_email" / "rejected" — адреса нет / негоден.
    Ревью (п.5): адрес отписан у другого клиента — отписка от адреса, переносим флаг."""
    from django.db import transaction

    from apps.promotions.models import Customer

    email = _clean_payer_email(raw)
    if not email:
        return "rejected" if isinstance(raw, str) and raw.strip() else "no_payer_email"
    if not order.customer_id:
        return "no_customer"
    with transaction.atomic():
        customer = Customer.objects.select_for_update().filter(pk=order.customer_id).first()
        if customer is None:
            return "no_customer"
        if customer.email:
            order.customer = customer
            return "same" if customer.email.lower() == email.lower() else "own"
        customer.email = email
        fields = ["email", "updated_at"]
        if (
            not customer.unsubscribed
            and Customer.objects.filter(email__iexact=email, unsubscribed=True)
            .exclude(pk=customer.pk)
            .exists()
        ):
            customer.unsubscribed = True
            fields.append("unsubscribed")
        customer.save(update_fields=fields)
    order.customer = customer
    return "adopted"


def _is_late_new_payment(order, payment_intent: str) -> bool:
    """FB-33 M2i-7.1: к ОТМЕНЁННОМУ заказу пришли новые деньги — платёж, которого нет в
    книге сделки. Это не повтор вебхука (тот находит свою строку), а ещё одна оплата:
    вторая открытая сессия Stripe, в т.ч. раньше, чем вернули первую. Такой платёж
    записывается и возвращается, в каком бы состоянии (paid / refunded) ни был заказ.
    Легаси без книги: повтор по intent самого заказа новым платежом не считаем."""
    from apps.core import payment_holds

    from .models import Order

    if order.status != Order.STATUS_CANCELLED:
        return False
    return payment_holds.is_new_payment("order", order, payment_intent)


def _locked_order(order_id):
    from django.core.exceptions import ValidationError

    from .models import Order

    try:
        return Order.objects.select_for_update().filter(id=order_id).first()
    except (ValidationError, ValueError):
        return None


def mark_order_processing(*, tenant_schema: str, order_id: str, payment_intent: str = "") -> bool:
    """FB-33 M2i-7.1 (ревью): Checkout завершён, деньги ещё в пути (SEPA/Klarna,
    `payment_status=unpaid`). Платёж привязывается к заказу БЕЗ смены `payment_state`:
    автоотмена брошенных такой заказ не трогает (условие «платёж не начат»), повторная
    ссылка оплаты и напоминание закрыты. Зачисление (`async_payment_succeeded`) придёт в
    `mark_order_paid` обычной новой оплатой; отказ — `release_failed_payment`.
    True — платёж привязан."""
    from django.db import transaction
    from django_tenants.utils import schema_context

    from .models import Order

    if not tenant_schema or not order_id or not payment_intent:
        return False
    with schema_context(tenant_schema), transaction.atomic():
        order = _locked_order(order_id)
        if (
            order is None
            or order.payment_state != Order.PAYMENT_UNPAID
            or order.status == Order.STATUS_CANCELLED  # поздняя оплата вернётся сама
            or order.stripe_payment_intent
        ):
            return False
        order.stripe_payment_intent = payment_intent
        order.save(update_fields=["stripe_payment_intent", "updated_at"])
    logger.info("order %s: payment is processing", order.pk)
    return True


def release_failed_payment(*, tenant_schema: str, order_id: str, payment_intent: str = "") -> bool:
    """FB-33 M2i-7.1 (ревью): отложенный платёж не прошёл — отвязываем его от неоплаченного
    заказа: снова доступны ссылка оплаты и напоминание, а заказ без e-mail снова подлежит
    автоотмене. Чужой платёж (другой intent) и оплаченный заказ не трогаем."""
    from django.db import transaction
    from django_tenants.utils import schema_context

    from .models import Order

    if not tenant_schema or not order_id or not payment_intent:
        return False
    with schema_context(tenant_schema), transaction.atomic():
        order = _locked_order(order_id)
        if (
            order is None
            or order.payment_state != Order.PAYMENT_UNPAID
            or order.stripe_payment_intent != payment_intent
        ):
            return False
        order.stripe_payment_intent = ""
        order.save(update_fields=["stripe_payment_intent", "updated_at"])
    logger.warning("order %s: processing payment failed — released", order.pk)
    return True


def mark_order_paid(
    *,
    tenant_schema: str,
    order_id: str,
    payment_intent: str = "",
    payer_email=None,
    amount_cents: int | None = None,
) -> bool:
    """Вебхук: заказ оплачен → payment_state=paid + авто-confirm (new→confirmed).
    Кросс-схемно, идемпотентно.

    FB-33 M2i-7: `payer_email` — `customer_details.email` оплаченной сессии. Заказу без
    адреса он становится адресом клиента, и письма «принят» и текущего статуса уходят на
    него — ровно по разу (dedupe_key письма), у незакрытого заказа. Выключенный канал и
    отписка уважаются внутри `enqueue_order_email`.

    FB-33 D4a (решение владельца 2026-11-24): второй платёж Stripe к оплаченному или
    возвращённому НЕотменённому заказу (главный платёж Stripe есть) — строкой книги на
    сумму `amount_cents` (`amount_total` сессии) и сразу назад (`settle_extra_payment`);
    главный intent не перезаписывается. «Касса, потом онлайн» (главного нет) — как раньше:
    строка пишется, переплата видна в карточке, WARNING без возврата."""
    from django.db import transaction
    from django_tenants.utils import schema_context

    from apps.core import payment_holds
    from apps.core.fsm import IllegalTransition

    from .models import Order
    from .state_machine import OrderSM

    if not tenant_schema or not order_id:
        return False
    with schema_context(tenant_schema):
        # FB-33 M2i-7.1: строка заказа — под блокировкой. Автоотмена брошенного заказа
        # (`tasks.expire_abandoned_online`) берёт ту же блокировку и проверяет оплату
        # повторно: либо оплата записана раньше и отмены нет, либо заказ уже отменён и
        # эта оплата возвращается ниже. Вызов Stripe (возврат) — после блокировки.
        with transaction.atomic():
            order = _locked_order(order_id)
            if order is None:
                return False
            cancelled = order.status == Order.STATUS_CANCELLED
            # Новые деньги: заказ ещё не оплачен ИЛИ к отменённому пришёл платёж, которого
            # нет в книге (второй/гоночный). Ревью B2-3: refunded НЕотменённого заказа
            # повтором вебхука не воскрешаем (как у броней).
            newly_paid = order.payment_state == Order.PAYMENT_UNPAID or _is_late_new_payment(
                order, payment_intent
            )
            # FB-33 D4a: второй платёж Stripe к неотменённому заказу — решение по свежей
            # строке под блокировкой (повтор того же intent находит свою строку; легаси —
            # повтор главного intent не дубль, ревью H1).
            extra = (
                not newly_paid
                and not cancelled
                and bool(order.stripe_payment_intent)
                and payment_intent != order.stripe_payment_intent
                and order.payment_state in (Order.PAYMENT_PAID, Order.PAYMENT_REFUNDED)
                and payment_holds.is_new_payment("order", order, payment_intent)
            )
            main_before = order.stripe_payment_intent
            fields = []
            if newly_paid and order.payment_state != Order.PAYMENT_PAID:
                order.payment_state = Order.PAYMENT_PAID
                fields.append("payment_state")
            new_intent = bool(payment_intent) and order.stripe_payment_intent != payment_intent
            # Главный платёж вторым не перезаписываем: у отменённого возврат первого
            # захватывает заказ по своему intent, у неотменённого второй возвращается
            # строкой (D4a); остальные платежи — строками книги
            # (`refunds._refund_other_card_rows`). Главного нет (касса, потом онлайн) —
            # этот платёж становится главным, как раньше.
            if new_intent and (not order.stripe_payment_intent or (newly_paid and not cancelled)):
                order.stripe_payment_intent = payment_intent
                fields.append("stripe_payment_intent")
            from apps.core import folio

            if extra:
                folio.record(
                    "order",
                    order,
                    amount_cents=int(amount_cents or 0) or int(round(order.total * 100)),
                    purpose="full",
                    method="stripe",
                    source="webhook",
                    intent=payment_intent,
                )
            elif (newly_paid or new_intent) and order.payment_state != Order.PAYMENT_REFUNDED:
                # KA-12 B2-3: платёж в фолио ДО записи состояния (opening легаси);
                # новый intent пишется и у уже «оплаченной» сделки (поздний вебхук
                # после кассы) — иначе онлайн-деньги выпали бы из книги.
                if not newly_paid and not main_before and order.payment_state == Order.PAYMENT_PAID:
                    # §9 №4 (владелец): «bezahlt» вручную, потом онлайн — не возвращаем,
                    # переплата видна в карточке.
                    logger.warning(
                        "order %s: online payment after a manual 'paid' — kept, see overpayment",
                        order.pk,
                    )
                folio.record_online("order", order, intent=payment_intent)
            if fields:
                fields.append("updated_at")
                order.save(update_fields=fields)
        # FB-33 M2i-7.1: оплата пришла к уже отменённому заказу (автоотмена брошенного,
        # отмена владельцем) — деньги возвращаются сразу; повтор вебхука второй раз не
        # возвращает (`newly_paid`). Книга сделки и состояние «refunded» — в карточке.
        # Сбой возврата не роняет вебхук (Stripe не должен получить 500 за принятую
        # оплату): пометка «Rückerstattung offen» в карточке, повтор — `retry_late_refunds`.
        try:
            payment_holds.settle_late_payment("order", order, newly_paid=newly_paid)
        except Exception:  # noqa: BLE001 — оплата уже записана; возврат повторит задача
            logger.exception("order %s: refund of a late payment crashed", order.pk)
        if extra:
            # FB-33 D4a: второй платёж — назад сразу; сбой не роняет вебхук (пометка в
            # карточке, повтор — `retry_late_refunds`).
            try:
                payment_holds.settle_extra_payment("order", order, intent=payment_intent)
            except Exception:  # noqa: BLE001 — строка в книге; возврат повторит задача
                logger.exception("order %s: refund of a second payment crashed", order.pk)
        order.refresh_from_db(fields=["payment_state"])
        if newly_paid and _late_refund_open(order):
            logger.error("order %s: late payment on a cancelled order is not refunded", order.pk)
        # FB-33 M2i-7: письма, не ушедшие без адреса, — после записи адреса И на повторе
        # вебхука (ревью п.1: сбой постановки после записи иначе терял их навсегда).
        # «created» — до авто-confirm (порядок писем); затем письмо текущего статуса
        # (ревью п.2). Дубли гасит dedupe_key `order:{id}:{event}:customer`.
        # FB-33 D3: адрес «same» (гость ввёл тот же адрес, или повтор вебхука) — догоняем
        # только недостающие письма: один запрос до авто-confirm, без рендера ушедших;
        # письмо «confirmed» после авто-confirm шлёт сама машина.
        from .notifications import enqueue_order_email, missing_customer_mails

        adopt = _adopt_payer_email(order, payer_email)
        catch_up = adopt in ("adopted", "same") and order.status not in _CLOSED
        before = order.status
        todo = None  # None — догонять всё (адрес записан сейчас)
        if catch_up and adopt == "same":
            wanted = ["created"] if before == Order.STATUS_NEW else ["created", before]
            todo = missing_customer_mails(order, wanted)
        if catch_up and (todo is None or "created" in todo):
            enqueue_order_email(order, "created")
        if order.status == Order.STATUS_NEW:
            try:
                OrderSM().apply(order, Order.STATUS_CONFIRMED)
            except IllegalTransition:
                pass
        if (
            catch_up
            and order.status != Order.STATUS_NEW
            and (todo is None or (order.status == before and before in todo))
        ):
            enqueue_order_email(order, order.status)
        if order.payment_state == Order.PAYMENT_PAID and not getattr(order.customer, "email", ""):
            # ревью п.3: деньги есть, писать некуда — владелец видит пометку в карточке
            logger.warning(
                "order %s: paid online without a contact email (%s) — confirmation not sent",
                order.pk,
                adopt,
            )
    return True
