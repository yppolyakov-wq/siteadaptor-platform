"""FB-30.12b: вкладка «Zahlung» карточками (макет 7) и запись подвида «оплаты на месте»."""

import re

import pytest

from apps.core import views as core_views
from apps.core.tests.test_payment_settings import _req, _user
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.billing import connect

    monkeypatch.setattr(connect, "is_connect_configured", lambda: True)


def _html(tenant, user="pc", **get):
    return core_views.payment_settings(_req("get", _user(user), tenant, get)).content.decode()


def _order(html):
    return re.findall(r'data-pay-card="(\w+)"', html)


def test_cards_list_active_methods_first_and_offer_the_rest():
    tenant = TenantFactory(disabled_modules=[], invoice_b2b_enabled=True)
    html = _html(tenant)
    assert _order(html) == ["on_site", "invoice", "stripe", "vorkasse"]
    add = html.split("data-pay-add", 1)[1].split("</details>", 1)[0]
    assert "?art=vorkasse#pay-vorkasse" in add and "?art=on_site" not in add
    assert "?art=invoice" not in add  # уже включён
    # мастер-секций на экране нет — одна форма полей, без двойников
    assert html.count('name="sec_vorkasse"') == 1 and html.count('name="sec_invoice"') == 1


def test_add_menu_opens_the_card_with_the_offer_ticked():
    tenant = TenantFactory(disabled_modules=[])
    html = _html(tenant, art="vorkasse")
    card = html.split('data-pay-card="vorkasse"', 1)[1].split("</li>", 1)[0]
    assert "<details open>" in card
    assert re.search(r'name="vorkasse_enabled"\s+checked', card)
    assert "<details open>" not in _html(tenant, user="pc2", art="<script>")


def test_without_orders_no_vorkasse_card_and_no_delivery_switch():
    tenant = TenantFactory(disabled_modules=["orders"])
    html = _html(tenant)
    assert "vorkasse" not in _order(html)
    assert 'name="on_site_delivery"' not in html and 'name="on_site_kind"' in html


def _post(tenant, data):
    return core_views.payment_settings(
        _req("post", _user(f"pp{len(data)}{tenant.pk}"), tenant, data)
    )


def test_on_site_kind_is_saved_and_garbage_is_dropped():
    tenant = TenantFactory(
        disabled_modules=[], site_config={"keep": 1, "payment_on_site": {"delivery": False}}
    )
    _post(tenant, {"tab": "zahlung", "sec_on_site": "1", "on_site_kind": "card",
                   "on_site_delivery_shown": "1"})  # fmt: skip
    tenant.refresh_from_db()
    # FB-30.13: «bei Lieferung» на экране больше нет — прежнее значение не трогается
    assert tenant.site_config["payment_on_site"] == {"kind": "card", "delivery": False}
    assert tenant.site_config["keep"] == 1, "точечная запись — чужие ключи целы"
    _post(tenant, {"tab": "zahlung", "sec_on_site": "1", "on_site_kind": "gold"})
    tenant.refresh_from_db()
    assert tenant.site_config["payment_on_site"] == {"kind": "", "delivery": False}


def test_without_sentinel_on_site_is_untouched():
    cfg = {"payment_on_site": {"kind": "cash", "delivery": False}}
    tenant = TenantFactory(disabled_modules=[], site_config=dict(cfg))
    _post(tenant, {"tab": "zahlung", "sec_invoice": "1", "on_site_kind": "both"})
    tenant.refresh_from_db()
    assert tenant.site_config["payment_on_site"] == cfg["payment_on_site"]


def test_on_site_card_points_to_the_shipping_methods():
    """FB-30.13: правило «оплата ↔ доставка» — в способах доставки, здесь только ссылка."""
    html = _html(TenantFactory(disabled_modules=[]))
    card = html.split('data-pay-card="on_site"', 1)[1].split("</li>", 1)[0]
    assert 'name="on_site_delivery"' not in card and "?tab=lieferung" in card


def test_wizard_keeps_the_old_sections():
    from django.template.loader import render_to_string

    html = render_to_string(
        "tenant/_payment_fields.html",
        {"orders_active": True, "connect_configured": True, "can_edit_bank": True},
    )
    assert "data-pay-card" not in html and 'name="sec_vorkasse"' in html


def test_opened_card_says_it_switches_on_with_save():
    tenant = TenantFactory(disabled_modules=[])
    card = _html(tenant, user="pc4", art="invoice").split('data-pay-card="invoice"', 1)[1]
    assert "data-pay-pending" in card.split("</li>", 1)[0]
    assert "data-pay-pending" not in _html(tenant, user="pc5")


def test_save_on_site_rereads_the_config_under_lock():
    tenant = TenantFactory(disabled_modules=[], site_config={})
    from apps.tenants.models import Tenant

    Tenant.objects.filter(pk=tenant.pk).update(site_config={"other_writer": True})
    _post(tenant, {"tab": "zahlung", "sec_on_site": "1", "on_site_kind": "cash"})
    tenant.refresh_from_db()
    assert tenant.site_config["other_writer"] is True
    assert tenant.site_config["payment_on_site"]["kind"] == "cash"
