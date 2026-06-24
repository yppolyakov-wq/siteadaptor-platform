"""R6: PDF «Teilnehmer-Memo» (памятка участника) — reportlab, зеркало jobs/pdf.py.

Инфоблок к билету: мероприятие/дата/место, программа, что взять, проживание
(если выбрано), контакт организатора, код билета. Не счёт — без Pflichtangaben.
"""

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

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
    event = ticket.event
    buffer = io.BytesIO()
    _, page_h = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    x = 20 * mm
    y = page_h - 25 * mm

    # Шапка: организатор.
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, tenant.name)
    c.setFont("Helvetica", 9)
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
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, "Teilnehmer-Infoblatt")
    y -= 9 * mm
    c.setFont("Helvetica-Bold", 12)
    y = _wrap(c, event.title, x, y, leading=6, font="Helvetica-Bold", size=12)

    # Дата / место.
    c.setFillColorRGB(*_MUTED)
    when = event.starts_at.strftime("%d.%m.%Y %H:%M")
    if event.ends_at:
        when += " – " + event.ends_at.strftime("%d.%m.%Y %H:%M")
    y -= 1 * mm
    y = _wrap(c, when, x, y, size=10)
    place = event.location or event.city
    if place:
        y = _wrap(c, f"Ort: {place}", x, y, size=10)

    def section(title, lines):
        nonlocal y
        if not lines:
            return
        y -= 4 * mm
        c.setFillColorRGB(*_INK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x, y, title)
        y -= 6 * mm
        c.setFillColorRGB(*_MUTED)
        for line in lines:
            y = _wrap(c, f"• {line}", x, y, size=10)

    section("Programm", event.program or [])
    section("Bitte mitbringen", event.landing.get("bring") or [])
    if ticket.stay_booking_id and ticket.stay_booking:
        section("Unterkunft", [ticket.stay_booking.unit.name])

    # Билет.
    y -= 6 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, f"Ticket: {ticket.reference_code}  ·  {ticket.quantity} Platz/Plätze")

    # R8: отметка о подписанном отказе от ответственности.
    waiver = getattr(ticket, "waiver", None)
    if waiver and waiver.signed_at:
        y -= 7 * mm
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*_MUTED)
        c.drawString(
            x,
            y,
            f"Haftungsausschluss unterschrieben am {waiver.signed_at:%d.%m.%Y} ({waiver.signed_name})",
        )

    c.showPage()
    c.save()
    return buffer.getvalue()
