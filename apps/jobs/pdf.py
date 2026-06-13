"""PDF Angebot / Kostenvoranschlag (G6 / F2) — reportlab, зеркало finance.pdf.

Шапка-отправитель из Tenant, получатель из Job, позиции из JobLine, итоги-снимок,
§19-Hinweis. Без юридических Pflichtangaben счёта (это смета, не Rechnung).
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


def build_quote_pdf(job, tenant) -> bytes:
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
    for bit in [b for b in [tenant.address, tenant.city] if b]:
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
    recipient = str(job.customer)
    if job.site_address:
        recipient = f"{recipient}\n{job.site_address}"
    for line in recipient.splitlines()[:5]:
        c.drawString(x, y, line)
        y -= 5 * mm

    # Заголовок документа.
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, f"Angebot {job.reference_code}")
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*_MUTED)
    c.drawRightString(page_w - x, y, f"Datum: {job.created_at:%d.%m.%Y}")
    if job.valid_until:
        y -= 5 * mm
        c.drawRightString(page_w - x, y, f"Gültig bis: {job.valid_until:%d.%m.%Y}")

    # Заголовок/описание работ.
    y -= 10 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, job.title[:80])

    # Таблица позиций.
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, "Bezeichnung")
    c.drawRightString(page_w - x - 60 * mm, y, "Menge")
    c.drawRightString(page_w - x - 30 * mm, y, "Einzelpreis")
    c.drawRightString(page_w - x, y, "Summe")
    y -= 2 * mm
    c.line(x, y, page_w - x, y)
    c.setFont("Helvetica", 9)
    for line in job.lines.all():
        y -= 6 * mm
        c.drawString(x, y, str(line.text)[:70])
        c.drawRightString(page_w - x - 60 * mm, y, str(line.qty))
        c.drawRightString(page_w - x - 30 * mm, y, _money(line.unit_price))
        c.drawRightString(page_w - x, y, _money(line.line_total))

    # Итоги.
    y -= 4 * mm
    c.line(page_w / 2, y, page_w - x, y)
    y -= 6 * mm
    c.drawRightString(page_w - x - 30 * mm, y, "Netto:")
    c.drawRightString(page_w - x, y, _money(job.net))
    if not tenant.small_business:
        y -= 6 * mm
        c.drawRightString(page_w - x - 30 * mm, y, f"USt. {job.vat_rate:.0f} %:")
        c.drawRightString(page_w - x, y, _money(job.vat_amount))
    y -= 7 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(page_w - x - 30 * mm, y, "Gesamt:")
    c.drawRightString(page_w - x, y, _money(job.gross))

    # Hinweise.
    y -= 14 * mm
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(*_MUTED)
    if tenant.small_business:
        c.drawString(x, y, "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.")
        y -= 5 * mm
    c.drawString(x, y, "Dies ist ein unverbindliches Angebot / Kostenvoranschlag.")

    c.showPage()
    c.save()
    return buffer.getvalue()
