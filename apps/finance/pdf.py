"""PDF Rechnung (Track D / D4b) — reportlab, как poster.py (Track B4).

Pflichtangaben §14 UStG из Tenant (название/адрес/USt-IdNr. или Steuernummer);
§19 Kleinunternehmer — обязательный Hinweis вместо НДС; KA-12: отмена — отдельная
Stornorechnung (водяной знак — только у легаси-отмен без неё).

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


def _rate_rows(invoice):
    """KA-12 E1.2: [(ставка, нетто, налог)] по ставкам строк; кривой/старый снимок —
    одна строка из сумм документа (повторное скачивание не меняет суммы)."""
    from decimal import ROUND_HALF_UP, Decimal

    cent = Decimal("0.01")
    fallback = [(Decimal(invoice.vat_rate), Decimal(invoice.net), Decimal(invoice.vat_amount))]
    by_rate: dict[Decimal, Decimal] = {}
    for line in invoice.lines or []:
        own = line.get("vat_rate") if isinstance(line, dict) else None
        if own in (None, ""):
            return fallback
        try:
            rate = Decimal(str(own))
            amount = Decimal(str(line["unit_price"])) * Decimal(str(line.get("qty", 1)))
        except Exception:  # noqa: BLE001 — кривой снимок не должен ронять счёт
            return fallback
        by_rate[rate] = by_rate.get(rate, Decimal("0")) + amount
    if not by_rate:
        return fallback
    rows = []
    for rate in sorted(by_rate, reverse=True):
        net = by_rate[rate].quantize(cent, rounding=ROUND_HALF_UP)
        vat = (net * rate / Decimal("100")).quantize(cent, rounding=ROUND_HALF_UP)
        rows.append((rate, net, vat))
    # Ревью W1.2 (M2): строки по ставкам обязаны сходиться со снимком документа.
    # Копеечная разница округления уходит в строку наибольшей ставки; заметная —
    # значит, строки считались не так (брутто-снимок и т. п.) → одна строка снимка.
    diff_net = Decimal(invoice.net) - sum(r[1] for r in rows)
    diff_vat = Decimal(invoice.vat_amount) - sum(r[2] for r in rows)
    if diff_net or diff_vat:
        tolerance = cent * len(invoice.lines or [])
        if abs(diff_net) > tolerance or abs(diff_vat) > tolerance:
            return fallback
        rate, net, vat = rows[0]
        rows[0] = (rate, net + diff_net, vat + diff_vat)
    return rows


def _vat_rows(invoice):
    """[(ставка, сумма налога)] — совместимость с прежними вызовами."""
    return [(rate, vat) for rate, _net, vat in _rate_rows(invoice)]


def _zero_rate_note(invoice) -> str:
    """KA-12 E1.2 (D-3): текст к позициям 0 % — из снимка строки (`vat_note`, напр.
    Kurtaxe), иначе общий. Формулировка — к юристу (пакет E7)."""
    for line in invoice.lines or []:
        if isinstance(line, dict) and str(line.get("vat_rate", "")) in ("0", "0.00", "0.0"):
            if line.get("vat_note"):
                return str(line["vat_note"])
    return _("Steuerfreie bzw. nicht steuerbare Leistung.")


class _NumberedCanvas(canvas.Canvas):
    """Двухпроходный холст: «Seite n von m» на каждой странице (KA-12 E1.2)."""

    def __init__(self, *args, **kwargs):
        self._font = kwargs.pop("page_font")
        super().__init__(*args, **kwargs)
        self._saved_states = []

    def showPage(self):  # noqa: N802 — API reportlab
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            if total > 1:
                self.setFont(self._font, 8)
                self.setFillColorRGB(*_MUTED)
                label = _("Seite %(n)s von %(m)s") % {"n": self._pageNumber, "m": total}
                self.drawRightString(A4[0] - 20 * mm, 12 * mm, label)
            super().showPage()
        super().save()


def build_invoice_pdf(invoice, tenant) -> bytes:
    from reportlab.lib.utils import simpleSplit

    font, font_bold = fonts()
    buffer = io.BytesIO()
    page_w, page_h = A4
    c = _NumberedCanvas(buffer, pagesize=A4, page_font=font)
    x = 20 * mm
    y = page_h - 25 * mm
    bottom = 25 * mm
    is_storno = getattr(invoice, "kind", "invoice") == "storno"
    # KA-12 B2-7b: корректура — свой заголовок (G-1) и ссылка на оригинал; оплаты нет.
    is_credit = getattr(invoice, "kind", "invoice") == "credit"
    no_payment = is_storno or is_credit
    desc_w = page_w - 2 * x - 75 * mm

    def table_header(y):
        c.setFillColorRGB(*_INK)
        c.setFont(font_bold, 9)
        c.drawString(x, y, _("Description"))
        c.drawRightString(page_w - x - 60 * mm, y, _("Quantity"))
        c.drawRightString(page_w - x - 30 * mm, y, _("Unit price"))
        c.drawRightString(page_w - x, y, _("Amount"))
        y -= 2 * mm
        c.line(x, y, page_w - x, y)
        c.setFont(font, 9)
        return y

    def need(y, height, header=False):
        """Мало места — новая страница (с шапкой таблицы, если она идёт)."""
        if y - height >= bottom:
            return y
        c.showPage()
        c.setFont(font, 9)
        y = page_h - 25 * mm
        return table_header(y) if header else y

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
    for line in recipient.splitlines()[:8]:  # CO-2: фирма + адрес + USt-IdNr
        c.drawString(x, y, line)
        y -= 5 * mm

    # Заголовок документа.
    y -= 10 * mm
    c.setFont(font_bold, 16)
    title = (
        _("Stornorechnung")
        if is_storno
        else (_("Rechnungskorrektur") if is_credit else _("Invoice"))
    )
    c.drawString(x, y, f"{title} {invoice.number_display}")
    c.setFont(font, 9)
    c.setFillColorRGB(*_MUTED)
    if invoice.issued_at:
        label_date = _("Date")
        c.drawRightString(page_w - x, y, f"{label_date}: {doc_date(invoice.issued_at)}")
    if is_storno and getattr(invoice, "cancels", None) is not None:
        # KA-12 E1.1: ссылка на исходный счёт (номер и дата) — обязательна у сторно.
        orig = invoice.cancels
        ref = _("Storno zu %(num)s vom %(date)s") % {
            "num": orig.number_display,
            "date": doc_date(orig.issued_at) if orig.issued_at else "",
        }
        c.drawString(x, y - 5 * mm, ref)
    if is_credit and getattr(invoice, "corrects", None) is not None:
        # § 31 UStDV: корректура однозначно ссылается на исправляемый счёт.
        orig = invoice.corrects
        ref = _("Korrektur zu Rechnung %(num)s vom %(date)s") % {
            "num": orig.number_display,
            "date": doc_date(orig.issued_at) if orig.issued_at else "",
        }
        c.drawString(x, y - 5 * mm, ref)
    # SH-23b (Р-2): срок оплаты на документе (у сторно оплаты нет).
    if invoice.due_date and not no_payment:
        label_due = _("Payable by")
        c.drawRightString(page_w - x, y - 4.5 * mm, f"{label_due}: {doc_date(invoice.due_date)}")
    # KA-H10: Leistungsdatum/-zeitraum (§ 14 Abs. 4 Nr. 6 UStG).
    if invoice.service_date:
        if invoice.service_date_end and invoice.service_date_end != invoice.service_date:
            label_service = _("Leistungszeitraum")
            service_text = (
                f"{doc_date(invoice.service_date)} – {doc_date(invoice.service_date_end)}"
            )
        else:
            label_service = _("Leistungsdatum")
            service_text = doc_date(invoice.service_date)
        c.drawRightString(page_w - x, y - 9 * mm, f"{label_service}: {service_text}")

    # Таблица позиций: описание переносится, длинный счёт — на следующие страницы.
    y -= 14 * mm
    y = table_header(y)
    for line in invoice.lines:
        qty_value = Decimal(str(line.get("qty", 1)))  # A7a: дробное кол-во
        unit_price = Decimal(str(line["unit_price"]))
        text = str(line["text"])
        if line.get("sku"):  # SH-20: Art.-Nr. рядом с позицией
            text = f"{text} · {_('Art.-Nr.')} {line['sku']}"
        parts = simpleSplit(text, font, 9, desc_w)[:12] or [""]
        y = need(y, (len(parts) + 1) * 4.5 * mm, header=True)
        y -= 6 * mm
        c.drawString(x, y, parts[0])
        c.drawRightString(page_w - x - 60 * mm, y, f"{qty_value:.2f}".rstrip("0").rstrip("."))
        c.drawRightString(page_w - x - 30 * mm, y, money(unit_price))
        c.drawRightString(page_w - x, y, money(unit_price * qty_value))
        for extra in parts[1:]:
            y -= 4.5 * mm
            c.drawString(x, y, extra)

    # Итоги: нетто и налог ПО КАЖДОЙ ставке (§ 14 Abs. 4 Nr. 8 UStG).
    rows = _rate_rows(invoice)
    y = need(y, (len(rows) * 2 + 6) * 6 * mm)
    y -= 4 * mm
    c.line(page_w / 2, y, page_w - x, y)
    label_net = _("Net")
    label_vat = _("VAT")
    if tenant.small_business:
        y -= 6 * mm
        c.drawRightString(page_w - x - 30 * mm, y, f"{label_net}:")
        c.drawRightString(page_w - x, y, money(invoice.net))
    else:
        for rate, net, vat in rows:
            y -= 6 * mm
            c.drawRightString(page_w - x - 30 * mm, y, f"{label_net} {rate:.0f} %:")
            c.drawRightString(page_w - x, y, money(net))
            y -= 5 * mm
            c.drawRightString(page_w - x - 30 * mm, y, f"{label_vat} {rate:.0f} %:")
            c.drawRightString(page_w - x, y, money(vat))
    y -= 7 * mm
    c.setFont(font_bold, 11)
    label_total = _("Total")
    c.drawRightString(page_w - x - 30 * mm, y, f"{label_total}:")
    c.drawRightString(page_w - x, y, money(invoice.gross))
    if invoice.prepaid_cents and not no_payment:  # KA-H10: уже получено → к оплате остаток
        from decimal import Decimal as _D

        c.setFont(font, 9)
        y -= 5 * mm
        label_paid = _("Bereits erhalten")
        c.drawRightString(page_w - x - 30 * mm, y, f"{label_paid}:")
        c.drawRightString(page_w - x, y, "−" + money(_D(invoice.prepaid_cents) / 100))
        y -= 5 * mm
        c.setFont(font_bold, 10)
        label_due_amount = _("Zu zahlen")
        c.drawRightString(page_w - x - 30 * mm, y, f"{label_due_amount}:")
        # Документ не меняется после выставления (GoBD): «к оплате» — на момент
        # выпуска, без последующих корректур (они — свои документы).
        printed_due = max(_D(invoice.gross) - _D(invoice.prepaid_cents) / 100, _D("0"))
        c.drawRightString(page_w - x, y, money(printed_due))

    # Hinweise.
    notes = []
    if tenant.small_business:
        # Ссылка на § 19 UStG остаётся — это идентификатор нормы, не текст.
        notes.append(_("No VAT is charged in accordance with § 19 UStG."))
    elif any(r[0] == 0 for r in rows):
        notes.append(_zero_rate_note(invoice))
    if invoice.note:
        notes.append(invoice.note)
    c.setFont(font, 8)
    c.setFillColorRGB(*_MUTED)
    y -= 14 * mm
    for note in notes:
        for part in simpleSplit(note, font, 8, page_w - 2 * x):
            y = need(y, 5 * mm)
            c.drawString(x, y, part)
            y -= 4.5 * mm

    # Легаси: отменённый счёт БЕЗ Stornorechnung (до KA-12) сохраняет водяной знак —
    # его PDF не меняется второй раз. Новые отмены — отдельный документ, без знака.
    legacy_cancel = invoice.status == "cancelled" and not getattr(
        invoice, "storno_doc_id_safe", None
    )
    if legacy_cancel:
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
