"""Маршрут тура по дням (MT-1) — канон хранения, видимость, срезы для рендера.

`Tour.itinerary` — JSON-список остановок. Одна остановка = один пункт дня:
`{day, time_from, time_to, title, text, km, overnight, lat, lng, visibility}`.
Времена дают хронометраж («09:00 выезд → 13:00 перевал»), `km` — дневной
километраж, `overnight` — место ночёвки, `lat/lng` — точка на карте.

**Видимость — сквозное требование владельца:** маршрут разрабатывает гид, и он
же решает, что показывать. Поэтому видимость живёт НА КАЖДОЙ остановке и по
умолчанию `private`: гид строит полный маршрут для себя, затем точечно открывает
ключевые места публике и/или участникам. Фильтрация — только здесь, на сервере
(`visible()`); шаблоны получают уже отфильтрованный список, чтобы закрытая точка
не могла утечь в HTML.
"""

from django.utils.translation import gettext_lazy as _

# --- видимость --------------------------------------------------------------
PRIVATE = "private"
PARTICIPANTS = "participants"
PUBLIC = "public"

VISIBILITIES = (PRIVATE, PARTICIPANTS, PUBLIC)
DEFAULT_VISIBILITY = PRIVATE

VISIBILITY_LABELS = {
    PRIVATE: _("Nur für mich"),
    PARTICIPANTS: _("Für Teilnehmer"),
    PUBLIC: _("Öffentlich"),
}

# Аудитории и то, какие уровни каждая имеет право видеть.
OWNER = "owner"
PARTICIPANT = "participant"
GUEST = "public"

_ALLOWED = {
    OWNER: frozenset(VISIBILITIES),
    PARTICIPANT: frozenset({PARTICIPANTS, PUBLIC}),
    GUEST: frozenset({PUBLIC}),
}

_MAX_STOPS = 80
_MAX_DAY = 120


def visibility_choices() -> list[tuple[str, str]]:
    """(value, label) для селекта формы кабинета — в порядке «закрытости»."""
    return [(v, VISIBILITY_LABELS[v]) for v in VISIBILITIES]


# --- нормализация -----------------------------------------------------------
def _s(value, limit=2000) -> str:
    return str(value or "").strip()[:limit]


def _int(value, maximum: int) -> int:
    """Неотрицательное целое из мусора, с потолком; иначе 0."""
    try:
        return max(0, min(maximum, int(float(str(value).strip().replace(",", ".")))))
    except (TypeError, ValueError):
        return 0


def _time(value) -> str:
    """«9:5» / «09:05» → «09:05»; мусор → ''. Хранение строкой — время без даты."""
    raw = _s(value, 10).replace(".", ":")
    if not raw:
        return ""
    parts = raw.split(":")
    if len(parts) != 2:
        return ""
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return ""
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return ""
    return f"{hour:02d}:{minute:02d}"


def _coord(value, limit: float) -> str:
    """Координата строкой (пустая = точки на карте нет). Вне диапазона → ''."""
    raw = _s(value, 32).replace(",", ".")
    if not raw:
        return ""
    try:
        num = float(raw)
    except (TypeError, ValueError):
        return ""
    if not (-limit <= num <= limit):
        return ""
    return f"{num:.6f}".rstrip("0").rstrip(".")


def _visibility(value) -> str:
    value = _s(value, 20)
    return value if value in VISIBILITIES else DEFAULT_VISIBILITY


def normalize(raw) -> list[dict]:
    """Привести `Tour.itinerary` к канону (безопасно к мусору).

    Остановка без названия и без текста отбрасывается — пустые строки редактора
    не должны копиться в JSON.
    """
    out: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        stop = {
            "day": _int(item.get("day"), _MAX_DAY) or 1,
            "time_from": _time(item.get("time_from")),
            "time_to": _time(item.get("time_to")),
            "title": _s(item.get("title"), 200),
            "text": _s(item.get("text"), 2000),
            "km": _int(item.get("km"), 10000),
            "overnight": _s(item.get("overnight"), 200),
            "lat": _coord(item.get("lat"), 90),
            "lng": _coord(item.get("lng"), 180),
            "visibility": _visibility(item.get("visibility")),
        }
        if stop["title"] or stop["text"] or stop["overnight"]:
            out.append(stop)
        if len(out) >= _MAX_STOPS:
            break
    out.sort(key=lambda s: (s["day"], s["time_from"] or "99:99"))
    return out


# --- срезы для рендера ------------------------------------------------------
def visible(raw, audience: str) -> list[dict]:
    """Остановки, которые вправе видеть `audience` (owner/participant/public).

    Неизвестная аудитория трактуется как посторонний (fail-closed).
    """
    allowed = _ALLOWED.get(audience, _ALLOWED[GUEST])
    return [s for s in normalize(raw) if s["visibility"] in allowed]


def hidden_count(raw, audience: str) -> int:
    """Сколько остановок скрыто от аудитории — для честной плашки на витрине."""
    return len(normalize(raw)) - len(visible(raw, audience))


def by_day(stops) -> list[dict]:
    """Сгруппировать остановки в дни: [{day, stops, km, overnight}].

    Принимает УЖЕ отфильтрованный список (см. `visible`), поэтому день,
    целиком состоящий из закрытых точек, просто не появится.
    """
    days: dict[int, dict] = {}
    for stop in stops:
        day = days.setdefault(
            stop["day"], {"day": stop["day"], "stops": [], "km": 0, "overnight": ""}
        )
        day["stops"].append(stop)
        day["km"] += stop["km"]
        if stop["overnight"]:
            day["overnight"] = stop["overnight"]
    return [days[key] for key in sorted(days)]


def map_points(stops) -> list[dict]:
    """Точки с координатами для Leaflet — в порядке маршрута."""
    return [
        {
            "lat": float(s["lat"]),
            "lng": float(s["lng"]),
            "title": s["title"] or s["overnight"],
            "day": s["day"],
        }
        for s in stops
        if s["lat"] and s["lng"]
    ]


def total_km(stops) -> int:
    return sum(s["km"] for s in stops)


def day_count(stops) -> int:
    return len({s["day"] for s in stops})


# --- форма кабинета ---------------------------------------------------------
POST_PREFIX = "it_"
_POST_FIELDS = (
    "day",
    "time_from",
    "time_to",
    "title",
    "text",
    "km",
    "overnight",
    "lat",
    "lng",
    "visibility",
)


def from_post(post) -> list[dict]:
    """Собрать маршрут из построчного редактора кабинета.

    Строки нумерованы (`it_title_0`, `it_title_1`, …); пустые строки отбросит
    `normalize`, поэтому редактор может отдавать запас пустых слотов.
    """
    rows: dict[int, dict] = {}
    for key in post:
        if not key.startswith(POST_PREFIX):
            continue
        name, _, index = key[len(POST_PREFIX) :].rpartition("_")
        if name not in _POST_FIELDS or not index.isdigit():
            continue
        rows.setdefault(int(index), {})[name] = post.get(key)
    return normalize([rows[i] for i in sorted(rows)])
