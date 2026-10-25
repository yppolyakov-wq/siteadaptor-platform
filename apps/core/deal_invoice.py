"""DC-6: счёт из сделки — одна точка для всех поверхностей.

Черновик ПЕРЕИСПОЛЬЗУЕТСЯ (повторный клик не плодит дубли в Finanzen; номер
присваивает только `issue_invoice` — GoBD цел). Общий ключ сделки
(`deal_kind`/`deal_id`) совпадает с автосчётом: подтверждение сделки выпустит этот
же черновик. KA-12 Z-1 (DF-Z2): сюда же ведёт «Rechnung» из списка броней номера —
раньше там жил легаси-счёт с 7 % на всё (питание не выделялось, net-базис).
"""


def _builders():
    from apps.finance import services as finance_services

    return {
        "order": finance_services.invoice_from_order,
        "stay": finance_services.invoice_from_stay,
        "booking": finance_services.invoice_from_booking,
        "ticket": finance_services.invoice_from_ticket,
    }


def supports(kind: str) -> bool:
    return kind in _builders()


def invoice_for_deal(kind: str, obj, *, tenant):
    """(invoice, created). Отменённый счёт не переиспользуется (KA-12 E1.1: после
    Stornorechnung сделке можно выставить исправленный)."""
    from apps.finance.models import Invoice

    builder = _builders()[kind]
    ref = str(getattr(obj, "reference_code", "") or obj.pk)[:64]
    live = Invoice.objects.exclude(status=Invoice.STATUS_CANCELLED).filter(
        kind=Invoice.KIND_INVOICE
    )
    invoice = live.filter(deal_kind=kind, deal_id=ref).order_by("created_at").first()
    existing = getattr(obj, "invoice_id", None)
    if invoice is None and existing:
        invoice = live.filter(pk=existing).first()
    if invoice is not None:
        return invoice, False
    invoice = builder(obj, tenant=tenant)
    invoice.deal_kind = kind
    invoice.deal_id = ref
    invoice.save(update_fields=["deal_kind", "deal_id", "updated_at"])
    if hasattr(obj, "invoice_id"):
        obj.invoice_id = invoice.pk
        obj.save(update_fields=["invoice_id", "updated_at"])
    return invoice, True
