"""Health / readiness endpoints.

`liveness`  — процесс жив (для рестарт-политики контейнера / простого пинга).
`readiness` — зависимости доступны (БД + кэш/Redis). Используется деплоем и
балансировщиком: при недоступной БД отдаёт 503, чтобы трафик не шёл на битый
инстанс.

`verify_domain` — endpoint для Caddy on-demand TLS (Phase 2, custom-домены):
Caddy спрашивает, можно ли выпускать сертификат для домена.
"""

from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse

# Поддомены этого базового домена авторизуются для TLS автоматически.
_ALLOWED_TLS_SUFFIX = ".siteadaptor.de"
_ALLOWED_TLS_ROOT = "siteadaptor.de"


def liveness(_request):
    return JsonResponse({"status": "ok"})


def readiness(_request):
    checks = {}
    healthy = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["db"] = "ok"
    except Exception:  # noqa: BLE001
        checks["db"] = "error"
        healthy = False

    try:
        cache.set("health:ping", "1", 5)
        checks["cache"] = "ok" if cache.get("health:ping") == "1" else "error"
        healthy = healthy and checks["cache"] == "ok"
    except Exception:  # noqa: BLE001
        checks["cache"] = "error"
        healthy = False

    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=200 if healthy else 503,
    )


def verify_domain(request):
    """Phase 2: авторизация домена для Caddy on-demand TLS.

    Разрешаем поддомены основного домена и любые домены из таблицы Domain
    (custom-домены арендаторов/порталов). Иначе 404 → Caddy не выпустит сертификат.
    """
    domain = (request.GET.get("domain") or "").lower().strip()
    if domain == _ALLOWED_TLS_ROOT or domain.endswith(_ALLOWED_TLS_SUFFIX):
        return HttpResponse("ok")

    from apps.tenants.models import Domain

    if Domain.objects.filter(domain=domain).exists():
        return HttpResponse("ok")
    return HttpResponse(status=404)
