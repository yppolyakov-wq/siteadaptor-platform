"""Структурные часы работы и live-статус «Jetzt geöffnet/geschlossen» (P1b).

Формат хранения (Tenant.opening_hours_structured): {"0": ["09:00","18:00"], …}
ключ — день недели как date.weekday() (0=Пн … 6=Вс), значение — [open, close]
"HH:MM". Один интервал на день в v1 (сплит-смены — позже). Пустой/отсутствующий
день = закрыто. Время трактуем в локальной таймзоне проекта.
"""

from datetime import datetime, time

WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _parse_hhmm(value) -> time | None:
    try:
        h, m = (int(x) for x in str(value).split(":"))
        return time(h, m)
    except (TypeError, ValueError):
        return None


def normalize(raw) -> dict:
    """Привести к {weekday_str: [open, close]} с валидным временем и open<close."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for wd in range(7):
        rng = raw.get(str(wd)) or raw.get(wd)
        if not isinstance(rng, (list, tuple)) or len(rng) != 2:
            continue
        o, c = _parse_hhmm(rng[0]), _parse_hhmm(rng[1])
        if o and c and o < c:
            out[str(wd)] = [f"{o.hour:02d}:{o.minute:02d}", f"{c.hour:02d}:{c.minute:02d}"]
    return out


def open_status(structured, now: datetime) -> dict | None:
    """Статус на момент now (aware/naive local). None — часы не заданы.

    → {"open": bool, "until": "HH:MM"|None, "next": ("Mo","HH:MM")|None}.
    """
    hours = normalize(structured)
    if not hours:
        return None
    today = hours.get(str(now.weekday()))
    if today:
        o, c = _parse_hhmm(today[0]), _parse_hhmm(today[1])
        if o <= now.time() < c:
            return {"open": True, "until": today[1], "next": None}
    # Закрыто сейчас — ищем ближайшее открытие в пределах недели.
    for delta in range(7):
        wd = (now.weekday() + delta) % 7
        rng = hours.get(str(wd))
        if not rng:
            continue
        o = _parse_hhmm(rng[0])
        if delta == 0 and now.time() >= o:
            continue  # сегодня уже открывались/закрылись — ищем дальше
        return {"open": False, "until": None, "next": (WEEKDAYS_DE[wd], rng[0])}
    return {"open": False, "until": None, "next": None}


def today_label(structured, now: datetime) -> str:
    """Сегодняшние часы строкой «09:00–18:00» или «Geschlossen»."""
    hours = normalize(structured)
    rng = hours.get(str(now.weekday()))
    return f"{rng[0]}–{rng[1]}" if rng else "Geschlossen"
