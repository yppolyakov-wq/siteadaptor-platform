"""Кэш публичных анонимных страниц (P2.2b) — выдача агрегатора/порталов.

Кэшируем целиком отрендеренный HTML только для GET без query-параметров
(первая страница выдачи — практически весь SEO- и пользовательский трафик;
cursor/utm/ch — мимо кэша). Ключ — host+path+язык (один и тот же path на
разных портальных хостах — разные страницы; язык приходит из cookie).

TTL — settings.PUBLIC_PAGE_CACHE_TTL (сек); 0 выключает кэш полностью (так
работают тесты вьюх — иначе они загрязняли бы друг друга отрендеренным HTML).
Инвалидация — только по TTL: выдача терпит минутную задержку, листинги и так
материализуются асинхронно. Fail-open: недоступный Redis не валит страницу.
"""

from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def cache_public_page(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        ttl = getattr(settings, "PUBLIC_PAGE_CACHE_TTL", 0)
        if not ttl or request.method != "GET" or request.GET:
            return view(request, *args, **kwargs)

        lang = getattr(request, "LANGUAGE_CODE", "de")
        key = f"pubpage:{request.get_host()}:{request.path}:{lang}"
        try:
            hit = cache.get(key)
        except Exception:  # noqa: BLE001 — кэш недоступен: рендерим как обычно
            hit = None
        if hit is not None:
            content, content_type = hit
            return HttpResponse(content, content_type=content_type)

        response = view(request, *args, **kwargs)
        if response.status_code == 200 and not response.streaming:
            try:
                cache.set(key, (response.content, response.get("Content-Type", "text/html")), ttl)
            except Exception:  # noqa: BLE001
                pass
        return response

    return wrapped
