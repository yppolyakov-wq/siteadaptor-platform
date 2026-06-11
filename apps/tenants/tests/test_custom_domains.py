"""Self-service custom-домены: валидация, подтверждение по DNS, вьюхи кабинета."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants import domains
from apps.tenants.models import CustomDomain, Domain
from apps.tenants.tests.factories import DomainFactory, TenantFactory

pytestmark = pytest.mark.django_db

TARGET = "203.0.113.7"


def _attach(request, user=None):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if user is not None:
        request.user = user
    return request


def _owner():
    return get_user_model().objects.create_user(
        username="o", email="o@test.de", password="pw12345678"
    )


# --- validate_new_domain -----------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Bakery.DE  ", "bakery.de"),
        ("https://shop.bakery.de/angebote", "shop.bakery.de"),
        ("bakery.de:8000", "bakery.de"),
        ("bakery.de.", "bakery.de"),
    ],
)
def test_validate_normalizes(raw, expected):
    assert domains.validate_new_domain(raw) == expected


@pytest.mark.parametrize("bad", ["", "nodot", "-bad.de", "1.2.3.4", "spaces here.de"])
def test_validate_rejects_invalid(bad):
    with pytest.raises(domains.DomainError):
        domains.validate_new_domain(bad)


def test_validate_rejects_platform_subdomain(settings):
    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    with pytest.raises(domains.DomainError, match="automatisch"):
        domains.validate_new_domain("shop.siteadaptor.de")
    with pytest.raises(domains.DomainError, match="automatisch"):
        domains.validate_new_domain("siteadaptor.de")


def test_validate_rejects_taken_domain():
    DomainFactory(domain="genommen.de")
    with pytest.raises(domains.DomainError, match="vergeben"):
        domains.validate_new_domain("genommen.de")


def test_validate_rejects_duplicate_request():
    t = TenantFactory()
    CustomDomain.objects.create(domain="schon.de", tenant=t)
    with pytest.raises(domains.DomainError, match="hinzugefügt"):
        domains.validate_new_domain("schon.de")


# --- verify ------------------------------------------------------------------


def _pending(tenant=None):
    return CustomDomain.objects.create(domain="bakery.de", tenant=tenant or TenantFactory())


def test_verify_activates_on_matching_a_record(settings, monkeypatch):
    settings.CUSTOM_DOMAIN_TARGET_IP = TARGET
    monkeypatch.setattr(domains, "_resolve_ipv4", lambda d, **k: [TARGET])
    custom = _pending()
    # субдомен бизнеса существует с онбординга и остаётся primary — иначе
    # DomainMixin сам сделает primary первый домен тенанта
    DomainFactory(domain="shop.siteadaptor.de", tenant=custom.tenant, is_primary=True)

    assert domains.verify(custom) is True
    custom.refresh_from_db()
    assert custom.status == CustomDomain.ACTIVE
    assert custom.verified_at is not None
    assert custom.last_check_error == ""
    # роутинг/TLS-строка django-tenants создана
    d = Domain.objects.get(domain="bakery.de")
    assert d.tenant_id == custom.tenant_id
    assert d.is_primary is False


def test_verify_pending_on_wrong_ip(settings, monkeypatch):
    settings.CUSTOM_DOMAIN_TARGET_IP = TARGET
    monkeypatch.setattr(domains, "_resolve_ipv4", lambda d, **k: ["198.51.100.1"])
    custom = _pending()

    assert domains.verify(custom) is False
    custom.refresh_from_db()
    assert custom.status == CustomDomain.PENDING
    assert "198.51.100.1" in custom.last_check_error
    assert not Domain.objects.filter(domain="bakery.de").exists()


def test_verify_pending_when_unresolved(settings, monkeypatch):
    settings.CUSTOM_DOMAIN_TARGET_IP = TARGET
    monkeypatch.setattr(domains, "_resolve_ipv4", lambda d, **k: [])
    custom = _pending()

    assert domains.verify(custom) is False
    custom.refresh_from_db()
    assert custom.status == CustomDomain.PENDING
    assert not Domain.objects.filter(domain="bakery.de").exists()


def test_verify_fails_without_target_ip(settings, monkeypatch):
    settings.CUSTOM_DOMAIN_TARGET_IP = ""
    called = []
    monkeypatch.setattr(domains, "_resolve_ipv4", lambda d, **k: called.append(d) or [TARGET])
    custom = _pending()

    assert domains.verify(custom) is False
    custom.refresh_from_db()
    assert custom.status == CustomDomain.FAILED
    assert called == []  # без IP сервера DNS даже не дёргаем


def test_remove_deletes_domain_and_request(settings, monkeypatch):
    settings.CUSTOM_DOMAIN_TARGET_IP = TARGET
    monkeypatch.setattr(domains, "_resolve_ipv4", lambda d, **k: [TARGET])
    custom = _pending()
    domains.verify(custom)

    domains.remove(custom)
    assert not Domain.objects.filter(domain="bakery.de").exists()
    assert not CustomDomain.objects.filter(pk=custom.pk).exists()


# --- вьюхи кабинета ----------------------------------------------------------


def test_domain_add_creates_pending():
    tenant = TenantFactory()
    req = _attach(RequestFactory().post("/dashboard/domains/add/", {"domain": "Neu.DE"}), _owner())
    req.tenant = tenant
    resp = core_views.domain_add(req)
    assert resp.status_code == 302
    assert CustomDomain.objects.get(domain="neu.de").tenant_id == tenant.id


def test_domain_verify_view_activates(settings, monkeypatch):
    settings.CUSTOM_DOMAIN_TARGET_IP = TARGET
    monkeypatch.setattr(domains, "_resolve_ipv4", lambda d, **k: [TARGET])
    tenant = TenantFactory()
    custom = CustomDomain.objects.create(domain="bakery.de", tenant=tenant)
    req = _attach(RequestFactory().post(f"/dashboard/domains/{custom.pk}/verify/"), _owner())
    req.tenant = tenant
    resp = core_views.domain_verify(req, pk=custom.pk)
    assert resp.status_code == 302
    custom.refresh_from_db()
    assert custom.status == CustomDomain.ACTIVE


def test_domain_views_isolated_per_tenant():
    """Чужую заявку нельзя проверить/удалить — get_object_or_404 по tenant."""
    other = CustomDomain.objects.create(domain="fremd.de", tenant=TenantFactory())
    req = _attach(RequestFactory().post(f"/dashboard/domains/{other.pk}/remove/"), _owner())
    req.tenant = TenantFactory()  # другой бизнес
    with pytest.raises(Http404):
        core_views.domain_remove(req, pk=other.pk)
    assert CustomDomain.objects.filter(pk=other.pk).exists()
