"""ERP-8: Mängelanzeige — рекламация поставщику (§ 377 HGB, Rügepflicht).

План — `docs/erp8-maengelanzeige-plan-2026-10-09.md`. Одна рекламация на поставку
(`Bestellung`), строки — дефектные позиции. Решение по строке применяется ровно один раз:

* `discount` — товар остаётся, скидка книжится сторно-расходом (Gutschrift);
* `return` — ERP-5 `return_po_line` целиком (движение, FEFO, сторно);
* `replacement` — возврат + строка снова ждёт столько же штук к приёмке. Деньги
  сходятся сами: приёмка +N, сторно −N, приёмка замены +N = одна оплата.

Склад и деньги двигают ТОЛЬКО существующие пути закупок — своей логики проводок здесь нет.
"""

import secrets
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import purchasing
from .models import BestellPosition, Bestellung, Maengelanzeige, Mangel

# Виды дефектов — как на бумажном бланке владельца (порядок = порядок галок).
DEFECT_TYPES = (
    ("packaging", _("Verpackungsschaden")),
    ("wrong_item", _("Artmangel / Falschlieferung")),
    ("quantity", _("Quantitätsmangel / falsche Menge")),
    ("quality", _("Qualitätsmangel")),
    ("other", _("Sonstiges")),
)
DEFECT_LABELS = dict(DEFECT_TYPES)

DECISION_DISCOUNT = "discount"
DECISION_REPLACEMENT = "replacement"
DECISION_RETURN = "return"
DECISIONS = {code for code, _label in Mangel.DECISIONS}

STATUS_OPEN = "open"
STATUS_DONE = "done"

_ALPHABET = "ACDEFGHJKLMNPQRSTUVWXYZ2345679"  # без похожих символов (как BE-код)


def clean_defect_types(raw) -> list[str]:
    """Коды из реестра, без дублей, в порядке реестра; мусор отбрасывается."""
    picked = {str(code) for code in (raw or [])}
    return [code for code, _label in DEFECT_TYPES if code in picked]


def defect_labels(mangel) -> list[str]:
    return [str(DEFECT_LABELS[code]) for code in clean_defect_types(mangel.defect_types)]


def _unique_code() -> str:
    for _attempt in range(10):
        code = "MA-" + "".join(secrets.choice(_ALPHABET) for _i in range(6))
        if not Maengelanzeige.objects.filter(reference=code).exists():
            return code
    raise RuntimeError("could not generate unique complaint reference code")


def create_anzeige(
    bestellung,
    *,
    lines,
    actor="",
    delivery_date=None,
    inspected_at=None,
    carrier="",
    delivery_note_ref="",
    result="",
):
    """Создать рекламацию по поставке. `lines` — [{position, qty, defect_types,
    description}]; берутся только строки ЭТОГО заказа с qty > 0, кол-во клампится по
    позиции (больше, чем заказано или принято, дефектным быть не может). Ни одной
    строки — None (пустой бланк не заводим)."""
    rows = []
    for spec in lines or []:
        position = spec.get("position")
        if not isinstance(position, BestellPosition) or position.bestellung_id != bestellung.pk:
            continue
        try:
            qty = int(spec.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0
        qty = min(max(qty, 0), max(position.qty, position.qty_received))
        if qty <= 0:
            continue
        rows.append(
            (
                position,
                qty,
                clean_defect_types(spec.get("defect_types")),
                (spec.get("description") or "").strip()[:2000],
            )
        )
    if not rows:
        return None
    with transaction.atomic():
        anzeige = Maengelanzeige.objects.create(
            bestellung=bestellung,
            reference=_unique_code(),
            delivery_date=delivery_date,
            inspected_at=inspected_at or timezone.localdate(),
            carrier=(carrier or "").strip()[:150],
            delivery_note_ref=(delivery_note_ref or "").strip()[:64],
            result=(result or "").strip()[:4000],
            inspected_by=(actor or "")[:150],
        )
        for position, qty, types, description in rows:
            Mangel.objects.create(
                anzeige=anzeige,
                position=position,
                qty=qty,
                defect_types=types,
                description=description,
            )
    return anzeige


def resolve(mangel, decision, *, discount=None, actor="", tenant=None) -> bool:
    """Применить решение к строке рекламации. Ровно один раз: строка с решением, неизвестное
    решение или скидка без суммы — False, ничего не двигается."""
    if decision not in DECISIONS:
        return False
    if decision == DECISION_DISCOUNT:
        try:
            discount = Decimal(str(discount or 0)).quantize(Decimal("0.01"))
        except Exception:  # noqa: BLE001 — мусор в сумме = скидки нет
            discount = Decimal("0")
        if discount <= 0:
            return False
    with transaction.atomic():
        # блокировка строки: двойной клик не применит решение дважды
        mangel = Mangel.objects.select_for_update().select_related("anzeige").get(pk=mangel.pk)
        if mangel.resolved_at is not None:
            return False
        position = BestellPosition.objects.select_related("bestellung__supplier").get(
            pk=mangel.position_id
        )
        reference = mangel.anzeige.reference
        resolved_qty = 0
        if decision == DECISION_DISCOUNT:
            from apps.finance.expenses import ExpenseEntry

            ExpenseEntry.objects.get_or_create(
                source=ExpenseEntry.SOURCE_PURCHASE,
                # ключ — 64 символа: два UUID не влезают; pk строки рекламации уникален сам
                source_ref=f"mangel:{mangel.pk}",
                defaults={
                    "amount": -discount,
                    "category": ExpenseEntry.CATEGORY_GOODS,
                    "supplier": position.bestellung.supplier,
                    "note": f"Preisnachlass {reference} · {position.bestellung.reference}"[:200],
                },
            )
            mangel.discount = discount
        else:
            resolved_qty = purchasing.return_po_line(
                position, qty=mangel.qty, tenant=tenant, actor=actor
            )
            if decision == DECISION_REPLACEMENT and resolved_qty:
                position.refresh_from_db()
                position.qty_replacement += resolved_qty
                position.save(update_fields=["qty_replacement", "updated_at"])
                _reopen(position.bestellung)
        mangel.decision = decision
        mangel.resolved_qty = resolved_qty
        mangel.resolved_at = timezone.now()
        mangel.save(
            update_fields=["decision", "discount", "resolved_qty", "resolved_at", "updated_at"]
        )
    return True


def _reopen(bestellung) -> None:
    """Замена ждёт приёмки — принятый заказ снова «bestellt» (иначе форма приёмки не
    покажется), а дата полной приёмки сбрасывается: заказ ещё не закрыт."""
    if bestellung.status != Bestellung.STATUS_RECEIVED:
        return
    bestellung.status = Bestellung.STATUS_ORDERED
    bestellung.received_at = None
    bestellung.save(update_fields=["status", "received_at", "updated_at"])


def status_of(anzeige) -> str:
    """Открыта, пока есть строка без решения (поставщик ещё не ответил)."""
    pending = any(m.resolved_at is None for m in anzeige.maengel.all())
    return STATUS_OPEN if pending else STATUS_DONE


def open_counts(bestellung_ids) -> dict:
    """{pk заказа: число открытых рекламаций} — для бейджа в списке заказов (1 запрос)."""
    from django.db.models import Count

    rows = (
        Maengelanzeige.objects.filter(
            bestellung_id__in=list(bestellung_ids), maengel__resolved_at__isnull=True
        )
        .values("bestellung_id")
        .annotate(n=Count("id", distinct=True))
    )
    return {row["bestellung_id"]: row["n"] for row in rows}


def mark_notified(anzeige) -> None:
    """Отметить, что поставщику заявлено (первая дата важна для § 377 HGB — не
    перезаписываем)."""
    if anzeige.notified_at is None:
        anzeige.notified_at = timezone.now()
        anzeige.save(update_fields=["notified_at", "updated_at"])


def send_to_supplier(anzeige, tenant) -> bool:
    """Отправить бланк поставщику по e-mail (PDF вложением) и отметить дату заявления.

    Без e-mail у поставщика — False (бланк уходит факсом/почтой, дату ставят вручную).
    Каждая отправка — своё письмо (повтор после правки бланка разрешён); dedupe-ключ
    с номером отправки гасит дубль одного и того же клика (блокировка строки)."""
    from django.db import connection
    from django.template.loader import render_to_string
    from django.utils import translation
    from django.utils.translation import gettext

    from apps.notifications.services import email_locale, notify

    from .pdf import build_maengel_pdf

    supplier = anzeige.bestellung.supplier
    email = (getattr(supplier, "email", "") or "").strip()
    if not email:
        return False
    with transaction.atomic():
        anzeige = (
            # of=self: поставщик — nullable join, его FOR UPDATE Postgres не берёт
            Maengelanzeige.objects.select_for_update(of=("self",))
            .select_related("bestellung__supplier")
            .get(pk=anzeige.pk)
        )
        ctx = {
            "reference": anzeige.reference,
            "order": anzeige.bestellung.reference,
            "business_name": getattr(tenant, "name", "") or "",
            "contact": supplier.contact_person,
        }
        with translation.override(email_locale()):
            subject = render_to_string("emails/maengelanzeige_subject.txt", ctx).strip()
            body = render_to_string("emails/maengelanzeige.txt", ctx)
            doc_name = gettext("Notice of defects")
            pdf = build_maengel_pdf(anzeige, tenant)
        number = anzeige.sent_count + 1
        sent = notify(
            dedupe_key=f"{connection.schema_name}:maengel:{anzeige.pk}:{number}",
            type="maengelanzeige",
            recipient=email,
            subject=subject,
            body=body,
            attachments=[(f"{doc_name}-{anzeige.reference}.pdf", pdf, "application/pdf")],
        )
        if sent is None:
            return False
        anzeige.sent_count = number
        anzeige.save(update_fields=["sent_count", "updated_at"])
        mark_notified(anzeige)
    return True
