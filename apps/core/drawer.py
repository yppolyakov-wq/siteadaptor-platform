"""UX-D D1: шторка кабинета — серверная половина.

Шторка (`templates/core/_drawer.html` + раздел `cabinet.js`) подгружает фрагменты
существующих страниц (`?box=1`) и отправляет их формы через fetch с заголовком
`X-Sf-Drawer: 1`. Вьюхи остаются обычными: делают своё и отвечают редиректом с
`messages`. `drawer_aware` превращает такой редирект в JSON — шторка показывает
сообщение у себя и обновляет страницу под собой без перезагрузки. Без JS (нет
заголовка) ответ не меняется.
"""

from __future__ import annotations

from functools import wraps
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.http import JsonResponse, QueryDict

from apps.core.owner_login import safe_next

HEADER = "HTTP_X_SF_DRAWER"


def is_drawer(request) -> bool:
    """Запрос пришёл из шторки (fetch с заголовком `X-Sf-Drawer`)."""
    return request.META.get(HEADER) == "1"


def is_box(request) -> bool:
    """Запрошен фрагмент для шторки (`?box=1`)."""
    return request.GET.get("box") == "1"


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
    """Фрагмент шторки: не кэшировать (браузер/прокси/назад-вперёд показали бы голый
    кусок страницы) и различать по заголовку запроса."""
    response["Cache-Control"] = "private, no-store"
    response["Vary"] = "X-Requested-With"
    return response


def drawer_aware(view):
    """Редирект + messages → JSON `{ok, messages}` для запросов из шторки.

    `ok` ложно, если среди сообщений есть ошибка. Прочие ответы (403 прав, 404, 409)
    проходят как есть — шторка покажет общий текст ошибки."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        if not is_drawer(request) or response.status_code not in (301, 302, 303):
            return response
        items = [{"level": m.level_tag, "text": str(m)} for m in messages.get_messages(request)]
        ok = not any(m["level"] == "error" for m in items)
        return JsonResponse({"ok": ok, "messages": items})

    return wrapped
