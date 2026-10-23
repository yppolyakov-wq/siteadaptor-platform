"""Запись выручки (Track D / D4a) — идемпотентно для хуков FSM.

Вызывается из OrderSM (picked_up) и ReservationSM (fulfilled): один документ →
одна запись, повторный вызов с тем же (source, source_ref) — no-op (unique
constraint в БД). Ручные записи (source=manual) идут без source_ref.
"""

import logging

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


def reverse_invoice_revenue(invoice) -> None:
    """Сторно счёта из заявки → сторно-записи на каждую проведённую строку."""
    if invoice.deal_kind != "job":
        return
    entries = RevenueEntry.objects.filter(
        source=RevenueEntry.SOURCE_JOB,
        source_ref__startswith=f"inv:{invoice.pk}:",
        amount__gt=0,
    )
    for entry in list(entries):
        if entry.source_ref.endswith(":reversal"):
            continue
        record_reversal(
            source=RevenueEntry.SOURCE_JOB,
            source_ref=f"{entry.source_ref}:reversal",
            amount=entry.amount,
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

    for _attempt in range(6):
        _net, _vat, gross = compute_totals(lines, vat_rate, small_business=small_business)
        diff = target - gross
        if not diff:
            return lines
        candidates = [
            ln
            for ln in lines
            if _to_decimal(ln["unit_price"], "0") > 0
            and (small_business or str(ln.get("vat_rate", "")) not in ("0", "0.00"))
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
        line["unit_price"] = str(_to_decimal(line["unit_price"], "0") + step)
    logger.warning("finance: invoice rounding residual vs deal total %s", target)
    return lines


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

    from .models import InvoiceCounter
    from .state_machine import InvoiceSM

    with transaction.atomic():
        counter, _created = InvoiceCounter.objects.select_for_update().get_or_create(pk=1)
        counter.last_number += 1
        counter.save(update_fields=["last_number"])
        invoice.number = counter.last_number
        invoice.issued_at = tz.now()
        fields = ["number", "issued_at", "updated_at"]
        # KA-H10: Leistungsdatum обязателен — без даты сделки берём день выставления.
        if invoice.service_date is None:
            invoice.service_date = tz.localdate()
            fields.append("service_date")
        if _refresh_prepaid(invoice):  # оплата могла прийти между черновиком и выпуском
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
    if booking.discount_cents:
        net, _v = _net_from_gross(Decimal(booking.discount_cents) / 100, rate)
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
    fit_gross(lines, Decimal(booking.total_cents or 0) / 100, rate, small_business=small)
    net, vat, gross = compute_totals(lines, rate, small_business=small)
    return Invoice.objects.create(
        customer=booking.customer,
        recipient=recipient_for(booking),
        lines=lines,
        vat_rate=rate,
        net=net,
        vat_amount=vat,
        gross=gross,
        note=str(_("Buchung %(code)s")) % {"code": booking.reference_code},
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
    title = getattr(booking.service, "name", "") or str(_("Leistung"))
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
    if booking.discount_cents:
        d_net, _v = _net_from_gross(Decimal(booking.discount_cents) / 100, rate)
        lines.append({"text": str(_("Rabatt")), "qty": 1, "unit_price": str(-d_net)})
    fit_gross(lines, Decimal(booking.total_cents or 0) / 100, rate, small_business=small)
    total_net, vat, gross = compute_totals(lines, rate, small_business=small)
    return Invoice.objects.create(
        customer=booking.customer,
        recipient=recipient_for(booking),
        lines=lines,
        vat_rate=rate,
        net=total_net,
        vat_amount=vat,
        gross=gross,
        note=str(_("Termin %(code)s")) % {"code": booking.reference_code},
        service_date=_local_date(booking.start),  # KA-H10: Leistungsdatum
        prepaid_cents=_prepaid_from_payment_state(booking),
    )


def _local_date(value):
    """datetime → локальная дата; date → как есть; None → None."""
    if value is None:
        return None
    from datetime import datetime

    from django.utils import timezone as tz

    if isinstance(value, datetime):
        return tz.localtime(value).date() if tz.is_aware(value) else value.date()
    return value


def _prepaid_from_payment_state(deal) -> int:
    """KA-H10: уже получено по брони/записи/заказу: Anzahlung → её сумма, оплачено → всё."""
    state = getattr(deal, "payment_state", "")
    if state == "deposit":
        return int(getattr(deal, "deposit_cents", 0) or 0)
    if state == "paid":
        cents = getattr(deal, "total_cents", None)
        if cents is None:  # заказ: итог в евро (Decimal)
            from decimal import Decimal

            cents = int(round(Decimal(str(getattr(deal, "total", 0) or 0)) * 100))
        return int(cents or 0)
    return 0


def _refresh_prepaid(invoice) -> bool:
    """KA-H10: «уже получено» на момент ВЫПУСКА (оплата могла прийти после черновика)."""
    kind, ref = invoice.deal_kind, invoice.deal_id
    if not kind or not ref:
        return False
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
    if order.discount_cents:
        rate = totals["rows"][0]["rate"] if totals["rows"] else Decimal("0")
        net_disc, _vat = split_gross(Decimal(order.discount_cents) / 100, rate)
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
    fit_gross(lines, order.total, rate, small_business=small)  # KA-MC X5: счёт = заказ
    net, vat, gross = compute_totals(lines, rate, small_business=small)
    return Invoice.objects.create(
        customer=order.customer,
        recipient=recipient_for(order),
        lines=lines,
        vat_rate=rate,
        net=net,
        vat_amount=vat,
        gross=gross,
        note=str(_("Auftrag %(code)s")) % {"code": order.reference_code},
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
    existing = Invoice.objects.filter(deal_kind=kind, deal_id=ref).first()
    if existing is not None:
        return existing
    # CO-2 (ревью): черновик, созданный кнопкой на карточке (`obj.invoice_id`), —
    # тот же документ; второй счёт на сделку не выпускаем.
    draft = None
    if getattr(obj, "invoice_id", None):
        draft = Invoice.objects.filter(pk=obj.invoice_id).first()
        if draft is not None and draft.status != Invoice.STATUS_DRAFT:
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


def _send_invoice_email(invoice, tenant, email, *, schema, notify):
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
    }
    with translation.override(email_locale()):
        subject = render_to_string("emails/invoice_issued_subject.txt", ctx).strip()
        body = render_to_string("emails/invoice_issued.txt", ctx)
    attachments = []
    try:
        from .pdf import build_invoice_pdf

        # Имя файла — на языке письма (msgid тот же, что в шапке PDF).
        doc_name = _("Invoice")
        attachments = [
            (
                f"{doc_name}-{invoice.number_display}.pdf",
                build_invoice_pdf(invoice, tenant),
                "application/pdf",
            )
        ]
    except Exception:  # noqa: BLE001 — письмо важнее вложения
        attachments = []
    sent = notify(
        dedupe_key=f"{schema}:invoice-issued:{invoice.pk}",
        type="invoice_issued",
        recipient=email,
        subject=subject,
        body=body,
        attachments=attachments,
    )
    if sent is not None:
        invoice.sent_at = tz.now()
        invoice.save(update_fields=["sent_at", "updated_at"])
