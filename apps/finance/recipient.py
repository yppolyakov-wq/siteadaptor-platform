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
        return str(customer or "")[:1000]
    if is_company and vat:
        lines.append(f"USt-IdNr: {vat}")
    return "\n".join(p for p in lines if p)[:1000]
