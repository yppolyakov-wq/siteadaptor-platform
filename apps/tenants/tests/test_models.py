import pytest
from django.db import connection

from apps.tenants.models import Domain, Tenant
from apps.tenants.tests.factories import DomainFactory, TenantFactory


@pytest.mark.django_db
def test_tenant_str():
    tenant = TenantFactory.build(schema_name="abc", name="Bäckerei X")
    assert str(tenant) == "Bäckerei X (abc)"


@pytest.mark.django_db
def test_tenant_defaults():
    tenant = Tenant()
    assert tenant.business_type == "other"
    assert tenant.country == "DE"
    assert tenant.default_locale == "de"
    assert tenant.default_currency == "EUR"
    assert tenant.timezone == "Europe/Berlin"
    assert tenant.data_region == "EU"
    assert tenant.primary_color == "#000000"
    assert tenant.subscription_status == "trial"
    assert tenant.is_active is True


@pytest.mark.django_db
def test_tenant_factory_creates_row():
    tenant = TenantFactory()
    assert tenant.pk is not None
    assert tenant.schema_name.startswith("tenant_test_")
    assert tenant.business_type == "bakery"
    assert tenant.enabled_locales == ["de", "en"]


@pytest.mark.django_db
def test_domain_factory_links_to_tenant():
    domain = DomainFactory()
    assert domain.tenant_id is not None
    assert domain.is_primary is True


@pytest.mark.django_db
def test_tenant_business_type_choices():
    choices = dict(Tenant.BUSINESS_TYPES)
    for key in (
        "bakery",
        "butcher",
        "grocery",
        "clothing",
        "restaurant",
        "cafe",
        "retail",
        "tour_operator",
        "hotel",
        "other",
    ):
        assert key in choices


@pytest.mark.django_db(transaction=True)
def test_tenant_save_creates_postgres_schema():
    """При сохранении Tenant с auto_create_schema=True django-tenants создаёт
    отдельную PostgreSQL-схему."""
    schema_name = "tenant_auto_create_xyz"
    tenant = Tenant(
        schema_name=schema_name,
        name="Auto-create test",
        slug="auto-create-test",
        business_type="bakery",
    )
    tenant.auto_create_schema = True
    try:
        tenant.save()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                [schema_name],
            )
            assert cursor.fetchone() is not None
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
        Domain.objects.filter(tenant=tenant).delete()
        Tenant.objects.filter(pk=tenant.pk).delete()
