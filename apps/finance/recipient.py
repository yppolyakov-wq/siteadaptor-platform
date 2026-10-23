"""CO-2a: получатель счёта — один выбор на все построители (план
docs/co2-v2-company-billing-plan-2026-10-21.md).

До CO-2a счёт брони/записи шёл на имя гостя, даже если бронировала фирма с
реквизитами (SH-23 их собирал, но ни один построитель не читал) — § 14 UStG.
Порядок: явный плательщик заказа → фирма со сделки (+ адрес из справочника) →
привязанная компания клиента → клиент.
"""


def recipient_for(deal) -> str:
    customer = getattr(deal, "customer", None)
    company = getattr(customer, "company", None) if customer is not None else None
    is_company = getattr(deal, "customer_type", "") == "company"
    firm = (getattr(deal, "billing_company", "") or "").strip()
    vat = (getattr(deal, "billing_vat_id", "") or "").strip()
    payer = (getattr(deal, "billing_name", "") or "").strip()
    address = (getattr(deal, "billing_address", "") or "").strip()

    if payer:
        lines = [payer, address]
    elif is_company and firm:
        if not address and company is not None:
            city = f"{company.postal_code} {company.city}".strip()
            address = "\n".join(p for p in (company.street, city) if p)
        lines = [firm, address]
        vat = vat or (getattr(company, "vat_id", "") or "")
    elif company is not None:
        return company.invoice_recipient[:1000]
    else:
        # KA-12 E1.3: частному лицу — имя И адрес (§ 14 Abs. 4 Nr. 1 UStG; без адреса
        # допустим только Kleinbetragsrechnung до 250 €). Адрес — со сделки.
        own = address or (getattr(deal, "shipping_address", "") or "").strip()
        return "\n".join(p for p in (str(customer or ""), own) if p)[:1000]
    if is_company and vat:
        lines.append(f"USt-IdNr: {vat}")
    return "\n".join(p for p in lines if p)[:1000]


#: § 33 UStDV: Kleinbetragsrechnung — до 250 € брутто адрес получателя не обязателен.
KLEINBETRAG_LIMIT = 250


def needs_address(invoice) -> bool:
    """KA-12 E1.3: счёт > 250 € брутто без адреса получателя выставлять нельзя.
    «Адрес» = получатель длиннее одной строки (имя + хотя бы строка адреса)."""
    from decimal import Decimal

    if getattr(invoice, "kind", "invoice") == "storno":
        return False
    if Decimal(invoice.gross or 0) <= KLEINBETRAG_LIMIT:
        return False
    lines = [ln for ln in (invoice.recipient or "").splitlines() if ln.strip()]
    return len(lines) < 2
