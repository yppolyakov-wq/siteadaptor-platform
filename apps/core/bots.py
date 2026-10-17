"""В5: «это не человек» — для счётчиков, а не для защиты.

Пустой UA, известные роботы/превью/библиотеки и предзагрузка браузера не считаются
посещением. Ошибка в сторону «бот» безопаснее: недосчёт честнее накрутки.
"""

from __future__ import annotations

_BOT_MARKERS = (
    "bot",
    "crawl",
    "spider",
    "slurp",
    "preview",
    "headless",
    "facebookexternalhit",
    "python-requests",
    "python-urllib",
    "aiohttp",
    "curl",
    "wget",
    "httpclient",
    "okhttp",
    "monitor",
    "uptime",
    "lighthouse",
    "pingdom",
)


def is_bot(request) -> bool:
    meta = request.META
    ua = (meta.get("HTTP_USER_AGENT") or "").strip().lower()
    if not ua:
        return True
    if any(marker in ua for marker in _BOT_MARKERS):
        return True
    purpose = f"{meta.get('HTTP_SEC_PURPOSE', '')} {meta.get('HTTP_PURPOSE', '')}".lower()
    return "prefetch" in purpose or "prerender" in purpose
