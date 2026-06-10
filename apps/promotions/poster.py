"""QR-постер магазина (A4 PDF) для печати и наклейки в витрину (Track B4).

«Scan & Angebote sichern»: крупный QR на корень витрины + слоган + URL. QR несёт
?ch=schaufenster — брони с постера попадают в атрибуцию каналов (см. analytics).
QR рисует segno (нативный PNG, без Pillow), вёрстку — reportlab (встроенный
Helvetica, без файлов шрифтов; WinAnsi покрывает äöüß).
"""

import io
from urllib.parse import quote, urlsplit

import segno
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

_INK = (0.10, 0.10, 0.12)
_ACCENT = (0.31, 0.27, 0.90)  # индиго, как в кабинете/витрине
_MUTED = (0.42, 0.42, 0.48)


def _pretty_url(url: str) -> str:
    """Человекочитаемый адрес для печати: без схемы и хвостового слэша."""
    parts = urlsplit(url)
    host = parts.netloc or parts.path
    path = parts.path if parts.netloc else ""
    return (host + path).rstrip("/") or url


def _with_channel(url: str, channel: str) -> str:
    if not channel:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}ch={quote(channel)}"


def _centered(c, page_w, y, text, font, size, *, max_width=None, color=_INK):
    """Центрированная строка с авто-уменьшением кегля под ширину."""
    if max_width:
        while size > 9 and c.stringWidth(text, font, size) > max_width:
            size -= 1
    c.setFont(font, size)
    c.setFillColorRGB(*color)
    c.drawCentredString(page_w / 2, y, text)


def build_shop_poster_pdf(
    business_name: str,
    storefront_url: str,
    *,
    channel: str = "schaufenster",
    headline: str | None = None,
    subline: str | None = None,
    footer: str | None = None,
) -> bytes:
    """Собрать A4-постер с QR на витрину. Возвращает байты PDF."""
    business_name = (business_name or "Unser Shop").strip()
    headline = headline or "Scan & Angebote sichern"
    subline = subline or "Aktuelle Angebote ansehen & direkt reservieren – mit dem Handy."
    footer = footer or "Kostenlos · keine App nötig · keine Anmeldung"

    qr_buf = io.BytesIO()
    segno.make(_with_channel(storefront_url, channel), error="m").save(
        qr_buf, kind="png", scale=10, border=2
    )
    qr_buf.seek(0)
    qr_img = ImageReader(qr_buf)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    # рамка-подсказка «вырезать/повесить»
    c.setStrokeColorRGB(*_ACCENT)
    c.setLineWidth(1.4)
    c.roundRect(12 * mm, 12 * mm, page_w - 24 * mm, page_h - 24 * mm, 8 * mm, stroke=1, fill=0)

    _centered(
        c, page_w, page_h - 38 * mm, business_name, "Helvetica-Bold", 34, max_width=page_w - 40 * mm
    )
    _centered(c, page_w, page_h - 55 * mm, headline, "Helvetica-Bold", 23, color=_ACCENT)

    qr_size = 108 * mm
    qr_x = (page_w - qr_size) / 2
    qr_y = page_h - 70 * mm - qr_size
    c.drawImage(qr_img, qr_x, qr_y, qr_size, qr_size, preserveAspectRatio=True, mask="auto")

    _centered(
        c,
        page_w,
        qr_y - 13 * mm,
        _pretty_url(storefront_url),
        "Helvetica-Bold",
        16,
        max_width=page_w - 40 * mm,
        color=_INK,
    )
    _centered(
        c,
        page_w,
        qr_y - 25 * mm,
        subline,
        "Helvetica",
        13,
        max_width=page_w - 44 * mm,
        color=_MUTED,
    )
    _centered(c, page_w, 24 * mm, footer, "Helvetica-Oblique", 12, color=_MUTED)

    c.showPage()
    c.save()
    return buf.getvalue()
