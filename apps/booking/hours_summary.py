"""SP-3: сводка недельных правил ресурса для кабинета.

Ресурс ресторана несёт по правилу на день («Mo 11:00–22:00 · 30 min» ×7) — экран
ресурсов у 9 столов растягивался до ~5800 px. Одинаковые окна склеиваются в
группы с диапазонами дней («Mo–So 11:00–22:00»): строка-сводка в заголовке
свёрнутой карточки и компактные группы в развёрнутой. Удаление остаётся
поштучным — у каждого дня группы своя кнопка (логика правил не меняется).
"""

from itertools import groupby

from django.utils.translation import gettext as _


def _day_short(weekday: int) -> str:
    # Те же msgid, что у календаря витрины (_booking_calendar.html) — переводы есть.
    return [_("Mo"), _("Tu"), _("We"), _("Th"), _("Fr"), _("Sa"), _("Su")][weekday]


def _day_ranges(days: list[int]) -> str:
    """[0,1,2,3,4,6] → «Mo–Fr, Su»: подряд идущие дни — диапазоном."""
    out = []
    for _key, run in groupby(enumerate(sorted(set(days))), key=lambda p: p[1] - p[0]):
        seq = [d for _i, d in run]
        if len(seq) >= 3:
            out.append(f"{_day_short(seq[0])}–{_day_short(seq[-1])}")
        else:
            out.extend(_day_short(d) for d in seq)
    return ", ".join(out)


def rule_groups(rules) -> list[dict]:
    """Группы правил с одинаковым окном и шагом, в порядке первого дня."""
    buckets: dict[tuple, list] = {}
    for rule in rules:
        key = (rule.start_time, rule.end_time, rule.slot_minutes)
        buckets.setdefault(key, []).append(rule)
    groups = []
    for (start, end, slot), items in buckets.items():
        items = sorted(items, key=lambda r: r.weekday)
        groups.append(
            {
                "days": _day_ranges([r.weekday for r in items]),
                "time": f"{start:%H:%M}–{end:%H:%M}",
                "slot": slot,
                "rules": [{"rule": r, "day": _day_short(r.weekday)} for r in items],
                "first": items[0].weekday,
            }
        )
    return sorted(groups, key=lambda g: (g["first"], g["time"]))


def summary(groups: list[dict]) -> str:
    """Одна строка для заголовка свёрнутой карточки: «Mo–Fr 11:00–22:00 · Sa 12:00–20:00»."""
    return " · ".join(f"{g['days']} {g['time']}" for g in groups)
