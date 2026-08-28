"""PDF Rechnung (Track D / D4b) — reportlab, как poster.py (Track B4).

Pflichtangaben §14 UStG из Tenant (название/адрес/USt-IdNr. или Steuernummer);
§19 Kleinunternehmer — обязательный Hinweis вместо НДС; Storno — водяной знак.

I18N-7b (2026-07-31): документ печатается на языке, активном в момент сборки
(вьюха оборачивает вызов в `translation.override`), шрифт и форматы чисел/дат —
из `apps.core.documents`. НЕ переводим сами немецкие налоговые идентификаторы
(«USt-IdNr.», «Steuernummer») и ссылку на § 19 UStG: по ним счёт опознают
получатель и налоговая, перевод обозначения сделал бы документ негодным.
"""

import io
from decimal import Decimal

from django.utils.translation import gettext as _
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.documents import doc_date, fonts, money

_INK = (0.10, 0.10, 0.12)
_MUTED = (0.42, 0.42, 0.48)


def _vat_rows(invoice):
    """[(ставка, сумма налога)] счёта: по ставкам строк, иначе снимок документа."""
    from decimal import ROUND_HALF_UP, Decimal

    cent = Decimal("0.01")
    by_rate: dict[Decimal, Decimal] = {}
    for line in invoice.lines or []:
        own = line.get("vat_rate") if isinstance(line, dict) else None
        if own in (None, ""):
            return [(Decimal(invoice.vat_rate), invoice.vat_amount)]
        try:
            rate = Decimal(str(own))
            amount = Decimal(str(line["unit_price"])) * Decimal(str(line.get("qty", 1)))
        except Exception:  # noqa: BLE001 — кривой снимок не должен ронять счёт
            return [(Decimal(invoice.vat_rate), invoice.vat_amount)]
        by_rate[rate] = by_rate.get(rate, Decimal("0")) + amount
    if not by_rate:
        return [(Decimal(invoice.vat_rate), invoice.vat_amount)]
    rows = []
    for rate in sorted(by_rate, reverse=True):
        net = by_rate[rate].quantize(cent, rounding=ROUND_HALF_UP)
        rows.append((rate, (net * rate / Decimal("100")).quantize(cent, rounding=ROUND_HALF_UP)))
    return rows


def build_invoice_pdf(invoice, tenant) -> bytes:
    font, font_bold = fonts()
    buffer = io.BytesIO()
    page_w, page_h = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    x = 20 * mm
    y = page_h - 25 * mm

    # Шапка: бизнес-отправитель.
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 14)
    c.drawString(x, y, tenant.name)
    c.setFont(font, 9)
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
    c.setFont(font, 10)
    recipient = invoice.recipient or (str(invoice.customer) if invoice.customer else "")
    for line in recipient.splitlines()[:5]:
        c.drawString(x, y, line)
        y -= 5 * mm

    # Заголовок документа.
    y -= 10 * mm
    c.setFont(font_bold, 16)
    title = _("Invoice")
    c.drawString(x, y, f"{title} {invoice.number_display}")
    c.setFont(font, 9)
    c.setFillColorRGB(*_MUTED)
    if invoice.issued_at:
        label_date = _("Date")
        c.drawRightString(page_w - x, y, f"{label_date}: {doc_date(invoice.issued_at)}")

    # Таблица позиций.
    y -= 12 * mm
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 9)
    c.drawString(x, y, _("Description"))
    c.drawRightString(page_w - x - 60 * mm, y, _("Quantity"))
    c.drawRightString(page_w - x - 30 * mm, y, _("Unit price"))
    c.drawRightString(page_w - x, y, _("Amount"))
    y -= 2 * mm
    c.line(x, y, page_w - x, y)
    c.setFont(font, 9)
    for line in invoice.lines:
        y -= 6 * mm
        qty_value = Decimal(str(line.get("qty", 1)))  # A7a: дробное кол-во
        unit_price = Decimal(str(line["unit_price"]))
        c.drawString(x, y, str(line["text"])[:70])
        c.drawRightString(page_w - x - 60 * mm, y, f"{qty_value:.2f}".rstrip("0").rstrip("."))
        c.drawRightString(page_w - x - 30 * mm, y, money(unit_price))
        c.drawRightString(page_w - x, y, money(unit_price * qty_value))

    # Итоги.
    y -= 4 * mm
    c.line(page_w / 2, y, page_w - x, y)
    y -= 6 * mm
    label_net = _("Net")
    c.drawRightString(page_w - x - 30 * mm, y, f"{label_net}:")
    c.drawRightString(page_w - x, y, money(invoice.net))
    if not tenant.small_business:
        # VAT-4: § 14 Abs. 4 Nr. 8 UStG — суммы разбиваются ПО СТАВКАМ. Строки
        # счёта несут свою ставку; у старых счетов её нет, и документ печатается
        # по снимку `invoice.vat_rate` — повторное скачивание не должно давать
        # другой документ под тем же номером.
        label_vat = _("VAT")
        for rate, amount in _vat_rows(invoice):
            y -= 6 * mm
            c.drawRightString(page_w - x - 30 * mm, y, f"{label_vat} {rate:.0f} %:")
            c.drawRightString(page_w - x, y, money(amount))
    y -= 7 * mm
    c.setFont(font_bold, 11)
    label_total = _("Total")
    c.drawRightString(page_w - x - 30 * mm, y, f"{label_total}:")
    c.drawRightString(page_w - x, y, money(invoice.gross))

    # Hinweise.
    y -= 14 * mm
    c.setFont(font, 8)
    c.setFillColorRGB(*_MUTED)
    if tenant.small_business:
        # Ссылка на § 19 UStG остаётся — это идентификатор нормы, не текст.
        c.drawString(x, y, _("No VAT is charged in accordance with § 19 UStG."))
        y -= 5 * mm
    if invoice.note:
        c.drawString(x, y, invoice.note[:110])

    # Сторно — диагональный водяной знак.
    if invoice.status == "cancelled":
        c.saveState()
        c.setFont(font_bold, 60)
        c.setFillColorRGB(0.85, 0.2, 0.2)
        c.translate(page_w / 2, page_h / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, _("CANCELLED"))
        c.restoreState()

    c.showPage()
    c.save()
    return buffer.getvalue()
