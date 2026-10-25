"""DC-1: единый скелет карточки сделки (ТЗ владельца 2026-08-25).

Требование владельца: «базовые функции и блоки должны иметь общие настройки —
меняется один, меняются все сразу». Поэтому вид карточки задаёт ОДИН шаблон
`core/deal_card_base.html` + общие партиалы `core/_deal_*.html`, а этот модуль —
их единый контекст: контракт `Transaction` (номер, статус, суммы, переходы),
гейты модулей и календарь сделки.

Секции карточки включаются ПО ДАННЫМ, а не по типу бизнеса: список позиций есть
там, где есть позиции; календарь — там, где у направления есть календарный
движок (бронь номера — Belegungsplan, запись — Tagesplan, заказ — Auftragsbuch
при используемых слотах выдачи). У заявок и билетов движка нет — блок не
рисуется вовсе, вместо пустой рамки.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import replace as _dc_replace
from decimal import Decimal

from django.http import QueryDict
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from apps.core import status_labels, transactions, transition_rules
from apps.core.vat import deal_vat

logger = logging.getLogger(__name__)

# Подписи секций — в одном месте: правка меняет ВСЕ карточки сразу.
SECTION_TITLES = {
    # DF-2: «запрос клиента» — то, что человек прислал своими словами.
    "request": _("Anfrage des Kunden"),
    "items": _("Positionen"),
    "discount": _("Rabatt"),
    "totals": _("Summen"),
    "payment": _("Zahlung & Rechnung"),
    # DF-1c: документы стоят рядом с оплатой — это её продолжение (счёт, смета).
    "documents": _("Dokumente"),
    # DF-3: переписка по сделке — прямо на карточке.
    "thread": _("Nachrichten"),
    "status": _("Status"),
    "customer": _("Kunde"),
    "calendar": _("Kalender"),
}

# Календарный движок направления: (шаблон тела, функция контекста).
_CALENDARS = {
    "stay": ("stays/_belegungsplan_body.html", "apps.stays.views.calendar_context"),
    "booking": ("booking/_tagesplan_body.html", "apps.booking.views.calendar_context"),
    "order": ("orders/_auftragsbuch_body.html", "apps.orders.views.auftragsbuch_context"),
}


def _ai_enabled() -> bool:
    from apps.ai.api import is_enabled

    return is_enabled("inbox_reply_draft")  # кнопка «Antwort vorschlagen» в переписке


def _module_active(tenant, key: str) -> bool:
    try:
        return bool(tenant and tenant.is_module_active(key))
    except Exception:  # noqa: BLE001 — гейты карточки fail-closed
        return False


def _resolve(path: str):
    module, _sep, name = path.rpartition(".")
    return getattr(__import__(module, fromlist=[name]), name)


def _calendar_query(kind: str, obj) -> dict | None:
    """GET-параметры календаря, наведённого на саму сделку."""
    from datetime import timedelta

    if kind == "stay":
        arrival = getattr(obj, "arrival", None)
        # Окно Belegungsplan начинается за пару дней до заезда — бронь видна сразу.
        return {"von": (arrival - timedelta(days=2)).isoformat()} if arrival else {}
    if kind == "booking":
        start = getattr(obj, "start", None)
        return {"tag": start.date().isoformat()} if start else {}
    if kind == "order":
        slot = getattr(obj, "pickup_slot", None)
        return {"tag": slot.date().isoformat()} if slot else {}
    return None


def calendar_html(request, kind: str, obj) -> str:
    """Календарь сделки, развёрнутый (владелец: «открывается сразу ниже сетки»).

    Тот же движок, что на странице продаж, — тела календарей партиализованы
    волной V. Ошибка построения не должна ронять карточку: календарь
    вспомогательный, а карточка — рабочая поверхность."""
    spec = _CALENDARS.get(kind)
    query = _calendar_query(kind, obj)
    if not spec or query is None:
        return ""
    tenant = getattr(request, "tenant", None)
    if kind == "order":
        from apps.core import sales_page

        # SH-1: Auftragsbuch показываем только там, где слоты выдачи реально ставятся.
        if "kalender" not in sales_page.views_for("order", tenant):
            return ""
    template, ctx_path = spec
    try:
        sub = copy.copy(request)  # поверхностная копия: оригинальный GET не трогаем
        sub.GET = (
            QueryDict(mutable=False)
            if not query
            else QueryDict("&".join(f"{k}={v}" for k, v in query.items()))
        )
        ctx = _resolve(ctx_path)(sub)
        if not isinstance(ctx, dict):  # ?box=1 — фрагмент карточки, не наш случай
            return ""
        # На карточке сделки календарь показывает ЗАНЯТОСТЬ; формы создания новой
        # брони/записи живут на самом календаре продаж (иначе карточка одной
        # сделки предлагала бы завести другую).
        ctx["deal_calendar_compact"] = True
        return render_to_string(template, ctx, request=sub)
    except Exception:  # noqa: BLE001 — см. docstring
        return ""


def _thread_for(kind: str, obj):
    """DF-3: тред ЭТОЙ сделки для инлайн-переписки на карточке.

    Владелец 2026-08-26: «написать клиенту должно просто ниже открываться тут
    же, чтобы не переходить в другую страницу». Тред ищем тем же резолвером,
    что и кнопка C1 (`inbox.deal_threads.find_thread`) — переписка по сделке
    остаётся в ОДНОМ месте, второго канала не появляется. Fail-safe: любая
    ошибка (модуль выключен, миграции не накачены) — карточка без блока."""
    try:
        from apps.inbox.deal_threads import find_thread

        return find_thread(kind, getattr(obj, "reference_code", "") or "", pk=obj.pk)
    except Exception:  # noqa: BLE001 — блок переписки не должен ронять карточку
        return None


def _rest_link(request, kind, obj, tenant):
    """{url, eur} для кнопки «Zahlungslink senden» или None (гейты balance_pay)."""
    from decimal import Decimal

    from apps.core import balance_pay

    try:
        if not balance_pay.rest_payable(kind, obj, tenant):
            return None
        return {
            "url": request.build_absolute_uri(balance_pay.pay_path(kind, obj)),
            "eur": Decimal(balance_pay.rest_cents(kind, obj)) / 100,
        }
    except Exception:  # noqa: BLE001 — карточка не падает из-за кнопки
        logger.exception("deal card: rest link failed %s %s", kind, getattr(obj, "pk", ""))
        return None


def _refund_form(request, kind, obj, tenant):
    """KA-12 B2-4a: форма возврата ПЕРЕПЛАТЫ — только владельцу и только когда
    получено больше цены. Карта — если подключён Stripe и переплата пришла картой;
    наличными — если есть деньги, полученные не картой."""
    from decimal import Decimal

    from apps.core import folio, refunds
    from apps.core.permissions import has_perm

    try:
        if kind not in folio.FOLIO_KINDS or not has_perm(request.user, "geld.korrektur"):
            return None
        if getattr(obj, "payment_state", "") == "installment":
            return None
        rows = folio.rows(kind, obj)
        over = refunds.overpaid_cents(kind, obj, rows) if rows else 0
        net = sum(r.amount_cents - r.refunded_cents for r in rows)
        # B2-4b: Minderung — уступка в цене (до суммы полученного), если её можно дать.
        minder = 0
        if kind in refunds.MINDERUNG_KINDS and net > 0:
            from apps.core import money_contract

            total = int((money_contract._total(kind, obj) * 100).to_integral_value())
            minder = min(net, total)
            if refunds._minderung_blocked(kind, obj, 1):
                minder = 0
        if over <= 0 and minder <= 0:
            return None
        card_rows = [
            {
                "pk": r.pk,
                "eur": Decimal(r.amount_cents - r.refunded_cents) / 100,
                "label": r.created_at,
            }
            for r in rows
            if r.stripe_payment_intent and r.amount_cents > r.refunded_cents
        ]
        cash_open = sum(
            r.amount_cents - r.refunded_cents for r in rows if not refunds._is_card_row(r)
        )
        card_ok = bool(card_rows and refunds._connect_id(tenant))
        if not card_ok and cash_open <= 0:
            return None
        return {
            "open_eur": Decimal(over) / 100,
            "minder_eur": Decimal(minder) / 100,
            "card_rows": card_rows,
            "card_ok": card_ok,
            "cash_ok": cash_open > 0,
        }
    except Exception:  # noqa: BLE001 — карточка не падает из-за формы
        logger.exception("deal card: refund form failed %s %s", kind, getattr(obj, "pk", ""))
        return None


def _invoice_id(kind, obj, tenant):
    """Счёт сделки: поле `invoice_id`, а у видов без поля (билет, KA-12 T-6) —
    по общему ключу сделки `deal_kind`/`deal_id` (тот же, что у `invoice_for_deal`)."""
    found = getattr(obj, "invoice_id", None)
    if found or hasattr(obj, "invoice_id") or not _module_active(tenant, "finance"):
        return found
    from apps.finance.models import Invoice

    ref = str(getattr(obj, "reference_code", "") or obj.pk)[:64]
    return (
        Invoice.objects.exclude(status=Invoice.STATUS_CANCELLED)
        .filter(kind=Invoice.KIND_INVOICE, deal_kind=kind, deal_id=ref)
        .order_by("created_at")
        .values_list("pk", flat=True)
        .first()
    )


def card_context(request, kind: str, obj, *, sections=(), links=None, hide_targets=()) -> dict:
    """Общий контекст карточки сделки для `core/deal_card_base.html`.

    `sections` — какие секции наполняет конкретная карточка (по данным);
    базовый шаблон рисует обёртку только для перечисленных."""
    tenant = getattr(request, "tenant", None)
    deal = transactions.transaction_for(
        kind,
        obj,
        status_labels.custom_labels(tenant, kind),
        transition_rules.subset_for(tenant, kind),
    )
    if hide_targets:
        # Переход, у которого есть СВОЙ приёмник со сторонним эффектом (у заявки
        # «invoiced» ещё и выставляет счёт), из общих кнопок статуса убираем —
        # иначе generic-путь сменил бы статус без этого эффекта.
        deal = _dc_replace(
            deal,
            allowed_actions=[
                a for a in deal.allowed_actions if a.get("target") not in hide_targets
            ],
        )
    calendar = calendar_html(request, kind, obj)
    # DC-8: честная разбивка НДС (у заказа — его собственный хелпер).
    small = bool(tenant and getattr(tenant, "small_business", False))
    try:
        vat = deal_vat(kind, obj, small_business=small)
    except Exception:  # noqa: BLE001 — разбивка не должна ронять карточку
        vat = {"rows": [], "gross": None, "net": None, "vat": None}
    # «Когда» в мете печатаем, только если этой даты ещё нет в заголовке сделки
    # (у брони номера title уже содержит даты — иначе строка дублируется).
    when = getattr(deal, "when", None)
    show_when = bool(
        when
        and getattr(when, "strftime", None)
        and when.strftime("%d.%m") not in (deal.title or "")
    )
    # DF-4: состав строками (бронь/запись/билет) — у заказа и заявки свои строки.
    try:
        from apps.core.deal_lines import deal_lines as _deal_lines

        lines = _deal_lines(kind, obj)
    except Exception:  # noqa: BLE001 — показ состава не должен ронять карточку
        lines = []
    # DF-7: у заказа состав рисует его собственный (редактируемый) блок, но
    # промежуточный итог и доставку для общих сумм берём из его же калькулятора —
    # иначе показ разошёлся бы с деньгами.
    subtotal = sum((r["total"] for r in lines), Decimal("0"))
    # SH-22: строки скидок акций есть только у заказа (у прочих видов — пусто).
    promo_rows = []
    shipping = None
    # DG-1: у сметы цены НЕТТО (остальные виды — брутто, PAngV), поэтому
    # промежуточный итог помечаем честно, а не молча смешиваем базы.
    subtotal_net = kind == "job"
    if kind == "job":
        subtotal = Decimal(getattr(obj, "net", 0) or 0)
    if kind == "order":
        try:
            from apps.orders.totals import order_totals

            totals = order_totals(obj, small_business=small)
            # SH-22: промежуточный итог — по ЛИСТОВЫМ ценам, скидки акций идут
            # отдельными строками ниже (иначе выгода клиента невидима).
            subtotal = totals["list_items"]
            promo_rows = totals["promo_rows"]
            shipping = totals["shipping"] or None
        except Exception:  # noqa: BLE001 — суммы не должны ронять карточку
            pass
    inbox_on = _module_active(tenant, "inbox")
    thread = _thread_for(kind, obj) if inbox_on else None
    from apps.core import refunds

    # KA-D3: в диалоге статуса — выбор «erstatten / nicht erstatten», если среди
    # переходов есть отмена оплаченной картой брони номера.
    refund_choice = any(
        refunds.needs_choice(kind, obj, a.get("target", ""), getattr(obj, "status", ""), tenant)
        for a in (getattr(deal, "allowed_actions", None) or [])
    )
    return {
        # KA-12 B2-5 (E1.11): ссылка на онлайн-доплату остатка (номер/запись/билет).
        "deal_rest": _rest_link(request, kind, obj, tenant),
        "deal_refund": _refund_form(request, kind, obj, tenant),
        "refund_choice": refund_choice,
        "deal": deal,
        "deal_obj": obj,
        "deal_kind": kind,
        "deal_sections": tuple(sections),
        "deal_titles": SECTION_TITLES,
        "deal_calendar_html": calendar,
        "deal_show_when": show_when,
        # DC-6: счёт из сделки (кнопка в блоке оплаты) — гейт модуля «Finanzen».
        "finance_active": _module_active(tenant, "finance"),
        "deal_invoice_id": _invoice_id(kind, obj, tenant),
        # KA-12 B2-8b: Anzahlungsrechnung (за флагом до вычета в итоговом счёте).
        "deal_advance": _advance(kind, obj, tenant, getattr(request, "user", None)),
        # DC-8: строки «davon X % MwSt.» в секции сумм.
        "deal_vat": vat,
        # DC-9: область действия скидки (вся сделка / позиция / доставка).
        "deal_discount_scope": getattr(obj, "discount_scope", "deal") or "deal",
        "deal_discount_scopes": list(getattr(obj, "DISCOUNT_SCOPES", ()) or ()),
        # DC-5: скидка владельца — общий блок между составом и суммами.
        "deal_discount_cents": int(getattr(obj, "discount_cents", 0) or 0),
        "deal_discount_input": f"{int(getattr(obj, 'discount_cents', 0) or 0) / 100:.2f}",
        "deal_discount_note": getattr(obj, "voucher_code", "") or "",
        # DF-4: строки состава для общего партиала `core/_deal_lines.html`.
        "deal_lines": lines,
        # SH-22: скидки акций — строками между промежуточным итогом и ручной
        # скидкой владельца (несколько акций в заказе = несколько строк).
        "deal_promo_rows": promo_rows,
        # Промежуточный итог = сумма строк (брутто ДО скидки) — макет требует
        # его отдельной строкой над скидкой.
        "deal_lines_total": subtotal,
        "deal_subtotal_is_net": subtotal_net,
        # DG-2: у сметы без скидки Netto == промежуточный итог — вторую строку
        # с тем же числом не печатаем.
        "deal_net_equals_subtotal": vat.get("net") is not None and vat["net"] == subtotal,
        # DF-7: доставка — отдельной строкой сумм (у прочих видов её нет).
        "deal_shipping_eur": shipping,
        "deal_discount_eur": Decimal(int(getattr(obj, "discount_cents", 0) or 0)) / 100,
        # DF-3: переписка с клиентом — прямо на карточке (тред или композер).
        "deal_thread": thread,
        "deal_thread_messages": (_thread_messages(thread) if thread is not None else []),
        # DC-4: внешний номер правится прямо в голове — там, где поле есть.
        "deal_external_editable": hasattr(obj, "external_code"),
        "deal_external_code": getattr(obj, "external_code", ""),
        "deal_links": links,
        "crm_active": _module_active(tenant, "crm"),
        # CO-2b: получатель счёта — у видов с типом покупателя (SH-23).
        "deal_billing": _billing(obj),
        "inbox_active": _module_active(tenant, "inbox"),
        # T-8.10g (G-3): «✨ Antwort vorschlagen» у существующего треда сделки.
        "ai_reply_enabled": thread is not None and _ai_enabled(),
    }


def _advance(kind, obj, tenant, user=None):
    """Кнопка/ссылка счёта на предоплату или None (флаг, модуль, вид, депозит, роль)."""
    from apps.core.permissions import has_perm
    from apps.finance import advance

    if not advance.enabled() or kind not in advance.KINDS:
        return None
    if user is None or not has_perm(user, "finanzen.korrektur"):
        return None
    if not _module_active(tenant, "finance"):
        return None
    try:
        live = advance.live_advance(kind, obj)
    except Exception:  # noqa: BLE001 — кнопка не должна ронять карточку
        logger.exception("deal card: advance lookup failed for %s", kind)
        return None
    if live is None and not int(getattr(obj, "deposit_cents", 0) or 0):
        return None
    return {"invoice": live}


def _billing(obj):
    """CO-2b: кому выставляется счёт — для блока «Rechnungsempfänger»."""
    if not hasattr(obj, "customer_type"):
        return None
    from apps.crm.models import Company
    from apps.finance.recipient import recipient_for

    customer = getattr(obj, "customer", None)
    return {
        "is_company": obj.customer_type == "company",
        "company": obj.billing_company,
        "vat_id": obj.billing_vat_id,
        "has_address": hasattr(obj, "billing_address"),
        "address": getattr(obj, "billing_address", ""),
        "linked": getattr(customer, "company", None) if customer is not None else None,
        "recipient": recipient_for(obj),
        "directory": list(Company.objects.only("pk", "name", "vat_id").order_by("name")[:200]),
    }


def _thread_messages(thread):
    """Сообщения треда с подписью автора (кто писал) — тот же резолвер, что у
    страницы беседы в кабинете."""
    from apps.inbox.display import labelled_messages
    from apps.inbox.models import Message

    return labelled_messages(thread, viewer=Message.AUTHOR_STAFF)
