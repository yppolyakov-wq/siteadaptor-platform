"""M20 ④: конфигурация навигации витрины — normalize + резолв шапки."""

import pytest

from apps.core.context import _storefront_nav
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    # storefront-* имена живут в urls_tenant — нужно для reverse() в _storefront_nav
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_normalize_defaults_nav_for_legacy_config():
    cfg = siteconfig.normalize({})  # легаси без nav
    assert cfg["nav"]["style"] == "classic"
    assert cfg["nav"]["sticky"] is True
    keys = [i["key"] for i in cfg["nav"]["items"]]
    assert keys[:2] == ["offers", "products"]
    assert all(i["enabled"] for i in cfg["nav"]["items"])


def test_normalize_keeps_owner_order_and_drops_unknown():
    cfg = siteconfig.normalize(
        {
            "nav": {
                "style": "centered",
                "sticky": False,
                "items": [
                    {"key": "products", "enabled": True},
                    {"key": "zzz", "enabled": True},  # неизвестный — отброшен
                    {"key": "offers", "enabled": False},
                ],
            }
        }
    )
    assert cfg["nav"]["style"] == "centered"
    assert cfg["nav"]["sticky"] is False
    keys = [i["key"] for i in cfg["nav"]["items"]]
    assert keys[0] == "products" and "zzz" not in keys
    assert keys[1] == "offers"
    # недостающие дописаны включёнными
    assert "booking" in keys


def test_storefront_nav_filters_disabled_and_inactive_modules():
    # booking-модуль выключим → ссылка «Book» не должна попасть
    tenant = TenantFactory(
        schema_name="public",
        slug="x",
        name="X",
        business_type="bakery",
        disabled_modules=["booking"],
        site_config={
            "nav": {
                "style": "classic",
                "sticky": True,
                "items": [
                    {"key": "offers", "enabled": True},
                    {"key": "products", "enabled": False},  # выключено владельцем
                    {"key": "booking", "enabled": True},  # включено, но модуль выкл
                ],
            }
        },
    )
    items, style, sticky = _storefront_nav(tenant)
    keys = [i["key"] for i in items]
    assert "offers" in keys
    assert "products" not in keys  # выключено владельцем
    assert "booking" not in keys  # модуль неактивен
    assert style == "classic" and sticky is True
    assert all("url" in i and "label" in i for i in items)


def test_storefront_header_does_not_leak_template_comment():
    """Регрессия: многострочный {# #} утекал текстом в шапку витрины.
    Урок CLAUDE.md — многострочные комментарии только {% comment %}."""
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.promotions import public_views
    from apps.tenants.tests.factories import TenantFactory

    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(name="Bäckerei X")
    body = public_views.storefront_home(req).content.decode()
    assert "classic/centered/minimal" not in body  # текст комментария не виден
    assert "M20" not in body
