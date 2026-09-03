"""Запись выручки (Track D / D4a) — идемпотентно для хуков FSM.

Вызывается из OrderSM (picked_up) и ReservationSM (fulfilled): один документ →
одна запись, повторный вызов с тем же (source, source_ref) — no-op (unique
constraint в БД). Ручные записи (source=manual) идут без source_ref.
"""

from django.utils import timezone

from .models import RevenueEntry


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


def record_reversal(*, source, source_ref, amount, currency="EUR", customer=None, note=""):
    """Сторно-запись возврата: отрицательная сумма, идемпотентно по source_ref.

    Для возвратов (A2c): на ту же сумму, что была проведена при выдаче/отправке,
    но со знаком минус — чистая выручка по документу становится нулевой.
    """
    if amount is None or amount <= 0:
        return None
    entry, created = RevenueEntry.objects.get_or_create(
        source=source,
        source_ref=source_ref,
        defaults={
            "amount": -amount,
            "currency": currency,
            "date": timezone.localdate(),
            "customer": customer,
            "note": note[:200],
        },
    )
    return entry if created else None


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
    net, vat, gross = compute_totals(lines, rate, small_business=small)
    return Invoice.objects.create(
        customer=booking.customer,
        recipient=str(booking.customer)[:1000],
        lines=lines,
        vat_rate=rate,
        net=net,
        vat_amount=vat,
        gross=gross,
        note=str(_("Buchung %(code)s")) % {"code": booking.reference_code},
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
        e_net, _v = _net_from_gross(Decimal(int(extra.get("price_cents", 0))) / 100, rate)
        lines.append(
            {"text": str(extra.get("label", ""))[:200], "qty": 1, "unit_price": str(e_net)}
        )
    if booking.discount_cents:
        d_net, _v = _net_from_gross(Decimal(booking.discount_cents) / 100, rate)
        lines.append({"text": str(_("Rabatt")), "qty": 1, "unit_price": str(-d_net)})
    total_net, vat, gross = compute_totals(lines, rate, small_business=small)
    return Invoice.objects.create(
        customer=booking.customer,
        recipient=str(booking.customer)[:1000],
        lines=lines,
        vat_rate=rate,
        net=total_net,
        vat_amount=vat,
        gross=gross,
        note=str(_("Termin %(code)s")) % {"code": booking.reference_code},
    )


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
    net, vat, gross = compute_totals(lines, rate, small_business=small)
    recipient = order.billing_name or str(order.customer)
    if order.billing_address:
        recipient = f"{recipient}\n{order.billing_address}"
    return Invoice.objects.create(
        customer=order.customer,
        recipient=recipient[:1000],
        lines=lines,
        vat_rate=rate,
        net=net,
        vat_amount=vat,
        gross=gross,
        note=str(_("Auftrag %(code)s")) % {"code": order.reference_code},
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
    builder = {
        "order": invoice_from_order,
        "stay": invoice_from_stay,
        "booking": invoice_from_booking,
    }.get(kind)
    if builder is None:
        return None
    invoice = builder(obj, tenant)
    if invoice is None:
        return None
    invoice.deal_kind = kind
    invoice.deal_id = ref[:64]
    invoice.save(update_fields=["deal_kind", "deal_id", "updated_at"])
    issue_invoice(invoice, tenant=tenant)
    invoice.refresh_from_db()
    if send_email:
        email = getattr(getattr(obj, "customer", None), "email", "") or ""
        if email:
            _send_invoice_email(
                invoice, tenant, email, schema=connection.schema_name, notify=notify
            )
    return invoice


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
