"""T2b: липкий мобильный нижний таб-бар витрины (_storefront_bottom_nav)."""

from types import SimpleNamespace

import pytest

from apps.core.context import _storefront_bottom_nav
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ALL_OPTIONAL_OFF = ["promotions", "orders", "booking", "stays", "events"]


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"  # storefront-* для reverse()


def _req(cart=None):
    """Лёгкий request: с сессией (для бейджа корзины) или без."""
    return SimpleNamespace(session={"cart": cart}) if cart is not None else SimpleNamespace()


def test_menu_item_always_present():
    t = TenantFactory.build(business_type="other", disabled_modules=ALL_OPTIONAL_OFF)
    nav = _storefront_bottom_nav(_req(), t)
    assert any(i["url"].endswith("/sortiment/") for i in nav)


def test_cart_is_primary_with_badge_when_orders_active():
    t = TenantFactory.build(business_type="restaurant")  # orders активен (disabled=[])
    nav = _storefront_bottom_nav(_req(cart={"a": 2, "b": 1}), t)
    primary = [i for i in nav if i["kind"] == "primary"]
    assert primary and primary[0]["url"].endswith("/warenkorb/")
    assert primary[0]["badge"] == 3


def test_primary_falls_back_to_booking_without_orders():
    t = TenantFactory.build(business_type="other", disabled_modules=["orders", "stays", "events"])
    nav = _storefront_bottom_nav(_req(), t)
    primary = [i for i in nav if i["kind"] == "primary"]
    assert primary and primary[0]["url"].endswith("/termin/")


def test_deals_only_when_promotions_active():
    off = TenantFactory.build(business_type="other", disabled_modules=ALL_OPTIONAL_OFF)
    assert not any(i["url"] == "/#aktionen" for i in _storefront_bottom_nav(_req(), off))
    on = TenantFactory.build(business_type="other", disabled_modules=["orders", "booking"])
    assert any(i["url"] == "/#aktionen" for i in _storefront_bottom_nav(_req(), on))


def test_call_added_when_phone_set():
    t = TenantFactory.build(
        business_type="other",
        contact_phone="+49 211 1234567",
        disabled_modules=ALL_OPTIONAL_OFF,
    )
    nav = _storefront_bottom_nav(_req(), t)
    assert any(i["url"] == "tel:+49 211 1234567" for i in nav)


def test_capped_at_five():
    t = TenantFactory.build(business_type="restaurant", contact_phone="+49 1")
    assert len(_storefront_bottom_nav(_req(cart={"a": 1}), t)) <= 5
