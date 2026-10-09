"""ERP-8: PDF-бланк «Mängelanzeige» — рекламация поставщику (§ 377 HGB), reportlab.

Повторяет бумажный бланк владельца: отправитель (бизнес) → получатель (поставщик) →
реквизиты поставки (заказ, накладная, даты, перевозчик) → строки дефектов → результат
проверки → правовая фраза → строка подписи. Подписи переводятся (язык задаёт вызывающий
`translation.override`), формат дат — по локали (`core/documents.py`).
"""

import io

from django.utils.translation import gettext as _
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from apps.core.documents import doc_date, fonts, money

from .maengel import defect_labels

_INK = (0.10, 0.10, 0.12)
_MUTED = (0.42, 0.42, 0.48)
_BOTTOM = 30 * mm


def _article(position) -> str:
    parts = [str(position.product)]
    variant = position.variant
    if variant is not None:
        parts.append(f"· {variant.label}")
    sku = (getattr(variant, "sku", "") if variant is not None else "") or getattr(
        position.product, "sku", ""
    )
    if sku:
        parts.append(f"· Art.-Nr. {sku}")
    return " ".join(parts)


def _decision_label(mangel) -> str:
    return str(dict(mangel.DECISIONS).get(mangel.decision, ""))


class _Page:
    """Курсор по странице: перенос на новую страницу, когда место кончилось."""

    def __init__(self, c, font, font_bold):
        self.c = c
        self.font = font
        self.bold = font_bold
        self.w, self.h = A4
        self.x = 20 * mm
        self.y = self.h - 25 * mm

    def need(self, height):
        if self.y - height < _BOTTOM:
            self.c.showPage()
            self.y = self.h - 25 * mm

    def text(self, value, *, size=9, bold=False, muted=False, indent=0, width=None):
        """Абзац с переносом строк; возвращает число строк."""
        width = width or (self.w - 2 * self.x - indent)
        font = self.bold if bold else self.font
        lines = simpleSplit(str(value or ""), font, size, width) or [""]
        for line in lines:
            self.need(size * 0.5 * mm + 4 * mm)
            self.c.setFont(font, size)
            self.c.setFillColorRGB(*(_MUTED if muted else _INK))
            self.c.drawString(self.x + indent, self.y, line)
            self.y -= size * 0.45 * mm + 1.6 * mm
        return len(lines)


def build_maengel_pdf(anzeige, tenant) -> bytes:
    font, font_bold = fonts()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    p = _Page(c, font, font_bold)
    bestellung = anzeige.bestellung
    supplier = bestellung.supplier

    # Отправитель — бизнес.
    p.text(getattr(tenant, "name", "") or "", size=14, bold=True)
    for bit in (getattr(tenant, "address", ""), getattr(tenant, "city", "")):
        if bit:
            p.text(str(bit).replace("\n", ", "), muted=True)

    # Получатель — поставщик.
    p.y -= 8 * mm
    if supplier is not None:
        p.text(supplier.name, size=10, bold=True)
        if supplier.contact_person:
            p.text(supplier.contact_person, size=10)
        for line in (supplier.address or "").splitlines()[:4]:
            p.text(line, size=10)
        if supplier.customer_number:
            label = _("Our customer number")
            p.text(f"{label}: {supplier.customer_number}", muted=True)

    # Заголовок.
    p.y -= 8 * mm
    title = _("Notice of defects")
    c.setFont(font_bold, 16)
    c.setFillColorRGB(*_INK)
    c.drawString(p.x, p.y, f"{title} {anzeige.reference}")
    c.setFont(font, 9)
    c.setFillColorRGB(*_MUTED)
    label_date = _("Date")
    c.drawRightString(p.w - p.x, p.y, f"{label_date}: {doc_date(anzeige.created_at)}")
    p.y -= 10 * mm

    # Реквизиты поставки.
    facts = [
        (_("Purchase order"), bestellung.reference),
        (_("Delivery note no."), anzeige.delivery_note_ref),
        (_("Delivery date"), doc_date(anzeige.delivery_date)),
        (_("Inspection date"), doc_date(anzeige.inspected_at)),
        (_("Carrier"), anzeige.carrier),
        (_("Inspected by"), anzeige.inspected_by),
    ]
    for label, value in facts:
        if value:
            p.need(6 * mm)
            c.setFont(font, 9)
            c.setFillColorRGB(*_MUTED)
            c.drawString(p.x, p.y, f"{label}:")
            c.setFillColorRGB(*_INK)
            c.drawString(p.x + 40 * mm, p.y, str(value))
            p.y -= 5 * mm

    p.y -= 4 * mm
    p.text(
        _(
            "We hereby give notice under § 377 HGB of the following defects in the "
            "delivery referred to above."
        ),
        size=10,
    )

    # Строки дефектов.
    p.y -= 4 * mm
    p.need(10 * mm)
    c.setFont(font_bold, 9)
    c.setFillColorRGB(*_INK)
    label_qty = _("Quantity")
    # колонка количества — по ширине подписи: ru «Количество» шире 22 мм (стенд)
    col = max(22 * mm, stringWidth(label_qty, font_bold, 9) + 5 * mm)
    c.drawString(p.x, p.y, label_qty)
    c.drawString(p.x + col, p.y, _("Item"))
    p.y -= 2 * mm
    c.line(p.x, p.y, p.w - p.x, p.y)
    p.y -= 5 * mm
    label_type = _("Type of defect")
    label_desc = _("Description")
    label_remedy = _("Requested remedy")
    for mangel in anzeige.maengel.select_related("position__product", "position__variant"):
        p.need(16 * mm)
        c.setFont(font_bold, 9)
        c.setFillColorRGB(*_INK)
        c.drawString(p.x, p.y, f"{mangel.qty}×")
        p.text(_article(mangel.position), bold=True, indent=col)
        types = ", ".join(defect_labels(mangel))
        if types:
            p.text(f"{label_type}: {types}", indent=col)
        if mangel.description:
            p.text(f"{label_desc}: {mangel.description}", indent=col, muted=True)
        if mangel.decision:
            remedy = _decision_label(mangel)
            if mangel.decision == "discount" and mangel.discount:
                remedy = f"{remedy}: {money(mangel.discount)}"
            p.text(f"{label_remedy}: {remedy}", indent=col)
        p.y -= 3 * mm

    # Результат проверки.
    if anzeige.result:
        p.y -= 2 * mm
        p.text(_("Inspection result"), bold=True)
        p.text(anzeige.result)

    # Правовое закрытие + подпись.
    p.y -= 6 * mm
    p.text(
        _(
            "We reserve all rights arising from the defective delivery. Please confirm "
            "receipt of this notice."
        ),
    )
    p.need(30 * mm)
    p.y -= 18 * mm
    c.setStrokeColorRGB(*_MUTED)
    half = (p.w - 2 * p.x - 10 * mm) / 2
    c.line(p.x, p.y, p.x + half, p.y)
    c.line(p.x + half + 10 * mm, p.y, p.w - p.x, p.y)
    c.setFont(font, 8)
    c.setFillColorRGB(*_MUTED)
    c.drawString(p.x, p.y - 4 * mm, _("Place, date"))
    signature = _("Signature")
    who = f" ({anzeige.inspected_by})" if anzeige.inspected_by else ""
    c.drawString(p.x + half + 10 * mm, p.y - 4 * mm, f"{signature}{who}")

    c.showPage()
    c.save()
    return buffer.getvalue()
