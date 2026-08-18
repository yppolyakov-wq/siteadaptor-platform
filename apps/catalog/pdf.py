"""GK-13: Speisekarte-PDF — печатная карта из каталога (reportlab, зеркало orders/pdf).

Генерируем из ЖИВЫХ данных (цены/диеты/аллергены всегда актуальны — ноль ручной
работы владельца, в отличие от загруженного файла). Язык задаёт вьюха через
translation.override (document_language: ?lang= → язык витрины); деньги — по
локали (documents.money). Аллергены — буквенные сноски + легенда (LMIV-стиль),
диеты — локализованные метки после названия.
"""

import io

from django.utils.translation import gettext as _
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.documents import fonts, money

_INK = (0.10, 0.10, 0.12)
_MUTED = (0.42, 0.42, 0.48)
_TOP = 25 * mm
_BOTTOM = 25 * mm


def _allergen_letters():
    """Стабильная карта аллерген-код → буква сноски (a..n по реестру LMIV).

    MEN-24a: источник поднят в food.allergen_letters — те же буквы у витринного
    прайс-листа; здесь остаётся тонкая обёртка ради существующих колл-сайтов."""
    from apps.catalog.food import allergen_letters

    return allergen_letters()


def _diet_labels(product) -> str:
    from apps.catalog.food import DIETS

    labels = dict((code, str(label)) for code, label, _icon in DIETS)
    picked = [labels[d] for d in (product.diets or []) if d in labels]
    return " · ".join(picked)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        cand = f"{line} {w}".strip()
        if len(cand) > width and line:
            lines.append(line)
            line = w
        else:
            line = cand
    if line:
        lines.append(line)
    return lines


def build_menu_pdf(tenant, groups) -> bytes:
    """PDF-карта: groups = [(заголовок_категории, [products])] (уже локализовано
    вызывающим). Многостраничная, легенда аллергенов в конце."""
    font, font_bold = fonts()
    letters = _allergen_letters()
    used_allergens = set()

    buffer = io.BytesIO()
    page_w, page_h = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    x = 20 * mm
    right = page_w - 20 * mm
    y = page_h - _TOP

    def newpage():
        nonlocal y
        c.showPage()
        y = page_h - _TOP

    def ensure(space):
        if y < _BOTTOM + space:
            newpage()

    # Шапка
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 18)
    c.drawString(x, y, tenant.name)
    y -= 8 * mm
    c.setFont(font_bold, 13)
    c.drawString(x, y, _("Menu"))
    c.setFont(font, 9)
    c.setFillColorRGB(*_MUTED)
    contact = ", ".join(b for b in (tenant.address, tenant.city) if b)
    if contact:
        y -= 5 * mm
        c.drawString(x, y, contact.replace("\n", ", "))
    y -= 10 * mm

    for title, products in groups:
        ensure(24 * mm)
        c.setFillColorRGB(*_INK)
        c.setFont(font_bold, 12)
        c.drawString(x, y, title)
        y -= 7 * mm
        for p in products:
            ensure(14 * mm)
            name = p.get_i18n("name")
            codes = "".join(sorted(letters[a] for a in (p.allergens or []) if a in letters))
            used_allergens.update(a for a in (p.allergens or []) if a in letters)
            c.setFillColorRGB(*_INK)
            c.setFont(font, 10)
            c.drawString(x, y, name + (f" ({codes})" if codes else ""))
            c.setFont(font_bold, 10)
            c.drawRightString(right, y, money(p.base_price))
            diets = _diet_labels(p)
            desc = (p.get_i18n("description") or "").strip().replace("\n", " ")
            sub = " — ".join(b for b in (diets, desc) if b)
            c.setFont(font, 8)
            c.setFillColorRGB(*_MUTED)
            for line in _wrap(sub, 100)[:2]:
                y -= 4 * mm
                c.drawString(x, y, line)
            y -= 6 * mm
        y -= 4 * mm

    # Легенда аллергенов — только встретившиеся (LMIV: сноска у позиции).
    if used_allergens:
        from apps.catalog.food import ALLERGENS

        labels = dict(ALLERGENS)
        ensure(20 * mm)
        c.setFillColorRGB(*_INK)
        c.setFont(font_bold, 9)
        c.drawString(x, y, _("Allergens"))
        y -= 5 * mm
        c.setFont(font, 8)
        c.setFillColorRGB(*_MUTED)
        legend = " · ".join(
            f"{letters[code]} = {labels[code]}"
            for code, _lbl in ALLERGENS
            if code in used_allergens
        )
        for line in _wrap(legend, 110):
            ensure(5 * mm)
            c.drawString(x, y, line)
            y -= 4 * mm

    c.save()
    return buffer.getvalue()
