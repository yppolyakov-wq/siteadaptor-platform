"""Запись выручки (Track D / D4a) — идемпотентно для хуков FSM.

Вызывается из OrderSM (picked_up) и ReservationSM (fulfilled): один документ →
одна запись, повторный вызов с тем же (source, source_ref) — no-op (unique
constraint в БД). Ручные записи (source=manual) идут без source_ref.
"""

import logging
from decimal import Decimal

from django.db import models
from django.utils import timezone

from .models import RevenueEntry
from .recipient import recipient_for

logger = logging.getLogger(__name__)


def record_revenue(
    *,
    source,
    amount,
    source_ref="",
    currency="EUR",
    vat_rate=None,
    date=None,
    customer=None,
    note="",
):
    """Создать запись выручки. None — дубль (идемпотентный повтор хука)."""
    if amount is None or amount <= 0:
        return None
    defaults = {
        "amount": amount,
        "currency": currency,
        "date": date or timezone.localdate(),
        "customer": customer,
        "note": note[:200],
    }
    if vat_rate is not None:
        defaults["vat_rate"] = vat_rate
    if not source_ref:  # ручная запись — без дедупа
        return RevenueEntry.objects.create(source=source, **defaults)
    entry, created = RevenueEntry.objects.get_or_create(
        source=source, source_ref=source_ref, defaults=defaults
    )
    return entry if created else None


def record_reversal(
    *, source, source_ref, amount, currency="EUR", customer=None, note="", vat_rate=None
):
    """Сторно-запись возврата: отрицательная сумма, идемпотентно по source_ref.

    Для возвратов (A2c): на ту же сумму, что была проведена при выдаче/отправке,
    но со знаком минус — чистая выручка по документу становится нулевой.
    """
    if amount is None or amount <= 0:
        return None
    defaults = {
        "amount": -amount,
        "currency": currency,
        "date": timezone.localdate(),
        "customer": customer,
        "note": note[:200],
    }
    if vat_rate is not None:  # KA-H8: ставка исходной записи (иначе — дефолт модели)
        defaults["vat_rate"] = vat_rate
    entry, created = RevenueEntry.objects.get_or_create(
        source=source, source_ref=source_ref, defaults=defaults
    )
    return entry if created else None


def minderung_total(source: str, deal_id) -> Decimal:
    """KA-12 B2-4b: сколько выручки сделки уже сторнировано Minderung (положительное
    число). Сторно при отмене вычитает его — иначе сумма ушла бы в минус дважды."""
    from django.db.models import Sum

    total = RevenueEntry.objects.filter(
        source=source, source_ref__startswith=f"{deal_id}:minderung:"
    ).aggregate(s=Sum("amount"))["s"]
    return -Decimal(total or 0)


def record_minderung(*, source: str, deal, amount: Decimal, key: str) -> None:
    """Сторно проведённой выручки на сумму уступки — по записям сделки (основная,
    потом «:meal» и прочие), каждая своей ставкой; уже сделанные уступки занимают
    записи в том же порядке (так их вычитает и сторно при отмене). Не проведено —
    нечего сторнировать: выручку потом посчитают от сниженной цены."""
    entries = list(
        RevenueEntry.objects.filter(source=source, amount__gt=0)
        .filter(models.Q(source_ref=str(deal.id)) | models.Q(source_ref__startswith=f"{deal.id}:"))
        .exclude(source_ref__startswith=f"{deal.id}:minderung:")
        .order_by("source_ref")
    )
    taken = minderung_total(source, deal.id)
    left = amount
    for entry in entries:
        room = entry.amount - min(taken, entry.amount)
        taken -= min(taken, entry.amount)
        part = min(left, room)
        if part <= 0:
            continue
        suffix = entry.source_ref[len(str(deal.id)) :]
        record_reversal(
            source=source,
            source_ref=f"{deal.id}:minderung:{key}{suffix}",
            amount=part,
            vat_rate=entry.vat_rate,
            customer=getattr(deal, "customer", None),
            note=f"Minderung {getattr(deal, 'reference_code', '')}",
        )
        left -= part
        if left <= 0:
            break
    if left > 0 and entries:
        logger.warning("minderung %s %s: %s not reversed (more than posted)", source, deal.id, left)


def _invoice_gross_by_rate(invoice) -> list:
    """[(ставка, брутто)] счёта по группам ставок строк (как compute_totals: строки
    нетто, налог по группе). Σ ≠ gross счёта (кривой снимок) → одна строка по ставке
    документа на весь gross — журнал никогда не расходится с документом."""
    from decimal import ROUND_HALF_UP, Decimal

    cent = Decimal("0.01")
    default_rate = Decimal(str(invoice.vat_rate))
    no_vat = Decimal(invoice.vat_amount or 0) == 0
    groups: dict[Decimal, Decimal] = {}
    try:
        for line in invoice.lines or []:
            own = line.get("vat_rate")
            rate = (
                Decimal("0")
                if no_vat
                else (default_rate if own in (None, "") else Decimal(str(own)))
            )
            amount = _to_decimal(line["unit_price"], "0") * _to_decimal(line.get("qty", 1))
            groups[rate] = groups.get(rate, Decimal("0")) + amount
    except (KeyError, TypeError, AttributeError, ArithmeticError):
        groups = {}
    rows = []
    for rate in sorted(groups, reverse=True):
        net = groups[rate].quantize(cent, rounding=ROUND_HALF_UP)
        gross = net + (net * rate / Decimal("100")).quantize(cent, rounding=ROUND_HALF_UP)
        if gross:
            rows.append((rate, gross))
    # Отрицательная группа (скидка другой ставки) не проводится record_revenue —
    # журнал разошёлся бы с документом; тогда одной строкой по ставке документа.
    if (
        not rows
        or any(g <= 0 for _r, g in rows)
        or sum(g for _r, g in rows) != Decimal(invoice.gross)
    ):
        return [(Decimal("0") if no_vat else default_rate, Decimal(invoice.gross))]
    return rows


def _minus_voucher(rows, voucher_cents: int) -> list:
    """Вычесть оплату Wertgutschein пропорционально строкам: продажа сертификата уже
    в журнале (`loyalty.gift`), повтор в счёте задвоил бы выручку."""
    from decimal import ROUND_HALF_UP, Decimal

    if not voucher_cents or not rows:
        return rows
    total = sum(g for _r, g in rows)
    cut = min(Decimal(voucher_cents) / 100, total)
    if cut <= 0:
        return rows
    out, left = [], cut
    for i, (rate, gross) in enumerate(rows):
        share = (
            left
            if i == len(rows) - 1
            else (cut * gross / total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        left -= share
        out.append((rate, gross - share))
    return [(rate, g) for rate, g in out if g > 0]


def journal_invoice_revenue(invoice) -> None:
    """KA-D2 (решение владельца 2026-10-23): выручка заявки/мастерской — в журнал при
    выставлении счёта, по строке на ставку. Только счета из заявок (`deal_kind="job"`):
    остальные виды проводятся своими статусами (иначе выручка задвоится).
    Идемпотентно по `inv:<pk>:<ставка>`."""
    if invoice.deal_kind != "job" or not invoice.gross:
        return
    if invoice.kind != invoice.KIND_INVOICE:  # B2-8b: предоплата — не выручка (MC-D1)
        return
    voucher_cents = 0
    try:
        from apps.jobs.models import Job
        from apps.jobs.services import voucher_payment_cents

        job = Job.objects.filter(reference_code=invoice.deal_id).first()
        voucher_cents = voucher_payment_cents(job) if job is not None else 0
    except Exception:  # noqa: BLE001 — журнал не должен ронять выпуск счёта
        logger.exception("job revenue: voucher lookup failed for invoice %s", invoice.pk)
    for rate, gross in _minus_voucher(_invoice_gross_by_rate(invoice), voucher_cents):
        record_revenue(
            source=RevenueEntry.SOURCE_JOB,
            amount=gross,
            source_ref=f"inv:{invoice.pk}:{rate}",
            vat_rate=rate,
            date=timezone.localdate(invoice.issued_at) if invoice.issued_at else None,
            customer=invoice.customer,
            note=f"Rechnung {invoice.number_display}"[:200],
        )


def _credit_marker(credit) -> str:
    """Метка сторно корректуры в source_ref (varchar(64): номер, а не uuid)."""
    return f"c{credit.number}"


def _job_credit_reversed(invoice) -> dict:
    """{ставка: сумма} уже сторнированного корректурами по счёту заявки (положительная)."""
    out: dict = {}
    for entry in RevenueEntry.objects.filter(
        source=RevenueEntry.SOURCE_JOB,
        source_ref__startswith=f"inv:{invoice.pk}:c",
        amount__lt=0,
    ):
        out[entry.vat_rate] = out.get(entry.vat_rate, Decimal("0")) - entry.amount
    return out


def reverse_job_credit(invoice, credit) -> None:
    """KA-12 B2-7c: корректура счёта заявки сторнирует проведённую выручку по
    ставкам — не больше, чем осталось проведённым по этой ставке."""
    from decimal import ROUND_HALF_UP

    if invoice.deal_kind != "job":
        return
    cent = Decimal("0.01")
    small = Decimal(credit.vat_amount or 0) == 0
    groups: dict = {}
    for line in credit.lines or []:
        own = line.get("vat_rate")
        rate = (
            Decimal("0")
            if small
            else Decimal(str(own if own not in (None, "") else credit.vat_rate))
        )
        amount = abs(_to_decimal(line["unit_price"], "0") * _to_decimal(line.get("qty", 1)))
        groups[rate] = groups.get(rate, Decimal("0")) + amount
    posted: dict = {}
    for entry in RevenueEntry.objects.filter(
        source=RevenueEntry.SOURCE_JOB, source_ref__startswith=f"inv:{invoice.pk}:", amount__gt=0
    ):
        posted[entry.vat_rate] = posted.get(entry.vat_rate, Decimal("0")) + entry.amount
    taken = _job_credit_reversed(invoice)
    for rate, net_sum in groups.items():
        net = net_sum.quantize(cent, rounding=ROUND_HALF_UP)
        gross = net + (net * rate / Decimal("100")).quantize(cent, rounding=ROUND_HALF_UP)
        room = posted.get(rate, Decimal("0")) - taken.get(rate, Decimal("0"))
        part = min(gross, room)
        if part <= 0:
            continue
        record_reversal(
            source=RevenueEntry.SOURCE_JOB,
            source_ref=f"inv:{invoice.pk}:{_credit_marker(credit)}:{rate}",
            amount=part,
            vat_rate=rate,
            customer=invoice.customer,
            note=f"Korrektur {credit.number_display}"[:200],
        )


def reverse_invoice_revenue(invoice) -> None:
    """Сторно счёта из заявки → сторно-записи на каждую проведённую строку за вычетом
    того, что уже сторнировали корректуры (B2-7c) — иначе выручка ушла бы в минус."""
    if invoice.kind != invoice.KIND_INVOICE:  # B2-8b: у предоплаты выручки нет
        return
    if invoice.deal_kind != "job":
        return
    entries = RevenueEntry.objects.filter(
        source=RevenueEntry.SOURCE_JOB,
        source_ref__startswith=f"inv:{invoice.pk}:",
        amount__gt=0,
    ).order_by("source_ref")
    credited = _job_credit_reversed(invoice)
    for entry in list(entries):
        if entry.source_ref.endswith(":reversal"):
            continue
        already = min(credited.get(entry.vat_rate, Decimal("0")), entry.amount)
        credited[entry.vat_rate] = credited.get(entry.vat_rate, Decimal("0")) - already
        record_reversal(
            source=RevenueEntry.SOURCE_JOB,
            source_ref=f"{entry.source_ref}:reversal",
            amount=entry.amount - already,
            vat_rate=entry.vat_rate,
            customer=entry.customer,
            note=f"Storno {entry.note}"[:200],
        )


def _to_decimal(value, default="1"):
    from decimal import Decimal, InvalidOperation

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def compute_totals(lines, vat_rate, *, small_business=False):
    """(net, vat, gross) из снимка позиций; §19 Kleinunternehmer — без НДС.

    qty может быть дробным (A7a, часы/единицы Handwerker) — считаем как Decimal.

    VAT-4: если строка несёт СВОЮ ставку (`line["vat_rate"]`), налог считается по
    группам ставок — иначе смешанный счёт (еда 7 % + напитки 19 %) считался по
    одной преобладающей и расходился с суммой заказа. Строки без своей ставки
    идут по переданной, поэтому старые вызовы работают байт-в-байт.
    """
    from decimal import ROUND_HALF_UP, Decimal

    cent = Decimal("0.01")
    default_rate = Decimal("0") if small_business else Decimal(str(vat_rate))
    by_rate: dict[Decimal, Decimal] = {}
    for line in lines:
        own = line.get("vat_rate")
        rate = default_rate if own in (None, "") else Decimal(str(own))
        if small_business:
            rate = Decimal("0")
        amount = _to_decimal(line["unit_price"], "0") * _to_decimal(line.get("qty", 1))
        by_rate[rate] = by_rate.get(rate, Decimal("0")) + amount

    net = Decimal("0")
    vat = Decimal("0")
    for rate, amount in by_rate.items():
        group_net = amount.quantize(cent, rounding=ROUND_HALF_UP)
        net += group_net
        vat += (group_net * rate / Decimal("100")).quantize(cent, rounding=ROUND_HALF_UP)
    return net, vat, net + vat


def fit_gross(lines, target, vat_rate, *, small_business=False):
    """KA-MC X5: подогнать снимок позиций так, чтобы брутто счёта = итогу сделки.

    Цены сделок брутто, счёт считает от нетто: нетто за штуку, округлённое до
    цента, при qty > 1 или нескольких строках уводит счёт на цент (2 × 12,50 €
    давали 24,99 €). Правим нетто САМОЙ КРУПНОЙ облагаемой строки с точностью
    0,0001 — `compute_totals` округляет только группы ставок, а PDF печатает цену
    штуки с двумя знаками, поэтому документ остаётся читаемым. Строки с явной
    ставкой 0 (Kurtaxe) не трогаем. Возвращает те же `lines` (изменены на месте)."""
    from decimal import ROUND_HALF_UP, Decimal

    cent = Decimal("0.01")
    fine = Decimal("0.0001")
    target = Decimal(str(target)).quantize(cent, rounding=ROUND_HALF_UP)
    default = Decimal("0") if small_business else Decimal(str(vat_rate))

    def line_rate(line):
        own = line.get("vat_rate")
        rate = default if own in (None, "") else Decimal(str(own))
        return Decimal("0") if small_business else rate

    # Подгоняем ТОЛЬКО остаток округления: цент на строку/штуку. Больше — значит в
    # строках нет какой-то части сделки; такое не прячем в цену, а оставляем как есть.
    tolerance = cent * (len(lines) + sum(_to_decimal(ln.get("qty", 1)) for ln in lines))
    _net, _vat, gross = compute_totals(lines, vat_rate, small_business=small_business)
    if target <= 0 or abs(target - gross) > tolerance:
        if target != gross:
            logger.warning("finance: invoice lines differ from deal total, not fitted")
        return lines
    for _attempt in range(6):
        _net, _vat, gross = compute_totals(lines, vat_rate, small_business=small_business)
        diff = target - gross
        if not diff:
            return lines
        candidates = [
            ln
            for ln in lines
            if _to_decimal(ln["unit_price"], "0") > 0 and (small_business or line_rate(ln) > 0)
        ]
        if not candidates:
            break
        line = max(
            candidates,
            key=lambda ln: _to_decimal(ln["unit_price"], "0") * _to_decimal(ln.get("qty", 1)),
        )
        qty = _to_decimal(line.get("qty", 1)) or Decimal("1")
        step = (diff / (1 + line_rate(line) / Decimal("100")) / qty).quantize(
            fine, rounding=ROUND_HALF_UP
        )
        if not step:
            step = fine if diff > 0 else -fine
        new_price = _to_decimal(line["unit_price"], "0") + step
        if new_price <= 0:
            break
        line["unit_price"] = str(new_price)
    logger.warning("finance: invoice rounding residual vs deal total %s", target)
    return lines


def _next_number() -> int:
    """Следующий номер счёта под блокировкой счётчика (вызывать внутри atomic).
    Один счётчик на счета и Stornorechnungen — сквозная нумерация без пропусков."""
    from .models import InvoiceCounter

    counter, _created = InvoiceCounter.objects.select_for_update().get_or_create(pk=1)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return counter.last_number


def create_storno(original):
    """KA-12 E1.1 (GoBD): Stornorechnung к отменённому счёту — свой номер из того же
    счётчика, позиции с количеством со знаком минус, суммы = минус суммы оригинала
    (снимок, не пересчёт). Идемпотентно: одна Stornorechnung на счёт (one-to-one).
    Оригинал не трогаем."""
    from django.db import transaction
    from django.utils import timezone as tz

    from .models import Invoice

    if original.kind == Invoice.KIND_STORNO or not original.number:
        return None
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=original.pk)
        existing = Invoice.objects.filter(cancels=locked).first()
        if existing is not None:
            return existing
        # KA-12 B2-7b: сторно снимает ОСТАТОК — у счёта с корректурами строки
        # корректур входят со своим знаком, иначе сторно + корректуры дали бы минус
        # больше оригинала.
        credits = list(locked.corrections.exclude(status=Invoice.STATUS_DRAFT))
        lines = []
        for doc_lines in [locked.lines or []] + [c.lines or [] for c in credits]:
            for line in doc_lines:
                neg = dict(line)
                neg["qty"] = -_to_decimal(line.get("qty", 1))
                neg["qty"] = int(neg["qty"]) if neg["qty"] == int(neg["qty"]) else str(neg["qty"])
                lines.append(neg)
        storno = Invoice.objects.create(
            kind=Invoice.KIND_STORNO,
            cancels=locked,
            status=Invoice.STATUS_ISSUED,
            number=_next_number(),
            issued_at=tz.now(),
            language=locked.language,
            customer=locked.customer,
            recipient=locked.recipient,
            lines=lines,
            vat_rate=locked.vat_rate,
            net=-(locked.net + sum((c.net for c in credits), Decimal("0"))),
            vat_amount=-(locked.vat_amount + sum((c.vat_amount for c in credits), Decimal("0"))),
            gross=-(locked.gross + sum((c.gross for c in credits), Decimal("0"))),
            service_date=locked.service_date,
            service_date_end=locked.service_date_end,
            note=f"Storno zu {locked.number_display}"[:200],
        )
        return storno


class CreditError(ValueError):
    """Корректуру выпустить нельзя (не тот документ/сумма) — причина в тексте."""


def create_credit(original, gross, *, reason: str, key: str):
    """KA-12 B2-7b: Rechnungskorrektur — частичное уменьшение выставленного счёта.

    Свой номер из общего счётчика, строки по ставкам оригинала пропорционально
    (`_invoice_gross_by_rate`), суммы со знаком минус, брутто ровно = −`gross`
    (`fit_gross`). Оригинал не меняется (GoBD). Идемпотентно по `key`.
    Полная сумма остатка — это Stornorechnung, не корректура (`CreditError`).
    Журнал выручки не трогает: сторно пишет тот, кто снизил цену (Minderung)."""
    from decimal import ROUND_HALF_UP, Decimal

    from django.db import transaction
    from django.db.models import Sum
    from django.utils import timezone as tz

    from .models import Invoice

    cent = Decimal("0.01")
    gross = Decimal(str(gross)).quantize(cent, rounding=ROUND_HALF_UP)
    key = str(key)[:64]
    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(pk=original.pk)
        # Поиск по ключу ПОСЛЕ блокировки: два одинаковых запроса не проскочат
        # оба мимо и не упрутся в уникальный индекс (500 вместо документа).
        existing = Invoice.objects.filter(correction_key=key).first() if key else None
        if existing is not None:
            if existing.corrects_id != locked.pk:
                raise CreditError("correction key belongs to another invoice")
            return existing
        if locked.kind != Invoice.KIND_INVOICE or not locked.number:
            raise CreditError("only an issued invoice can be corrected")
        if locked.status not in (Invoice.STATUS_ISSUED, Invoice.STATUS_PAID):
            raise CreditError("invoice is not issued")
        credited = -(
            locked.corrections.exclude(status=Invoice.STATUS_DRAFT).aggregate(s=Sum("gross"))["s"]
            or Decimal("0")
        )
        remaining = Decimal(locked.gross) - credited
        if gross <= 0 or gross >= remaining:
            raise CreditError("credit must be positive and below the remaining amount")
        rows = _invoice_gross_by_rate(locked)
        total = sum(g for _r, g in rows)
        label = (reason or "Preisminderung")[:200]
        lines, left = [], gross
        for i, (rate, row_gross) in enumerate(rows):
            share = (
                left
                if i == len(rows) - 1
                else (gross * row_gross / total).quantize(cent, rounding=ROUND_HALF_UP)
            )
            left -= share
            if share <= 0:
                continue
            lines.append(
                {
                    "text": label,
                    "qty": 1,
                    "unit_price": str(_net_from_gross(share, rate)[0]),
                    "vat_rate": str(rate),
                }
            )
        if not lines:
            raise CreditError("nothing to correct")
        # Цент округления групп — в цену крупнейшей строки; потом знак минус.
        fit_gross(lines, gross, locked.vat_rate)
        for line in lines:
            line["qty"] = -1
        net, vat, total_gross = compute_totals(lines, locked.vat_rate)
        return Invoice.objects.create(
            kind=Invoice.KIND_CREDIT,
            corrects=locked,
            correction_key=key,
            status=Invoice.STATUS_ISSUED,
            number=_next_number(),
            issued_at=tz.now(),
            language=locked.language,
            customer=locked.customer,
            recipient=locked.recipient,
            lines=lines,
            vat_rate=locked.vat_rate,
            net=net,
            vat_amount=vat,
            gross=total_gross,
            deal_kind=locked.deal_kind,
            deal_id=locked.deal_id,
            service_date=locked.service_date,
            service_date_end=locked.service_date_end,
            note=f"Korrektur zu {locked.number_display}"[:200],
        )


def manual_credit(invoice, gross, *, reason: str, key: str, tenant=None):
    """KA-12 B2-7c: «Gutschrift erstellen» со страницы счёта. Деньги не двигает.
    Заказ/запись/номер — снижение цены сделки (`refunds.reduce_price`: скидка, сторно
    выручки, корректура одной транзакцией). Заявка — корректура + сторно журнала по
    ставкам. Счёт без сделки — только документ. Прочие виды — CreditError (выручка
    там проводится иначе, документ разошёлся бы с журналом)."""
    from django.db import transaction

    from apps.core import money_contract, refunds, transactions

    from .models import Invoice

    if invoice.kind != Invoice.KIND_INVOICE or invoice.status not in (
        Invoice.STATUS_ISSUED,
        Invoice.STATUS_PAID,
    ):
        raise CreditError("invoice is not issued")
    gross = Decimal(str(gross)).quantize(Decimal("0.01"))
    kind = invoice.deal_kind
    if kind in refunds.MINDERUNG_KINDS:
        deal = transactions.model_for(kind).objects.filter(reference_code=invoice.deal_id).first()
        current = money_contract.invoice_for(kind, deal) if deal is not None else None
        if current is None or current.pk != invoice.pk:
            raise CreditError("deal of the invoice not found")
        try:
            credit = refunds.reduce_price(
                kind, deal, int(gross * 100), tenant, key, reason=reason or "Preisminderung"
            )
        except refunds.PriceReductionBlocked as exc:
            raise CreditError("price reduction not possible") from exc
        if credit is None:
            raise CreditError("no credit issued")
        return credit
    if kind and kind != "job":
        raise CreditError("unsupported deal kind")
    with transaction.atomic():
        credit = create_credit(invoice, gross, reason=reason, key=f"man:{key}")
        reverse_job_credit(invoice, credit)
    return credit


def issue_invoice(invoice, *, tenant=None, terms_days=None):
    """draft → issued: последовательный номер под блокировкой счётчика.

    Номер выдаётся только здесь — черновики не нумеруются, поэтому удаление
    черновика дыру в нумерации не оставляет (GoBD-последовательность).

    SH-23b (решение владельца Р-2): при выпуске фиксируется срок оплаты —
    Zahlungsziel бизнеса (по умолчанию 14 дней) снимком, чтобы позднее изменение
    настройки не переписало уже выставленный документ.
    """
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone as tz

    from .state_machine import InvoiceSM

    with transaction.atomic():
        # KA-12 B2-8c: предоплата сделки — вычет (оплачена) или сторно (не оплачена).
        from .advance import deducted_cents, settle_for_final

        settle_for_final(invoice)
        invoice.number = _next_number()
        invoice.issued_at = tz.now()
        fields = ["number", "issued_at", "updated_at"]
        # KA-H10: Leistungsdatum обязателен — без даты сделки берём день выставления.
        if invoice.service_date is None:
            invoice.service_date = tz.localdate()
            fields.append("service_date")
        if _refresh_prepaid(invoice):  # оплата могла прийти между черновиком и выпуском
            fields.append("prepaid_cents")
        # B2-8c: вычтенная предоплата — уже полученные деньги, даже если депозит брони
        # пересчитали после её выставления (иначе «к оплате» включало бы её снова).
        deducted = deducted_cents(invoice)
        if deducted:
            deducted += _other_prepaid_cents(invoice)  # сертификат/ваучер — тоже получены
        if deducted > invoice.prepaid_cents:
            invoice.prepaid_cents = deducted
            if "prepaid_cents" not in fields:
                fields.append("prepaid_cents")
        if invoice.due_date is None:
            days = terms_days
            if days is None:
                days = int(getattr(tenant, "invoice_terms_days", 0) or 14)
            invoice.payment_terms_days = days
            invoice.due_date = (invoice.issued_at + timedelta(days=days)).date()
            fields += ["due_date", "payment_terms_days"]
        invoice.save(update_fields=fields)
        return InvoiceSM().apply(invoice, "issued")


def invoice_from_stay(booking, tenant=None):
    """DC-6 (ТЗ владельца 2026-08-25): черновик счёта ИЗ БРОНИ НОМЕРА.

    Позиции — снимок: ночи (проживание за вычетом авто-скидки), доп-услуги,
    Kurtaxe отдельной строкой БЕЗ НДС (курортный сбор не облагается) и скидка
    владельца. Ставка счёта одна (модель Invoice знает одну) — для размещения
    в DE это 7 %; §19 Kleinunternehmer обнуляет. Черновик: номер и
    неизменяемость наступают при `issue_invoice`.
    """
    from decimal import Decimal

    from django.utils.translation import gettext as _

    from apps.core import extras as extras_engine

    from .models import Invoice

    small = bool(tenant and getattr(tenant, "small_business", False))
    # DC-8: ставка — СНИМОК брони (проживание в DE 7 %, но владелец может иметь
    # свою; §19 обнуляет). Смешанные ставки допов показывает карточка сделки —
    # модель Invoice знает одну ставку, поэтому берём ставку проживания.
    rate = Decimal("0") if small else Decimal(str(booking.vat_rate or "7.00"))
    nights = max(1, (booking.departure - booking.arrival).days)
    lodging = max(
        0,
        (booking.total_cents or 0)
        - (booking.kurtaxe_cents or 0)
        - extras_engine.total_cents(booking.extras)
        + (booking.discount_cents or 0),
    )
    # Одна строка на всё проживание: цена за ночь округлялась бы дважды и итог
    # счёта расходился с суммой брони на копейку (поймано замком).
    # KA-H6: питание тарифа — своей строкой по 19 % (Aufteilungsgebot), проживание
    # уменьшается на ту же сумму — итог счёта = итог брони.
    from apps.stays.meal import MEAL_VAT_RATE, meal_cents

    meal = meal_cents(booking)
    lodging -= meal
    stay_net, _vat = _net_from_gross(Decimal(lodging) / 100, rate)
    unit_name = getattr(booking.unit, "name", "") or str(_("Übernachtung"))
    nights_label = str(_("%(n)s Nächte")) % {"n": nights}
    lines = [
        {
            "text": f"{unit_name} · {nights_label}"[:200],
            "qty": 1,
            "unit_price": str(stay_net),
            "vat_rate": str(rate),
        }
    ]
    if meal:
        meal_rate = Decimal("0") if small else MEAL_VAT_RATE
        meal_net, _v = _net_from_gross(Decimal(meal) / 100, meal_rate)
        snap = booking.rate_snapshot or {}
        lines.append(
            {
                "text": str(_("Verpflegung"))
                + (f" · {snap.get('meal_label')}" if snap.get("meal_label") else ""),
                "qty": 1,
                "unit_price": str(meal_net),
                "vat_rate": str(meal_rate),
            }
        )
    for extra in booking.extras or []:
        if not isinstance(extra, dict):
            continue
        # VAT-4: у допа своя ставка (завтрак 19 % рядом с проживанием 7 % —
        # Aufteilungsgebot). Снимок без ставки идёт по ставке брони, как раньше.
        own = extra.get("vat_rate")
        extra_rate = rate if small or own in (None, "") else Decimal(str(own))
        net, _v = _net_from_gross(Decimal(int(extra.get("price_cents", 0))) / 100, extra_rate)
        lines.append(
            {
                "text": str(extra.get("label", ""))[:200],
                "qty": 1,
                "unit_price": str(net),
                "vat_rate": str(extra_rate),
            }
        )
    cert = certificate_cents(booking)  # E1.8: сертификат — оплата, не Rabatt
    rabatt = (booking.discount_cents or 0) - cert
    if rabatt:
        net, _v = _net_from_gross(Decimal(rabatt) / 100, rate)
        lines.append(
            {
                "text": str(_("Rabatt")),
                "qty": 1,
                "unit_price": str(-net),
                "vat_rate": str(rate),
            }
        )
    if booking.kurtaxe_cents:
        # Курортный сбор НЕ облагается НДС: без явной ставки 0 общий расчёт
        # начислил бы на него ставку проживания, и счёт стал бы больше брони.
        lines.append(
            {
                "text": str(_("Kurtaxe")),
                "qty": 1,
                "unit_price": str(Decimal(booking.kurtaxe_cents) / 100),
                "vat_rate": "0",
            }
        )
    fit_gross(lines, Decimal((booking.total_cents or 0) + cert) / 100, rate, small_business=small)
    net, vat, gross = compute_totals(lines, rate, small_business=small)
    return Invoice.objects.create(
        customer=booking.customer,
        recipient=recipient_for(booking),
        lines=lines,
        vat_rate=rate,
        net=net,
        vat_amount=vat,
        gross=gross,
        note=_with_note(
            str(_("Buchung %(code)s")) % {"code": booking.reference_code},
            _certificate_note(booking, cert),
        ),
        service_date=booking.arrival,  # KA-H10: Leistungszeitraum — проживание
        service_date_end=booking.departure,
        prepaid_cents=_prepaid_from_payment_state(booking),
    )


def invoice_from_booking(booking, tenant=None):
    """DC-6: черновик счёта ИЗ ЗАПИСИ НА УСЛУГУ (услуга + допы − скидка)."""
    from decimal import Decimal

    from django.utils.translation import gettext as _

    from .models import Invoice

    small = bool(tenant and getattr(tenant, "small_business", False))
    # DC-8: ставка — снимок записи (услуга могла иметь свою ставку).
    rate = Decimal("0") if small else Decimal(str(booking.vat_rate or "19.00"))
    title = getattr(booking, "service_label", "") or str(_("Leistung"))
    net, _vat = _net_from_gross(Decimal(booking.price_cents or 0) / 100, rate)
    lines = [{"text": str(title)[:200], "qty": 1, "unit_price": str(net)}]
    for extra in booking.extras or []:
        if not isinstance(extra, dict):
            continue
        # KA-MC X5: у допа своя ставка (как в счёте из брони номера, VAT-4).
        own = extra.get("vat_rate")
        e_rate = rate if small or own in (None, "") else Decimal(str(own))
        e_net, _v = _net_from_gross(Decimal(int(extra.get("price_cents", 0))) / 100, e_rate)
        lines.append(
            {
                "text": str(extra.get("label", ""))[:200],
                "qty": 1,
                "unit_price": str(e_net),
                "vat_rate": str(e_rate),
            }
        )
    cert = certificate_cents(booking)  # E1.8: сертификат — оплата, не Rabatt
    rabatt = (booking.discount_cents or 0) - cert
    if rabatt:
        d_net, _v = _net_from_gross(Decimal(rabatt) / 100, rate)
        lines.append({"text": str(_("Rabatt")), "qty": 1, "unit_price": str(-d_net)})
    fit_gross(lines, Decimal((booking.total_cents or 0) + cert) / 100, rate, small_business=small)
    total_net, vat, gross = compute_totals(lines, rate, small_business=small)
    return Invoice.objects.create(
        customer=booking.customer,
        recipient=recipient_for(booking),
        lines=lines,
        vat_rate=rate,
        net=total_net,
        vat_amount=vat,
        gross=gross,
        note=_with_note(
            str(_("Termin %(code)s")) % {"code": booking.reference_code},
            _certificate_note(booking, cert),
        ),
        service_date=_local_date(booking.start),  # KA-H10: Leistungsdatum
        prepaid_cents=_prepaid_from_payment_state(booking),
    )


def _with_note(head: str, extra: str) -> str:
    """Заметка счёта + пометка об оплате (поле 200 знаков; пометку не обрезаем)."""
    if not extra:
        return head[:200]
    room = 200 - len(extra) - 3
    return f"{head[: max(room, 0)]} · {extra}"[:200]


def _local_date(value):
    """datetime → локальная дата; date → как есть; None → None."""
    if value is None:
        return None
    from datetime import datetime

    from django.utils import timezone as tz

    if isinstance(value, datetime):
        return tz.localtime(value).date() if tz.is_aware(value) else value.date()
    return value


def certificate_cents(deal) -> int:
    """KA-12 E1.8 (MC-Z9): часть скидки брони/записи/заказа, оплаченная сертификатом
    с остатком (Wertgutschein, Mehrzweckgutschein — средство платежа, не Rabatt).

    Признак — код сделки совпадает с сертификатом с балансом (то же правило, что
    у легаси-заявок в `jobs.services.voucher_payment_cents`). Скидка владельца
    (DC-5) пишет в `voucher_code` свою заметку, поэтому после ручной правки скидки
    код не совпадёт — и она честно остаётся Rabatt. Точное поле
    `voucher_paid_cents` для этих видов — батч 2 (миграция)."""
    disc = int(getattr(deal, "discount_cents", 0) or 0)
    if disc <= 0:
        return 0
    paid = int(getattr(deal, "voucher_paid_cents", 0) or 0)
    if paid:  # KA-12 B2-1: точное поле (новые сделки); легаси — признак по коду ниже
        return min(paid, disc)
    code = (getattr(deal, "voucher_code", "") or "").strip()
    if not code:
        return 0
    try:
        from apps.loyalty.models import Voucher
    except ImportError:  # pragma: no cover
        return 0
    if Voucher.objects.filter(code__iexact=code, balance_cents__isnull=False).exists():
        return disc
    return 0


def _certificate_note(deal, cents: int) -> str:
    """Пометка «Gutschein CODE: −X» (та же строка, что у счёта из заявки)."""
    if not cents:
        return ""
    from decimal import Decimal

    from django.utils.translation import gettext as _

    from apps.core.documents import money

    return str(_("Gutschein %(code)s: −%(amount)s")) % {
        "code": (deal.voucher_code or "")[:20],
        "amount": money(Decimal(cents) / 100),
    }


def _prepaid_from_payment_state(deal) -> int:
    """KA-H10: уже получено по брони/записи/заказу: Anzahlung → её сумма, оплачено → всё.

    KA-12 E1.8: сертификат с остатком — тоже уже полученные деньги (счёт идёт на
    полную цену, сертификат вычитается как оплата)."""
    cert = certificate_cents(deal)
    state = getattr(deal, "payment_state", "")
    if state == "deposit":
        return int(getattr(deal, "deposit_cents", 0) or 0) + cert
    if state == "paid":
        cents = getattr(deal, "total_cents", None)
        if cents is None:  # заказ: итог в евро (Decimal)
            from decimal import Decimal

            cents = int(round(Decimal(str(getattr(deal, "total", 0) or 0)) * 100))
        return int(cents or 0) + cert
    return cert


def _other_prepaid_cents(invoice) -> int:
    """B2-8c: полученное помимо депозита (сертификат брони / ваучер заявки) — чтобы
    кламп «prepaid ≥ вычет» не потерял его, если депозит пересчитали."""
    kind, ref = invoice.deal_kind, invoice.deal_id
    try:
        if kind == "job":
            from apps.jobs.models import Job
            from apps.jobs.services import voucher_payment_cents

            job = Job.objects.filter(reference_code=ref).first()
            return voucher_payment_cents(job) if job is not None else 0
        if kind in ("stay", "booking"):
            from apps.core import transactions

            deal = transactions.model_for(kind).objects.filter(reference_code=ref).first()
            return certificate_cents(deal) if deal is not None else 0
    except Exception:  # noqa: BLE001 — пол «к оплате»: без него выпуск всё равно корректен
        logger.exception("invoice %s: other prepaid lookup failed", invoice.pk)
    return 0


def _refresh_prepaid(invoice) -> bool:
    """KA-H10: «уже получено» на момент ВЫПУСКА (оплата могла прийти после черновика)."""
    kind, ref = invoice.deal_kind, invoice.deal_id
    if not kind or not ref or invoice.kind == invoice.KIND_ADVANCE:
        return False  # B2-8b: предоплата — ровно депозит, «уже получено» не её
    if kind == "job":
        from apps.jobs.models import Job
        from apps.jobs.services import prepaid_cents as job_prepaid

        job = Job.objects.filter(reference_code=ref).first()
        if job is None:
            return False
        invoice.prepaid_cents = job_prepaid(job)
        return True
    if kind in ("stay", "booking", "order"):
        from apps.core import transactions

        deal = transactions.model_for(kind).objects.filter(reference_code=ref).first()
        if deal is None:
            return False
        invoice.prepaid_cents = _prepaid_from_payment_state(deal)
        return True
    return False


def _net_from_gross(gross, rate):
    """Нетто из брутто по ставке (цены сделок брутто — PAngV)."""
    from apps.orders.totals import split_gross

    return split_gross(gross, rate)


def invoice_from_order(order, tenant=None):
    """SH-9: черновик счёта ИЗ ЗАКАЗА (фидбэк владельца 2026-08-20 «выставление счёта»).

    Раньше счёт набирался руками, хотя все данные уже есть в заказе. Позиции —
    снимок (`lines`), как у ручного счёта; получатель — плательщик заказа, если
    он задан (§14 UStG требует реквизиты получателя СЧЁТА), иначе клиент.
    Возвращает черновик: нумерация и неизменяемость наступают при `issue_invoice`.

    Цены заказа брутто, а счёт считает от нетто — поэтому нетто позиций получаем
    из `orders.totals` (единый хелпер), а не делим повторно здесь.
    """
    from decimal import Decimal

    from django.utils.translation import gettext as _

    from apps.orders.totals import order_totals, split_gross

    from .models import Invoice

    small = bool(tenant and getattr(tenant, "small_business", False))
    totals = order_totals(order, small_business=small)
    lines = []
    for item in order.items.all():
        rate = Decimal("0") if small else Decimal(str(item.vat_rate or 0))
        net_unit, _vat = split_gross(item.unit_price, rate)
        # SH-22 (решение владельца Р-7): скидка акции — СТРУКТУРНО, позиция по
        # листовой цене + минус-строка сразу за ней той же ставкой. Минус-строку
        # считаем как РАЗНИЦУ уже посчитанных нетто (net_list − net_unit), а не
        # отдельным делением: иначе округление двух независимых делений уводило
        # бы счёт на цент от заказа (инвариант `Invoice.gross == Order.total`).
        net_list = net_unit
        if item.discount_per_unit:
            net_list, _v = split_gross(item.list_price, rate)
        lines.append(
            {
                "text": item.title_snapshot[:200],
                "sku": item.sku,  # SH-20: Art.-Nr. едет в счёт (JSON; compute_totals ключ игнорирует)
                "qty": item.qty,
                "unit_price": str(net_list),
                # VAT-4: ставка в снимке строки — иначе смешанный счёт считался бы
                # по одной преобладающей и не сошёлся бы с итогом заказа.
                "vat_rate": str(rate),
            }
        )
        if item.discount_per_unit:
            name = item.promo_name
            text = (
                str(_("Rabatt · Aktion „%(name)s“")) % {"name": name} if name else str(_("Rabatt"))
            )
            lines.append(
                {
                    "text": text[:200],
                    "qty": item.qty,
                    "unit_price": str(-(net_list - net_unit)),
                    "vat_rate": str(rate),
                }
            )
    if order.is_delivery and order.shipping_cents:
        rate = totals["rows"][0]["rate"] if totals["rows"] else Decimal("0")
        net_ship, _vat = split_gross(Decimal(order.shipping_cents) / 100, rate)
        lines.append(
            {
                "text": str(_("Lieferung")),
                "qty": 1,
                "unit_price": str(net_ship),
                "vat_rate": str(rate),
            }
        )
    cert = certificate_cents(order)  # E1.8: сертификат — оплата, не Rabatt
    rabatt = (order.discount_cents or 0) - cert
    if rabatt:
        rate = totals["rows"][0]["rate"] if totals["rows"] else Decimal("0")
        net_disc, _vat = split_gross(Decimal(rabatt) / 100, rate)
        lines.append(
            {
                "text": str(_("Rabatt")),
                "qty": 1,
                "unit_price": str(-net_disc),
                "vat_rate": str(rate),
            }
        )
    # `Invoice.vat_rate` остаётся полем документа (легаси-счета и §19), но налог
    # считается ПО СТАВКАМ СТРОК: у смешанного заказа одна усреднённая ставка
    # давала счёт, не совпадающий с суммой, которую клиент реально заплатил.
    rate = totals["rows"][0]["rate"] if totals["rows"] else Decimal("19.00")
    # KA-MC X5: счёт = заказ; E1.8: + сертификат (он оплата, а не уменьшение цены).
    fit_gross(lines, Decimal(str(order.total)) + Decimal(cert) / 100, rate, small_business=small)
    net, vat, gross = compute_totals(lines, rate, small_business=small)
    return Invoice.objects.create(
        customer=order.customer,
        recipient=recipient_for(order),
        lines=lines,
        vat_rate=rate,
        net=net,
        vat_amount=vat,
        gross=gross,
        note=_with_note(
            str(_("Auftrag %(code)s")) % {"code": order.reference_code},
            _certificate_note(order, cert),
        ),
        # KA-H10: Leistungsdatum — отгрузка, иначе слот выдачи; иначе при выпуске.
        service_date=_local_date(
            getattr(order, "shipped_at", None) or getattr(order, "pickup_slot", None)
        ),
        prepaid_cents=_prepaid_from_payment_state(order),  # оплаченный заказ — не «offen»
    )


def issue_invoice_for_deal(kind, obj, tenant, *, send_email=True):
    """SH-23b (решение владельца Р-1): счёт юрлицу выпускается АВТОМАТИЧЕСКИ на
    чекауте — с письмом и PDF.

    Идемпотентно: у сделки со счётом второй не создаётся (повторный POST/ретрай
    задачи). Модуль «Finanzen» не гейтит — счёт нужен покупателю независимо от
    того, ведёт ли владелец финансы в кабинете; тот же документ потом виден в
    «Offene Posten» и в Mahnwesen.

    Возвращает `Invoice` (уже issued) либо None, если счёт построить нечем.
    """
    from django.db import connection

    from apps.notifications.services import notify

    from .models import Invoice

    ref = str(getattr(obj, "reference_code", "") or getattr(obj, "pk", ""))
    # Ревью W1.2 (H2): отменённый счёт (и его сторно) — уже не счёт сделки; после
    # отмены повторное подтверждение выпускает новый документ.
    # KA-12 B2-7b: Stornorechnung и корректура — не счёт сделки.
    live = Invoice.objects.exclude(status=Invoice.STATUS_CANCELLED).filter(
        kind=Invoice.KIND_INVOICE
    )
    existing = live.filter(deal_kind=kind, deal_id=ref).first()
    if existing is not None:
        return existing
    # CO-2 (ревью): черновик, созданный кнопкой на карточке (`obj.invoice_id`), —
    # тот же документ; второй счёт на сделку не выпускаем.
    draft = None
    if getattr(obj, "invoice_id", None):
        draft = Invoice.objects.filter(pk=obj.invoice_id).first()
        if draft is not None and draft.status == Invoice.STATUS_CANCELLED:
            draft = None
        elif draft is not None and draft.status != Invoice.STATUS_DRAFT:
            return draft
    builder = {
        "order": invoice_from_order,
        "stay": invoice_from_stay,
        "booking": invoice_from_booking,
    }.get(kind)
    if builder is None:
        return None
    if draft is not None:
        # Черновик кнопки мог устареть (допы, скидка, получатель) — выпускаем свежий:
        # черновик ещё не документ GoBD, выпущенный уже не исправить (ревью CO-2).
        if hasattr(obj, "invoice_id"):
            obj.invoice_id = None
        draft.delete()
    invoice = builder(obj, tenant)
    if invoice is None:
        return None
    invoice.deal_kind = kind
    invoice.deal_id = ref[:64]
    invoice.save(update_fields=["deal_kind", "deal_id", "updated_at"])
    if hasattr(obj, "invoice_id") and obj.invoice_id != invoice.pk:
        obj.invoice_id = invoice.pk
        obj.save(update_fields=["invoice_id", "updated_at"])
    issue_invoice(invoice, tenant=tenant)
    invoice.refresh_from_db()
    if send_email:
        email = getattr(getattr(obj, "customer", None), "email", "") or ""
        if email and not _invoice_mail_allowed(email):
            logger.warning("finance: invoice %s mail throttled", invoice.pk)
        elif email:
            _send_invoice_email(
                invoice, tenant, email, schema=connection.schema_name, notify=notify
            )
    return invoice


def _invoice_mail_allowed(email: str) -> bool:
    """Ревью безопасности CO-2: адрес вводит посетитель витрины — письма со счётом на
    один адрес не чаще 3 в час (иначе ротацией IP можно слать «официальные» счета
    бизнеса на чужой ящик). Сам счёт выпускается в любом случае."""
    import hashlib

    from django.core.cache import cache

    key = "invoice-mail:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()
    cache.add(key, 0, 3600)
    try:
        return cache.incr(key) <= 3
    except ValueError:
        return True


def _send_invoice_email(
    invoice,
    tenant,
    email,
    *,
    schema,
    notify,
    template="invoice_issued",
    dedupe_prefix="invoice-issued",
):
    """Письмо клиенту со счётом (PDF вложением). Сбой PDF не отменяет письмо —
    в нём остаются номер, сумма и срок оплаты."""
    from django.template.loader import render_to_string
    from django.utils import timezone as tz
    from django.utils import translation
    from django.utils.translation import gettext as _

    from apps.notifications.services import email_locale

    ctx = {
        "number": invoice.number_display,
        "gross": f"{invoice.gross:.2f}".replace(".", ","),
        "due": invoice.due_date,
        "business_name": getattr(tenant, "name", "") or "",
        "reference": invoice.deal_id,
        "paid": invoice.status == "paid",
    }
    with translation.override(email_locale()):
        subject = render_to_string(f"emails/{template}_subject.txt", ctx).strip()
        body = render_to_string(f"emails/{template}.txt", ctx)
    attachments = []
    try:
        from .pdf import build_invoice_pdf

        # Имя файла — на языке письма (msgid тот же, что в шапке PDF).
        doc_name = _("Anzahlungsrechnung") if invoice.kind == "advance" else _("Invoice")
        attachments = [
            (
                f"{doc_name}-{invoice.number_display}.pdf",
                build_invoice_pdf(invoice, tenant),
                "application/pdf",
            )
        ]
    except Exception:  # noqa: BLE001 — письмо важнее вложения
        logger.warning("finance: invoice %s pdf for mail failed", invoice.pk, exc_info=True)
        attachments = []
    sent = notify(
        dedupe_key=f"{schema}:{dedupe_prefix}:{invoice.pk}",
        type=template,
        recipient=email,
        subject=subject,
        body=body,
        attachments=attachments,
    )
    if sent is not None:
        invoice.sent_at = tz.now()
        invoice.save(update_fields=["sent_at", "updated_at"])
