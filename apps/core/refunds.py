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

from django.db import transaction
from django.db.models import F
from django.utils import timezone

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
    REFUSED = "refused"  # KA-12 B2-4: частичный возврат невозможен (сумма/вид/рассрочка)
    UNCERTAIN = "uncertain"  # B2-4: Stripe не ответил — проверить возврат в Stripe
    PRICE_UNCHANGED = "price_unchanged"  # B2-4b: деньги вернули, цену поправить вручную


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
        # KA-12 B2-4: после частичного возврата — только остаток платежа, явной
        # суммой и ключом на накопленную сумму (иначе Stripe по старому ключу
        # «повторил» бы прежний частичный ответ или вернул бы весь платёж).
        open_cents, cumulative = _open_on_intent(kind, obj, intent)
        if open_cents is None:
            connect.refund(connect_id=connect_id, payment_intent=intent, idempotency_key=key)
        elif open_cents > 0:
            connect.refund(
                connect_id=connect_id,
                payment_intent=intent,
                idempotency_key=_partial_key(kind, obj.pk, intent, cumulative),
                amount_cents=open_cents,
            )
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
        # error-handling: «возвращено» оставило бы доплату остатка без повтора —
        # возвращаем прежнее состояние; повтор отмены перезапустит возврат (основной
        # платёж Stripe повторит по тому же ключу, без второго списания).
        return _rollback(kind, obj, previous, tenant)
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
            if row.refunded_cents:
                connect.refund(
                    connect_id=connect_id,
                    payment_intent=row.stripe_payment_intent,
                    idempotency_key=_partial_key(
                        kind, obj.pk, row.stripe_payment_intent, row.amount_cents
                    ),
                    amount_cents=open_cents,
                )
            else:
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


def _partial_key(kind: str, pk, intent: str, cumulative_cents: int) -> str:
    """Ключ частичного возврата — на НАКОПЛЕННУЮ сумму возвратов платежа: повтор
    того же нажатия — тот же ключ, следующий возврат — новый."""
    return _idempotency_key(kind, pk, f"{intent}:partial:{int(cumulative_cents)}")


def _open_on_intent(kind: str, obj, intent: str):
    """(ещё не возвращено, полная сумма) по строке фолио этого платежа; (None, 0) —
    строки нет или возвратов по ней не было (тогда возвращаем весь платёж)."""
    from apps.core.models import DealPayment

    row = DealPayment.objects.filter(
        deal_kind=kind, deal_id=obj.pk, stripe_payment_intent=intent
    ).first()
    if row is None or not row.refunded_cents:
        return None, 0
    return max(row.amount_cents - row.refunded_cents, 0), row.amount_cents


def refund_partial(
    kind: str,
    obj,
    *,
    cents: int,
    method: str,
    tenant=None,
    row_pk=None,
    user=None,
    reason: str = "ueberzahlung",
) -> RefundResult:
    """KA-12 B2-4 (MC-E8): частичный возврат владельцем.

    `method`: «card» — возврат части платежа Stripe (строка фолио `row_pk` или
    платёж с наибольшим невозвращённым остатком); «offline» — наличными/переводом
    (только запись в книге). Сумма захватывается условным UPDATE под блокировкой
    сделки ДО вызова Stripe: двойной клик не вернёт дважды; сбой Stripe откатывает
    захват. Грубое состояние становится «возвращено» только когда вернули всё."""
    import stripe

    from apps.billing import connect
    from apps.core import folio, transactions
    from apps.core.models import DealPayment

    cents = int(cents or 0)
    minderung = reason == "minderung"
    if (
        kind not in folio.FOLIO_KINDS
        or cents <= 0
        or method not in ("card", "offline")
        or reason not in ("ueberzahlung", "minderung")
        or (minderung and kind not in MINDERUNG_KINDS)
        or getattr(obj, "payment_state", "") == "installment"
    ):
        return RefundResult.REFUSED
    connect_id = _connect_id(tenant)
    if method == "card" and not connect_id:
        return RefundResult.REFUSED
    folio.ensure_opening(kind, obj)
    model = transactions.model_for(kind)
    claims = []  # [(row_pk, было, стало)]
    with transaction.atomic():
        locked = model.objects.select_for_update().get(pk=obj.pk)
        rows = list(
            DealPayment.objects.filter(deal_kind=kind, deal_id=obj.pk).order_by("created_at")
        )
        # Переплату возвращаем без правки цены; всё, что сверх переплаты, — только
        # как Minderung (снижение цены со сторно выручки), иначе выручка осталась
        # бы проведённой, а сделка — неотменённой.
        if minderung:
            if _minderung_blocked(kind, locked, cents):
                return RefundResult.REFUSED
        elif cents > overpaid_cents(kind, locked, rows):
            return RefundResult.REFUSED
        if method == "card":
            card = [r for r in rows if r.stripe_payment_intent]
            if row_pk:
                card = [r for r in card if str(r.pk) == str(row_pk)]
            card.sort(key=lambda r: r.amount_cents - r.refunded_cents, reverse=True)
            if not card or cents > card[0].amount_cents - card[0].refunded_cents:
                return RefundResult.REFUSED
            targets = [(card[0], cents)]
        else:
            # Наличными/переводом — только из денег, полученных НЕ картой (иначе
            # карта осталась бы списанной, а книга показала бы возврат).
            cash = [r for r in rows if not _is_card_row(r)]
            if cents > sum(r.amount_cents - r.refunded_cents for r in cash):
                return RefundResult.REFUSED
            targets, left = [], cents
            for r in cash:
                take = min(left, r.amount_cents - r.refunded_cents)
                if take > 0:
                    targets.append((r, take))
                    left -= take
        for row, take in targets:
            new = row.refunded_cents + take
            updated = DealPayment.objects.filter(
                pk=row.pk, refunded_cents=row.refunded_cents
            ).update(refunded_cents=new, refunded_at=timezone.now())
            if not updated:
                transaction.set_rollback(True)
                return RefundResult.ALREADY
            claims.append((row, row.refunded_cents, new))
    if method == "card":
        row, old, new = claims[0]
        try:
            connect.refund(
                connect_id=connect_id,
                payment_intent=row.stripe_payment_intent,
                idempotency_key=_partial_key(kind, obj.pk, row.stripe_payment_intent, new),
                amount_cents=new - old,
            )
        except (
            stripe.error.InvalidRequestError,
            stripe.error.CardError,
            stripe.error.PermissionError,
            stripe.error.AuthenticationError,
        ) as exc:
            # Stripe ОТКАЗАЛ — денег не вернули: захват назад. Арифметикой F, а не
            # сравнением со «стало»: параллельная отмена могла уже дописать строку.
            if getattr(exc, "code", "") != "charge_already_refunded":
                DealPayment.objects.filter(pk=row.pk, refunded_cents__gte=new - old).update(
                    refunded_cents=F("refunded_cents") - (new - old)
                )
                folio.forget(obj)
                logger.warning("partial refund rejected: %s %s", kind, obj.pk)
                _notify_owner_failed(kind, obj, tenant, reason="partial", cents=new - old)
                return RefundResult.FAILED
        except Exception:  # noqa: BLE001 — нет ответа: возврат мог пройти
            # Таймаут/обрыв: Stripe мог вернуть деньги. Захват оставляем (иначе
            # следующая попытка с другой суммой — новый ключ — вернула бы ещё раз);
            # владелец сверяет в Stripe.
            if minderung:  # книга уже «вернула» — цена следует за книгой
                _apply_minderung(kind, obj, cents, tenant, _short_key(row.pk, new))
            folio.forget(obj)
            logger.error("partial refund uncertain: %s %s", kind, obj.pk)
            _notify_owner_failed(kind, obj, tenant, reason="partial", cents=new - old)
            return RefundResult.UNCERTAIN
    if minderung:
        mkey = _short_key(claims[0][0].pk, claims[0][2])
        if not _apply_minderung(kind, obj, cents, tenant, mkey):
            # Деньги вернулись (Stripe подтвердил) — это НЕ «Stripe не ответил».
            _mark_refunded_if_complete(kind, obj)
            folio.forget(obj)
            return RefundResult.PRICE_UNCHANGED
    _mark_refunded_if_complete(kind, obj)
    folio.forget(obj)
    from apps.core.audit import audit_event

    audit_event(
        action="deal.partial_refund",
        resource_type=kind,
        resource_id=str(obj.pk),
        actor=user,
        changes={"cents": cents, "method": method, "reason": reason},
    )
    return RefundResult.REFUNDED


#: KA-12 B2-4b: виды со скидкой владельца (DC-5) — у билета цену не снизить.
MINDERUNG_KINDS = ("order", "booking", "stay")


def _minderung_blocked(kind: str, obj, cents: int) -> bool:
    """Minderung невозможна: сделка отменена, уступка больше итога (или — при
    выставленном счёте — не меньше его остатка: полная сумма = Stornorechnung) или
    сертификат не даёт править скидку."""
    from apps.core import deal_discount, money_contract, status_registry
    from apps.finance.models import Invoice

    if obj.status in status_registry.cancelled_statuses_for(kind, None):
        return True
    invoice = money_contract.invoice_for(kind, obj)
    if invoice is not None and invoice.status != Invoice.STATUS_DRAFT:
        # KA-12 B2-7b: выставленный счёт не отказ — Minderung выпустит корректуру.
        if Decimal(cents) / 100 >= invoice.corrected_gross:
            return True
    total = int((money_contract._total(kind, obj) * 100).to_integral_value())
    if cents > total:
        return True
    new = int(getattr(obj, "discount_cents", 0) or 0) + cents
    return deal_discount.certificate_locked(obj, new)


def _short_key(row_pk, cumulative: int) -> str:
    """Уникальный короткий ключ сторно: source_ref — varchar(64), а uuid сделки +
    uuid строки фолио туда не влезают (грабля MX-2e, повторилась в B2-4b)."""
    import hashlib

    return hashlib.md5(f"{row_pk}:{cumulative}".encode()).hexdigest()[:12]  # noqa: S324


class PriceReductionBlocked(ValueError):
    """Снижение цены невозможно (отмена/больше остатка/сертификат)."""


def reduce_price(kind: str, obj, cents: int, tenant, key: str, *, reason="Preisminderung"):
    """KA-12 B2-4b/B2-7c: снизить цену сделки на `cents` — скидка сделки выше, проведённая
    выручка сторнируется по ставкам, при выставленном счёте — Rechnungskorrektur.
    Всё в одной транзакции под блокировкой сделки; блок → PriceReductionBlocked, прочие
    ошибки пробрасываются. Деньги не двигает: возврат — забота вызывающего.
    Возвращает корректуру или None (счёта нет)."""
    from apps.core import deal_discount, transactions
    from apps.finance.models import Invoice, RevenueEntry
    from apps.finance.services import record_minderung

    with transaction.atomic():
        fresh = transactions.model_for(kind).objects.select_for_update().get(pk=obj.pk)
        # Уже применено с этим ключом (повтор формы/двойной клик) — второй раз цену
        # не снижаем: сторно и корректура идемпотентны по ключу, скидка — нет.
        done = Invoice.objects.filter(correction_key=f"mind:{key}").first()
        if (
            done is not None
            or RevenueEntry.objects.filter(
                source=kind, source_ref__startswith=f"{fresh.id}:minderung:{key}"
            ).exists()
        ):
            obj.refresh_from_db()
            return done
        if _minderung_blocked(kind, fresh, cents):
            raise PriceReductionBlocked(kind)
        new = int(getattr(fresh, "discount_cents", 0) or 0) + cents
        if kind == "stay":
            # Цена брони — та, что была; пересчёт по сегодняшним тарифам сдвинул
            # бы итог на разницу сезонов (ревью B2-4b).
            fresh.discount_cents = new
            fresh.total_cents = max(int(fresh.total_cents) - cents, 0)
            fresh.save(update_fields=["discount_cents", "total_cents", "updated_at"])
        else:
            deal_discount.set_discount(kind, fresh, cents=new, tenant=tenant, allow_closed=True)
        record_minderung(source=kind, deal=fresh, amount=Decimal(cents) / 100, key=key)
        credit = _credit_issued_invoice(kind, fresh, cents, key, reason=reason)
    obj.refresh_from_db()
    return credit


def _apply_minderung(kind: str, obj, cents: int, tenant, key: str) -> bool:
    """Снижение цены после уже сделанного возврата (повторная проверка под блокировкой:
    между захватом и Stripe сделку могли отменить). False — применить нельзя: деньги
    уже вернулись, владелец получает письмо и правит вручную (ревью B2-4b)."""
    try:
        reduce_price(kind, obj, cents, tenant, key)
    except Exception:  # noqa: BLE001 — деньги ушли; цену правит владелец, не 500
        logger.error("minderung not applied: %s %s", kind, obj.pk, exc_info=True)
        _notify_owner_failed(kind, obj, tenant, reason="price", cents=cents)
        obj.refresh_from_db()
        return False
    return True


def _credit_issued_invoice(kind: str, obj, cents: int, key: str, *, reason="Preisminderung"):
    """KA-12 B2-7b: у сделки выставлен счёт — уступка оформляется Rechnungskorrektur
    (свой номер, минус по ставкам). В транзакции Minderung: не вышла корректура —
    откатывается и снижение цены (документы и сделка не расходятся)."""
    from apps.core import money_contract
    from apps.finance.models import Invoice
    from apps.finance.services import create_credit

    invoice = money_contract.invoice_for(kind, obj)
    if invoice is None or invoice.status == Invoice.STATUS_DRAFT:
        return None
    return create_credit(invoice, Decimal(cents) / 100, reason=reason, key=f"mind:{key}")


def _is_card_row(row) -> bool:
    return bool(row.stripe_payment_intent) or row.method == "stripe"


def overpaid_cents(kind: str, obj, rows=None) -> int:
    """Сколько получено сверх цены (по книге). Только это пока можно вернуть
    частично; отменённая сделка — 0 (возврат при отмене — свой путь)."""
    from apps.core import money_contract, status_registry
    from apps.core.models import DealPayment

    if obj.status in status_registry.cancelled_statuses_for(kind, None):
        return 0
    if rows is None:
        rows = DealPayment.objects.filter(deal_kind=kind, deal_id=obj.pk)
    net = sum(r.amount_cents - r.refunded_cents for r in rows)
    total = int((money_contract._total(kind, obj) * 100).to_integral_value())
    return max(net - total, 0)


def _mark_refunded_if_complete(kind: str, obj) -> None:
    """Вернули всё полученное — грубое состояние «возвращено» (условным UPDATE)."""
    from django.db.models import Sum

    from apps.core.models import DealPayment

    sums = DealPayment.objects.filter(deal_kind=kind, deal_id=obj.pk).aggregate(
        amount=Sum("amount_cents"), refunded=Sum("refunded_cents")
    )
    model = type(obj)
    if sums["amount"] and sums["refunded"] == sums["amount"] and hasattr(model, "PAYMENT_REFUNDED"):
        model.objects.filter(pk=obj.pk).exclude(payment_state=model.PAYMENT_REFUNDED).update(
            payment_state=model.PAYMENT_REFUNDED
        )
    obj.refresh_from_db(fields=["payment_state"])


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


def _notify_owner_failed(kind: str, obj, tenant, *, reason: str = "cancel", cents: int = 0) -> None:
    """Письмо владельцу о сбое возврата. `reason`: cancel (отмена) · partial (частичный
    возврат) · price (деньги вернули, цену не снизили). Ключ — на причину и сумму:
    второй сбой по той же сделке тоже доходит (ревью silent-failure)."""
    from django.db import connection
    from django.utils import timezone, translation
    from django.utils.translation import gettext as _

    from apps.notifications.services import email_locale, notify

    if tenant is None:
        tenant = getattr(connection, "tenant", None)
    recipient = (getattr(tenant, "owner_email", "") or "").strip()
    code = getattr(obj, "reference_code", "") or str(obj.pk)
    if not recipient:
        logger.error("refund problem (%s) for %s %s, owner has no email", reason, kind, code)
        return
    amount = f"{Decimal(int(cents or 0)) / 100:.2f}".replace(".", ",")
    with translation.override(email_locale()):
        subject = _("Erstattung nicht bestätigt: %(code)s") % {"code": code}
        if reason == "price":
            body = _(
                "Für %(code)s wurden %(amount)s € erstattet, aber der Preis konnte nicht "
                "angepasst werden. Bitte setzen Sie den Rabatt in der Buchung von Hand."
            ) % {"code": code, "amount": amount}
        elif reason == "partial":
            body = _(
                "Die Erstattung von %(amount)s € für %(code)s wurde von Stripe nicht "
                "bestätigt. Bitte prüfen Sie die Zahlung im Stripe-Dashboard."
            ) % {"code": code, "amount": amount}
        else:
            body = _(
                "Die Stornierung von %(code)s ist gespeichert, aber die Erstattung wurde "
                "von Stripe nicht bestätigt. Bitte prüfen Sie die Zahlung im "
                "Stripe-Dashboard und erstatten Sie sie dort bei Bedarf manuell."
            ) % {"code": code}
    try:
        notify(
            dedupe_key=(
                f"refund-failed:{connection.schema_name}:{kind}:{obj.pk}:{reason}:{cents}:"
                f"{timezone.now():%Y%m%d%H%M}"
            ),
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
