"""KA-H4 (2026-10-23): возврат оплаты при отмене — одна точка для всех поверхностей.

Раньше Stripe-возврат делали только старые per-app экраны (карточка заказа,
бронь, номер). Отмена с доски, из списка, со страницы доставок или из общей
карточки сделки (выпадающий статус → `board-action`) меняла статус, а деньги
оставались у бизнеса. Теперь кабинетная смена статуса идёт через
`transactions.apply_action`, а он зовёт `refund_on_cancel`.

Клиентские и системные пути (ЛК, витрина, истечение удержаний) зовут FSM
напрямую и сюда НЕ попадают: у них своё правило (платная отмена гостем
оставляет депозит бизнесу). Им остаётся низкоуровневая `refund_payment`.

Правила:
* возврат — при переходе в статус роли «cancelled» (встроенный или свой), кроме
  `no_show`/`expired`: неявка оставляет депозит, как и раньше;
* только оплаченное картой: состояние из `REFUNDABLE_STATES`, есть payment
  intent и Stripe-Connect у бизнеса (Vorkasse/на месте/счёт — вручную);
* захват условным UPDATE (двойной клик, гонка доски и карточки → один возврат)
  + ключ идемпотентности Stripe; ошибка Stripe откатывает состояние и пишет
  владельцу письмо.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from decimal import Decimal
from enum import StrEnum

logger = logging.getLogger(__name__)

#: KA-12 E1.6: часть оплаты, которую карта не покрывает (депозит картой + остаток
#: наличными/переводом). Её владелец возвращает сам — `flash` и письмо говорят сумму.
_OFFLINE_REST: ContextVar[Decimal] = ContextVar("refund_offline_rest", default=Decimal("0"))

NO_REFUND_TARGETS = frozenset({"no_show", "expired"})


class RefundResult(StrEnum):
    NONE = "none"  # возвращать нечего / не та отмена
    REFUNDED = "refunded"
    ALREADY = "already"  # уже возвращено (повтор, гонка)
    FAILED = "failed"  # Stripe отказал — состояние «оплачено» сохранено
    MANUAL = "manual"  # доля рассрочки оплачена вне Stripe — возвращает владелец


class RefundChoiceRequired(Exception):
    """KA-D3: отмена оплаченной брони номера без выбора «erstatten / nicht erstatten»."""


#: KA-D3 (решение владельца 2026-10-23): виды, где владелец выбирает возврат сам
#: (невозвратный тариф отеля); остальные возвращают при отмене как раньше (KA-H4).
CHOICE_KINDS = frozenset({"stay"})


def _refundable_states(model) -> frozenset[str]:
    paid = getattr(model, "PAYMENT_PAID", None)
    states = {paid} if paid else set()
    deposit = getattr(model, "PAYMENT_DEPOSIT", None)
    if deposit:
        states.add(deposit)  # билет: оплачен депозит (R4)
    return frozenset(states)


def _connect_id(tenant) -> str:
    if tenant is None:
        from django.db import connection

        tenant = getattr(connection, "tenant", None)
    return (getattr(tenant, "stripe_connect_id", "") or "").strip()


def wants_refund(kind: str, target: str, source: str, tenant=None) -> bool:
    """Переход ВХОДИТ в отмену (роль cancelled), а не происходит внутри неё."""
    from apps.core import status_registry

    if target in NO_REFUND_TARGETS:
        return False
    dst = status_registry.resolve(kind, target, tenant)
    if dst is None or dst.role != "cancelled" or dst.no_refund:
        # KA-12 E1.12: свой статус отмены с флагом «ohne Erstattung» оставляет оплату.
        return False
    src = status_registry.resolve(kind, source, tenant)
    return src is None or src.role != "cancelled"


def needs_choice(kind: str, obj, target: str, source: str, tenant=None) -> bool:
    """Отмена, при которой есть что вернуть картой, у вида с выбором владельца."""
    if kind not in CHOICE_KINDS or not wants_refund(kind, target, source, tenant):
        return False
    model = type(obj)
    return (
        getattr(obj, "payment_state", "") in _refundable_states(model)
        and bool((getattr(obj, "stripe_payment_intent", "") or "").strip())
        and bool(_connect_id(tenant))
    )


def refund_payment(kind: str, obj, tenant=None) -> RefundResult:
    """Вернуть оплату сделки целиком (без проверки статуса). Безопасна к повтору."""
    import stripe

    from apps.billing import connect

    _OFFLINE_REST.set(Decimal("0"))  # подсказка относится только к ЭТОМУ возврату
    model = type(obj)
    if not hasattr(model, "PAYMENT_REFUNDED") or not hasattr(obj, "stripe_payment_intent"):
        return RefundResult.NONE
    intent = (obj.stripe_payment_intent or "").strip()
    connect_id = _connect_id(tenant)
    refundable = _refundable_states(model)
    if not connect_id:
        return RefundResult.NONE
    if _has_installment_plan(obj):
        # KA-12 E1.12: у каждой доли рассрочки свой платёж — возвращаем все оплаченные.
        return _refund_installments(kind, obj, connect_id, tenant)
    if not intent:
        return RefundResult.NONE
    # Решение — по свежему состоянию из БД (вебхук оплаты мог прийти после
    # загрузки объекта в память).
    obj.refresh_from_db(fields=["payment_state"])
    previous = obj.payment_state
    if previous not in refundable:
        return RefundResult.ALREADY if previous == model.PAYMENT_REFUNDED else RefundResult.NONE
    rest = _offline_rest(kind, obj)
    claimed = model.objects.filter(
        pk=obj.pk, payment_state=previous, stripe_payment_intent=intent
    ).update(payment_state=model.PAYMENT_REFUNDED)
    if not claimed:
        obj.refresh_from_db(fields=["payment_state"])
        return RefundResult.ALREADY
    key = _idempotency_key(kind, obj.pk, intent)
    # Окно «захвачено, Stripe ещё не ответил»: если процесс упадёт здесь, по логу
    # видно, какую сделку проверить (повтор с тем же ключом безопасен).
    logger.info("refund claimed: %s %s", kind, obj.pk)
    try:
        connect.refund(connect_id=connect_id, payment_intent=intent, idempotency_key=key)
    except stripe.error.InvalidRequestError as exc:
        if getattr(exc, "code", "") != "charge_already_refunded":
            return _rollback(kind, obj, previous, tenant)
    except Exception:  # noqa: BLE001 — сбой не должен оставить ложное «возвращено»
        return _rollback(kind, obj, previous, tenant)
    obj.refresh_from_db(fields=["payment_state"])
    from apps.core import folio

    folio.mark_refunded(kind, obj, intent=intent)  # KA-12 B2-3: книга знает о возврате
    # KA-12 B2-5: остаток, доплаченный онлайн отдельным платежом, — свой intent;
    # вернуть и его (иначе карта осталась бы списанной, а книга — «возвращено»).
    extra_cents, extra_failed = _refund_other_card_rows(kind, obj, connect_id, intent)
    rest = max(rest - Decimal(extra_cents) / 100, Decimal("0"))
    if extra_failed:
        _notify_owner_failed(kind, obj, tenant)
        return RefundResult.FAILED
    if rest > 0:
        _OFFLINE_REST.set(rest)
        _notify_owner_rest(kind, obj, rest, tenant)
    return RefundResult.REFUNDED


def _refund_other_card_rows(kind: str, obj, connect_id: str, main_intent: str):
    """Вернуть прочие платежи Stripe сделки (доплата остатка B2-5). Возвращает
    (сколько вернули в центах, был ли сбой). Повтор безопасен: ключ — на intent."""
    import stripe

    from apps.billing import connect
    from apps.core import folio
    from apps.core.models import DealPayment

    refunded = 0
    rows = (
        DealPayment.objects.filter(deal_kind=kind, deal_id=obj.pk)
        .exclude(stripe_payment_intent="")
        .exclude(stripe_payment_intent=main_intent)
    )
    for row in rows:
        open_cents = row.amount_cents - row.refunded_cents
        if open_cents <= 0:
            continue
        try:
            connect.refund(
                connect_id=connect_id,
                payment_intent=row.stripe_payment_intent,
                idempotency_key=_idempotency_key(kind, obj.pk, row.stripe_payment_intent),
            )
        except stripe.error.InvalidRequestError as exc:
            if getattr(exc, "code", "") != "charge_already_refunded":
                logger.warning("refund of extra payment failed: %s %s", kind, obj.pk)
                return refunded, True
        except Exception:  # noqa: BLE001 — сбой виден владельцу, не «возвращено»
            logger.warning("refund of extra payment failed: %s %s", kind, obj.pk)
            return refunded, True
        folio.mark_refunded(kind, obj, intent=row.stripe_payment_intent)
        refunded += open_cents
    return refunded, False


def _offline_rest(kind: str, obj) -> Decimal:
    """Оплачено сверх онлайн-платежа (остаток отмечен «bezahlt» вручную)."""
    from apps.core import money_contract as mc

    try:
        total = mc._total(kind, obj)
        online = min(mc._online_paid(kind, obj, total), total)
        paid = min(mc._paid(kind, obj, total, online), total)
    except Exception:  # noqa: BLE001 — подсказка не должна мешать возврату
        return Decimal("0")
    return max(paid - online, Decimal("0"))


def _notify_owner_rest(kind: str, obj, rest: Decimal, tenant) -> None:
    from django.db import connection
    from django.utils import translation
    from django.utils.translation import gettext as _

    from apps.notifications.services import email_locale, notify

    if tenant is None:
        tenant = getattr(connection, "tenant", None)
    recipient = (getattr(tenant, "owner_email", "") or "").strip()
    if not recipient:
        return
    code = getattr(obj, "reference_code", "") or str(obj.pk)
    amount = f"{rest:.2f}".replace(".", ",")
    with translation.override(email_locale()):
        subject = _("Restbetrag manuell erstatten: %(code)s") % {"code": code}
        body = _(
            "Bei der Stornierung von %(code)s wurde die Kartenzahlung automatisch "
            "erstattet. Den Restbetrag von %(amount)s €, der bar oder per Überweisung "
            "bezahlt wurde, erstatten Sie bitte selbst."
        ) % {"code": code, "amount": amount}
    try:
        notify(
            dedupe_key=f"refund-rest:{connection.schema_name}:{kind}:{obj.pk}",
            type="refund_rest_owner",
            recipient=recipient,
            subject=subject,
            body=body,
        )
    except Exception:  # noqa: BLE001 — письмо не должно ронять смену статуса
        logger.warning("refund rest notification not sent", exc_info=True)


def _refund_installments(kind: str, ticket, connect_id: str, tenant) -> RefundResult:
    """Вернуть каждую оплаченную долю рассрочки (R10). Захват доли — условным
    UPDATE paid→refunded, ключ идемпотентности — на платёж доли; сбой Stripe
    откатывает только эту долю. Сделка «возвращена» — когда оплаченных долей нет."""
    import stripe

    from apps.billing import connect
    from apps.events.models import InstallmentCharge

    model = type(ticket)
    plan = getattr(ticket, "installment_plan", None)
    if plan is None:
        return RefundResult.NONE
    refunded_any = failed = False
    paid = InstallmentCharge.STATUS_PAID
    for charge in plan.charges.filter(status=paid).exclude(stripe_payment_intent=""):
        claimed = InstallmentCharge.objects.filter(pk=charge.pk, status=paid).update(
            status=InstallmentCharge.STATUS_REFUNDED
        )
        if not claimed:
            continue
        intent = charge.stripe_payment_intent
        logger.info("refund claimed: %s %s installment %s", kind, ticket.pk, charge.sequence)
        try:
            connect.refund(
                connect_id=connect_id,
                payment_intent=intent,
                idempotency_key=_idempotency_key(kind, ticket.pk, intent),
            )
        except stripe.error.InvalidRequestError as exc:
            if getattr(exc, "code", "") != "charge_already_refunded":
                failed = True
        except Exception:  # noqa: BLE001 — сбой доли не должен оставить ложное «возвращено»
            failed = True
        if failed:
            InstallmentCharge.objects.filter(
                pk=charge.pk, status=InstallmentCharge.STATUS_REFUNDED
            ).update(status=paid)
            logger.warning("refund failed: %s %s installment %s", kind, ticket.pk, charge.sequence)
            _notify_owner_failed(kind, ticket, tenant)
            break
        refunded_any = True
    any_refunded = plan.charges.filter(status=InstallmentCharge.STATUS_REFUNDED).exists()
    if any_refunded and not plan.charges.filter(status=paid).exists():
        model.objects.filter(pk=ticket.pk).exclude(payment_state=model.PAYMENT_REFUNDED).exclude(
            payment_state=model.PAYMENT_NONE
        ).update(payment_state=model.PAYMENT_REFUNDED)
    ticket.refresh_from_db(fields=["payment_state"])
    if failed:
        return RefundResult.FAILED
    if plan.charges.filter(status=paid, stripe_payment_intent="").exists():
        # Оплаченная доля без платежа Stripe (отмечена вручную) — автоматически не
        # вернуть: владелец возвращает сам (ревью: раньше выходило молчаливое NONE).
        _notify_owner_failed(kind, ticket, tenant)
        return RefundResult.MANUAL
    if refunded_any:
        return RefundResult.REFUNDED
    return (
        RefundResult.ALREADY
        if ticket.payment_state == model.PAYMENT_REFUNDED
        else RefundResult.NONE
    )


def _has_installment_plan(obj) -> bool:
    if getattr(obj, "payment_state", "") == "installment":
        return True
    try:
        return getattr(obj, "installment_plan", None) is not None
    except Exception:  # noqa: BLE001 — RelatedObjectDoesNotExist у OneToOne
        return False


def _idempotency_key(kind: str, pk, intent: str) -> str:
    """Ключ на (сделка, платёж): новый платёж — новый ключ. Имя схемы наружу
    не уходит — хеш."""
    import hashlib

    from django.db import connection

    raw = f"{connection.schema_name}:{kind}:{pk}:{intent}"
    return "refund:" + hashlib.sha256(raw.encode()).hexdigest()[:40]


def _rollback(kind: str, obj, previous: str, tenant) -> RefundResult:
    model = type(obj)
    model.objects.filter(pk=obj.pk, payment_state=model.PAYMENT_REFUNDED).update(
        payment_state=previous
    )
    obj.refresh_from_db(fields=["payment_state"])
    logger.warning("refund failed: %s %s", kind, obj.pk)
    _notify_owner_failed(kind, obj, tenant)
    return RefundResult.FAILED


def _notify_owner_failed(kind: str, obj, tenant) -> None:
    from django.db import connection
    from django.utils import translation
    from django.utils.translation import gettext as _

    from apps.notifications.services import email_locale, notify

    if tenant is None:
        tenant = getattr(connection, "tenant", None)
    recipient = (getattr(tenant, "owner_email", "") or "").strip()
    if not recipient:
        return
    code = getattr(obj, "reference_code", "") or str(obj.pk)
    with translation.override(email_locale()):
        subject = _("Erstattung nicht bestätigt: %(code)s") % {"code": code}
        body = _(
            "Die Stornierung von %(code)s ist gespeichert, aber die Erstattung wurde "
            "von Stripe nicht bestätigt. Bitte prüfen Sie die Zahlung im "
            "Stripe-Dashboard und erstatten Sie sie dort bei Bedarf manuell."
        ) % {"code": code}
    try:
        notify(
            dedupe_key=f"refund-failed:{connection.schema_name}:{kind}:{obj.pk}",
            type="refund_failed_owner",
            recipient=recipient,
            subject=subject,
            body=body,
        )
    except Exception:  # noqa: BLE001 — письмо не должно ронять смену статуса
        logger.warning("refund failed notification not sent", exc_info=True)


def refund_on_cancel(
    kind: str, obj, target: str, source: str, tenant=None, refund: bool = True
) -> RefundResult:
    """Хук кабинетной смены статуса: вернуть оплату, если это вход в отмену.
    `refund=False` — владелец выбрал «nicht erstatten» (KA-D3)."""
    result = RefundResult.NONE
    if refund and wants_refund(kind, target, source, tenant):
        result = refund_payment(kind, obj, tenant)
    if result != RefundResult.FAILED:
        # KA-MC X6: что бизнес оставил себе (неявка, «nicht erstatten») — выручка.
        from apps.core.money_contract import retain_on_cancel

        retain_on_cancel(kind, obj, tenant)
    return result


def flash(request, result: RefundResult, kind: str) -> None:
    """Сообщение владельцу по результату (прежние тексты экранов)."""
    from django.contrib import messages
    from django.utils.translation import gettext as _

    if result == RefundResult.REFUNDED:
        if kind in ("booking", "stay"):
            messages.success(request, _("Deposit refunded."))
        else:
            messages.success(request, _("Payment refunded."))
        rest = _OFFLINE_REST.get()
        if rest > 0:
            _OFFLINE_REST.set(Decimal("0"))
            messages.warning(
                request,
                _(
                    "Den Restbetrag von %(amount)s € (bar oder per Überweisung bezahlt) "
                    "erstatten Sie bitte selbst."
                )
                % {"amount": f"{rest:.2f}".replace(".", ",")},
            )
    elif result == RefundResult.FAILED:
        messages.error(request, _("Refund failed — please check Stripe."))
    elif result == RefundResult.MANUAL:  # доля оплачена вне Stripe
        messages.warning(
            request,
            _(
                "Ratenzahlung: Eine Rate wurde ohne Online-Zahlung bezahlt — "
                "bitte erstatten Sie sie selbst."
            ),
        )
