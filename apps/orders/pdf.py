"""Lieferschein-PDF — накладная к заказу (A2b), reportlab, зеркало jobs/finance.

Накладная к заказу доставки: шапка-отправитель из Tenant, получатель и адрес из
Order, позиции (количество + название, без цен — это Lieferschein, не Rechnung) +
вырезаемая адресная этикетка внизу для наклейки на посылку.

I18N-7b: подписи переводятся, язык задаёт вьюха (`translation.override`).
"""

import io

from django.utils.translation import gettext as _
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.documents import doc_date, fonts

_INK = (0.10, 0.10, 0.12)
_MUTED = (0.42, 0.42, 0.48)


def _item_label(item) -> str:
    parts = [item.title_snapshot]
    if item.variant_label:
        parts.append(f"({item.variant_label})")
    if item.modifiers_label:
        parts.append(f"+ {item.modifiers_label}")
    return " ".join(parts)


def build_delivery_note_pdf(order, tenant) -> bytes:
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
    for bit in [b for b in [tenant.address, tenant.city] if b]:
        y -= 5 * mm
        c.drawString(x, y, bit.replace("\n", ", "))

    # Получатель (адрес доставки).
    y -= 15 * mm
    c.setFillColorRGB(*_INK)
    c.setFont(font, 10)
    recipient = str(order.customer)
    if order.shipping_address:
        recipient = f"{recipient}\n{order.shipping_address}"
    for line in recipient.splitlines()[:6]:
        c.drawString(x, y, line)
        y -= 5 * mm

    # Заголовок документа.
    y -= 8 * mm
    c.setFont(font_bold, 16)
    title = _("Delivery note")
    c.drawString(x, y, f"{title} {order.reference_code}")
    c.setFont(font, 9)
    c.setFillColorRGB(*_MUTED)
    label_date = _("Date")
    c.drawRightString(page_w - x, y, f"{label_date}: {doc_date(order.created_at)}")

    # Таблица позиций (без цен).
    y -= 12 * mm
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 9)
    c.drawString(x, y, _("Quantity"))
    c.drawString(x + 25 * mm, y, _("Item"))
    y -= 2 * mm
    c.line(x, y, page_w - x, y)
    c.setFont(font, 9)
    for item in order.items.all():
        y -= 6 * mm
        c.drawString(x, y, f"{item.qty}×")
        c.drawString(x + 25 * mm, y, _item_label(item)[:80])
    if order.note:
        y -= 10 * mm
        c.setFillColorRGB(*_MUTED)
        c.setFont(font, 8)
        label_note = _("Note")
        c.drawString(x, y, f"{label_note}: {order.note[:90]}")

    # Адресная этикетка (вырезать и наклеить на посылку).
    box_h = 40 * mm
    box_y = 30 * mm
    c.setStrokeColorRGB(*_MUTED)
    c.setDash(2, 2)
    c.rect(x, box_y, page_w - 2 * x, box_h)
    c.setDash()
    ly = box_y + box_h - 8 * mm
    c.setFillColorRGB(*_MUTED)
    c.setFont(font, 7)
    label_sender = _("Sender")
    c.drawString(x + 4 * mm, ly, f"{label_sender}: {tenant.name}")
    ly -= 8 * mm
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 12)
    for line in recipient.splitlines()[:5]:
        c.drawString(x + 4 * mm, ly, line[:60])
        ly -= 6 * mm

    c.showPage()
    c.save()
    return buffer.getvalue()
