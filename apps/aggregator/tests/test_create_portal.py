"""Тесты P2.1d: команда create_portal (портал + строка Domain на public)."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.aggregator.models import AggregatorPortal
from apps.tenants.models import Domain
from apps.tenants.tests.factories import DomainFactory, TenantFactory

pytestmark = pytest.mark.django_db

_HOST = "muenchen.siteadaptor.de"


def _public():
    return TenantFactory(schema_name="public")


def _create(**extra):
    args = {
        "host": _HOST,
        "kind": "city",
        "city": "München",
        "title_de": "Angebote München",
    }
    args.update(extra)
    call_command("create_portal", **args)


def test_creates_portal_and_domain_on_public():
    public = _public()
    _create(tagline_de="Lokale Deals")
    portal = AggregatorPortal.objects.get(host=_HOST)
    assert portal.kind == "city"
    assert portal.city == "München"
    assert portal.title_text == "Angebote München"
    assert portal.tagline_text == "Lokale Deals"
    assert portal.is_active
    domain = Domain.objects.get(domain=_HOST)
    assert domain.tenant_id == public.id
    assert not domain.is_primary


def test_host_is_normalized_to_lowercase():
    _public()
    _create(host="MUENCHEN.siteadaptor.de ")
    assert AggregatorPortal.objects.filter(host=_HOST).exists()
    assert Domain.objects.filter(domain=_HOST).exists()


def test_duplicate_portal_host_rejected():
    _public()
    _create()
    with pytest.raises(CommandError, match="уже существует"):
        _create()


def test_kind_requirements_enforced():
    _public()
    with pytest.raises(CommandError, match="--city"):
        _create(city="")
    with pytest.raises(CommandError, match="--business-type"):
        _create(kind="vertical", city="", business_type="")
    with pytest.raises(CommandError, match="--city и --business-type"):
        _create(kind="combo", business_type="")


def test_unknown_business_type_rejected():
    _public()
    with pytest.raises(CommandError, match="business-type"):
        _create(kind="vertical", city="", business_type="florist")


def test_domain_of_other_tenant_rejected():
    _public()
    DomainFactory(domain=_HOST)  # домен уже привязан к обычному тенанту
    with pytest.raises(CommandError, match="уже привязан"):
        _create()
    assert not AggregatorPortal.objects.filter(host=_HOST).exists()


def test_existing_public_domain_reused():
    public = _public()
    DomainFactory(domain=_HOST, tenant=public, is_primary=False)
    _create()
    assert Domain.objects.filter(domain=_HOST).count() == 1
    assert AggregatorPortal.objects.filter(host=_HOST).exists()


def test_missing_public_tenant_rejected():
    with pytest.raises(CommandError, match="Public tenant"):
        _create()


def test_vertical_portal_created():
    _public()
    _create(
        host="baeckerei.siteadaptor.de",
        kind="vertical",
        city="",
        business_type="bakery",
        title_de="Bäckerei-Angebote",
    )
    portal = AggregatorPortal.objects.get(host="baeckerei.siteadaptor.de")
    assert portal.kind == "vertical"
    assert portal.business_type == "bakery"
    assert portal.city == ""
