"""KA-MC: денежный контракт сделки — единое чтение «сколько стоит / оплачено /
возвращено / ждём / проведено в журнал» для всех 6 видов сделок.

План — docs/ka-mc-money-contract-plan-2026-10-23.md. Модуль ТОЛЬКО читает поля,
которые уже есть у моделей (миграций нет), и ничего не пишет. Он — единственный
источник карт состояний оплаты: «Offene Posten» (finance.bank), страница
«Zahlungen» (core.payments_page) и удержание онлайн-оплаты (core.payment_holds)
берут их отсюда.

Решения владельца (2026-10-23): выручка проводится в журнал ПРИ ИСПОЛНЕНИИ
(выдача, визит, выезд гостя, подтверждение билета; у заявки — выставление счёта),
не при поступлении денег. Поэтому инвариант делится по фазам (см. тест
`apps/core/tests/test_money_invariant.py`).

Ограничение (MC-E8): после возврата модель знает только состояние `refunded`,
но не сумму. Считаем возвращённой онлайн-часть (депозит или весь итог) — именно
её возвращает `core.refunds.refund_payment`; наличная часть после возврата
неизвестна до миграции `refunded_cents`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")

# kind → payment_state, означающие «ждём денег». `none` у броней/билетов —
# оплата на месте, это не долг. Порядок ключей = порядок разделов Offene Posten.
OPEN_STATES = {
    "order": ("unpaid",),
    "booking": ("pending", "deposit"),
    "stay": ("pending", "deposit"),
    "ticket": ("pending", "deposit"),
}
PAID_STATES = {k: ("paid",) for k in OPEN_STATES}
REFUNDED_STATES = {k: ("refunded",) for k in OPEN_STATES}
# Удержание места до оплаты (core.payment_holds): «денег ещё нет». У билета
# `deposit` тоже держит место (MC-T1: известное расхождение с бронями).
UNPAID_HOLD_STATES = {
    "booking": ("none", "pending"),
    "stay": ("none", "pending"),
    "ticket": ("none", "pending", "deposit"),
}


#: Способы, при которых бизнес ждёт перевод: «none» у брони с ними — тоже долг.
TRANSFER_METHODS = ("vorkasse", "invoice")


def open_q(kind: str):
    """Q «сделка ждёт денег» для Offene Posten. Бронь/билет с Vorkasse или счётом
    остаются в `none` до перевода — без этого правила банк их не сопоставил бы."""
    from django.db.models import Q

    q = Q(payment_state__in=OPEN_STATES[kind])
    if "none" in UNPAID_HOLD_STATES.get(kind, ()):
        q |= Q(payment_state="none", payment_method__in=TRANSFER_METHODS)
    return q


@dataclass(frozen=True)
class MoneyState:
    """Деньги сделки в евро (Decimal). `recognized` — сколько пишется в журнал при
    исполнении (у визита по абонементу — только Extras; у заявки — брутто счёта)."""

    total: Decimal
    paid: Decimal
    refunded: Decimal
    due: Decimal
    posted: Decimal
    recognized: Decimal
    online_paid: Decimal
    invoice: object = None


def _eur(cents) -> Decimal:
    return Decimal(int(cents or 0)) / 100


def _dec(value) -> Decimal:
    return Decimal(str(value or 0))


# --- итог к оплате ----------------------------------------------------------------


def _total(kind, obj) -> Decimal:
    if kind == "order":
        return _dec(obj.total)
    if kind in ("booking", "stay"):
        return _eur(obj.total_cents)
    if kind == "ticket":
        return _eur(obj.payable_cents)
    if kind == "job":
        return _dec(obj.payable_gross)
    if kind == "reservation":
        price = getattr(obj.promotion, "new_price", None)
        return _dec(price) * obj.quantity if price else ZERO
    raise KeyError(kind)


def _online_paid(kind, obj, total) -> Decimal:
    """Сумма онлайн-платежа (то, что вернёт refund_payment)."""
    deposit = _eur(getattr(obj, "deposit_cents", 0))
    if kind == "ticket":
        return _eur(obj.amount_due_now_cents)
    if ZERO < deposit < total:
        return deposit
    return total


def _paid(kind, obj, total, online) -> Decimal:
    state = getattr(obj, "payment_state", "")
    if kind == "reservation":
        return total if obj.status == "fulfilled" else ZERO
    if kind == "job":
        from apps.jobs.services import prepaid_cents

        return min(_eur(prepaid_cents(obj)), total) if state == "paid" else ZERO
    if state in ("paid", "refunded"):
        return total if state == "paid" else online
    if state == "deposit":
        return _eur(getattr(obj, "deposit_cents", 0))
    if state == "installment":
        plan = getattr(obj, "installment_plan", None)
        return _eur(plan.paid_cents) if plan is not None else ZERO
    return ZERO


# --- журнал -----------------------------------------------------------------------


def _posted(kind, obj, invoice) -> Decimal:
    from django.db.models import Q, Sum

    from apps.finance.models import RevenueEntry

    ident = str(obj.id)
    if kind == "job":
        if invoice is None:
            return ZERO
        q = Q(source=RevenueEntry.SOURCE_JOB, source_ref__startswith=f"inv:{invoice.pk}:")
    else:
        source = {"ticket": "event"}.get(kind, kind)
        # Все ссылки сделки: «{id}», «{id}:meal», «{id}:return», «{id}:reversal…».
        q = Q(source=source) & (Q(source_ref=ident) | Q(source_ref__startswith=f"{ident}:"))
    total = RevenueEntry.objects.filter(q).aggregate(s=Sum("amount"))["s"]
    return _dec(total)


def _recognized(kind, obj, total, invoice) -> Decimal:
    if kind == "booking":
        from apps.booking.revenue import revenue_for

        return _dec(revenue_for(obj)[0]) if obj.total_cents else ZERO
    if kind == "job":
        return _dec(invoice.gross) if invoice is not None else ZERO
    return total


def invoice_for(kind, obj):
    """Выставленный счёт сделки (по deal_kind/deal_id, затем по invoice_id) или None."""
    from apps.finance.models import Invoice

    ref = str(getattr(obj, "reference_code", "") or obj.pk)
    inv = Invoice.objects.filter(deal_kind=kind, deal_id=ref).first()
    if inv is None and getattr(obj, "invoice_id", None):
        inv = Invoice.objects.filter(pk=obj.invoice_id).first()
    return inv


def due(kind: str, obj) -> Decimal:
    """Сколько ждём от клиента — без запросов к журналу и счетам (для списков)."""
    from apps.core import status_registry

    if obj.status in status_registry.cancelled_statuses_for(kind, None):
        return ZERO
    if getattr(obj, "payment_state", "") == "refunded":
        return ZERO
    total = _total(kind, obj)
    online = min(_online_paid(kind, obj, total), total) if kind != "reservation" else total
    return max(total - min(_paid(kind, obj, total, online), total), ZERO)


def money_state(kind: str, obj) -> MoneyState:
    from apps.core import status_registry

    total = _total(kind, obj)
    online = min(_online_paid(kind, obj, total), total) if kind != "reservation" else total
    paid = min(_paid(kind, obj, total, online), total)
    refunded = paid if getattr(obj, "payment_state", "") == "refunded" else ZERO
    cancelled = obj.status in status_registry.cancelled_statuses_for(kind, None)
    due = ZERO if cancelled or getattr(obj, "payment_state", "") == "refunded" else total - paid
    invoice = invoice_for(kind, obj)
    return MoneyState(
        total=total,
        paid=paid,
        refunded=refunded,
        due=max(due, ZERO),
        posted=_posted(kind, obj, invoice),
        recognized=_recognized(kind, obj, total, invoice),
        online_paid=online,
        invoice=invoice,
    )


# --- запись: единый путь «оплачено вне Stripe» (X2) ---------------------------------

# Вид → состояние «новая/ждёт», из которого оплата подтверждает сделку (зеркало вебхуков).
_CONFIRM_ON_PAY = {"order": "new", "ticket": "pending", "booking": "pending", "stay": "pending"}


def settle_payment(kind: str, obj, *, source: str = "manual") -> bool:
    """Отметить сделку оплаченной ПОЛНОСТЬЮ вне Stripe (касса, перевод, банк).

    Единый путь для ручной кнопки «bezahlt», сопоставления выписки и оплаты счёта:
    тот же набор полей и подтверждение, что у вебхука. Возврат не «воскрешаем».
    Возвращает True, если состояние оплаты изменилось."""
    from apps.core.fsm import IllegalTransition

    paid = getattr(type(obj), "PAYMENT_PAID", "paid")
    refunded = getattr(type(obj), "PAYMENT_REFUNDED", "refunded")
    state = getattr(obj, "payment_state", None)
    if state is None or state == refunded:
        return False
    fields = []
    if state != paid:
        obj.payment_state = paid
        fields.append("payment_state")
        if kind == "job" and obj.deposit_cents:
            # KA-H10: ручная отметка заявки = оплачено полностью, не Anzahlung.
            obj.deposit_cents = 0
            fields.append("deposit_cents")
    if getattr(obj, "payment_due_at", None) is not None:
        obj.payment_due_at = None  # KA-P6: оплачено — удержание снято
        fields.append("payment_due_at")
    if fields:
        fields.append("updated_at")
        obj.save(update_fields=fields)
    _settle_invoice(kind, obj)
    if obj.status == _CONFIRM_ON_PAY.get(kind) and not _needs_manual_confirm(kind, obj):
        try:
            _sm(kind).apply(obj, "confirmed")
        except IllegalTransition:
            pass
    return "payment_state" in fields


def _sm(kind):
    from apps.core import transactions

    return transactions.sm_for(kind)


def _needs_manual_confirm(kind, obj) -> bool:
    holder = {"booking": "resource", "stay": "unit"}.get(kind)
    target = getattr(obj, holder, None) if holder else None
    return bool(getattr(target, "require_manual_confirm", False))


def _settle_invoice(kind, obj) -> None:
    """X3: оплаченная сделка закрывает и свой выставленный счёт (иначе он висит в
    Offene Posten второй строкой и уходит в Mahnung)."""
    from apps.finance.state_machine import InvoiceSM

    inv = invoice_for(kind, obj)
    if inv is not None and inv.status == "issued":
        InvoiceSM().apply(inv, "paid")


def settle_invoice_deal(invoice) -> None:
    """Счёт оплачен → сделка, из которой он выставлен, тоже оплачена (X3)."""
    from apps.core import transactions

    kind = invoice.deal_kind
    if kind not in transactions.TRANSACTION_KINDS or not invoice.deal_id:
        return
    model = transactions.model_for(kind)
    obj = model.objects.filter(reference_code=invoice.deal_id).first()
    if obj is None and kind == "job":
        obj = model.objects.filter(invoice_id=invoice.pk).first()
    if obj is not None:
        settle_payment(kind, obj, source="invoice")


# --- X1: оплата на месте получена в момент исполнения ------------------------------

#: Вид → статусы ИСПОЛНЕНИЯ (у билета выручка при подтверждении, но деньги на
#: месте приходят на входе — «attended»).
DELIVERED = {
    "order": ("picked_up", "shipped"),
    "booking": ("fulfilled",),
    "stay": ("fulfilled",),
    "ticket": ("attended",),
}
_CASH_METHODS = ("", "on_site")


def settle_on_delivery(kind: str, obj) -> bool:
    """Решение владельца X1 (2026-10-23): при исполнении сделки оплата «на месте»
    считается полученной — сделка уходит из Offene Posten. Остаток после онлайн-
    Anzahlung кассируется там же. Vorkasse/счёт/ожидание онлайн-оплаты остаются
    открытыми — это настоящая дебиторка. Идемпотентно."""
    state = getattr(obj, "payment_state", None)
    method = getattr(obj, "payment_method", "") or ""
    if kind not in DELIVERED or state is None:
        return False
    deposit = getattr(type(obj), "PAYMENT_DEPOSIT", None)
    open_cash = state in ("unpaid", "none") and method in _CASH_METHODS
    rest_on_site = (
        deposit is not None and state == deposit and method not in ("vorkasse", "invoice")
    )
    if not (open_cash or rest_on_site):
        return False
    obj.payment_state = getattr(type(obj), "PAYMENT_PAID", "paid")
    obj.save(update_fields=["payment_state", "updated_at"])
    return True


# --- X6: удержанные деньги отменённой брони — выручка ---------------------------------

RETAIN_KINDS = ("booking", "stay")


def retain_on_cancel(kind: str, obj, tenant=None) -> None:
    """Отменённая бронь, деньги по которой остались у бизнеса (неявка, «nicht
    erstatten» у номера), — выручка: удержанная Anzahlung это вознаграждение
    за резерв, а не «ничего». Запись «{id}:retained» по ставке брони,
    идемпотентно. Билет удерживает свою сумму сам (`events.revenue`)."""
    from apps.core import status_registry
    from apps.finance.services import record_revenue

    if kind not in RETAIN_KINDS:
        return
    if obj.status not in status_registry.cancelled_statuses_for(kind, tenant):
        return
    ms = money_state(kind, obj)
    kept = ms.paid - ms.refunded - ms.posted
    if kept <= ZERO:
        return
    record_revenue(
        source=kind,
        source_ref=f"{obj.id}:retained",
        amount=kept,
        vat_rate=_retain_rate(kind, obj, tenant),
        customer=obj.customer,
        note=f"Einbehalten {obj.reference_code}",
    )


def _retain_rate(kind, obj, tenant):
    if kind == "booking":
        from apps.booking.revenue import revenue_for

        return revenue_for(obj, tenant)[1]
    from apps.stays.meal import revenue_parts

    return revenue_parts(obj, tenant)[0][2]
