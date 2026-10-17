"""В5 V5-5: откуда пришла сделка — канал (`ch`) и карточка каталога города (`cl`).

Решение владельца (план v5-portal-analytics §13): без новых cookie. Канал едет
скрытыми полями форм (тег `portal_attribution_fields`), на один переход — по
Referer того же сайта, через многошаговую корзину — в УЖЕ необходимой сессии
корзины (`remember`). Окно — тот же визит (`VISIT_HOURS`). Посадка с `?ch=` сессию
не создаёт (раньше `_capture_channel` создавал — TTDSG §25).

Канал — свободный слаг (T-8.6: flyer/instagram/…); в статистику каталога города
попадают только каналы города (`portal`, `entdecken`) — решает потребитель.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

SESSION_KEY = "src_attr"
VISIT_HOURS = 4
_CH_RE = re.compile(r"[^a-z0-9_-]+")
_CL_RE = re.compile(r"^\d{1,10}$")
# Внутренние метки `source_channel`, которые меняют поведение сделки (`quote` = смета,
# `promo` = бейдж «Aktion», …). Снаружи их принимать нельзя (ревью V5-5a).
RESERVED_CHANNELS = frozenset(
    {"quote", "promo", "manual", "offer", "anprobe", "retreat", "booking", "booking_com"}
)


@dataclass(frozen=True)
class Attribution:
    channel: str = ""
    listing: int | None = None

    def __bool__(self) -> bool:
        return bool(self.channel)


def clean_channel(raw) -> str:
    """`Instagram Story` → `instagram-story`; мусор → "". Пустое остаётся пустым."""
    value = _CH_RE.sub("-", str(raw or "").strip().lower()).strip("-")[:30]
    return "" if value in RESERVED_CHANNELS else value


def clean_listing(raw) -> int | None:
    value = str(raw or "").strip()
    if not _CL_RE.match(value):
        return None
    number = int(value)
    return number or None


def _from(data) -> Attribution:
    channel = clean_channel(data.get("ch"))
    if not channel:
        return Attribution()
    return Attribution(channel, clean_listing(data.get("cl")))


def _from_referer(request) -> Attribution:
    try:
        ref = urlsplit(request.META.get("HTTP_REFERER", ""))
        if not ref.query or ref.netloc != request.get_host():
            return Attribution()
        query = {k: v[0] for k, v in parse_qs(ref.query).items() if v}
        return _from(query)
    except Exception:  # noqa: BLE001 — кривой Referer = нет атрибуции
        return Attribution()


def _from_session(request) -> Attribution:
    session = getattr(request, "session", None)
    if session is None:
        return Attribution()
    try:
        data = session.get(SESSION_KEY)  # чтение не помечает сессию изменённой
    except Exception:  # noqa: BLE001
        return Attribution()
    if not isinstance(data, dict):
        return Attribution()
    try:
        fresh = time.time() - float(data.get("at") or 0) <= VISIT_HOURS * 3600
    except (TypeError, ValueError):
        fresh = False
    return _from(data) if fresh else Attribution()


def resolve(request) -> Attribution:
    """POST → легаси POST `channel` → GET → Referer этого сайта → сессия корзины."""
    post = getattr(request, "POST", {}) if request.method == "POST" else {}
    found = _from(post)
    if found:
        return found
    legacy = clean_channel(post.get("channel"))  # формы, открытые до деплоя V5-5
    if legacy:
        return Attribution(legacy)
    for source in (_from(request.GET), _from_referer(request), _from_session(request)):
        if source:
            return source
    return Attribution()


def context(request) -> dict:
    """Для шаблона: что нести дальше скрытыми полями (`attr` в контексте вьюхи)."""
    found = resolve(request)
    return {"ch": found.channel, "cl": found.listing or ""} if found else {}


def query_tail(request) -> list[tuple[str, str]]:
    """Пары `ch`/`cl` для ссылок многошаговых путей (выбор слота, дат)."""
    found = resolve(request)
    if not found:
        return []
    pairs = [("ch", found.channel)]
    if found.listing:
        pairs.append(("cl", str(found.listing)))
    return pairs


def remember(request) -> None:
    """Запомнить атрибуцию в сессии корзины. Зовётся ТОЛЬКО там, где сессия и так
    пишется (добавление в корзину): новой cookie атрибуция не создаёт."""
    session = getattr(request, "session", None)
    found = resolve(request)
    if session is None or not found:
        return
    if found == _from_session(request):
        return  # та же атрибуция из сессии: не продлеваем окно визита каждым добавлением
    session[SESSION_KEY] = {"ch": found.channel, "cl": found.listing or "", "at": time.time()}


def forget(request) -> None:
    session = getattr(request, "session", None)
    if session is not None and SESSION_KEY in session:
        del session[SESSION_KEY]
