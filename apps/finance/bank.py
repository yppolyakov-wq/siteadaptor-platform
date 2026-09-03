"""ERP-2: банковская выписка — импорт CSV, сопоставление с открытыми позициями.

План docs/erp-wave-plan-2026-08-21.md §ERP-2. Замыкает цикл денег: Vorkasse (E7
пишет Verwendungszweck = reference_code сделки) до сих пор сверялась глазами.

Импорт: авто-детект колонок по заголовкам немецких банков (Sparkasse/DKB/ING и
пр. называют их по-разному), `;`- и `,`-CSV, немецкие суммы «1.234,56», cp1252
и utf-8. Кривой файл — честная ошибка, а не тихий ноль. Дедуп повторного
импорта — по хэшу (дата|сумма|назначение).

Сопоставление: код сделки в Verwendungszweck (сильное) и совпадение суммы
(кандидаты). Подтверждение кликом ставит оплату ШТАТНО (payment_state / InvoiceSM)
— своих тропинок к статусам не заводим.
"""

import csv
import hashlib
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core import status_registry, transactions

# --- разбор CSV ----------------------------------------------------------------

_DATE_HEADERS = ("buchungstag", "buchung", "datum", "valutadatum", "wertstellung", "date")
_AMOUNT_HEADERS = ("betrag", "umsatz", "amount", "betrag (eur)")
_PURPOSE_HEADERS = ("verwendungszweck", "zweck", "buchungstext", "beschreibung", "purpose")
_PARTY_HEADERS = (
    "beguenstigter/zahlungspflichtiger",
    "beguenstigter",
    "begünstigter/zahlungspflichtiger",
    "auftraggeber/empfaenger",
    "auftraggeber",
    "name",
    "empfaenger",
    "empfänger",
)


class BankImportError(Exception):
    """CSV не распознан (нет колонок даты/суммы) — честная ошибка владельцу."""


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _find(header_row, candidates):
    lowered = [h.strip().lower() for h in header_row]
    for cand in candidates:
        if cand in lowered:
            return lowered.index(cand)
    # частичное совпадение («betrag (eur)» и пр.)
    for i, h in enumerate(lowered):
        if any(cand in h for cand in candidates):
            return i
    return None


def _parse_amount(raw: str) -> Decimal:
    s = str(raw or "").strip().replace("\xa0", "").replace(" ", "")
    if "," in s:  # немецкий формат: точка — тысячи, запятая — центы
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def _parse_date(raw: str):
    s = str(raw or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_csv(raw: bytes) -> list[dict]:
    """[{date, amount, purpose, counterparty}] из выгрузки банка. Строки без
    даты/суммы пропускаются; нет самих колонок → BankImportError."""
    text = _decode(raw)
    delimiter = ";" if text.count(";") >= text.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise BankImportError("empty file")
    header = rows[0]
    di = _find(header, _DATE_HEADERS)
    ai = _find(header, _AMOUNT_HEADERS)
    if di is None or ai is None:
        raise BankImportError("no date/amount columns")
    pi = _find(header, _PURPOSE_HEADERS)
    ci = _find(header, _PARTY_HEADERS)
    out = []
    for r in rows[1:]:
        if len(r) <= max(di, ai):
            continue
        date = _parse_date(r[di])
        try:
            amount = _parse_amount(r[ai])
        except (InvalidOperation, ValueError):
            amount = None
        if date is None or amount is None:
            continue
        out.append(
            {
                "date": date,
                "amount": amount,
                "purpose": (r[pi].strip() if pi is not None and len(r) > pi else "")[:500],
                "counterparty": (r[ci].strip() if ci is not None and len(r) > ci else "")[:200],
            }
        )
    return out


def import_rows(rows) -> int:
    """Создать BankTransaction из разобранных строк; дедуп по хэшу. Возвращает
    число НОВЫХ строк."""
    from .models import BankTransaction

    created = 0
    for row in rows:
        h = hashlib.md5(
            f"{row['date']}|{row['amount']}|{row['purpose']}|{row['counterparty']}".encode()
        ).hexdigest()
        _, was_created = BankTransaction.objects.get_or_create(
            import_hash=h,
            defaults={
                "date": row["date"],
                "amount": row["amount"],
                "purpose": row["purpose"],
                "counterparty": row["counterparty"],
            },
        )
        created += int(was_created)
    return created


# --- открытые позиции ----------------------------------------------------------

# kind → какие payment_state означают «ЖДЁМ денег». none у броней = оплата на
# месте (не долг), поэтому в открытые не идёт; у заказа unpaid — идёт.
_OPEN_PAYMENT_STATES = {
    "order": ("unpaid",),
    "booking": ("pending",),
    "stay": ("pending",),
    "ticket": ("pending", "deposit"),
}


def open_items(tenant) -> list[dict]:
    """Открытые позиции: сделки, ждущие оплату (+ выставленные счета). Строка:
    {kind, obj, code, title, amount, customer, age_days, tx}."""
    from .models import Invoice

    today = timezone.localdate()
    out = []
    for kind, states in _OPEN_PAYMENT_STATES.items():
        if not tenant.is_module_active(transactions.KIND_MODULE[kind]):
            continue
        model = transactions.model_for(kind)
        qs = (
            model.objects.filter(payment_state__in=states)
            .exclude(status__in=status_registry.cancelled_statuses_for(kind, tenant))
            .order_by("created_at")[:200]
        )
        for obj in qs:
            t = transactions.transaction_for(kind, obj)
            if not t.amount_value:
                continue
            out.append(
                {
                    "kind": kind,
                    "kind_label": transactions.KIND_LABEL.get(kind, kind),
                    "obj": obj,
                    "code": getattr(obj, "reference_code", str(obj.pk)),
                    "title": t.title,
                    "amount": t.amount_value,
                    "customer": getattr(obj, "customer", None),
                    "age_days": (today - obj.created_at.date()).days,
                    "manage_url": t.manage_url,
                    # SH-23b: срок оплаты сделки (Р-2/Р-4) — просроченное видно
                    # сразу, а не по возрасту записи.
                    "due_date": (
                        getattr(obj, "payment_due_at", None).date()
                        if getattr(obj, "payment_due_at", None)
                        else None
                    ),
                }
            )
    for inv in Invoice.objects.filter(status="issued").order_by("issued_at")[:200]:
        out.append(
            {
                "kind": "invoice",
                "kind_label": _("Rechnung"),
                "obj": inv,
                "code": inv.number_display if hasattr(inv, "number_display") else str(inv.number),
                "title": str(inv.recipient or "")[:60],
                "amount": inv.gross,
                "customer": inv.customer,
                "age_days": (today - inv.issued_at.date()).days if inv.issued_at else 0,
                "manage_url": "",
                "due_date": inv.due_date,
            }
        )
    # SH-23b: сначала просроченное (по сроку оплаты), затем самое старое —
    # владелец видит «что горит», а не просто «что давно лежит».
    out.sort(key=lambda r: (r.get("due_date") or today, -r["age_days"]))
    return out


# --- сопоставление -------------------------------------------------------------

_CODE_RE = re.compile(r"\b([A-Z]-[A-Z0-9]{6})\b")


def suggestions(tx, items) -> list[dict]:
    """Кандидаты открытых позиций для транзакции: код сделки в Verwendungszweck —
    сильное совпадение (первым); равная сумма — слабое."""
    purpose = (tx.purpose or "").upper()
    codes = set(_CODE_RE.findall(purpose))
    strong = [i for i in items if str(i["code"]).upper() in codes]
    weak = [
        i
        for i in items
        if i not in strong and i["amount"] is not None and abs(tx.amount) == i["amount"]
    ]
    return [{"item": i, "strong": True} for i in strong] + [
        {"item": i, "strong": False} for i in weak[:5]
    ]


def apply_match(tx, kind: str, obj) -> None:
    """Подтвердить сопоставление: пометить оплату ШТАТНЫМ путём + привязать tx."""
    if kind == "invoice":
        from .state_machine import InvoiceSM

        if obj.status == "issued":
            InvoiceSM().apply(obj, "paid")
    else:
        paid = "paid"
        if obj.payment_state != paid:
            obj.payment_state = paid
            obj.save(update_fields=["payment_state", "updated_at"])
    tx.matched_kind = kind
    tx.matched_id = str(obj.pk)
    tx.matched_at = timezone.now()
    tx.save(update_fields=["matched_kind", "matched_id", "matched_at", "updated_at"])
