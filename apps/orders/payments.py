"""Онлайн-предоплата Click&Collect через Stripe Connect (P2.5c).

Checkout создаётся НА connected account бизнеса (деньги идут ему; вариант B —
application_fee=0). Подтверждение оплаты ставит вебхук на public-схеме
(apps.billing.webhooks → mark_order_paid), кросс-схемно через schema_context.
"""

import logging

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


def has_contact_email(order) -> bool:
    """У клиента заказа есть e-mail (свежо из БД: адрес мог записать вебхук оплаты)."""
    from apps.promotions.models import Customer

    if not order.customer_id:
        return False
    email = Customer.objects.filter(pk=order.customer_id).values_list("email", flat=True).first()
    return bool((email or "").strip())


def _session_expires_at(order, *, now=None) -> int | None:
    """FB-33 M2i-7.1: срок сессии Stripe у заказа без e-mail — раньше автоотмены
    (`tasks.expire_abandoned_online`), чтобы оплата «в последнюю минуту» не пришла к уже
    отменённому заказу. Заказ с адресом не отменяется — сессия без своего срока. До отмены
    меньше минимума Stripe — тоже без срока: поздняя оплата вернётся (`mark_order_paid`)."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.core import payment_holds

    if has_contact_email(order) or not order.created_at:
        return None
    now = now or timezone.now()
    deadline = order.created_at + timedelta(hours=abandoned_hours())
    expires = min(deadline, now + payment_holds.ONLINE_HOLD) - payment_holds.SESSION_MARGIN
    if expires - now < payment_holds.STRIPE_MIN_SESSION:
        return None
    return int(expires.timestamp())


def order_checkout_url(order, tenant, *, success_url: str, cancel_url: str) -> str:
    """URL Stripe-оплаты заказа (на connected account бизнеса)."""
    return connect.connected_checkout_session(
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


def _second_late_payment(order, payment_intent: str) -> bool:
    """FB-33 M2i-7.1: к отменённому заказу, оплату которого уже вернули, пришёл ЕЩЁ один
    платёж (вторая открытая сессия Stripe — другой intent, которого нет в книге сделки).
    Это новые деньги, а не повтор вебхука: их тоже надо записать и вернуть. Повтор по
    уже записанному intent сюда не попадает."""
    from apps.core.models import DealPayment

    from .models import Order

    if (
        not payment_intent
        or order.status != Order.STATUS_CANCELLED
        or order.payment_state != Order.PAYMENT_REFUNDED
        or order.stripe_payment_intent == payment_intent
    ):
        return False
    return not DealPayment.objects.filter(
        deal_kind="order", deal_id=order.pk, stripe_payment_intent=payment_intent
    ).exists()


def mark_order_paid(
    *, tenant_schema: str, order_id: str, payment_intent: str = "", payer_email=None
) -> bool:
    """Вебхук: заказ оплачен → payment_state=paid + авто-confirm (new→confirmed).
    Кросс-схемно, идемпотентно.

    FB-33 M2i-7: `payer_email` — `customer_details.email` оплаченной сессии. Заказу без
    адреса он становится адресом клиента, и письма «принят» и текущего статуса уходят на
    него — ровно по разу (dedupe_key письма), у незакрытого заказа. Выключенный канал и
    отписка уважаются внутри `enqueue_order_email`."""
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
            order = Order.objects.select_for_update().filter(id=order_id).first()
            if order is None:
                return False
            fields = []
            # Ревью B2-3: refunded не воскрешаем повтором вебхука (как у броней).
            if order.payment_state not in (
                Order.PAYMENT_PAID,
                Order.PAYMENT_REFUNDED,
            ) or _second_late_payment(order, payment_intent):
                order.payment_state = Order.PAYMENT_PAID
                fields.append("payment_state")
            if payment_intent and order.stripe_payment_intent != payment_intent:
                order.stripe_payment_intent = payment_intent
                fields.append("stripe_payment_intent")
            if fields:
                fields.append("updated_at")
                if (
                    "payment_state" in fields or "stripe_payment_intent" in fields
                ) and order.payment_state != "refunded":
                    # KA-12 B2-3: платёж в фолио ДО записи состояния (opening легаси);
                    # новый intent пишется и у уже «оплаченной» сделки (поздний вебхук
                    # после кассы) — иначе онлайн-деньги выпали бы из книги.
                    from apps.core import folio

                    folio.record_online("order", order, intent=payment_intent)
                order.save(update_fields=fields)
        # FB-33 M2i-7.1: оплата пришла к уже отменённому заказу (автоотмена брошенного,
        # отмена владельцем) — деньги возвращаются сразу; повтор вебхука второй раз не
        # возвращает (`newly_paid`). Книга сделки и состояние «refunded» — в карточке.
        payment_holds.settle_late_payment("order", order, newly_paid="payment_state" in fields)
        order.refresh_from_db(fields=["payment_state"])
        # FB-33 M2i-7: письма, не ушедшие без адреса, — после записи адреса И на повторе
        # вебхука (ревью п.1: сбой постановки после записи иначе терял их навсегда).
        # «created» — до авто-confirm (порядок писем); затем письмо текущего статуса
        # (ревью п.2). Дубли гасит dedupe_key `order:{id}:{event}:customer`.
        adopt = _adopt_payer_email(order, payer_email)
        catch_up = adopt in ("adopted", "same") and order.status not in _CLOSED
        if catch_up:
            from .notifications import enqueue_order_email

            enqueue_order_email(order, "created")
        if order.status == Order.STATUS_NEW:
            try:
                OrderSM().apply(order, Order.STATUS_CONFIRMED)
            except IllegalTransition:
                pass
        if catch_up and order.status != Order.STATUS_NEW:
            from .notifications import enqueue_order_email

            enqueue_order_email(order, order.status)
        if order.payment_state == Order.PAYMENT_PAID and not getattr(order.customer, "email", ""):
            # ревью п.3: деньги есть, писать некуда — владелец видит пометку в карточке
            logger.warning(
                "order %s: paid online without a contact email (%s) — confirmation not sent",
                order.pk,
                adopt,
            )
    return True
