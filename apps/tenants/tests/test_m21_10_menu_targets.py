"""M21.10: «Versand» и правовые страницы — цели меню/подвала (их не было в селекте)."""

import pytest
from django.urls import reverse

from apps.core.models import LegalDoc
from apps.tenants import menu
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

NEW = ("shipping", "impressum", "privacy", "withdrawal", "agb")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(target, **kw):
    cfg = {"menus": {"top": {"items": [{"label": "X", "type": "page", "target": target}]}}}
    return TenantFactory.build(site_config=cfg, **kw)


def test_new_targets_are_in_the_one_registry_and_reverse():
    values = {c["value"] for c in menu.page_target_choices()}
    for key in NEW:
        assert key in values
        assert reverse(menu._PAGE_URL_NAMES[key])


@pytest.mark.parametrize("key", ["impressum", "privacy", "withdrawal"])
def test_legal_pages_always_resolve(key):
    items = menu.resolve_menu(_tenant(key), "top")
    assert items and items[0]["url"] == reverse(menu._PAGE_URL_NAMES[key])


def test_agb_only_with_text():
    assert not menu.resolve_menu(_tenant("agb"), "top")
    LegalDoc.objects.create(kind="agb", locale="de", text="§ 1 Geltung")
    items = menu.resolve_menu(_tenant("agb"), "top")
    assert items and items[0]["url"] == reverse("storefront-agb")


def test_shipping_follows_orders_module(monkeypatch):
    from apps.core import modules

    monkeypatch.setattr(modules, "is_module_active", lambda t, k, **kw: k != "orders")
    assert not menu.resolve_menu(_tenant("shipping"), "top")
    monkeypatch.setattr(modules, "is_module_active", lambda t, k, **kw: True)
    items = menu.resolve_menu(_tenant("shipping"), "top")
    assert items and items[0]["url"] == reverse("storefront-shipping")
