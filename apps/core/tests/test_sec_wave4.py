"""SEC волна 4 (решение владельца 2026-11-02): рубильник, CSP, CSRF-кука."""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import CSPReportOnlyMiddleware, SuspendedTenantMiddleware


def _req(path, *, active, user=None):
    req = RequestFactory().get(path)
    req.tenant = SimpleNamespace(schema_name="biz", is_active=active, name="Krume")
    req.user = user or AnonymousUser()
    return req


def _ok(request):
    return HttpResponse("storefront", content_type="text/html")


@pytest.mark.parametrize("path", ["/", "/sortiment/", "/p/x/"])
def test_suspended_tenant_storefront_is_410(path):
    resp = SuspendedTenantMiddleware(_ok)(_req(path, active=False))
    assert resp.status_code == 410 and b"storefront" not in resp.content


@pytest.mark.parametrize(
    "path", ["/dashboard/", "/dashboard/billing/", "/accounts/login/", "/tg/x/"]
)
def test_suspended_tenant_keeps_cabinet_login_and_hooks(path):
    assert SuspendedTenantMiddleware(_ok)(_req(path, active=False)).status_code == 200


def test_active_tenant_and_member_preview_unaffected():
    assert SuspendedTenantMiddleware(_ok)(_req("/", active=True)).status_code == 200
    member = SimpleNamespace(is_authenticated=True)
    assert SuspendedTenantMiddleware(_ok)(_req("/", active=False, user=member)).status_code == 200


def test_csp_report_only_header_on_html(settings):
    settings.CSP_REPORT_ONLY = "default-src 'self'"
    settings.CSP_REPORT_URI = "https://sentry.example/csp"
    resp = CSPReportOnlyMiddleware(_ok)(RequestFactory().get("/"))
    assert resp["Content-Security-Policy-Report-Only"] == (
        "default-src 'self'; report-uri https://sentry.example/csp"
    )
    assert "Content-Security-Policy" not in resp  # не блокирует
    plain = CSPReportOnlyMiddleware(lambda r: HttpResponse("{}", content_type="application/json"))
    assert "Content-Security-Policy-Report-Only" not in plain(RequestFactory().get("/"))


def test_production_csrf_cookie_is_host_prefixed_and_no_subdomain_wildcard():
    import importlib
    import os

    os.environ.setdefault("SECRET_KEY", "x" * 50)
    from config.settings import production

    importlib.reload(production)
    assert production.CSRF_COOKIE_NAME == "__Host-csrftoken"
    assert production.CSRF_COOKIE_SECURE is True
    assert "https://*.siteadaptor.de" not in production.CSRF_TRUSTED_ORIGINS
