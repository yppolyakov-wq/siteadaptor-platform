"""iCal экспорт/импорт для Übernachtung (A5b) — без внешних зависимостей.

Экспорт: фид занятости юнита (наши брони + блоки) — Booking.com/Airbnb/Google
импортируют его и блокируют даты. Импорт: тянем iCal внешней площадки и заводим
UnitBlock на занятые диапазоны (анти-двойная-бронь). Формат — простой all-day
VEVENT (DTSTART/DTEND VALUE=DATE), что и используют площадки.
"""

from datetime import UTC, date, datetime

_DT = "%Y%m%d"


def _fold_unfold(text: str) -> list[str]:
    """Снять folding (строки-продолжения начинаются с пробела/таба)."""
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    head = value.split("T", 1)[0]  # дата или datetime → берём дату
    try:
        return datetime.strptime(head[:8], _DT).date()
    except ValueError:
        return None


def parse_events(text: str) -> list[tuple[str, date, date]]:
    """[(uid, start, end)] из VEVENT. end (DTEND) — день выезда (эксклюзивно)."""
    events: list[tuple[str, date, date]] = []
    uid = start = end = None
    in_event = False
    for line in _fold_unfold(text or ""):
        key, _, val = line.partition(":")
        name = key.split(";", 1)[0].upper().strip()
        if name == "BEGIN" and val.strip().upper() == "VEVENT":
            in_event, uid, start, end = True, "", None, None
        elif name == "END" and val.strip().upper() == "VEVENT":
            if start and end:
                events.append((uid or "", start, end))
            in_event = False
        elif in_event:
            if name == "UID":
                uid = val.strip()
            elif name == "DTSTART":
                start = _parse_date(val)
            elif name == "DTEND":
                end = _parse_date(val)
    return events


def build_feed(unit, bookings, blocks, *, host: str = "siteadaptor.de") -> str:
    """iCal-текст занятости юнита: брони (эксклюзивный DTEND) + блоки (включительно→+1)."""
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SiteAdaptor//Stays//DE",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{unit.name}",
    ]

    def event(uid, start, end, summary):
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}@{host}",
                f"DTSTAMP:{now}",
                f"DTSTART;VALUE=DATE:{start.strftime(_DT)}",
                f"DTEND;VALUE=DATE:{end.strftime(_DT)}",
                f"SUMMARY:{summary}",
                "END:VEVENT",
            ]
        )

    for b in bookings:
        event(b.reference_code, b.arrival, b.departure, f"Belegt ({b.reference_code})")
    for bl in blocks:
        from datetime import timedelta

        # блок включителен по end_date → DTEND эксклюзивно = end_date + 1
        event(f"block-{bl.pk}", bl.start_date, bl.end_date + timedelta(days=1), "Blockiert")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
