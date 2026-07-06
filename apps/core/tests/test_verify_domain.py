"""Caddy on-demand TLS ask: verify_domain — строгий allowlist по Domain.

Инцидент 2026-07-06: blanket-allow *.siteadaptor.de позволял сканерам выжигать
квоту Let's Encrypt мусорными хостами. Теперь: корень (+www) + только строки
таблицы Domain.
"""

import pytest
from django.test import RequestFactory

from apps.core.health import verify_domain
from apps.tenants.models import Domain
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _status(domain: str) -> int:
    return verify_domain(
        RequestFactory().get("/internal/verify-domain", {"domain": domain})
    ).status_code


def test_root_and_www_allowed():
    assert _status("siteadaptor.de") == 200
    assert _status("www.siteadaptor.de") == 200


def test_existing_tenant_subdomain_allowed_via_domain_row():
    tenant = TenantFactory(slug="huette", name="H")
    Domain.objects.create(domain="huette.siteadaptor.de", tenant=tenant, is_primary=True)
    assert _status("huette.siteadaptor.de") == 200
    assert _status("HUETTE.siteadaptor.de") == 200  # регистронезависимо


def test_unknown_subdomain_of_base_is_rejected():
    # Замок инцидента: раньше endswith(".siteadaptor.de") пропускал ЛЮБОЙ мусор.
    assert _status("nope-unknown.siteadaptor.de") == 404
    assert _status("www.1www.www.whm.www.baeckerei-test.siteadaptor.de") == 404
    assert _status("5432whm.www.whm.1x.siteadaptor.de") == 404


def test_custom_domain_allowed_only_when_registered():
    assert _status("baeckerei-mueller.de") == 404
    tenant = TenantFactory(slug="mueller2", name="M")
    Domain.objects.create(domain="baeckerei-mueller.de", tenant=tenant, is_primary=False)
    assert _status("baeckerei-mueller.de") == 200


def test_empty_domain_rejected():
    assert _status("") == 404
