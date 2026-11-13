"""FB-27 «Design», срез D-b: «Fertige Designs» — применение с подтверждением без скриптов.
Без галочки готовый дизайн меняет только вид; состав и порядок главной — по галочке."""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import design_page
from apps.tenants import siteconfig, sitetemplates
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(method, tenant, data=None, query=""):
    req = getattr(RequestFactory(), method)("/dashboard/design/" + query, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _html(tenant, query=""):
    return design_page.design_view(_req("get", tenant, query=query)).content.decode()


def _cfg(tenant):
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def _home(cfg):
    return [(s["key"], s.get("id", ""), bool(s.get("enabled", True))) for s in cfg["sections"]]


def _shop():
    return TenantFactory(business_type="online_shop")


def _key(tenant):
    return sitetemplates.bundles_for(tenant.business_type, tenant)[-1]["key"]


def test_cards_link_to_a_confirmation_and_need_no_script():
    tenant = _shop()
    body = _html(tenant)
    key = _key(tenant)
    assert f"confirm={key}" in body
    assert "onsubmit=" not in body and "confirm(" not in body
    assert "data-design-confirm" not in body  # панели нет, пока дизайн не выбран
    assert 'value="apply_template"' not in body  # шаблоны слиты с готовыми дизайнами


def test_confirmation_lists_what_changes_and_what_stays():
    tenant = _shop()
    key = _key(tenant)
    body = _html(tenant, f"?confirm={key}")
    assert "data-design-confirm" in body
    assert "Das ändert sich" in body and "Das bleibt" in body
    assert f'name="bundle" value="{key}"' in body
    box = body[body.index('name="rebuild_home"') - 200 :][:400]
    assert "checked" not in box.split(">")[0] + box.split('name="rebuild_home"')[1].split(">")[0]


def test_rubbish_confirmation_shows_no_panel():
    tenant = _shop()
    body = _html(tenant, "?confirm=<script>")
    assert "data-design-confirm" not in body and "<script>alert" not in body


def test_without_the_checkbox_the_home_page_keeps_its_blocks():
    tenant = _shop()
    before = _cfg(tenant)
    key = _key(tenant)
    resp = design_page.design_view(_req("post", tenant, {"bundle": key}))
    assert resp.status_code == 302
    after = _cfg(tenant)
    assert _home(after) == _home(before), "состав и порядок главной не меняются"
    assert after.get("page_blocks") == before.get("page_blocks")
    assert after["design"]["bundle"] == key
    look = sitetemplates.get_look_family(after["design"]["look"])
    assert after["font"] == look["font"]  # вид поменялся


def test_with_the_checkbox_the_result_equals_the_full_bundle():
    one, two = _shop(), _shop()
    key = _key(one)
    design_page.design_view(_req("post", one, {"bundle": key, "rebuild_home": "on"}))
    two = Tenant.objects.get(pk=two.pk)
    assert sitetemplates.apply_bundle(two, key)
    assert _cfg(one) == _cfg(two)


def test_unknown_design_changes_nothing():
    tenant = _shop()
    before = Tenant.objects.get(pk=tenant.pk).site_config
    design_page.design_view(_req("post", tenant, {"bundle": "junk", "rebuild_home": "on"}))
    assert Tenant.objects.get(pk=tenant.pk).site_config == before


@pytest.mark.parametrize("rebuild", [False, True])
def test_announced_changes_match_what_is_applied(rebuild):
    tenant = _shop()
    key = _key(tenant)
    tenant = Tenant.objects.get(pk=tenant.pk)
    raw = tenant.site_config
    after, colour = design_page.design_result(tenant, key, rebuild)
    tenant = Tenant.objects.get(pk=tenant.pk)
    assert tenant.site_config == raw, "расчёт ничего не пишет"
    sitetemplates.apply_bundle(tenant, key, rebuild_home=rebuild)
    tenant = Tenant.objects.get(pk=tenant.pk)
    assert siteconfig.normalize(tenant.site_config) == after
    assert tenant.primary_color == colour


def test_all_designs_are_a_second_level_and_demo_is_one_row():
    tenant = _shop()
    body = _html(tenant)
    assert 'id="design-looks"' not in body and "alle=1" in body
    assert 'id="design-looks"' in _html(tenant, "?alle=1")
    assert 'value="load_demo"' in body or 'value="clear_demo"' in body
