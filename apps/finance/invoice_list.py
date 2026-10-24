"""KA-12 E2.9: фильтры списка счетов — чипы статуса/вида, «überfällig», поиск,
период и сортировка по белому списку.

Всё из URL проходит через словари этого модуля: неизвестное значение
отбрасывается, а не попадает в запрос. Поиск — по номеру и имени клиента; по
получателю — только владельцу и бухгалтеру (`full_search`): у клиента без
имени получатель = его e-mail (`Customer.__str__`), и поиск по нему давал бы
сотруднику посимвольный подбор адресов (KA-H11).
"""

from datetime import date

from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Invoice

OVERDUE = "ueberfaellig"

SORTS = {
    "datum": ("-created_at",),
    "nummer": (F("number").desc(nulls_last=True), "-created_at"),
    "summe": ("-gross", "-created_at"),
    "status": ("status", "-created_at"),
}
SORT_LABELS = {
    "datum": _("Neueste zuerst"),
    "nummer": _("Rechnungsnummer"),
    "summe": _("Höchster Betrag"),
    "status": _("Status"),
}


def _overdue_q() -> Q:
    return Q(status=Invoice.STATUS_ISSUED, due_date__lt=timezone.localdate())


def _date(raw) -> date | None:
    try:
        return date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def _clean(params) -> dict:
    statuses = {code for code, _label in Invoice.STATUSES} | {OVERDUE}
    kinds = {code for code, _label in Invoice.KINDS}
    status = (params.get("status") or "").strip()
    art = (params.get("art") or "").strip()
    sort = (params.get("sort") or "").strip()
    von, bis = _date(params.get("von")), _date(params.get("bis"))
    return {
        "status": status if status in statuses else "",
        "art": art if art in kinds else "",
        "sort": sort if sort in SORTS else "",
        "q": (params.get("q") or "").strip()[:100],
        "von": von.isoformat() if von else "",
        "bis": bis.isoformat() if bis else "",
    }


def _base(qs, state: dict, full_search: bool = False):
    """Всё, кроме чипа статуса (счётчики чипов считаются по этой выборке)."""
    if state["art"]:
        qs = qs.filter(kind=state["art"])
    if state["von"]:
        qs = qs.filter(created_at__date__gte=state["von"])
    if state["bis"]:
        qs = qs.filter(created_at__date__lte=state["bis"])
    q = state["q"]
    if q:
        cond = Q(customer__name__icontains=q)
        if full_search:
            cond |= Q(recipient__icontains=q)
        digits = q.lstrip("#").strip()
        if digits.isdigit() and len(digits) <= 9:
            cond |= Q(number=int(digits))
        qs = qs.filter(cond)
    return qs


def filtered(qs, params, full_search: bool = False) -> tuple:
    """(queryset, состояние фильтров для шаблона)."""
    state = _clean(params)
    qs = _base(qs, state, full_search)
    if state["status"] == OVERDUE:
        qs = qs.filter(_overdue_q())
    elif state["status"]:
        qs = qs.filter(status=state["status"])
    if state["sort"]:
        qs = qs.order_by(*SORTS[state["sort"]])
    return qs, state


def status_counts(qs, params, full_search: bool = False) -> dict:
    """Счётчики чипов одним запросом (+ один на «überfällig»).

    `order_by()` снимается до `values()` — иначе сортировка попадает в GROUP BY
    и даёт по строке на счёт (грабля VS-2c)."""
    base = _base(qs, _clean(params), full_search).order_by()
    counts = {row["status"]: row["n"] for row in base.values("status").annotate(n=Count("pk"))}
    counts[""] = sum(counts.values())
    counts[OVERDUE] = base.filter(_overdue_q()).count()
    return counts


def chips(counts: dict) -> list[tuple]:
    """(значение, подпись, число) — «Alle», статусы, затем «überfällig»."""
    out = [("", _("Alle"), counts.get("", 0))]
    out += [(code, label, counts.get(code, 0)) for code, label in Invoice.STATUSES]
    out.append((OVERDUE, _("Überfällig"), counts.get(OVERDUE, 0)))
    return out


def sort_options() -> list[tuple]:
    return list(SORT_LABELS.items())
