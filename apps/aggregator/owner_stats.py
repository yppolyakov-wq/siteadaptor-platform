"""В5 V5-3: цифры экрана владельца «Besuche aus dem Stadtportal» — только чтение.

Схема бизнеса — ТОЛЬКО из `request.tenant` (никогда из запроса); у public-схемы
данных нет. Действия, которые ещё не пишутся (показы — V5-4, обращения/сделки — V5-5),
не выдаются за «0»: значение None + подпись «Wird bald gezählt» — ноль утверждал бы,
что никто не смотрел. Четыре запроса, все по префиксу уникального ключа
`(tenant_schema, day, …)`."""

from __future__ import annotations

from datetime import timedelta
from functools import reduce
from operator import or_

from django.db.models import Max, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.dashboard import _sparkline_points

from .models import AggregatorListing, PortalStat

PERIODS = (7, 30, 90, 365)
DEFAULT_PERIOD = 30
#: какие действия уже пишутся; V5-4 добавит "impression", V5-5 — "contact" и "deal".
TRACKED_ACTIONS = ("view", "click")
TOP_LIMIT = 10
#: строки «бизнес целиком» (профиль компании; V5-5 — обращение без предложения).
BUSINESS_KINDS = ("business", "")
_WEEKLY_FROM = 365  # на годе точек по дням 365 — в 120px это шум, берём недели


def parse_period(raw) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PERIOD
    return value if value in PERIODS else DEFAULT_PERIOD


def _delta_hint(cur: int, prev: int) -> str:
    if not prev:
        return _("neu vs. Vorperiode") if cur else ""
    delta = round(100 * (cur - prev) / prev)
    arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "→")
    return _("%(arrow)s %(delta)s %% vs. Vorperiode") % {"arrow": arrow, "delta": abs(delta)}


def _schema(tenant) -> str:
    schema = getattr(tenant, "schema_name", "") or ""
    return "" if schema == "public" else schema


def summary(tenant, days: int, *, today=None) -> dict:
    days = days if days in PERIODS else DEFAULT_PERIOD
    today = today or timezone.localdate()
    cur_start = today - timedelta(days=days - 1)
    prev_start = cur_start - timedelta(days=days)
    labels = dict(PortalStat.ACTIONS)
    cur = dict.fromkeys(PortalStat.ACTIONS_CODES, 0)
    prev = dict.fromkeys(PortalStat.ACTIONS_CODES, 0)
    per_day: dict = {}
    top: list = []
    featured = None
    schema = _schema(tenant)

    if schema:
        # .order_by() снимает ordering модели — иначе count попал бы в GROUP BY.
        daily = (
            PortalStat.objects.filter(tenant_schema=schema, day__gte=prev_start, day__lte=today)
            .values("day", "action")
            .annotate(n=Sum("count"))
            .order_by()
        )
        for row in daily:
            n = row["n"] or 0
            if row["day"] >= cur_start:
                cur[row["action"]] = cur.get(row["action"], 0) + n
                if row["action"] in ("view", "click"):
                    per_day[row["day"]] = per_day.get(row["day"], 0) + n
            else:
                prev[row["action"]] = prev.get(row["action"], 0) + n
        top = _top(schema, cur_start, today)
        agg = AggregatorListing.objects.filter(tenant_schema=schema).aggregate(
            imp=Sum("featured_impressions"), clk=Sum("featured_clicks")
        )
        if agg["imp"] or agg["clk"]:
            featured = (agg["imp"] or 0, agg["clk"] or 0)

    series = [per_day.get(cur_start + timedelta(days=i), 0) for i in range(days)]
    if days >= _WEEKLY_FROM:
        series = [sum(series[i : i + 7]) for i in range(0, len(series), 7)]
    funnel = []
    for code in PortalStat.ACTIONS_CODES:
        tracked = code in TRACKED_ACTIONS
        funnel.append(
            {
                "code": code,
                "label": labels[code],
                "tracked": tracked,
                "value": cur[code] if tracked else None,
                "hint": _delta_hint(cur[code], prev[code]) if tracked else "",
            }
        )
    return {
        "days": days,
        "funnel": funnel,
        "sparkline": _sparkline_points(series) if any(series) else "",
        "top": top,
        "featured": featured,
        "has_data": any(cur.values()) or any(prev.values()),
        "status": _status(tenant),
        "is_demo": bool(getattr(tenant, "is_demo", False)),
    }


def _top(schema: str, start, end) -> list:
    sums = {code: Sum("count", filter=Q(action=code)) for code in PortalStat.ACTIONS_CODES}
    rows = list(
        PortalStat.objects.filter(tenant_schema=schema, day__gte=start, day__lte=end)
        .values("listing_kind", "source_ref")
        .annotate(
            **sums,
            hot=Sum("count", filter=Q(action__in=("view", "click"))),
            lid=Max("listing_id"),
        )
        .order_by("-hot", "-impression", "listing_kind", "source_ref")[:TOP_LIMIT]
    )
    keys = [
        (r["listing_kind"], r["source_ref"])
        for r in rows
        if r["listing_kind"] not in BUSINESS_KINDS
    ]
    # Заголовок — по ключу листинга, не по listing_id: синк пересоздаёт листинг с новым
    # pk, а старые строки статистики хранят прежний.
    titles = {}
    if keys:
        q = reduce(or_, (Q(listing_kind=k, source_ref=r) for k, r in keys))
        for lst in AggregatorListing.objects.filter(tenant_schema=schema).filter(q):
            titles[(lst.listing_kind, lst.source_ref)] = lst.title_text
    out = []
    for r in rows:
        key = (r["listing_kind"], r["source_ref"])
        if r["listing_kind"] in BUSINESS_KINDS:
            title = _("Ihr Unternehmensprofil")
        else:
            title = titles.get(key) or _("(nicht mehr im Stadtportal)")
        out.append(
            {
                "title": title,
                "values": {
                    code: (r[code] or 0) if code in TRACKED_ACTIONS else None
                    for code in PortalStat.ACTIONS_CODES
                },
            }
        )
    return out


def _status(tenant) -> str:
    from . import visibility

    if not getattr(tenant, "in_city_catalog", True):
        return "not_in_catalog"
    if getattr(tenant, "email_pending", False):
        return "email_pending"
    if not visibility.listable(tenant):
        return "hidden"
    return "ok"


def portal_totals(tenant, days: int = DEFAULT_PERIOD) -> tuple[int, int]:
    """(просмотры, переходы) за последние `days` дней — для панели Marketing."""
    schema = _schema(tenant)
    if not schema:
        return 0, 0
    start = timezone.localdate() - timedelta(days=days - 1)
    agg = dict(
        PortalStat.objects.filter(
            tenant_schema=schema, day__gte=start, action__in=("view", "click")
        )
        .values("action")
        .annotate(n=Sum("count"))
        .order_by()
        .values_list("action", "n")
    )
    return agg.get("view") or 0, agg.get("click") or 0
