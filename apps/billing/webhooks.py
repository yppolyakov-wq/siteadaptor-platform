"""Stripe-вебхуки биллинга: верификация подписи + диспетчер на SubscriptionSM.

Свой эндпоинт (не webhook-view dj-stripe) — полный контроль и тестируемость без
внешних вызовов. Идемпотентность: по event.id (Redis cache.add) + сама SM
(повтор статуса = no-op). Эндпоинт смонтирован на public-схеме (Stripe шлёт на
один URL — см. config/urls_public). Резолв арендатора — по stripe_customer_id
или metadata.tenant_id / client_reference_id.
"""

import logging
import re
from datetime import UTC, datetime

import stripe
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.tenants.models import Tenant

from . import connect, featured, services

logger = logging.getLogger("billing")

# Окно дедупликации event.id (Stripe ретраит вебхуки до 3 суток).
_EVENT_TTL = 60 * 60 * 24 * 3


def _epoch_to_dt(epoch):
    if not epoch:
        return None
    return datetime.fromtimestamp(int(epoch), tz=UTC)


def _tenant_from_object(obj: dict) -> Tenant | None:
    customer_id = obj.get("customer")
    if not customer_id and obj.get("object") == "customer":
        customer_id = obj.get("id")
    meta = obj.get("metadata") or {}
    tenant_id = meta.get("tenant_id") or obj.get("client_reference_id")

    qs = Tenant.objects.all()
    if customer_id:
        tenant = qs.filter(stripe_customer_id=customer_id).first()
        if tenant:
            return tenant
    if tenant_id:
        return qs.filter(id=tenant_id).first()
    return None


# SEC-D1: виды событий, которые приходят ТОЛЬКО с connected-аккаунта бизнеса. Для них
# `event.account` обязан совпадать со `stripe_connect_id` тенанта из metadata — иначе
# владелец с подключённым Stripe создал бы Checkout у СЕБЯ с чужой metadata (оплатить
# чужой заказ «за копейку», выпустить себе Pass, активировать подписку без оплаты).
CONNECT_KINDS = frozenset(
    {
        "booking_deposit",
        "order_payment",
        "stay_deposit",
        "deal_balance",
        "gift_voucher",
        "job_deposit",
        "pass_purchase",
        "event_ticket",
        "event_installment",
    }
)


#: SEC-D3: сессия Checkout «оплачена» — деньги действительно зачислены.
PAID_STATUSES = frozenset({"paid", "no_payment_required"})


def _connect_account_ok(meta: dict, account: str) -> bool:
    schema = str(meta.get("tenant_schema") or "")
    if not account or not schema:
        return False
    connect_id = (
        Tenant.objects.filter(schema_name=schema)
        .values_list("stripe_connect_id", flat=True)
        .first()
    )
    return bool(connect_id) and connect_id == account


#: Потолок длины id из metadata в логе (значение пишет отправитель).
_LOG_ID_MAX = 64


def _log_id(value) -> str:
    """id из metadata для лога: значение пишет отправитель — без управляющих знаков и пробелов
    (подделка строк лога), не длиннее `_LOG_ID_MAX`."""
    return re.sub(r"[^\w-]", "?", str(value or ""))[:_LOG_ID_MAX] or "-"


def _money_not_booked(
    kind: str, meta: dict, obj: dict, *, id_key: str, event_id: str = "", notify: bool = True
) -> None:
    """FB-33 D3: деньги пришли на аккаунт бизнеса, а сделки нет — ERROR и письмо владельцу.

    В лог — только вид, схема, id сделки из metadata, intent и event.id: `meta` целиком несёт
    имя и e-mail покупателя (`pass_purchase`). Ответ вебхука остаётся 200: повтор Stripe того
    же события ничего не найдёт. Письмо — `balance_pay._notify_unbooked` (ключ на платёж,
    без ПДн); без intent ключ — по id сессии, без обоих — только лог."""
    schema = str(meta.get("tenant_schema") or "")
    intent = str(obj.get("payment_intent") or "")
    logger.error(
        "stripe webhook %s: payment NOT booked (schema=%s, %s=%s, payment_intent=%s, event=%s)",
        kind,
        schema,
        id_key,
        _log_id(meta.get(id_key)),
        intent or "-",
        event_id or "-",
    )
    ref = intent or str(obj.get("id") or "")
    if not notify or not schema or not ref:
        return
    from apps.core.balance_pay import _notify_unbooked

    tenant = Tenant.objects.filter(schema_name=schema).first()
    if tenant is None:
        return
    _notify_unbooked(tenant, schema, kind, meta.get(id_key), ref, int(obj.get("amount_total") or 0))


def handle_event(event_type: str, obj: dict, account: str = "", event_id: str = "") -> None:
    """Применить эффект события к арендатору (идемпотентно через SM).

    SEC-D1: источник события — часть авторизации. Connect-виды принимаются только от
    аккаунта своего бизнеса; платформенные (подписка, featured) — только без `account`;
    `account.updated` — только о самом себе. Чужое отбрасывается с логом, без эффекта.
    """
    meta = obj.get("metadata") or {}
    kind = str(meta.get("kind") or "")

    if kind in CONNECT_KINDS:
        if not _connect_account_ok(meta, account):
            logger.error(
                "stripe webhook %s/%s: account mismatch (schema=%s, account=%s) — dropped",
                event_type,
                kind,
                meta.get("tenant_schema"),
                account or "-",
            )
            return
    elif event_type == "account.updated":
        if not account or str(obj.get("id") or "") != account:
            logger.error("stripe webhook account.updated: object/account mismatch — dropped")
            return
    elif account:
        # Платформенные события (подписка, featured, без kind) с connected-аккаунта —
        # подделка metadata: `client_reference_id`/`tenant_id` там выбирает отправитель.
        logger.warning(
            "stripe webhook %s from connected account %s — dropped (platform-only kind %r)",
            event_type,
            account,
            kind,
        )
        return

    # SEC-D3: отложенные способы (SEPA, Sofort, Klarna) — `completed` приходит ДО
    # зачисления денег (`payment_status=unpaid`), сами деньги — `async_payment_succeeded`.
    # `deal_balance` разбирает это сам (mark_balance_paid проверяет payment_status).
    if kind and kind != "deal_balance" and (kind in CONNECT_KINDS or kind == "featured"):
        from apps.core import payment_holds

        if event_type == "checkout.session.async_payment_succeeded":
            event_type = "checkout.session.completed"
            payment_holds.clear_in_flight(meta)
        elif event_type == "checkout.session.async_payment_failed":
            # Деньги не пришли: место держим ещё час (оплата картой), дальше сделку снимет
            # удержание (expire_overdue). Оплату не ставим.
            logger.warning(
                "stripe webhook %s: async payment failed (schema=%s, event=%s)",
                kind,
                meta.get("tenant_schema"),
                event_id or "-",
            )
            payment_holds.release_after_failed(meta)
            if kind == "order_payment":
                # FB-33 M2i-7.1: платёж отвязан — заказ снова можно оплатить, а брошенный
                # без e-mail снова подлежит автоотмене.
                from apps.orders.payments import release_failed_payment

                release_failed_payment(
                    tenant_schema=meta.get("tenant_schema", ""),
                    order_id=meta.get("order_id", ""),
                    payment_intent=obj.get("payment_intent") or "",
                )
            return
        elif event_type == "checkout.session.completed" and (
            obj.get("payment_status") not in PAID_STATUSES
        ):
            logger.info("stripe webhook %s: payment pending (%s)", kind, obj.get("payment_status"))
            # Ревью волны 1 (M3): пока деньги в пути, удержание не снимает сделку.
            payment_holds.hold_while_processing(meta)
            if kind == "order_payment":
                # FB-33 M2i-7.1: у заказа удержания нет — платёж «в пути» привязывается к
                # заказу (без смены оплаты), и автоотмена брошенных его не трогает.
                from apps.orders.payments import mark_order_processing

                mark_order_processing(
                    tenant_schema=meta.get("tenant_schema", ""),
                    order_id=meta.get("order_id", ""),
                    payment_intent=obj.get("payment_intent") or "",
                )
            return

    # Разовый платёж за продвижение листинга (P2.4b) — не подписка: ставим срок
    # на сам листинг (public-схема), статус подписки не трогаем. Различаем по
    # metadata.kind, проставленному в create_featured_checkout_session.
    if event_type == "checkout.session.completed" and meta.get("kind") == "featured":
        # SEC-D1: срок — только из таблицы планов (metadata несёт отправитель).
        try:
            plan = featured.get_plan(int(meta.get("days") or 0))
        except (TypeError, ValueError):
            plan = None
        if plan is None:
            logger.error("stripe webhook featured: days %r not a plan — dropped", meta.get("days"))
            return
        ok = services.apply_featured_purchase(
            tenant_schema=meta.get("tenant_schema", ""),
            promo_uuid=meta.get("promo_uuid", ""),
            listing_kind=meta.get("listing_kind", ""),
            source_ref=meta.get("source_ref", ""),
            days=plan.days,
            payment_ref=obj.get("payment_intent") or obj.get("id", ""),
        )
        if not ok:
            # платёж платформе (не бизнесу) — без письма владельцу
            _money_not_booked(
                "featured", meta, obj, id_key="promo_uuid", event_id=event_id, notify=False
            )
        return

    # Депозит за бронь (P2.5b): Checkout на connected account → бронь оплачена.
    # Бронь живёт в TENANT-схеме (tenant_schema из metadata), статус подписки не трогаем.
    if event_type == "checkout.session.completed" and meta.get("kind") == "booking_deposit":
        from apps.booking.payments import mark_deposit_paid

        ok = mark_deposit_paid(
            tenant_schema=meta.get("tenant_schema", ""),
            booking_id=meta.get("booking_id", ""),
            payment_intent=obj.get("payment_intent", ""),
        )
        if not ok:
            _money_not_booked("booking_deposit", meta, obj, id_key="booking_id", event_id=event_id)
        return

    # Предоплата заказа Click&Collect (P2.5c): Checkout на connected account.
    if event_type == "checkout.session.completed" and meta.get("kind") == "order_payment":
        from apps.orders.payments import mark_order_paid

        # FB-33 M2i-7: адрес плательщика — для заказа, оформленного без e-mail в форме
        # (сюда доходит только оплаченная сессия своего бизнеса; проверка адреса — там).
        details = obj.get("customer_details")
        ok = mark_order_paid(
            tenant_schema=meta.get("tenant_schema", ""),
            order_id=meta.get("order_id", ""),
            payment_intent=obj.get("payment_intent", ""),
            payer_email=details.get("email") if isinstance(details, dict) else None,
            amount_cents=int(obj.get("amount_total") or 0),
        )
        if not ok:
            _money_not_booked("order_payment", meta, obj, id_key="order_id", event_id=event_id)
        return

    # Депозит за date-range-бронь / Übernachtung (Track E / E4): Checkout на
    # connected account → бронь оплачена (кросс-схемно, статус подписки не трогаем).
    if event_type == "checkout.session.completed" and meta.get("kind") == "stay_deposit":
        from apps.stays.payments import mark_stay_paid

        ok = mark_stay_paid(
            tenant_schema=meta.get("tenant_schema", ""),
            booking_id=meta.get("booking_id", ""),
            payment_intent=obj.get("payment_intent", ""),
        )
        if not ok:
            _money_not_booked("stay_deposit", meta, obj, id_key="booking_id", event_id=event_id)
        return

    # KA-12 B2-5 (E1.11): доплата остатка после Anzahlung (номер/запись/билет).
    # Деньги — только от connected account этого бизнеса (`account` события) и только
    # зачисленные (`payment_status`; отложенные способы — async_payment_succeeded).
    if (
        event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded")
        and meta.get("kind") == "deal_balance"
    ):
        from apps.core.balance_pay import mark_balance_paid

        ok = mark_balance_paid(
            tenant_schema=meta.get("tenant_schema", ""),
            deal_kind=meta.get("deal_kind", ""),
            deal_id=meta.get("deal_id", ""),
            payment_intent=obj.get("payment_intent") or "",
            amount_cents=int(obj.get("amount_total") or 0),
            account=account or "",
            payment_status=obj.get("payment_status") or "",
        )
        if not ok:
            _money_not_booked("deal_balance", meta, obj, id_key="deal_id", event_id=event_id)
        return

    # Подарочный сертификат (G1) — Checkout на connected account → выпуск Voucher.
    if event_type == "checkout.session.completed" and meta.get("kind") == "gift_voucher":
        from apps.loyalty.gift import mark_gift_voucher_paid

        ok = mark_gift_voucher_paid(
            tenant_schema=meta.get("tenant_schema", ""),
            gift_id=meta.get("gift_id", ""),
            payment_intent=obj.get("payment_intent", ""),
        )
        if not ok:
            _money_not_booked("gift_voucher", meta, obj, id_key="gift_id", event_id=event_id)
        return

    # Anzahlung за смету Handwerker (A7c) — TENANT-схема, статус подписки не трогаем.
    if event_type == "checkout.session.completed" and meta.get("kind") == "job_deposit":
        from apps.jobs.payments import mark_deposit_paid as mark_job_deposit_paid

        ok = mark_job_deposit_paid(
            tenant_schema=meta.get("tenant_schema", ""),
            job_id=meta.get("job_id", ""),
            payment_intent=obj.get("payment_intent", ""),
        )
        if not ok:
            _money_not_booked("job_deposit", meta, obj, id_key="job_id", event_id=event_id)
        return

    # Покупка Mehrfachkarte онлайн (A3) — TENANT-схема, статус подписки не трогаем.
    if event_type == "checkout.session.completed" and meta.get("kind") == "pass_purchase":
        from apps.booking.pass_payments import purchase_pass

        ok = purchase_pass(
            tenant_schema=meta.get("tenant_schema", ""),
            plan_id=meta.get("plan_id", ""),
            name=meta.get("name", ""),
            email=meta.get("email", ""),
            payment_intent=obj.get("payment_intent", ""),
        )
        if not ok:
            _money_not_booked("pass_purchase", meta, obj, id_key="plan_id", event_id=event_id)
        return

    # Билет на событие (A6c) — TENANT-схема, статус подписки не трогаем.
    if event_type == "checkout.session.completed" and meta.get("kind") == "event_ticket":
        from apps.events.payments import mark_ticket_paid

        ok = mark_ticket_paid(
            tenant_schema=meta.get("tenant_schema", ""),
            ticket_id=meta.get("ticket_id", ""),
            payment_intent=obj.get("payment_intent", ""),
        )
        if not ok:
            _money_not_booked("event_ticket", meta, obj, id_key="ticket_id", event_id=event_id)
        return

    # Рассрочка билета (R10b): первая доля оплачена → создать план + график.
    if event_type == "checkout.session.completed" and meta.get("kind") == "event_installment":
        from apps.events.payments import create_installment_plan

        ok = create_installment_plan(
            tenant_schema=meta.get("tenant_schema", ""),
            ticket_id=meta.get("ticket_id", ""),
            payment_intent=obj.get("payment_intent", ""),
        )
        if not ok:
            _money_not_booked("event_installment", meta, obj, id_key="ticket_id", event_id=event_id)
        return

    # Stripe Connect (P2.5): статус connected-аккаунта бизнеса. obj — это Account,
    # его id == Tenant.stripe_connect_id. Подписку не трогаем.
    if event_type == "account.updated":
        connect.set_connect_status(obj.get("id", ""), bool(obj.get("charges_enabled")))
        return

    tenant = _tenant_from_object(obj)
    if tenant is None:
        logger.warning("stripe webhook %s: tenant not resolved", event_type)
        return

    if event_type == "checkout.session.completed":
        # SEC-D3 (ревью волны 1): подписка по SEPA — после зачисления; включает её
        # customer.subscription.updated (status=active), а не завершённый Checkout.
        if obj.get("payment_status") not in PAID_STATUSES:
            logger.info("stripe webhook subscription: payment pending — waiting")
            return
        services.activate_subscription(tenant)
    elif event_type == "invoice.payment_failed":
        services.mark_past_due(tenant)
    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        status = obj.get("status")
        ends_at = _epoch_to_dt(obj.get("current_period_end"))
        if event_type.endswith("deleted") or status in (
            "past_due",
            "unpaid",
            "canceled",
            "incomplete_expired",
        ):
            services.mark_past_due(tenant)
        elif status in ("active", "trialing"):
            services.activate_subscription(tenant, ends_at=ends_at)


def _webhook_secrets() -> list[str]:
    """Секреты подписи: эндпоинт платформы и эндпоинт подключённых аккаунтов (Connect).

    У Stripe это два разных эндпоинта на один URL, у каждого свой Signing secret.
    Что событие с аккаунта бизнеса делает только своё, проверяет `handle_event`
    (SEC-D1: `event.account` против `stripe_connect_id` тенанта)."""
    secrets = [settings.STRIPE_WEBHOOK_SECRET]
    connect = getattr(settings, "STRIPE_CONNECT_WEBHOOK_SECRET", "") or ""
    if connect and connect not in secrets:
        secrets.append(connect)
    return secrets


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Эндпоинт Stripe-вебхука (public-схема)."""
    payload = request.body
    sig = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    if not settings.STRIPE_WEBHOOK_SECRET:
        # SEC-D2: HMAC с пустым ключом вычислит кто угодно — construct_event принял бы
        # любую подделку. Без секрета вебхук выключен (503 → Stripe повторит после настройки).
        logger.error("stripe webhook: STRIPE_WEBHOOK_SECRET is not configured")
        return HttpResponse(status=503)
    event = None
    secrets = _webhook_secrets()
    for secret in secrets:
        try:
            event = stripe.Webhook.construct_event(payload, sig, secret)
            # Эндпоинт подключённых аккаунтов шлёт ТОЛЬКО события с `account`. Без него
            # такое событие — подделка утёкшим секретом под платформенное (подписка,
            # featured): `handle_event` по одному `account` их не различил бы.
            if secret != secrets[0] and not event.get("account"):
                return HttpResponseBadRequest("connect event without account")
            break
        except ValueError:
            return HttpResponseBadRequest("invalid payload")
        except stripe.error.SignatureVerificationError:
            continue  # подпись другого эндпоинта (платформа / подключённые аккаунты)
    if event is None:
        return HttpResponseBadRequest("invalid signature")

    # Дедупликация по event.id: первый приход выигрывает cache.add, повторы — no-op.
    evt_key = f"stripe_evt:{event['id']}"
    if not cache.add(evt_key, "1", timeout=_EVENT_TTL):
        return HttpResponse(status=200)

    try:
        handle_event(
            event["type"],
            event["data"]["object"],
            account=event.get("account") or "",
            event_id=str(event.get("id") or ""),
        )
    except Exception:
        # Ревью silent-failure: ключ дедупа снят — повтор Stripe обработается заново,
        # иначе упавшая оплата никогда не попала бы в книгу.
        cache.delete(evt_key)
        raise
    return HttpResponse(status=200)
