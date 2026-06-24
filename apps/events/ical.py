"""R3b: iCal (RFC 5545) экспорт событий — один .ics на событие и фид-подписка.

Без внешних зависимостей: строим VCALENDAR вручную (CRLF, экранирование текста,
UTC-таймстемпы). Используется витриной (`/veranstaltung/<pk>/ical`,
`/veranstaltung/feed.ics`) — «Zum Kalender hinzufügen» / подписка на ретриты.
"""

from datetime import UTC

_PRODID = "-//siteadaptor//retreat//DE"


def _esc(text) -> str:
    """Экранирование TEXT по RFC 5545 (запятая/точка-с-запятой/перевод строки)."""
    s = str(text or "")
    s = s.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
    return s


def _utc(value) -> str:
    """tz-aware datetime → UTC-форма YYYYMMDDTHHMMSSZ."""
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """Складывание длинных строк (75 октетов) — простая ASCII-эвристика."""
    if len(line) <= 73:
        return line
    chunks, rest = [], line
    while len(rest) > 73:
        chunks.append(rest[:73])
        rest = " " + rest[73:]
    chunks.append(rest)
    return "\r\n".join(chunks)


def _vevent(event, *, url, dtstamp, host) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{event.pk}@{host}",
        f"DTSTAMP:{_utc(dtstamp)}",
        f"DTSTART:{_utc(event.starts_at)}",
    ]
    if event.ends_at:
        lines.append(f"DTEND:{_utc(event.ends_at)}")
    lines.append(f"SUMMARY:{_esc(event.title)}")
    location = event.location or event.city
    if location:
        lines.append(f"LOCATION:{_esc(location)}")
    if event.description:
        lines.append(f"DESCRIPTION:{_esc(event.description)}")
    if url:
        lines.append(f"URL:{_esc(url)}")
    lines.append("END:VEVENT")
    return lines


def render(events, *, url_for, dtstamp, host) -> str:
    """VCALENDAR-строка для списка событий. url_for(event)->абсолютный URL (или '')."""
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{_PRODID}", "CALSCALE:GREGORIAN"]
    for event in events:
        out += _vevent(event, url=url_for(event), dtstamp=dtstamp, host=host)
    out.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in out) + "\r\n"
