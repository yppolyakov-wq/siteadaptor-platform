"""Часы работы ↔ Google Business Profile (Д3-2, план docs/d3-gbp-sync-plan-2026-10-18.md §3).

Решение владельца В-3: обе стороны — ручными кнопками с предпросмотром, автосинхронизации нет.
Наша модель — один интервал в день без ночных часов (`apps/tenants/openinghours`); у Google бывают
разрывы в смене, ночные и круглосуточные дни. Такие дни «с потерями»: при заборе остаётся наше
значение, при отправке нужна явная галочка (иначе один клик стёр бы разрывы у Google). Пустые
часы не отправляем и пустые не забираем — кнопка не может стереть часы ни с одной стороны.
Особые часы (праздники) — только чтение (В-10): `updateMask=regularHours`."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from apps.tenants import openinghours

from . import gbp

DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
ACTION_LIMIT = 3  # действий с часами в минуту на бизнес (предпросмотр → применить укладывается)
ACTION_WINDOW = 60


class HoursError(Exception):
    """`empty` — у нас нет часов; `google_empty` — у Google нет; `lossy` — нужна галочка."""

    def __init__(self, code: str, diff: HoursDiff | None = None):
        super().__init__(code)
        self.code = code
        self.diff = diff


@dataclass
class HoursDiff:
    rows: list = field(default_factory=list)
    lossy_days: set = field(default_factory=set)
    equal: bool = True
    special_count: int = 0
    google_empty: bool = False
    google: dict = field(default_factory=dict)  # часы Google в нашем формате (без дней с потерями)


def _hhmm(value: str) -> dict:
    hours, minutes = (int(x) for x in value.split(":"))
    return {"hours": hours, "minutes": minutes}


def to_periods(structured) -> list[dict]:
    """Наши часы → `regularHours.periods` Google (закрытые дни опускаются)."""
    out = []
    for wd, (open_, close) in sorted(openinghours.normalize(structured).items()):
        day = DAYS[int(wd)]
        out.append(
            {"openDay": day, "openTime": _hhmm(open_), "closeDay": day, "closeTime": _hhmm(close)}
        )
    return out


def _time(value) -> tuple[int, int] | None:
    """TimeOfDay Google → (часы, минуты); нулевые поля Google опускает."""
    if not isinstance(value, dict):
        return None
    hours, minutes = value.get("hours", 0), value.get("minutes", 0)
    if not isinstance(hours, int) or not isinstance(minutes, int) or isinstance(hours, bool):
        return None
    if not (0 <= hours <= 24 and 0 <= minutes < 60):
        return None
    return hours, minutes


def _fmt(t: tuple[int, int]) -> str:
    return f"{t[0]:02d}:{t[1]:02d}"


def _google_by_day(periods) -> dict[int, list]:
    """{wd: [(open, close, close_wd)]} — только распознанные интервалы."""
    by_day: dict[int, list] = {}
    for period in periods if isinstance(periods, list) else []:
        if not isinstance(period, dict) or period.get("openDay") not in DAYS:
            continue
        open_t, close_t = _time(period.get("openTime")), _time(period.get("closeTime"))
        close_day = period.get("closeDay") or period.get("openDay")
        if open_t is None or close_t is None or close_day not in DAYS:
            by_day.setdefault(DAYS.index(period["openDay"]), []).append(None)
            continue
        wd = DAYS.index(period["openDay"])
        by_day.setdefault(wd, []).append((open_t, close_t, DAYS.index(close_day)))
    return by_day


def from_periods(periods) -> tuple[dict, set]:
    """Google → (наши часы, дни с потерями). День с потерями в часы не попадает."""
    structured, lossy = {}, set()
    for wd, intervals in _google_by_day(periods).items():
        if len(intervals) != 1 or intervals[0] is None:
            lossy.add(wd)
            continue
        open_t, close_t, close_wd = intervals[0]
        if close_wd != wd or close_t[0] == 24 or not open_t < close_t:
            lossy.add(wd)
            continue
        structured[str(wd)] = [_fmt(open_t), _fmt(close_t)]
    return openinghours.normalize(structured), lossy


def _google_label(wd: int, intervals) -> str:
    parts = []
    for item in intervals:
        if item is None:
            parts.append("?")
            continue
        open_t, close_t, close_wd = item
        suffix = f" ({openinghours.weekday_abbr(close_wd)})" if close_wd != wd else ""
        parts.append(f"{_fmt(open_t)}–{_fmt(close_t)}{suffix}")
    return ", ".join(parts)


def diff(ours, periods, special_count: int = 0) -> HoursDiff:
    ours = openinghours.normalize(ours)
    google, lossy = from_periods(periods)
    raw = _google_by_day(periods)
    result = HoursDiff(
        lossy_days=lossy, special_count=special_count, google_empty=not raw, google=google
    )
    for wd in range(7):
        mine = ours.get(str(wd))
        theirs = google.get(str(wd))
        is_lossy = wd in lossy
        google_text = (
            _google_label(wd, raw[wd]) if is_lossy else ("–".join(theirs) if theirs else "")
        )
        changed = is_lossy or mine != theirs
        result.equal = result.equal and not changed
        result.rows.append(
            {
                "wd": wd,
                "label": openinghours.weekday_abbr(wd),
                "ours": "–".join(mine) if mine else "",
                "google": google_text,
                "lossy": is_lossy,
                "changed": changed,
            }
        )
    return result


def fetch(tenant, config) -> HoursDiff:
    """Прочитать часы Google и сравнить с нашими (предпросмотр)."""
    _v4, v1 = gbp.location_ids(config)
    data = gbp.get_hours(gbp.access_token(config), v1)
    return diff(tenant.opening_hours_structured, data["periods"], data["special_count"])


def push(tenant, config, *, confirm: bool = False) -> HoursDiff:
    """Отправить наши часы в Google. Пустые — отказ без запроса; потери у Google — галочка."""
    ours = openinghours.normalize(tenant.opening_hours_structured)
    if not ours:
        raise HoursError("empty")
    _v4, v1 = gbp.location_ids(config)
    token = gbp.access_token(config)
    data = gbp.get_hours(token, v1)
    current = diff(ours, data["periods"], data["special_count"])
    if current.lossy_days and not confirm:
        raise HoursError("lossy", current)
    gbp.patch_regular_hours(token, v1, to_periods(ours))
    return current


def pull_apply(tenant, config) -> HoursDiff:
    """Забрать часы из Google. Дни с потерями остаются нашими; пустой Google — отказ.

    Пишем только колонку часов (W7a): параллельные записи других полей тенанта целы."""
    current = fetch(tenant, config)
    if current.google_empty:
        raise HoursError("google_empty", current)
    model = type(tenant)
    fresh = model.objects.filter(pk=tenant.pk).values_list("opening_hours_structured", flat=True)
    merged = dict(openinghours.normalize(fresh.first()))
    google = current.google
    for row in current.rows:
        if row["lossy"]:
            continue
        key = str(row["wd"])
        if key in google:
            merged[key] = google[key]
        else:
            merged.pop(key, None)
    merged = openinghours.normalize(merged)
    model.objects.filter(pk=tenant.pk).update(
        opening_hours_structured=merged, updated_at=timezone.now()
    )
    tenant.opening_hours_structured = merged
    from apps.aggregator.tasks import refresh_tenant_fields

    refresh_tenant_fields(tenant)
    return current
