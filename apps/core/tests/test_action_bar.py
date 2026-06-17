"""P1: липкая мобильная панель действий витрины (_storefront_actions)."""

import pytest

from apps.core.context import _storefront_actions
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"  # storefront-* для reverse()


def test_call_and_directions_from_tenant_fields():
    t = TenantFactory.build(
        business_type="other",
        contact_phone="+49 211 1234567",  # public_phone — property поверх него
        map_url="https://maps.example/abc",
        disabled_modules=["booking", "orders", "stays", "events"],
    )
    actions = _storefront_actions(t)
    kinds = {a["kind"] for a in actions}
    assert "call" in kinds and "route" in kinds
    call = next(a for a in actions if a["kind"] == "call")
    assert call["url"] == "tel:+49 211 1234567"


def test_primary_action_is_booking_when_active():
    t = TenantFactory.build(business_type="restaurant")
    primary = [a for a in _storefront_actions(t) if a["kind"] == "primary"]
    assert len(primary) == 1
    assert primary[0]["url"].endswith("/termin/")  # booking активен у restaurant


def test_primary_falls_back_to_orders_when_no_booking():
    # retail: booking не рекомендован, orders — да
    t = TenantFactory.build(business_type="retail", disabled_modules=["booking"])
    primary = [a for a in _storefront_actions(t) if a["kind"] == "primary"]
    assert primary and primary[0]["url"].endswith("/sortiment/")


def test_no_actions_when_nothing_configured():
    t = TenantFactory.build(
        business_type="other",
        contact_phone="",
        owner_phone="",
        map_url="",
        disabled_modules=["booking", "orders", "stays", "events"],
    )
    assert _storefront_actions(t) == []
