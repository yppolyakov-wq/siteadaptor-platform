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


def _sf_version(schema: str) -> int:
    """SE-5a: текущая версия кэша витрины тенанта (часть ключа). Недоступный Redis → 0."""
    try:
        return cache.get(f"sfver:{schema}") or 0
    except Exception:  # noqa: BLE001
        return 0


def bump_storefront_cache(schema: str) -> None:
    """SE-5a: сброс кэша витрины тенанта при публикации — инкремент версии в ключе.
    Старые ключи осиротевают и истекают по TTL (без delete_pattern). Fail-open."""
    try:
        cache.set(f"sfver:{schema}", _sf_version(schema) + 1, None)
    except Exception:  # noqa: BLE001
        pass


def _cacheable(request, response) -> bool:
    """P0-1 (аудит 2026-09-03 §9.3): в ОБЩИЙ кэш нельзя класть персональное.

    Раньше в кэш попадало тело с `{% csrf_token %}`, а на хите отдавался голый
    HttpResponse без Set-Cookie — в течение TTL все анонимы получали токен
    ПЕРВОГО посетителя без своей куки, и любой POST давал 403 (воспроизведено
    пробником). Два признака персонального ответа:
    * `CSRF_COOKIE_NEEDS_UPDATE` — Django 5.1 ставит его в `get_token()` всегда
      (`csrf.py:111`), то есть страница использовала токен; проверяем ДО
      CsrfViewMiddleware.process_response, который флаг сбрасывает;
    * `response.cookies` — вьюха выставила куку (сессия/корзина/согласие).
    Цена: страницы с формами перестают кэшироваться для анонимов (состояние до
    SE-5a). Возврат кэша на них — токен вне тела (JS из куки), отдельный шаг.
    """
    if response.status_code != 200 or getattr(response, "streaming", False):
        return False
    if response.cookies:
        return False
    meta = getattr(request, "META", None) or {}
    return not meta.get("CSRF_COOKIE_NEEDS_UPDATE")


def _pack(response) -> tuple:
    # Vary из вьюхи (напр. Accept-Language) обязан пережить хит: без него
    # промежуточные кэши склеили бы варианты. Middleware-Vary патчится позже
    # и на хит-ответ ложится сам.
    return (response.content, response.get("Content-Type", "text/html"), response.get("Vary", ""))


def _unpack(hit) -> HttpResponse:
    content, content_type, vary = hit
    response = HttpResponse(content, content_type=content_type)
    if vary:
        response["Vary"] = vary
    return response


def cache_storefront_page(view):
    """SE-5a: кэш HTML витрины тенанта. Как `cache_public_page`, но ключ включает
    версию `site_config` тенанта → публикация (bump_storefront_cache) мгновенно
    инвалидирует выдачу, а не только по TTL. Мимо кэша: непустая сессия (владелец
    залогинен / есть корзина), query-параметры (?preview=1, ?tisch=N), не-GET,
    и — P0-1 — любой ответ с CSRF-токеном или Set-Cookie (см. `_cacheable`)."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        ttl = getattr(settings, "PUBLIC_PAGE_CACHE_TTL", 0)
        has_session = hasattr(request, "session") and not request.session.is_empty()
        schema = getattr(getattr(request, "tenant", None), "schema_name", None)
        if not ttl or request.method != "GET" or request.GET or has_session or not schema:
            return view(request, *args, **kwargs)

        lang = getattr(request, "LANGUAGE_CODE", "de")
        # sfpage2: формат записи сменился (кортеж из трёх) — старые ключи
        # осиротеют по TTL, смешивать форматы нельзя.
        key = f"sfpage2:{schema}:{request.path}:{lang}:v{_sf_version(schema)}"
        try:
            hit = cache.get(key)
        except Exception:  # noqa: BLE001
            hit = None
        if hit is not None:
            return _unpack(hit)

        response = view(request, *args, **kwargs)
        if _cacheable(request, response):
            try:
                cache.set(key, _pack(response), ttl)
            except Exception:  # noqa: BLE001
                pass
        return response

    return wrapped


def cache_public_page(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        ttl = getattr(settings, "PUBLIC_PAGE_CACHE_TTL", 0)
        # Непустая сессия = персонализированная страница (вход клиента портала,
        # P2.3) — мимо кэша; анонимы и краулеры сессии не имеют.
        has_session = hasattr(request, "session") and not request.session.is_empty()
        if not ttl or request.method != "GET" or request.GET or has_session:
            return view(request, *args, **kwargs)

        lang = getattr(request, "LANGUAGE_CODE", "de")
        key = f"pubpage2:{request.get_host()}:{request.path}:{lang}"
        try:
            hit = cache.get(key)
        except Exception:  # noqa: BLE001 — кэш недоступен: рендерим как обычно
            hit = None
        if hit is not None:
            return _unpack(hit)

        response = view(request, *args, **kwargs)
        if _cacheable(request, response):
            try:
                cache.set(key, _pack(response), ttl)
            except Exception:  # noqa: BLE001
                pass
        return response

    return wrapped
