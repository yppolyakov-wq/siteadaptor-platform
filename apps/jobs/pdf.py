"""PDF Angebot / Kostenvoranschlag (G6 / F2) — reportlab, зеркало finance.pdf.

Шапка-отправитель из Tenant, получатель из Job, позиции из JobLine, итоги-снимок,
§19-Hinweis. Без юридических Pflichtangaben счёта (это смета, не Rechnung).

I18N-7b: язык — активный в момент сборки (вьюха оборачивает в override),
шрифт/форматы — `apps.core.documents`. Немецкие налоговые идентификаторы
(USt-IdNr./Steuernummer) и ссылка на § 19 UStG не переводятся.
"""

import io

from django.utils.translation import gettext as _
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.documents import doc_date, fonts, money, qty

_INK = (0.10, 0.10, 0.12)
_MUTED = (0.42, 0.42, 0.48)


def build_quote_pdf(job, tenant) -> bytes:
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
    recipient = str(job.customer)
    if job.site_address:
        recipient = f"{recipient}\n{job.site_address}"
    for line in recipient.splitlines()[:5]:
        c.drawString(x, y, line)
        y -= 5 * mm

    # Заголовок документа.
    y -= 10 * mm
    c.setFont(font_bold, 16)
    title = _("Quote")
    c.drawString(x, y, f"{title} {job.reference_code}")
    c.setFont(font, 9)
    c.setFillColorRGB(*_MUTED)
    label_date = _("Date")
    c.drawRightString(page_w - x, y, f"{label_date}: {doc_date(job.created_at)}")
    if job.valid_until:
        y -= 5 * mm
        label_valid = _("Valid until")
        c.drawRightString(page_w - x, y, f"{label_valid}: {doc_date(job.valid_until)}")

    # Заголовок/описание работ.
    y -= 10 * mm
    c.setFillColorRGB(*_INK)
    c.setFont(font_bold, 11)
    c.drawString(x, y, job.title[:80])

    # Таблица позиций.
    y -= 10 * mm
    c.setFont(font_bold, 9)
    c.drawString(x, y, _("Description"))
    c.drawRightString(page_w - x - 60 * mm, y, _("Quantity"))
    c.drawRightString(page_w - x - 30 * mm, y, _("Unit price"))
    c.drawRightString(page_w - x, y, _("Amount"))
    y -= 2 * mm
    c.line(x, y, page_w - x, y)
    c.setFont(font, 9)
    for line in job.lines.all():
        y -= 6 * mm
        c.drawString(x, y, str(line.text)[:70])
        c.drawRightString(page_w - x - 60 * mm, y, qty(line.qty))
        c.drawRightString(page_w - x - 30 * mm, y, money(line.unit_price))
        c.drawRightString(page_w - x, y, money(line.line_total))

    # Итоги.
    y -= 4 * mm
    c.line(page_w / 2, y, page_w - x, y)
    y -= 6 * mm
    label_net = _("Net")
    c.drawRightString(page_w - x - 30 * mm, y, f"{label_net}:")
    c.drawRightString(page_w - x, y, money(job.net))
    if not tenant.small_business:
        # VAT-1: § 14 Abs. 4 Nr. 8 UStG требует разбивку сумм ПО СТАВКАМ, поэтому
        # при смешанной смете печатаем строку на каждую ставку. Цифры даёт тот же
        # quote_totals, что считает карточку и итог документа.
        from apps.jobs.totals import quote_totals

        label_vat = _("VAT")
        totals = quote_totals(list(job.lines.all()), job.vat_rate)
        rows = totals["rows"] or [{"rate": job.vat_rate, "vat": job.vat_amount}]
        for row in rows:
            y -= 6 * mm
            c.drawRightString(page_w - x - 30 * mm, y, f"{label_vat} {row['rate']:.0f} %:")
            c.drawRightString(page_w - x, y, money(row["vat"]))
    y -= 7 * mm
    c.setFont(font_bold, 11)
    label_total = _("Total")
    c.drawRightString(page_w - x - 30 * mm, y, f"{label_total}:")
    c.drawRightString(page_w - x, y, money(job.gross))

    # Hinweise.
    y -= 14 * mm
    c.setFont(font, 8)
    c.setFillColorRGB(*_MUTED)
    if tenant.small_business:
        c.drawString(x, y, _("No VAT is charged in accordance with § 19 UStG."))
        y -= 5 * mm
    c.drawString(x, y, _("This is a non-binding quote / cost estimate."))

    c.showPage()
    c.save()
    return buffer.getvalue()
