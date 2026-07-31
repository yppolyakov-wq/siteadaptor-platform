"""R6: PDF «Teilnehmer-Memo» (памятка участника) — reportlab, зеркало jobs/pdf.py.

Инфоблок к билету: мероприятие/дата/место, программа, что взять, проживание
(если выбрано), контакт организатора, код билета. Не счёт — без Pflichtangaben.

I18N-7b: памятку скачивает КЛИЕНТ с витрины, поэтому она печатается на языке,
который посетитель выбрал на сайте (вьюха оборачивает сборку в override).
"""

import io

from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.documents import doc_date, doc_datetime, fonts

_INK = (0.10, 0.10, 0.12)
_MUTED = (0.42, 0.42, 0.48)


def _wrap(c, text, x, y, *, width_mm=170, leading=5, font="Helvetica", size=10):
    """Примитивный перенос строк по ширине; возвращает новый y."""
    c.setFont(font, size)
    max_chars = int(width_mm * 2.0)  # грубая оценка символов на ширину
    for paragraph in str(text or "").split("\n"):
        line = ""
        for word in paragraph.split(" "):
            if len(line) + len(word) + 1 > max_chars:
                c.drawString(x, y, line)
                y -= leading * mm
                line = word
            else:
                line = f"{line} {word}".strip()
        c.drawString(x, y, line)
        y -= leading * mm
    return y


def build_memo_pdf(ticket, tenant) -> bytes:
    font, font_bold = fonts()
    event = ticket.event
    buffer = io.BytesIO()
    _unused_w, page_h = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    x = 20 * mm
    y = page_h - 25 * mm

    # Шапка: организатор.
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 14)
    c.drawString(x, y, tenant.name)
    c.setFont(font, 9)
    c.setFillColorRGB(*_MUTED)
    for bit in [b for b in [tenant.address, tenant.city] if b]:
        y -= 5 * mm
        c.drawString(x, y, bit.replace("\n", ", "))
    contact = " · ".join(
        b for b in [getattr(tenant, "phone", ""), getattr(tenant, "email", "")] if b
    )
    if contact:
        y -= 5 * mm
        c.drawString(x, y, contact)

    # Заголовок памятки.
    y -= 14 * mm
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 16)
    c.drawString(x, y, _("Participant information sheet"))
    y -= 9 * mm
    c.setFont(font_bold, 12)
    y = _wrap(c, event.title, x, y, leading=6, font=font_bold, size=12)

    # Дата / место.
    c.setFillColorRGB(*_MUTED)
    when = doc_datetime(event.starts_at)
    if event.ends_at:
        when += " – " + doc_datetime(event.ends_at)
    y -= 1 * mm
    y = _wrap(c, when, x, y, font=font, size=10)
    place = event.location or event.city
    if place:
        label_place = _("Location")
        y = _wrap(c, f"{label_place}: {place}", x, y, font=font, size=10)

    def section(title, lines):
        nonlocal y
        if not lines:
            return
        y -= 4 * mm
        c.setFillColorRGB(*_INK)
        c.setFont(font_bold, 11)
        c.drawString(x, y, title)
        y -= 6 * mm
        c.setFillColorRGB(*_MUTED)
        for line in lines:
            y = _wrap(c, f"• {line}", x, y, font=font, size=10)

    section(_("Programme"), event.program or [])
    section(_("Please bring"), event.landing.get("bring") or [])
    if ticket.stay_booking_id and ticket.stay_booking:
        section(_("Accommodation"), [ticket.stay_booking.unit.name])

    # Билет.
    y -= 6 * mm
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 11)
    places = ngettext("%(n)s place", "%(n)s places", ticket.quantity) % {"n": ticket.quantity}
    label_ticket = _("Ticket")
    c.drawString(x, y, f"{label_ticket}: {ticket.reference_code}  ·  {places}")

    # R8: отметка о подписанном отказе от ответственности.
    waiver = getattr(ticket, "waiver", None)
    if waiver and waiver.signed_at:
        y -= 7 * mm
        c.setFont(font, 9)
        c.setFillColorRGB(*_MUTED)
        c.drawString(
            x,
            y,
            _("Liability waiver signed on %(date)s (%(name)s)")
            % {"date": doc_date(waiver.signed_at), "name": waiver.signed_name},
        )

    c.showPage()
    c.save()
    return buffer.getvalue()
