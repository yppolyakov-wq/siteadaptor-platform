"""UX-D D1: шторка кабинета — серверная половина.

Шторка (`templates/core/_drawer.html` + раздел `cabinet.js`) подгружает фрагменты
существующих страниц (`?box=1`) и отправляет их формы через fetch с заголовком
`X-Sf-Drawer: 1`. Вьюхи остаются обычными: делают своё и отвечают редиректом с
`messages`. `drawer_aware` превращает такой редирект в JSON — шторка показывает
сообщение у себя и обновляет страницу под собой без перезагрузки. Без JS (нет
заголовка) ответ не меняется.
"""

from __future__ import annotations

import json
from functools import wraps
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.http import JsonResponse, QueryDict
from django.utils.cache import patch_vary_headers

from apps.core.owner_login import safe_next

HEADER = "HTTP_X_SF_DRAWER"

# Сообщения в заголовке X-Sf-Messages: не больше стольких и не длиннее — заголовок
# сверх лимита прокси дал бы 502 на уже выполненном действии (ECC-ревью D1).
MAX_HEADER_MESSAGES = 10
MAX_MESSAGE_CHARS = 300


# Параметры шторки в адресе страницы: убираются при перерисовке областей и возврате.
# `buchung` — наследие панели брони (редирект после действия без JS).
DRAWER_PARAMS = ("box", "drawer", "buchung")


def is_drawer(request) -> bool:
    """Запрос пришёл из шторки (fetch с заголовком `X-Sf-Drawer`) — и GET, и POST.

    Шторка НЕ шлёт `X-Requested-With`: на него часть вьюх отвечает 204/409/HTML
    (перетаскивание, доска) — действие прошло бы, а шторка показала бы ошибку."""
    return request.META.get(HEADER) == "1"


def is_box(request) -> bool:
    """Запрошен фрагмент для шторки (`?box=1` — наследие, или заголовок шторки на GET)."""
    return request.GET.get("box") == "1" or (request.method == "GET" and is_drawer(request))


def open_after(request, url: str) -> None:
    """После действия открыть в шторке другой объект (созданную бронь и т.п.)."""
    request._drawer_open = url


def drawer_next(request, default: str) -> str:
    """GET-`next` фрагмента (куда вернуть после действия) — только локальный путь."""
    return safe_next(request, request.GET.get("next") or "", default=default)


def with_param(url: str, key: str, value) -> str:
    """Добавить/заменить параметр в URL без ручной склейки строк.

    D1 (разведка): `f"{back}&buchung={pk}"` при `back` без `?` давал
    `/dashboard/stays/buchung/<pk>/&buchung=…` → 404 после «Als bezahlt markieren»."""
    parts = urlsplit(url)
    query = QueryDict(parts.query, mutable=True)
    query[key] = str(value)
    return urlunsplit(parts._replace(query=query.urlencode()))


def without_params(url: str, *keys: str) -> str:
    """URL без служебных параметров (`box`, `buchung`) — адрес для перерисовки."""
    parts = urlsplit(url)
    query = QueryDict(parts.query, mutable=True)
    for key in keys:
        query.pop(key, None)
    return urlunsplit(parts._replace(query=urlencode(sorted(query.lists()), doseq=True)))


def fragment(response):
    """Фрагмент шторки: метка `X-Sf-Fragment` (без неё клиент не вставит ответ — так
    в шторку никогда не попадёт целая страница или страница входа), без кэша
    (браузер/прокси/назад-вперёд показали бы голый кусок страницы)."""
    response["X-Sf-Fragment"] = "1"
    response["Cache-Control"] = "private, no-store"
    patch_vary_headers(response, ("X-Sf-Drawer",))
    return response


def drawer_aware(view):
    """Ответы вьюхи для запросов из шторки (без заголовка — ответ прежний).

    - редирект → JSON `{ok, messages, navigate, location, open}`: `ok` ложно при ошибке
      среди сообщений; `navigate` — редирект ведёт на ДРУГУЮ страницу, чем `next`
      формы (счёт, полная карточка) — клиент переходит; `open` — `open_after()`;
    - прочие ответы (фрагмент с ошибками формы, 403, 404, 409) проходят как есть, но
      сообщения сессии забираются в заголовок `X-Sf-Messages` — не всплывут позже.

    Должен стоять ВНУТРЕННИМ декоратором (под login_required/require_POST)."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        if not is_drawer(request):
            return response
        drained = list(messages.get_messages(request))
        items = [{"level": m.level_tag, "text": str(m)} for m in drained]
        if response.status_code not in (301, 302, 303):
            if items:
                short = [
                    {"level": m["level"], "text": m["text"][:MAX_MESSAGE_CHARS]}
                    for m in items[-MAX_HEADER_MESSAGES:]
                ]
                response["X-Sf-Messages"] = json.dumps(short, ensure_ascii=True)
            return response
        # `next` сначала через safe_next: сырой `//[` ронял urlsplit (ValueError) → 500
        # на действии, которое уже записалось (ECC-ревью D1, класс STU-7).
        nxt = safe_next(request, (request.POST.get("next") or "").strip(), default="")
        location = safe_next(request, response.url, default="")
        navigate = bool(nxt and location) and urlsplit(nxt).path != urlsplit(location).path
        payload = {
            "ok": not any(m["level"] == "error" for m in items),
            "messages": items,
            "navigate": navigate,
            "open": getattr(request, "_drawer_open", ""),
        }
        if navigate:
            payload["location"] = location
            # браузер уходит на другую страницу — сообщения показывает она (иначе отказ
            # «оплаченную бронь не удалить» пропадал бы молча)
            for m in drained:
                messages.add_message(request, m.level, m.message, extra_tags=m.extra_tags)
        return JsonResponse(payload)

    wrapped.drawer_aware = True
    return wrapped
