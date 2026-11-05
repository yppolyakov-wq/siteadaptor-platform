"""AIS-W W4-1 срез 1: «Website veröffentlichen» — поле, гейт витрины и каталога, публикация."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from apps.aggregator import visibility
from apps.core.middleware import PendingStorefrontMiddleware
from apps.tenants import onboarding
from apps.tenants.models import Tenant
from apps.tenants.services import _new_tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _storefront(tenant, user=None):
    request = RequestFactory().get("/")
    request.tenant = tenant
    request.user = user or AnonymousUser()
    return PendingStorefrontMiddleware(lambda r: HttpResponse("ok"))(request)


def test_new_tenants_are_published_by_default_and_v4_starts_hidden():
    assert TenantFactory.build().published_at is not None
    v3 = _new_tenant(business_name="A", slug="a", business_type="bakery", city="X", email="a@x.de")
    assert v3.published_at is not None and "onboarding" not in v3.site_config
    v4 = _new_tenant(
        business_name="B",
        slug="b",
        business_type="bakery",
        city="X",
        email="b@x.de",
        wizard_v4=True,
    )
    assert v4.published_at is None
    assert onboarding.get_state(v4)["flow"] == "v4"


def test_unpublished_storefront_is_hidden_from_guests_only():
    hidden = TenantFactory.build(schema_name="shop1", published_at=None)
    response = _storefront(hidden)
    assert response.status_code == 503
    assert response["Cache-Control"] == "no-store" and "noindex" in response["X-Robots-Tag"]
    assert _storefront(TenantFactory.build(schema_name="shop2")).status_code == 200


def test_unpublished_is_not_in_city_catalog():
    assert not visibility.listable(TenantFactory.build(published_at=None))
    assert visibility.listable(TenantFactory.build())
    hidden = TenantFactory(schema_name="hid", slug="hid", published_at=None)
    assert hidden.schema_name in set(
        visibility.withheld_schemas().values_list("schema_name", flat=True)
    )


def _ready_tenant(**kw):
    """Тенант в своей схеме (таблицы тенанта тестовой БД лежат в public)."""
    kw.setdefault("schema_name", "public")
    kw.setdefault("slug", "pub")
    kw.setdefault("business_type", "bakery")
    return TenantFactory(published_at=None, **kw)


def test_publish_refuses_without_contact_and_impressum_then_publishes_once():
    from apps.core.models import LegalDoc

    tenant = _ready_tenant(address="", contact_phone="", contact_email="")
    keys = {row["key"] for row in onboarding.publish(tenant)}
    assert {"contact", "impressum"} <= keys
    tenant.refresh_from_db()
    assert tenant.published_at is None

    tenant.address, tenant.contact_phone = "Weg 1, Hilden", "0211 1"
    tenant.save(update_fields=["address", "contact_phone"])
    LegalDoc.objects.create(kind="impressum", locale="de", text="Bäckerei, Weg 1, Hilden")
    assert onboarding.publish(tenant) == []
    tenant.refresh_from_db()
    first = tenant.published_at
    state = onboarding.get_state(tenant)
    assert first is not None and state["completed"] and state["source"] == "wizard"
    assert "completed" in state["times"]  # финиш замера AIS-0

    assert onboarding.publish(tenant) == []  # повтор — время прежнее
    tenant.refresh_from_db()
    assert tenant.published_at == first


def test_mark_complete_publishes_quick_start_demo_import():
    tenant = _ready_tenant(slug="mc")
    onboarding.mark_complete(tenant, source="demo")
    assert Tenant.objects.get(pk=tenant.pk).published_at is not None


def test_unpublished_storefront_refuses_guest_post_too():
    request = RequestFactory().post("/warenkorb/")
    request.tenant = TenantFactory.build(schema_name="shop3", published_at=None)
    request.user = AnonymousUser()
    assert PendingStorefrontMiddleware(lambda r: HttpResponse("ok"))(request).status_code == 503
    request.tenant = TenantFactory.build(schema_name="shop4")
    assert PendingStorefrontMiddleware(lambda r: HttpResponse("ok"))(request).status_code == 200


def test_publish_side_effects_run_once(monkeypatch):
    from apps.core.models import LegalDoc

    calls = []
    monkeypatch.setattr(onboarding, "_after_publish", lambda t: calls.append(t.pk))
    tenant = _ready_tenant(slug="fx", address="Weg 1", contact_phone="0211 1")
    LegalDoc.objects.create(kind="impressum", locale="de", text="Bäckerei, Weg 1, Hilden")
    onboarding.publish(tenant)
    onboarding.publish(tenant)
    onboarding.mark_complete(tenant)
    assert calls == [tenant.pk]


def test_registration_reads_the_v4_flag(settings, django_capture_on_commit_callbacks):
    from apps.tenants.services import start_business_provisioning

    settings.SETUP_WIZARD_V4 = True
    tenant = start_business_provisioning(
        business_name="Neu",
        slug="neu-v4",
        business_type="bakery",
        city="Hilden",
        email="neu@x.de",
        password_hash="x",
    )
    assert tenant.published_at is None
    settings.SETUP_WIZARD_V4 = False
    old = start_business_provisioning(
        business_name="Alt",
        slug="alt-v3",
        business_type="bakery",
        city="Hilden",
        email="alt@x.de",
        password_hash="x",
    )
    assert old.published_at is not None
