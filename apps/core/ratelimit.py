"""Rate-limit публичных эндпоинтов (Hardening H8).

Атомарный счётчик в кэше (Redis INCR — без гонок между gunicorn-воркерами):
первая попытка создаёт ключ с TTL-окном, дальше инкремент без продления TTL —
окно фиксированное от первой попытки. Fail-open: недоступный кэш не блокирует
клиентов (лимит — защита от злоупотреблений, а не бизнес-инвариант; их
закрывает anti-oversell на уровне БД).
"""

from django.core.cache import cache


def client_ip(request) -> str:
    """IP клиента (за прокси — первый адрес из X-Forwarded-For, его ставит Caddy)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def hit(scope: str, ident: str, *, limit: int, window: int) -> bool:
    """Зарегистрировать попытку; True — лимит превышен (запрос надо отклонить)."""
    key = f"rl:{scope}:{ident}"
    try:
        cache.add(key, 0, window)
        count = cache.incr(key)
    except ValueError:
        # ключ истёк между add и incr — начинаем новое окно
        cache.add(key, 1, window)
        return False
    except Exception:  # noqa: BLE001 — кэш недоступен: fail-open
        return False
    return count > limit
