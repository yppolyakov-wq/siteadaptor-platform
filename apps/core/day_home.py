"""UX-D D8.1: главная = сводка дня у ВСЕХ видов продаж (не только у отеля).

План — docs/ux-d8-archetype-parity-plan-2026-11-04.md. Отель (D1.4) живёт в
`stays/home_summary.py`; здесь — заказы, записи, заявки и билеты по той же схеме
макета Home: цифры дня · список «Heute / diese Woche» · «Neu eingegangen» ·
«Braucht Aufmerksamkeit» · загрузка на 7 дней.

Источники — те же, что у экранов, куда ведут ссылки, поэтому числа не расходятся:
«Nicht bezahlt» = строки Offene Posten (`finance.bank.deal_open_items`), «Heute»
у заказов/записей = колонки `sales_page.heute_columns` (вид `?view=heute`),
стадии — `pipeline.stage_for` (свои статусы владельца учитываются), даты —
поле события вида (то же, что сортирует доску). Каждый блок fail-safe: упавший
источник не роняет главную. Запросов — константа (списки ограничены).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.digest import _safe

KINDS = ("order", "booking", "job", "ticket")
LIST_LIMIT = 8
NEW_LIMIT = 5
DAYS = 7

# Поле даты СОБЫТИЯ вида (выдача / начало записи / дата мероприятия заявки / начало события).
_DATE_FIELD = {
    "order": "pickup_slot",
    "booking": "start",
    "job": "event_date",
    "ticket": "event__starts_at",
}
_DATE_IS_DATE = {"job"}  # event_date — DateField, остальные — DateTimeField

# Колонки «Heute» страницы продаж, которые относятся к виду.
_HEUTE_COLUMNS = {"order": ("abholung", "lieferung"), "booking": ("termine",)}

TEXTS = {
    "order": {
        "today": _("Heute abholen & liefern"),
        "kpi": _("Abholungen heute"),
        "week": _("Abholungen 7 Tage"),
    },
    "booking": {
        "today": _("Termine heute"),
        "kpi": _("Termine heute"),
        "week": _("Termine 7 Tage"),
    },
    "job": {
        "today": _("Nächste Einsätze"),
        "kpi": _("Einsätze heute"),
        "week": _("Einsätze 7 Tage"),
    },
    "ticket": {
        "today": _("Nächste Veranstaltungen"),
        "kpi": _("Tickets heute"),
        "week": _("Tickets 7 Tage"),
    },
}


def applies(kind: str) -> bool:
    return kind in KINDS


def _terminal(kind, tenant) -> list:
    from apps.core import sales_page

    return list(sales_page._terminal_statuses(kind, tenant))


def _cancelled(kind, tenant) -> list:
    from apps.core import status_registry

    return list(status_registry.cancelled_statuses_for(kind, tenant))


def _stage_counts(kind, tenant) -> dict:
    """{stage: число открытых сделок} — один GROUP BY по статусу."""
    from django.db.models import Count

    from apps.core import pipeline, transactions

    rows = (
        transactions.model_for(kind)
        .objects.exclude(status__in=_terminal(kind, tenant))
        .values("status")
        .annotate(n=Count("pk"))
        .order_by()
    )
    out: dict[str, int] = {}
    for row in rows:
        stage = pipeline.stage_for(kind, row["status"])
        out[stage] = out.get(stage, 0) + row["n"]
    return out


def _date_q(kind, start, end):
    """Q «дата события в [start, end]» (end включительно), в локальном дне."""
    from django.db.models import Q

    field = _DATE_FIELD[kind]
    if kind in _DATE_IS_DATE:
        return Q(**{f"{field}__gte": start, f"{field}__lte": end})
    return Q(**{f"{field}__date__gte": start, f"{field}__date__lte": end})


def _week(kind, tenant, today) -> list[dict]:
    """Сделок с датой события на каждый из 7 дней (отмены не считаются)."""
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    from apps.core import transactions

    field = _DATE_FIELD[kind]
    end = today + timedelta(days=DAYS - 1)
    qs = (
        transactions.model_for(kind)
        .objects.filter(_date_q(kind, today, end))
        .exclude(status__in=_cancelled(kind, tenant))
    )
    if kind in _DATE_IS_DATE:
        rows = qs.values(field).annotate(n=Count("pk")).order_by()
        counts = {r[field]: r["n"] for r in rows}
    else:
        tz = timezone.get_current_timezone()
        rows = qs.annotate(d=TruncDate(field, tzinfo=tz)).values("d").annotate(n=Count("pk"))
        counts = {r["d"]: r["n"] for r in rows.order_by()}
    days = [today + timedelta(days=i) for i in range(DAYS)]
    peak = max([counts.get(d, 0) for d in days] + [1])
    return [
        {"day": d, "n": counts.get(d, 0), "pct": round(100 * counts.get(d, 0) / peak)} for d in days
    ]


def _cards(kind, objs) -> list[dict]:
    """Строки списка из контракта Transaction: клиент, что/код, когда, статус, ссылка."""
    from apps.core import transactions

    out = []
    for obj in objs:
        tx = transactions.transaction_for(kind, obj)
        if tx is None:
            continue
        code = tx.reference_code
        # у заказа заголовок = «#код» — второй раз код не повторяем
        what = "" if code and code in (tx.title or "") else (tx.title or "")
        out.append(
            {
                "title": str(tx.customer or "").strip() or tx.title or code,
                "subtitle": " · ".join(x for x in (what, code) if x),
                "when": tx.when,
                "status": tx.status_label,
                "url": tx.manage_url,
                "drawer": kind == "booking",
            }
        )
    return out


def _upcoming(kind, tenant, today) -> list[dict]:
    """Заявки: ближайшие по дате события (сегодня и дальше, без верхней границы —
    кейтеринг планирует на месяцы вперёд). Билеты — по СОБЫТИЯМ, а не по билетам."""
    from apps.core import transactions

    if kind == "ticket":
        return _upcoming_events(tenant)
    field = _DATE_FIELD[kind]
    qs = (
        transactions.model_for(kind)
        .objects.filter(**{f"{field}__gte": today})
        .exclude(status__in=_terminal(kind, tenant))
        .select_related(*transactions._SELECT_RELATED.get(kind, ()))
        .order_by(field)[:LIST_LIMIT]
    )
    return _cards(kind, list(qs))


def _upcoming_events(tenant) -> list[dict]:
    """Ближайшие опубликованные события с числом мест в активных билетах — один запрос."""
    from django.db.models import Q, Sum
    from django.urls import reverse
    from django.utils.translation import gettext

    from apps.core import status_registry
    from apps.events.models import Event

    active = status_registry.active_statuses_for("ticket", tenant)
    events = (
        Event.objects.filter(status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now())
        .annotate(sold=Sum("tickets__quantity", filter=Q(tickets__status__in=active)))
        .order_by("starts_at")[:LIST_LIMIT]
    )
    return [
        {
            "title": str(e),
            "subtitle": gettext("%(n)s Teilnehmer") % {"n": e.sold or 0},
            "when": e.starts_at,
            "status": "",
            "url": reverse("events:detail", args=[e.pk]),
            "drawer": False,
        }
        for e in events
    ]


def _today(kind, tenant, user) -> tuple[list[dict], bool]:
    """Заказы/записи — ровно колонки вида «Heute» страницы продаж."""
    from apps.core import sales_page

    wanted = _HEUTE_COLUMNS[kind]
    items, error = [], False
    section = "orders" if kind == "order" else "booking"
    for col in sales_page.heute_columns(tenant, user, sections={section}):
        if col["key"] in wanted:
            error = error or col["error"]
            for it in col["items"]:
                items.append({**it, "drawer": kind == "booking"})
    return items[:LIST_LIMIT], error


def _new(kind, tenant) -> list[dict]:
    """Последние сделки в приёмной стадии («Neu») — то, что ждёт реакции."""
    from apps.core import pipeline, transactions

    model = transactions.model_for(kind)
    statuses = [
        s
        for s in model.objects.exclude(status__in=_terminal(kind, tenant))
        .values_list("status", flat=True)
        .distinct()
        .order_by()
        if pipeline.stage_for(kind, s) == "intake"
    ]
    if not statuses:
        return []
    qs = (
        model.objects.filter(status__in=statuses)
        .select_related(*transactions._SELECT_RELATED.get(kind, ()))
        .order_by("-created_at")[:NEW_LIMIT]
    )
    return _cards(kind, list(qs))


def _unpaid(tenant, kind) -> dict:
    from apps.finance import bank

    rows = bank.deal_open_items(tenant, kind)
    return {"count": len(rows), "amount": sum((r["amount"] for r in rows), Decimal("0"))}


def _overdue_quotes(tenant) -> int:
    """Сметы с истёкшим «gültig bis», ещё не закрытые."""
    from apps.jobs.models import Job

    return (
        Job.objects.filter(valid_until__lt=timezone.localdate())
        .exclude(status__in=_terminal("job", tenant))
        .count()
    )


def _low_stock(tenant) -> int:
    from apps.inventory import services

    return services.reorder_count(services.low_stock_threshold(tenant))


def _screen_open(request, url_name: str) -> bool:
    """Экран доступен ЭТОМУ пользователю здесь: запись меню видна тенанту (модуль,
    направление), экран в пакете, и у пользователя есть право (``view_perms``).
    Ссылки и счётчики сводки показываем только тогда — иначе цифра ведёт в 403."""
    from apps.core import nav_registry, packages
    from apps.core.templatetags.cabinet import can_open

    tenant = request.tenant
    entry = next((e for e in nav_registry.ENTRIES if e.url_name == url_name), None)
    if entry is not None and not nav_registry.entry_visible(entry, tenant):
        return False
    return packages.view_allowed(tenant, url_name) and can_open(url_name, request)


def _unread(tenant) -> int:
    if not tenant.is_module_active("inbox"):
        return 0
    from apps.inbox.models import Conversation

    return Conversation.objects.filter(unread_for_staff=True).count()


def summary(request, kind: str) -> dict:
    """Контекст `core/_day_home.html` (префикс dh_). Без побочных эффектов."""
    from django.urls import reverse

    from apps.core import sales_page, transactions
    from apps.core.templatetags.cabinet import can_open

    tenant = request.tenant
    today = timezone.localdate()
    stages = _safe(lambda: _stage_counts(kind, tenant), {})
    if kind in _HEUTE_COLUMNS:
        items, items_error = _safe(lambda: _today(kind, tenant, request.user), ([], True))
    else:
        items, items_error = _safe(lambda: (_upcoming(kind, tenant, today), False), ([], True))
    if kind == "ticket" and not can_open("events:detail", request):
        items = [{**it, "url": f"{reverse('verkaeufe')}?tab=ticket"} for it in items]
    week = _safe(lambda: _week(kind, tenant, today), [])
    new = _safe(lambda: _new(kind, tenant), [])
    unread = (
        _safe(lambda: _unread(tenant), 0)
        if _safe(lambda: _screen_open(request, "inbox:list"), False)
        else 0
    )
    overdue = _safe(lambda: _overdue_quotes(tenant), 0) if kind == "job" else 0
    low_stock = 0
    if kind == "order" and _safe(lambda: _screen_open(request, "stock"), False):
        low_stock = _safe(lambda: _low_stock(tenant), 0)
    create = sales_page.create_target(kind)
    if create and not can_open(_url_name(create), request):
        create = ""
    return {
        "day_home": True,
        "dh_kind": kind,
        "dh_label": transactions.KIND_LABEL.get(kind, kind),
        "dh_texts": TEXTS[kind],
        "dh_today_count": week[0]["n"] if week else 0,
        "dh_new_n": stages.get("intake", 0),
        "dh_progress_n": stages.get("in_progress", 0),
        "dh_items": items,
        "dh_items_error": items_error,
        "dh_new": new,
        "dh_week": week,
        "dh_unpaid": _safe(lambda: _unpaid(tenant, kind), {"count": 0, "amount": Decimal("0")}),
        "dh_finance": tenant.is_module_active("finance"),
        "dh_finance_link": tenant.is_module_active("finance")
        and _safe(lambda: _screen_open(request, "finance:offene"), False),
        "dh_unread": unread,
        "dh_overdue": overdue,
        "dh_low_stock": low_stock,
        "dh_attention": bool(unread or overdue or low_stock or stages.get("intake")),
        "dh_sales_url": f"{reverse('verkaeufe')}?tab={kind}",
        "dh_create": create,
        "dh_create_drawer": sales_page.opens_in_drawer(create) if create else False,
    }


def _url_name(url: str) -> str:
    """url-name адреса «＋» (для проверки права) — без аргументов, адреса фиксированы."""
    from django.urls import Resolver404, resolve

    try:
        match = resolve(url.split("?", 1)[0])
    except Resolver404:
        return ""
    return f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
