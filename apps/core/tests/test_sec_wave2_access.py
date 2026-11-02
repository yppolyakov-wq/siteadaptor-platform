"""SEC волна 2 (решение владельца 2026-11-02): доступ к админке платформы."""

import uuid
from types import SimpleNamespace

import pytest
from django.core.cache.backends.locmem import LocMemCache
from django.http import Http404, HttpResponse
from django.test import RequestFactory

from apps.core.middleware import AdminGuardMiddleware


@pytest.fixture(autouse=True)
def _rl(monkeypatch):
    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-{uuid.uuid4()}", {}))


def _call(path="/admin/login/", method="post", ip="10.7.7.7", schema="public"):
    req = getattr(RequestFactory(), method)(path, REMOTE_ADDR=ip)
    req.tenant = SimpleNamespace(schema_name=schema)
    return AdminGuardMiddleware(lambda r: HttpResponse("ok"))(req)


def test_admin_login_attempts_are_limited():
    codes = [_call().status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_admin_limit_ignores_tenant_hosts():
    assert all(_call(schema="biz").status_code == 200 for _ in range(12))


def test_admin_outside_allowed_networks_is_404(settings):
    settings.ADMIN_ALLOWED_NETWORKS = ["192.0.2.0/24"]
    with pytest.raises(Http404):
        _call(method="get", path="/admin/", ip="10.7.7.7")
    assert _call(method="get", path="/admin/", ip="192.0.2.15").status_code == 200


# --- SEC-A4: секрет заголовка вебхука ≠ секрет пути ---------------------------------


def test_webhook_header_secret_differs_from_path_and_is_accepted(settings):
    from apps.telegram import services

    path = "p" * 32
    header = services.header_secret(path)
    assert header != path and len(header) >= 24
    assert services.header_ok(header, path)
    settings.TELEGRAM_WEBHOOK_LEGACY_HEADER = False
    assert not services.header_ok(path, path)  # знание пути (логи 404) больше не пускает
    assert not services.header_ok("", path)
