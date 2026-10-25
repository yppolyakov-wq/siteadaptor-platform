"""KA-12 Zimmer Z-6: PDF Kurtaxe-Meldung (для общины) и Meldeschein на подпись гостя.

Стиль — как у Lieferschein (`orders/pdf.py`): reportlab, шрифты `core.documents.fonts()`.
Номер документа гостя (О-10) — ТОЛЬКО в печатном Meldeschein, в CSV не выгружается.
Подписи переводятся, язык задаёт вьюха (`translation.override`).
"""

import io

from django.utils.translation import gettext as _
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.documents import doc_date, fonts, money

_INK = (0.10, 0.10, 0.12)
_MUTED = (0.42, 0.42, 0.48)


def _header(c, tenant, title, subtitle=""):
    font, font_bold = fonts()
    _w, page_h = A4
    x, y = 20 * mm, page_h - 25 * mm
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 14)
    c.drawString(x, y, tenant.name)
    c.setFont(font, 9)
    c.setFillColorRGB(*_MUTED)
    for bit in [b for b in [getattr(tenant, "address", ""), getattr(tenant, "city", "")] if b]:
        y -= 5 * mm
        c.drawString(x, y, bit.replace("\n", ", "))
    y -= 14 * mm
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 16)
    c.drawString(x, y, title)
    if subtitle:
        y -= 7 * mm
        c.setFont(font, 10)
        c.drawString(x, y, subtitle)
    return y - 10 * mm


def build_kurtaxe_pdf(report, tenant) -> bytes:
    """Таблица Kurtaxe за месяц: код брони, категория, даты, ночи, сумма; итоги."""
    font, font_bold = fonts()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    period = f"{doc_date(report['first'])} – {doc_date(report['last'])}"
    title = _("Kurtaxe-Meldung")
    y = _header(c, tenant, f"{title} · {report['label']}", period)
    cols = [20, 50, 100, 140, 160, 175]  # мм
    heads = [
        _("Buchung"),
        _("Kategorie"),
        _("Zeitraum"),
        _("Nächte"),
        _("Erw."),
        _("Betrag"),
    ]

    def head_row(y):
        c.setFont(font_bold, 9)
        for x, h in zip(cols, heads, strict=True):
            c.drawString(x * mm, y, h)
        return y - 6 * mm

    y = head_row(y)
    c.setFont(font, 9)
    for r in report["rows"]:
        if y < 30 * mm:
            c.showPage()
            y = head_row(A4[1] - 25 * mm)
            c.setFont(font, 9)
        b = r.booking
        vals = [
            b.reference_code,
            str(b.unit)[:28],
            f"{doc_date(b.arrival)} – {doc_date(b.departure)}",
            str(r.nights),
            str(r.adult_nights),
            money(r.kurtaxe_cents / 100),
        ]
        for x, v in zip(cols, vals, strict=True):
            c.drawString(x * mm, y, v)
        y -= 5 * mm
    y -= 6 * mm
    c.setFont(font_bold, 10)
    totals = [
        (_("Übernachtungen Erwachsene"), report["adult_nights"]),
        (_("Übernachtungen Kinder"), report["child_nights"]),
        (_("davon befreit"), report["free_child_nights"]),
        (_("Summe"), money(report["kurtaxe_cents"] / 100)),
    ]
    lines = [f"{label}: {value}" for label, value in totals]
    for line in lines:
        if y < 20 * mm:
            c.showPage()
            y = A4[1] - 25 * mm
            c.setFont(font_bold, 10)
        c.drawString(20 * mm, y, line)
        y -= 6 * mm
    c.save()
    return buffer.getvalue()


def build_meldeschein_pdf(booking, reg, tenant) -> bytes:
    """Meldeschein (BMG §§ 29–30) на подпись: данные гостя (если есть) и пустые строки."""
    font, font_bold = fonts()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = _header(c, tenant, _("Meldeschein"), booking.reference_code)
    rows = [
        (_("Anreise"), doc_date(booking.arrival)),
        (_("Abreise"), doc_date(booking.departure)),
        (_("Nachname"), getattr(reg, "last_name", "")),
        (_("Vorname"), getattr(reg, "first_name", "")),
        (_("Geburtsdatum"), doc_date(reg.birth_date) if reg and reg.birth_date else ""),
        (_("Staatsangehörigkeit"), getattr(reg, "nationality", "")),
        (_("Straße"), getattr(reg, "street", "")),
        (
            _("PLZ / Ort"),
            " ".join(x for x in [getattr(reg, "postal_code", ""), getattr(reg, "city", "")] if x),
        ),
        (_("Land"), getattr(reg, "country", "")),
        (_("Ausweisart"), getattr(reg, "doc_type", "")),
        (_("Ausweisnummer"), getattr(reg, "doc_number", "")),
        (_("Mitreisende"), str(getattr(reg, "accompanying", "") or "")),
    ]
    for label, value in rows:
        c.setFont(font, 9)
        c.setFillColorRGB(*_MUTED)
        c.drawString(20 * mm, y, label)
        c.setFillColorRGB(*_INK)
        c.setFont(font_bold, 11)
        c.drawString(70 * mm, y, value or "")
        c.setStrokeColorRGB(*_MUTED)
        c.line(70 * mm, y - 1.5 * mm, 190 * mm, y - 1.5 * mm)
        y -= 10 * mm
    y -= 10 * mm
    c.setFont(font, 9)
    c.drawString(20 * mm, y, _("Datum, Unterschrift des Gastes"))
    c.line(70 * mm, y - 1.5 * mm, 190 * mm, y - 1.5 * mm)
    c.save()
    return buffer.getvalue()
