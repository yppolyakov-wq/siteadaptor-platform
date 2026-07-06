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

# Для TLS автоматически авторизуются только корень (+www); поддомены — СТРОГО
# по таблице Domain (инцидент 2026-07-06: blanket-allow *.siteadaptor.de давал
# сканерам выжигать квоту Let's Encrypt (50 серт/нед) мусорными хостами вида
# www.1www.whm...baeckerei-test.siteadaptor.de — «refused to connect» у всех
# НОВЫХ легитимных поддоменов до конца окна лимита).
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

    Разрешаем корень (+www) и ТОЛЬКО существующие домены из таблицы Domain —
    субдомены тенантов, порталы и custom-домены заводят свою строку Domain при
    создании, так что легитимным хостам blanket-allow не нужен. Иначе 404 →
    Caddy не выпустит сертификат (и квота Let's Encrypt не тратится на мусор).
    """
    domain = (request.GET.get("domain") or "").lower().strip()
    if domain in (_ALLOWED_TLS_ROOT, f"www.{_ALLOWED_TLS_ROOT}"):
        return HttpResponse("ok")

    from apps.tenants.models import Domain

    if Domain.objects.filter(domain=domain).exists():
        return HttpResponse("ok")
    return HttpResponse(status=404)
