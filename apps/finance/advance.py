"""KA-12 B2-8b: Anzahlungsrechnung — счёт на предоплату сделки (§ 14 Abs. 5 UStG).

Отдельный документ со своим номером на сумму Anzahlung, разбитую по ставкам НДС
сделки. Это НЕ выручка (MC-D1: выручка — при исполнении; момент налога решает
срез UStVA, `ustva.py`) и НЕ счёт сделки: `invoice_for`/«Rechnung erstellen» его
не видят, а `invoice_id` сделки он не занимает. Итоговый счёт вычтет его
(`InvoiceDeduction`, B2-8c) — до тех пор фича за флагом
`ADVANCE_INVOICES_ENABLED` (иначе НДС предоплаты был бы указан дважды, § 14c).

Оплата синхронизируется в обе стороны: пришёл депозит на сделку → предоплата
«bezahlt» (`sync_advance_paid`); оплачена предоплата (банк, кнопка) → на сделке
отмечен ТОЛЬКО депозит (`on_advance_paid`), не вся сумма.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

KINDS = ("stay", "booking", "job")
CENT = Decimal("0.01")


class AdvanceError(ValueError):
    """Предоплату выставить нельзя (сообщение — для владельца)."""


def enabled() -> bool:
    return bool(getattr(settings, "ADVANCE_INVOICES_ENABLED", False))


def _ref(obj) -> str:
    return str(getattr(obj, "reference_code", "") or obj.pk)


def live_advance(kind: str, obj):
    from .models import Invoice

    return (
        Invoice.objects.filter(kind=Invoice.KIND_ADVANCE, deal_kind=kind, deal_id=_ref(obj))
        .exclude(status=Invoice.STATUS_CANCELLED)
        .first()
    )


def deposit_received(kind: str, obj) -> bool:
    state = getattr(obj, "payment_state", "")
    if kind == "job":
        # «paid» у заявки — депозит (вебхук/банк) или всё целиком (кнопка обнуляет
        # deposit_cents, KA-H10): в обоих случаях деньги предоплаты пришли.
        return state == "paid"
    return state in ("deposit", "paid")


def advance_lines(kind: str, obj, *, small_business: bool = False) -> list:
    """Строки предоплаты: депозит пропорционально составу сделки по ставкам,
    остаток округления — в последнюю строку (Σ брутто = депозит)."""
    from django.utils.translation import gettext as _

    from apps.core.vat import deal_vat

    from .services import _net_from_gross

    deposit = Decimal(int(obj.deposit_cents or 0)) / 100
    rows = [r for r in deal_vat(kind, obj, small_business=small_business)["rows"] if r["gross"]]
    total = sum((r["gross"] for r in rows), Decimal("0"))
    if not rows or total <= 0:
        rate = Decimal("0") if small_business else Decimal(str(getattr(obj, "vat_rate", 19)))
        rows, total = [{"rate": rate, "gross": deposit}], deposit
    label = str(_("Anzahlung zu %(ref)s")) % {"ref": _ref(obj)}
    lines, left = [], deposit
    for i, row in enumerate(rows):
        gross = (
            left
            if i == len(rows) - 1
            else (deposit * row["gross"] / total).quantize(CENT, rounding=ROUND_HALF_UP)
        )
        left -= gross
        if gross <= 0:
            continue
        rate = Decimal("0") if small_business else Decimal(str(row["rate"]))
        net, _vat = _net_from_gross(gross, rate)
        text = label if len(rows) == 1 else f"{label} · {rate.normalize():f} %"
        lines.append({"text": text[:200], "qty": 1, "unit_price": str(net), "vat_rate": str(rate)})
    return lines


def _service_date(kind, obj):
    from .services import _local_date

    if kind == "stay":
        return obj.arrival
    if kind == "booking":
        return _local_date(obj.start)
    return getattr(obj, "event_date", None)


def create_advance_invoice(kind: str, obj, tenant):
    """Выставить предоплату (повтор — тот же документ). Отказ — AdvanceError."""
    from django.utils.translation import gettext as _

    from apps.core import money_contract, status_registry, transactions

    from .models import Invoice
    from .recipient import recipient_for
    from .services import compute_totals, fit_gross, issue_invoice
    from .state_machine import InvoiceSM

    if kind not in KINDS:
        raise AdvanceError(_("Für diese Art von Verkauf gibt es keine Anzahlungsrechnung."))
    small = bool(getattr(tenant, "small_business", False))
    with transaction.atomic():
        locked = transactions.model_for(kind).objects.select_for_update().get(pk=obj.pk)
        existing = live_advance(kind, locked)
        if existing is not None:
            return existing
        if int(locked.deposit_cents or 0) <= 0:
            raise AdvanceError(_("Für diesen Verkauf ist keine Anzahlung festgelegt."))
        if locked.status in status_registry.cancelled_statuses_for(kind, None):
            raise AdvanceError(_("Der Verkauf ist storniert."))
        state = getattr(locked, "payment_state", "")
        if state == "refunded" or (kind != "job" and state == "paid"):
            # Полностью оплаченной сделке нужен итоговый счёт, а не счёт на предоплату.
            raise AdvanceError(_("Der Verkauf ist bereits vollständig bezahlt."))
        final = money_contract.invoice_for(kind, locked)
        if final is not None and final.status != Invoice.STATUS_DRAFT:
            raise AdvanceError(_("Für diesen Verkauf gibt es schon eine Rechnung."))
        lines = advance_lines(kind, locked, small_business=small)
        top = max((Decimal(ln["vat_rate"]) for ln in lines), default=Decimal("0"))
        fit_gross(lines, Decimal(int(locked.deposit_cents)) / 100, top, small_business=small)
        net, vat, gross = compute_totals(lines, top, small_business=small)
        invoice = Invoice.objects.create(
            kind=Invoice.KIND_ADVANCE,
            customer=getattr(locked, "customer", None),
            recipient=recipient_for(locked),
            lines=lines,
            vat_rate=top,
            net=net,
            vat_amount=vat,
            gross=gross,
            deal_kind=kind,
            deal_id=_ref(locked),
            service_date=_service_date(kind, locked),
            note=(str(_("Anzahlung zu %(ref)s")) % {"ref": _ref(locked)})[:200],
        )
        issue_invoice(invoice, tenant=tenant)
        invoice.refresh_from_db()
        if deposit_received(kind, locked):
            InvoiceSM().apply(invoice, Invoice.STATUS_PAID)
        return invoice


def sync_advance_paid(kind: str, obj) -> None:
    """Депозит сделки получен → её выставленная предоплата «bezahlt».

    Бухгалтерия поверх уже записанной оплаты: сбой здесь логируется и НЕ откатывает
    платёж (вебхук не уходит в повтор, кнопка «bezahlt» не теряет отметку)."""
    if kind not in KINDS:
        return
    try:
        _sync_advance_paid(kind, obj)
    except Exception:  # noqa: BLE001 — оплата важнее документа; виден в логах
        logger.exception("advance invoice: sync paid failed for %s %s", kind, obj.pk)


def lock_deal(kind: str, deal_id: str):
    """Блокировка сделки по коду — ВСЕГДА раньше строки счёта (один порядок замков
    на всех путях: вебхук, банк, кнопка — без взаимной блокировки)."""
    from apps.core import transactions

    return (
        transactions.model_for(kind)
        .objects.select_for_update()
        .filter(reference_code=deal_id)
        .first()
    )


def _sync_advance_paid(kind: str, obj) -> None:
    from .models import Invoice
    from .state_machine import InvoiceSM

    with transaction.atomic():
        lock_deal(kind, _ref(obj))
        inv = live_advance(kind, obj)
        if inv is None:
            return
        inv = Invoice.objects.select_for_update().get(pk=inv.pk)
        if inv.status == Invoice.STATUS_ISSUED and deposit_received(kind, obj):
            InvoiceSM().apply(inv, Invoice.STATUS_PAID)


def on_advance_paid(invoice, *, source: str = "invoice") -> None:
    """Предоплата оплачена (банк, кнопка) → на сделке отмечен ТОЛЬКО депозит."""
    from apps.core import money_contract, transactions

    kind = invoice.deal_kind
    if kind not in KINDS or not invoice.deal_id:
        return
    model = transactions.model_for(kind)
    with transaction.atomic():
        obj = model.objects.select_for_update().filter(reference_code=invoice.deal_id).first()
        if obj is None:
            logger.warning(
                "advance %s paid: deal %s %s not found", invoice.pk, kind, invoice.deal_id
            )
            return
        if deposit_received(kind, obj):
            return
        if kind == "job":
            if int(obj.deposit_cents or 0) <= 0:
                # Депозит обнулили — «оплачено полностью» ставить нельзя.
                logger.warning(
                    "advance %s paid: job %s has no deposit", invoice.pk, invoice.deal_id
                )
                return
            if not money_contract.settle_payment("job", obj, source=source, deposit_only=True):
                logger.warning("advance %s paid: job %s not settled", invoice.pk, invoice.deal_id)
            return
        if obj.payment_state in ("paid", "deposit", "refunded"):
            logger.warning(
                "advance %s paid: deal %s state %s", invoice.pk, invoice.deal_id, obj.payment_state
            )
            return
        from apps.core import folio
        from apps.core.payment_holds import settle_late_payment

        # Пришли деньги ДОКУМЕНТА (депозит брони мог пересчитаться после выставления).
        paid_cents = int((Decimal(invoice.gross) * 100).to_integral_value())
        if paid_cents <= 0:
            logger.warning("advance %s paid: zero amount", invoice.pk)
            return
        folio.record(
            kind,
            obj,
            amount_cents=paid_cents,
            purpose="deposit",
            method={"bank": "bank"}.get(source, "invoice"),
            source=source,
        )
        obj.payment_state = "deposit" if paid_cents < obj.total_cents else "paid"
        fields = ["payment_state", "updated_at"]
        if getattr(obj, "payment_due_at", None) is not None:
            obj.payment_due_at = None
            fields.append("payment_due_at")
        obj.save(update_fields=fields)
    settle_late_payment(kind, obj, newly_paid=True)
