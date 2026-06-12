"""PDF Rechnung (Track D / D4b) — reportlab, как poster.py (Track B4).

Pflichtangaben §14 UStG из Tenant (название/адрес/USt-IdNr. или Steuernummer);
§19 Kleinunternehmer — обязательный Hinweis вместо НДС; Storno — водяной знак.
Встроенный Helvetica (WinAnsi покрывает äöüß), без файлов шрифтов.
"""

import io
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

_INK = (0.10, 0.10, 0.12)
_MUTED = (0.42, 0.42, 0.48)


def _money(value) -> str:
    return f"{Decimal(value):.2f}".replace(".", ",") + " EUR"


def build_invoice_pdf(invoice, tenant) -> bytes:
    buffer = io.BytesIO()
    page_w, page_h = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    x = 20 * mm
    y = page_h - 25 * mm

    # Шапка: бизнес-отправитель.
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, tenant.name)
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*_MUTED)
    sender_bits = [bit for bit in [tenant.address, tenant.city] if bit]
    for bit in sender_bits:
        y -= 5 * mm
        c.drawString(x, y, bit.replace("\n", ", "))
    if tenant.vat_id:
        y -= 5 * mm
        c.drawString(x, y, f"USt-IdNr.: {tenant.vat_id}")
    elif tenant.tax_number:
        y -= 5 * mm
        c.drawString(x, y, f"Steuernummer: {tenant.tax_number}")

    # Получатель.
    y -= 15 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica", 10)
    recipient = invoice.recipient or (str(invoice.customer) if invoice.customer else "")
    for line in recipient.splitlines()[:5]:
        c.drawString(x, y, line)
        y -= 5 * mm

    # Заголовок документа.
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, f"Rechnung {invoice.number_display}")
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*_MUTED)
    if invoice.issued_at:
        c.drawRightString(page_w - x, y, f"Datum: {invoice.issued_at:%d.%m.%Y}")

    # Таблица позиций.
    y -= 12 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, "Bezeichnung")
    c.drawRightString(page_w - x - 60 * mm, y, "Menge")
    c.drawRightString(page_w - x - 30 * mm, y, "Einzelpreis")
    c.drawRightString(page_w - x, y, "Summe")
    y -= 2 * mm
    c.line(x, y, page_w - x, y)
    c.setFont("Helvetica", 9)
    for line in invoice.lines:
        y -= 6 * mm
        qty = int(line.get("qty", 1))
        unit_price = Decimal(str(line["unit_price"]))
        c.drawString(x, y, str(line["text"])[:70])
        c.drawRightString(page_w - x - 60 * mm, y, str(qty))
        c.drawRightString(page_w - x - 30 * mm, y, _money(unit_price))
        c.drawRightString(page_w - x, y, _money(unit_price * qty))

    # Итоги.
    y -= 4 * mm
    c.line(page_w / 2, y, page_w - x, y)
    y -= 6 * mm
    c.drawRightString(page_w - x - 30 * mm, y, "Netto:")
    c.drawRightString(page_w - x, y, _money(invoice.net))
    if not tenant.small_business:
        y -= 6 * mm
        c.drawRightString(page_w - x - 30 * mm, y, f"USt. {invoice.vat_rate:.0f} %:")
        c.drawRightString(page_w - x, y, _money(invoice.vat_amount))
    y -= 7 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(page_w - x - 30 * mm, y, "Gesamt:")
    c.drawRightString(page_w - x, y, _money(invoice.gross))

    # Hinweise.
    y -= 14 * mm
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(*_MUTED)
    if tenant.small_business:
        c.drawString(x, y, "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.")
        y -= 5 * mm
    if invoice.note:
        c.drawString(x, y, invoice.note[:110])

    # Сторно — диагональный водяной знак.
    if invoice.status == "cancelled":
        c.saveState()
        c.setFont("Helvetica-Bold", 60)
        c.setFillColorRGB(0.85, 0.2, 0.2)
        c.translate(page_w / 2, page_h / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, "STORNIERT")
        c.restoreState()

    c.showPage()
    c.save()
    return buffer.getvalue()
