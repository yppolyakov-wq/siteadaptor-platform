"""SEC волна 2 (решение владельца 2026-11-02): регистрация и сертификаты.

План — `docs/sec-wave2-signup-access-plan-2026-11-02.md`. Замки красные до фикса.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

from apps.core import ratelimit
from apps.tenants import quickstart_views
from apps.tenants.models import Domain, Tenant
from apps.tenants.tests.factories import TenantFactory
from apps.tenants.tests.test_quick_start import _drop, _post, _post_data

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


# --- SEC-B-H1: лимит по сети, а не по адресу -----------------------------------------------


def test_client_net_groups_ipv6_by_64():
    rf = RequestFactory()
    a = rf.get("/", REMOTE_ADDR="2a01:4f8:1:2:aaaa::1")
    b = rf.get("/", REMOTE_ADDR="2a01:4f8:1:2:ffff:1:2:3")
    c = rf.get("/", REMOTE_ADDR="2a01:4f8:1:3::1")
    v4 = rf.get("/", REMOTE_ADDR="10.1.2.3")
    assert ratelimit.client_net(a) == ratelimit.client_net(b)
    assert ratelimit.client_net(a) != ratelimit.client_net(c)
    assert ratelimit.client_net(v4) == "10.1.2.3"
    assert ratelimit.client_net(rf.get("/", REMOTE_ADDR="")) == ""


def _quick(ip, n):
    created = []
    for i in range(n):
        data = _post_data(business_name=f"Laden {i} Krume", email=f"o{i}@krume.test")
        with mock.patch("apps.tenants.tasks.provision_quick.delay"):
            quickstart_views.quick_start(_post(data, ip=ip(i)))
        created += list(Tenant.objects.filter(name=f"Laden {i} Krume"))
    return created


def test_quick_start_limit_shared_by_ipv6_64():
    created = _quick(lambda i: f"2a01:4f8:1:2::{i + 1:x}", 6)
    try:
        assert len(created) == 5  # шестой адрес той же /64 — уже лимит
    finally:
        for t in created:
            _drop(t)


def test_quick_start_global_hourly_cap(settings):
    settings.QUICK_START_HOURLY_CAP = 2
    created = _quick(lambda i: f"10.200.{i}.1", 3)
    try:
        assert len(created) == 2
    finally:
        for t in created:
            _drop(t)


def test_quick_start_cap_per_email():
    created = []
    for i in range(4):
        data = _post_data(business_name=f"Shop {i} Krume", email="same@krume.test")
        with mock.patch("apps.tenants.tasks.provision_quick.delay"):
            quickstart_views.quick_start(_post(data, ip=f"10.201.{i}.1"))
        created += list(Tenant.objects.filter(name=f"Shop {i} Krume"))
    try:
        assert len(created) == 3
    finally:
        for t in created:
            _drop(t)


# --- SEC-B-H1: сертификат не выдаётся поддомену, не подтвердившему почту за сутки ----------


def _domain_for(tenant, name):
    return Domain.objects.create(domain=name, tenant=tenant, is_primary=True)


def test_verify_domain_refuses_stale_unconfirmed_tenant():
    from apps.core.health import verify_domain

    fresh = TenantFactory(schema_name="sec_w2_fresh", email_pending=True)
    stale = TenantFactory(schema_name="sec_w2_stale", email_pending=True)
    Tenant.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(days=40))
    ok = TenantFactory(schema_name="sec_w2_ok", email_pending=False)
    Tenant.objects.filter(pk=ok.pk).update(created_at=timezone.now() - timedelta(days=30))
    _domain_for(fresh, "fresh.example.test")
    _domain_for(stale, "stale.example.test")
    _domain_for(ok, "ok.example.test")
    rf = RequestFactory()
    assert verify_domain(rf.get("/", {"domain": "fresh.example.test"})).status_code == 200
    assert verify_domain(rf.get("/", {"domain": "stale.example.test"})).status_code == 404
    assert verify_domain(rf.get("/", {"domain": "ok.example.test"})).status_code == 200
