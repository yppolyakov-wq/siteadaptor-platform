"""KA-12 B2-5 (E1.11): онлайн-оплата ОСТАТКА после Anzahlung.

До этого «Jetzt bezahlen» существовал только для неоплаченного депозита
(`payment_state == pending`): после Anzahlung клиент мог доплатить остаток лишь
наличными на месте. Здесь — общий для брони номера, записи и билета путь:

* `rest_payable` — тот же набор гейтов, что у публичной страницы оплаты (онлайн-оплата
  включена, Stripe Connect настроен, сделка не отменена и ещё не прошла);
* `checkout_url` — Stripe Checkout на connected account бизнеса на сумму `due`
  (место уже держит депозит — удержание KA-P6 не нужно);
* `mark_balance_paid` — вебхук `deal_balance`: строка в фолио по intent
  (идемпотентно), затем штатный `settle_payment` (состояние, счёт сделки). Статус
  сделки здесь не меняется: остаток — это деньги, а не шаг процесса.

Заявка (Handwerk) сюда не входит: по решению владельца (J-2) её остаток платится
по выставленному счёту.
"""

from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Виды сделок с онлайн-доплатой остатка.
KINDS = ("stay", "booking", "ticket")

#: Публичная страница оплаты каждого вида (она и уводит в Checkout).
PAY_ROUTES = {
    "stay": "storefront-stay-pay",
    "booking": "storefront-termin-pay",
    "ticket": "storefront-ticket-pay",
}
CONFIRM_ROUTES = {
    "stay": "storefront-stay-ok",
    "booking": "storefront-termin-ok",
    "ticket": "storefront-ticket-ok",
}


def rest_cents(kind: str, obj) -> int:
    """Сколько ещё ждём от клиента, в центах (денежный контракт)."""
    from apps.core import money_contract

    return int((money_contract.due(kind, obj) * 100).to_integral_value())


def _not_past(kind: str, obj) -> bool:
    if kind == "stay":
        return obj.departure >= timezone.localdate()
    if kind == "booking":
        return obj.start > timezone.now()
    if kind == "ticket":
        return obj.event.starts_at > timezone.now()
    return False


def rest_payable(kind: str, obj, tenant) -> bool:
    """Можно ли доплатить остаток онлайн прямо сейчас."""
    from apps.billing import connect
    from apps.core import status_registry

    if kind not in KINDS or obj is None:
        return False
    if getattr(obj, "payment_state", "") != getattr(type(obj), "PAYMENT_DEPOSIT", "deposit"):
        return False
    if obj.status in status_registry.cancelled_statuses_for(kind, tenant):
        return False
    if not (getattr(tenant, "payments_enabled", False) and connect.is_connect_configured()):
        return False
    if not getattr(tenant, "stripe_connect_id", ""):
        return False
    return _not_past(kind, obj) and rest_cents(kind, obj) > 0


def pay_path(kind: str, obj) -> str:
    from django.urls import reverse

    return reverse(PAY_ROUTES[kind], args=[obj.reference_code])


def checkout_url(kind: str, obj, tenant, *, success_url: str, cancel_url: str) -> str:
    """Stripe Checkout на остаток (сумма — `due` на момент создания сессии)."""
    from apps.billing import connect

    return connect.connected_checkout_session(
        connect_id=tenant.stripe_connect_id,
        amount_cents=rest_cents(kind, obj),
        product_name=f"Restzahlung {obj.reference_code}",
        metadata={
            "kind": "deal_balance",
            "tenant_schema": tenant.schema_name,
            "deal_kind": kind,
            "deal_id": str(obj.pk),
        },
        success_url=success_url,
        cancel_url=cancel_url,
        business_type=getattr(tenant, "business_type", ""),
        payment_method_types=getattr(tenant, "stripe_payment_methods", None),
    )


def redirect_to_checkout(request, kind: str, obj):
    """Страница «Jetzt bezahlen»: остаток → Checkout; None, если доплачивать нечего."""
    import stripe
    from django.contrib import messages
    from django.http import HttpResponse
    from django.shortcuts import redirect
    from django.urls import reverse
    from django.utils.translation import gettext as _

    from apps.core import ratelimit

    tenant = getattr(request, "tenant", None)
    if not rest_payable(kind, obj, tenant):
        return None
    # Каждый заход создаёт сессию Stripe на аккаунте бизнеса — троттлим.
    if ratelimit.hit("rest_pay", ratelimit.client_ip(request), limit=20, window=600):
        return HttpResponse(status=429)
    back = request.build_absolute_uri(reverse(CONFIRM_ROUTES[kind], args=[obj.reference_code]))
    try:
        return redirect(
            checkout_url(kind, obj, tenant, success_url=back + "?paid=1", cancel_url=back)
        )
    except stripe.error.StripeError:
        messages.error(request, _("Payment is temporarily unavailable. Please try again later."))
        return None


def mark_balance_paid(
    *,
    tenant_schema: str,
    deal_kind: str,
    deal_id: str,
    payment_intent: str,
    amount_cents: int,
    account: str = "",
    payment_status: str = "paid",
) -> bool:
    """Вебхук `deal_balance`: записать оплату остатка. Кросс-схемно, идемпотентно.

    В книгу пишется сумма, которую Stripe реально списал (`amount_total`), а не
    пересчитанная: если владелец успел изменить сделку, разница видна в «ждём».
    Переплата (остаток уже отмечен «bezahlt» на месте) записывается и сообщается
    владельцу — деньги вернуть должен он.

    Ревью B2-5: событие принимается только от connected account ЭТОГО бизнеса
    (иначе чужой аккаунт с подделанной metadata писал бы в книгу другого
    тенанта) и только с `payment_status == paid` (SEPA и др. — после зачисления).
    «До» и переплата считаются под блокировкой сделки: повтор вебхука и гонка с
    кассой не дают ложной или пропущенной «Überzahlung»."""
    from django.db import transaction
    from django_tenants.utils import schema_context

    from apps.core import folio, money_contract, transactions
    from apps.core.models import DealPayment
    from apps.promotions.notifications import _tenant

    if not tenant_schema or deal_kind not in KINDS or not deal_id or not payment_intent:
        return False
    if payment_status != "paid":
        return True  # отложенная оплата: придёт async_payment_succeeded
    tenant = _tenant(tenant_schema)
    connect_id = getattr(tenant, "stripe_connect_id", "") if tenant else ""
    if not connect_id or account != connect_id:
        logger.warning("deal_balance: account mismatch for %s", tenant_schema)
        return False
    amount = int(amount_cents or 0)
    notice = None
    with schema_context(tenant_schema), transaction.atomic():
        model = transactions.model_for(deal_kind)
        obj = model.objects.select_for_update().filter(pk=deal_id).first()
        if obj is None:
            return False
        if DealPayment.objects.filter(
            deal_kind=deal_kind, deal_id=obj.pk, stripe_payment_intent=payment_intent
        ).exists():
            return True  # повтор вебхука: платёж уже в книге (и не «переплата»)
        if getattr(obj, "payment_state", "") == "refunded":
            # Возвращённую сделку оплата остатка не «воскрешает»: платёж — в книгу,
            # владельцу — письмо.
            # refunded_cents=0: деньги ещё у бизнеса — вернуть их должен владелец.
            folio.record(
                deal_kind,
                obj,
                amount_cents=amount,
                purpose="balance",
                method="stripe",
                source="webhook",
                intent=payment_intent,
            )
            notice = (obj, amount, True)
        else:
            before = rest_cents(deal_kind, obj)
            folio.record(
                deal_kind,
                obj,
                amount_cents=amount,
                purpose="balance",
                method="stripe",
                source="webhook",
                intent=payment_intent,
            )
            obj.refresh_from_db()
            if rest_cents(deal_kind, obj) <= 0:
                money_contract.settle_payment(deal_kind, obj, source="online")
            if amount - before > 0:
                notice = (obj, amount - before, False)
    if notice is not None:
        _notify_owner(
            tenant_schema,
            deal_kind,
            notice[0],
            notice[1],
            refunded=notice[2],
            intent=payment_intent,
        )
    return True


def _notify_owner(
    schema: str, kind: str, obj, cents: int, *, refunded: bool = False, intent: str = ""
) -> None:
    """Переплата / оплата по возвращённой сделке — владельцу письмом (dedupe)."""
    from decimal import Decimal

    from django.utils import translation
    from django.utils.translation import gettext as _

    from apps.notifications.services import email_locale, notify
    from apps.promotions.notifications import _tenant

    tenant = _tenant(schema)
    email = getattr(tenant, "owner_email", "") if tenant else ""
    if not email or cents <= 0:
        return
    amount = f"{Decimal(cents) / 100:.2f}".replace(".", ",")
    with translation.override(email_locale()):
        subject = _("Überzahlung bei %(code)s") % {"code": obj.reference_code}
        body = (
            _(
                "Für %(code)s ist online eine Zahlung eingegangen, obwohl die Buchung "
                "bereits erstattet war. Bitte prüfen und %(amount)s € zurückzahlen."
            )
            if refunded
            else _(
                "Für %(code)s wurde online mehr bezahlt als offen war "
                "(Überzahlung %(amount)s €). Bitte erstatten Sie den Betrag."
            )
        ) % {"code": obj.reference_code, "amount": amount}
    try:
        notify(
            dedupe_key=f"overpaid:{schema}:{kind}:{obj.pk}:{intent}",
            type="deal_overpaid_owner",
            recipient=email,
            subject=subject,
            body=body,
        )
    except Exception:  # noqa: BLE001 — письмо не роняет вебхук
        logger.exception("balance_pay: owner notify failed %s %s", kind, obj.pk)
