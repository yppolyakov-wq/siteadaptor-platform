"""T-8.9 «Aushang»: флаер на ОДНУ акцию с QR (A4 / A6 / 4×A6 на листе A4).

План — docs/t8-9-flyer-plan-2026-10-10.md. Вёрстка одна: флаер рисуется в координатах
A6 (105 × 148 мм) и масштабируется — A4 и A6 подобны (√2), поэтому кегли и отступы
растут вместе со страницей. QR ведёт на страницу акции с `?ch=flyer` (атрибуция).

Языки и шрифты — общий слой `apps.core.documents` (I18N-7b): вызывающий кладёт
`translation.override`, здесь только `gettext`.
"""

from __future__ import annotations

import io

import segno
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from apps.core.documents import fonts

from . import response as promo_response
from .poster import _hex_to_rgb, _pretty_url, _with_channel

FORMATS = ("a4", "a6", "a6x4")
CHANNEL = "flyer"

W = 105 * mm  # ширина A6
H = 148 * mm  # высота A6
_PAD = 8 * mm
_INK = (0.10, 0.10, 0.12)
_MUTED = (0.42, 0.42, 0.48)
_LINE = (0.80, 0.80, 0.84)


def _money(value) -> str:
    return f"{formats.number_format(value, decimal_pos=2, use_l10n=True)} €"


def price_lines(promo) -> dict:
    """Блок цены для печати. Mystery цену НЕ раскрывает (как витрина, замки SF-1)."""
    if getattr(promo, "discount_style", "") == "mystery":
        return {"main": _("Überraschungspreis"), "old": "", "badge": "", "unit": ""}
    pct = promo.discount_percent_display
    badge = f"−{pct} %" if pct else ""
    new = promo.new_price
    if new is None:
        return {"main": badge, "old": "", "badge": "", "unit": ""}
    old = _money(promo.old_price) if promo.has_discount else ""
    unit = ""
    gp = promo.grundpreis  # (Decimal, "kg"|"l") — PAngV, как на витрине
    if gp:
        unit = f"{_money(gp[0])} / {gp[1]}"
    return {"main": _money(new), "old": old, "badge": badge if old else "", "unit": unit}


def validity_line(promo, now=None) -> str:
    now = timezone.localtime(now or timezone.now())
    parts = []
    starts, ends = promo.starts_at, promo.ends_at
    if starts and starts > now:
        parts.append(
            _("ab %(date)s") % {"date": formats.date_format(timezone.localtime(starts), "d.m.")}
        )
    if ends:
        local_end = timezone.localtime(ends)
        if local_end.date() == now.date():
            parts.append(_("Nur heute bis %(time)s") % {"time": local_end.strftime("%H:%M")})
        else:
            parts.append(
                _("gültig bis %(date)s") % {"date": formats.date_format(local_end, "d.m.Y")}
            )
    if promo.available_quantity:
        parts.append(_("Solange der Vorrat reicht"))
    return " · ".join(parts)


def call_to_action(promo, tenant) -> str:
    kind = promo_response.response_for(promo, tenant)
    return {
        promo_response.RESERVE: _("Scannen & zurücklegen lassen"),
        promo_response.INQUIRE: _("Scannen & anfragen"),
        promo_response.BUY: _("Scannen & bestellen"),
        promo_response.BOOKING: _("Scannen & Termin buchen"),
    }.get(kind, _("Scannen für alle Details"))


def flyer_url(promo_url: str) -> str:
    return _with_channel(promo_url, CHANNEL)


def _load_image(img: dict | None):
    """ImageReader главного фото (storage или статика демо) или None — fail-safe."""
    if not img:
        return None
    try:
        from PIL import Image

        path = img.get("path")
        if path:
            from django.core.files.storage import default_storage

            with default_storage.open(path, "rb") as fh:
                data = fh.read()
        else:
            from django.conf import settings
            from django.contrib.staticfiles import finders

            url = img.get("url") or ""
            static = settings.STATIC_URL or "/static/"
            if not url.startswith(static):
                return None
            found = finders.find(url[len(static) :])
            if not found:
                return None
            with open(found, "rb") as fh:
                data = fh.read()
        pil = Image.open(io.BytesIO(data))
        pil.load()
        if pil.mode not in ("RGB", "L"):
            pil = pil.convert("RGB")
        return ImageReader(pil)
    except Exception:  # noqa: BLE001 — нет файла/битое фото: флаер без фото
        return None


def _centered_lines(c, text, font, size, y, *, max_lines, color, width=W - 2 * _PAD):
    lines = simpleSplit(text or "", font, size, width)[:max_lines]
    c.setFont(font, size)
    c.setFillColorRGB(*color)
    for line in lines:
        c.drawCentredString(W / 2, y, line)
        y -= size * 1.25
    return y


def _draw(c, data: dict):
    """Один флаер в координатах A6 (0,0 — левый нижний угол)."""
    font, bold = fonts()
    accent = data["accent"]

    c.setStrokeColorRGB(*accent)
    c.setLineWidth(0.8)
    c.roundRect(4 * mm, 4 * mm, W - 8 * mm, H - 8 * mm, 4 * mm, stroke=1, fill=0)

    y = H - 13 * mm
    y = _centered_lines(c, data["business"], bold, 10, y, max_lines=1, color=accent)
    y -= 1 * mm

    image = data.get("image")
    if image is not None:
        bw, bh = W - 2 * _PAD, 40 * mm
        bx, by = _PAD, y - bh
        iw, ih = image.getSize()
        scale = max(bw / iw, bh / ih)
        dw, dh = iw * scale, ih * scale
        c.saveState()
        path = c.beginPath()
        path.roundRect(bx, by, bw, bh, 3 * mm)
        c.clipPath(path, stroke=0, fill=0)
        c.drawImage(image, bx + (bw - dw) / 2, by + (bh - dh) / 2, dw, dh)
        c.restoreState()
        y = by - 7 * mm
    else:
        y -= 6 * mm

    y = _centered_lines(c, data["title"], bold, 15, y, max_lines=2, color=_INK)
    if data["description"]:
        y = _centered_lines(c, data["description"], font, 8, y, max_lines=2, color=_MUTED)
    y -= 4 * mm

    price = data["price"]
    if price["main"]:
        size = 24
        while size > 12 and c.stringWidth(price["main"], bold, size) > W - 2 * _PAD:
            size -= 1
        c.setFont(bold, size)
        c.setFillColorRGB(*accent)
        c.drawCentredString(W / 2, y - size * 0.75, price["main"])
        y -= size * 0.75 + 5 * mm
        side = "  ".join(x for x in (price["old"], price["badge"]) if x)
        if side:
            c.setFont(font, 9)
            c.setFillColorRGB(*_MUTED)
            c.drawCentredString(W / 2, y, side)
            if price["old"]:
                text_w = c.stringWidth(side, font, 9)
                old_w = c.stringWidth(price["old"], font, 9)
                x0 = W / 2 - text_w / 2
                c.setStrokeColorRGB(*_MUTED)
                c.setLineWidth(0.6)
                c.line(x0, y + 3, x0 + old_w, y + 3)
            y -= 4.5 * mm
        if price["unit"]:
            y = _centered_lines(c, price["unit"], font, 7, y, max_lines=1, color=_MUTED)
    if data["validity"]:
        _centered_lines(c, data["validity"], bold, 8, y, max_lines=2, color=_INK)

    # Нижний блок: QR слева, призыв/адрес справа.
    qr_size = 32 * mm
    qx, qy = _PAD, 9 * mm
    c.drawImage(data["qr"], qx, qy, qr_size, qr_size, mask="auto")
    tx = qx + qr_size + 3 * mm
    tw = W - _PAD - tx
    ty = qy + qr_size - 4 * mm
    c.setFillColorRGB(*accent)
    c.setFont(bold, 10)
    for line in simpleSplit(data["cta"], bold, 10, tw)[:3]:
        c.drawString(tx, ty, line)
        ty -= 12.5
    ty -= 2
    c.setFillColorRGB(*_INK)
    c.setFont(font, 7)
    for line in simpleSplit(data["url"], font, 7, tw)[:2]:
        c.drawString(tx, ty, line)
        ty -= 9
    c.setFillColorRGB(*_MUTED)
    for line in simpleSplit(data["address"], font, 7, tw)[:2]:
        c.drawString(tx, ty, line)
        ty -= 9


def build_promo_flyer_pdf(promo, promo_url: str, *, fmt: str = "a4", tenant=None) -> bytes:
    """Собрать флаер акции. ``fmt`` — a4 | a6 | a6x4 (мусор → a4)."""
    fmt = fmt if fmt in FORMATS else "a4"
    qr_buf = io.BytesIO()
    segno.make(flyer_url(promo_url), error="m").save(qr_buf, kind="png", scale=10, border=2)
    qr_buf.seek(0)
    address = (getattr(tenant, "address", "") or "").strip()
    city = (getattr(tenant, "city", "") or "").strip()
    if city and city not in address:
        address = f"{address}, {city}" if address else city
    data = {
        "accent": _hex_to_rgb(getattr(tenant, "primary_color", "") or ""),
        "business": (getattr(tenant, "name", "") or "").strip(),
        "image": _load_image(promo.primary_image),
        "title": promo.title_text or str(promo),
        "description": promo.description_text or "",
        "price": price_lines(promo),
        "validity": validity_line(promo),
        "qr": ImageReader(qr_buf),
        "cta": call_to_action(promo, tenant),
        # Только адрес сайта: путь с UUID не переносится и вылезал за край (стенд);
        # полную ссылку несёт QR.
        "url": _pretty_url(promo_url).split("/", 1)[0],
        "address": address,
    }

    buf = io.BytesIO()
    if fmt == "a6":
        c = canvas.Canvas(buf, pagesize=(W, H))
        _draw(c, data)
    elif fmt == "a6x4":
        c = canvas.Canvas(buf, pagesize=A4)
        page_w, page_h = A4
        cell_h = page_h / 2
        for col in (0, 1):
            for row in (0, 1):
                c.saveState()
                c.translate(col * W, row * cell_h + (cell_h - H) / 2)
                _draw(c, data)
                c.restoreState()
        # линии реза
        c.setStrokeColorRGB(*_LINE)
        c.setDash(3, 3)
        c.setLineWidth(0.5)
        c.line(page_w / 2, 0, page_w / 2, page_h)
        c.line(0, cell_h, page_w, cell_h)
    else:
        c = canvas.Canvas(buf, pagesize=A4)
        page_w, page_h = A4
        scale = min(page_w / W, page_h / H)
        c.translate((page_w - W * scale) / 2, (page_h - H * scale) / 2)
        c.scale(scale, scale)
        _draw(c, data)
    c.showPage()
    c.save()
    return buf.getvalue()
