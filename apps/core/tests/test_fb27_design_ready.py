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
    body = _html(tenant, "?mehr=1")
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


def test_header_style_stays_without_the_checkbox():
    """Ревью: кожа Look несёт свой вид шапки — без перестройки главной он остаётся прежним."""
    tenant = _shop()
    before = _cfg(tenant)
    for bundle in sitetemplates.bundles_for(tenant.business_type, tenant):
        fresh = Tenant.objects.get(pk=tenant.pk)
        fresh.site_config = before
        fresh.save(update_fields=["site_config"])
        sitetemplates.apply_bundle(fresh, bundle["key"], rebuild_home=False)
        after = _cfg(tenant)
        assert (after.get("nav") or {}).get("style") == (before.get("nav") or {}).get("style")
        assert ((after.get("menus") or {}).get("top") or {}).get("style") == (
            (before.get("menus") or {}).get("top") or {}
        ).get("style"), bundle["key"]
        assert _home(after) == _home(before), bundle["key"]


def test_design_not_offered_to_this_business_is_refused():
    tenant = _shop()
    offered = {b["key"] for b in sitetemplates.bundles_for(tenant.business_type, tenant)}
    foreign = next((b["key"] for b in sitetemplates.BUNDLES if b["key"] not in offered), None)
    if foreign is None:
        pytest.skip("этому типу бизнеса предложены все дизайны")
    before = Tenant.objects.get(pk=tenant.pk).site_config
    design_page.design_view(_req("post", tenant, {"bundle": foreign}))
    assert Tenant.objects.get(pk=tenant.pk).site_config == before


def test_owner_chooses_how_many_designs_to_see():
    """Владелец (2026-11-13): сколько карточек видеть — решает он сам. Сразу четыре и
    действующий дизайн, остальные по ссылке; обратно — «Weniger»."""
    tenant = _shop()
    total = len(sitetemplates.bundles_for(tenant.business_type, tenant))
    assert total > design_page.DESIGNS_SHOWN
    body = _html(tenant)
    assert body.count("data-design-card=") == design_page.DESIGNS_SHOWN
    assert "mehr=1" in body
    assert _html(tenant, "?mehr=1").count("data-design-card=") == total
    # действующий дизайн виден всегда, даже если он не в первой четвёрке
    last = _key(tenant)
    sitetemplates.apply_bundle(Tenant.objects.get(pk=tenant.pk), last, rebuild_home=False)
    body = _html(Tenant.objects.get(pk=tenant.pk))
    assert f'data-design-card="{last}"' in body
    assert body.count("data-design-card=") == design_page.DESIGNS_SHOWN + 1


def test_design_preview_carries_the_design_to_other_pages():
    """Владелец (2026-11-13): в предпросмотре дизайн терялся при переходе на другую
    страницу — ссылки витрины обязаны нести выбранный дизайн дальше."""
    import pathlib

    base = pathlib.Path("templates/storefront/_base.html").read_text()
    assert "data-design-preview-keep" in base
    block = base[base.index("data-design-preview-keep") :][:900]
    assert '"look", "bundle"' in block and "searchParams.set" in block
    # значения дизайна сервер в скрипт не печатает
    assert "{{ request.GET.look" not in base and "{{ request.GET.bundle" not in base
