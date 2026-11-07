"""FB-25: «Website › Seitenaufbau» — схема блоков страниц и точечная правка."""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import site_schema
from apps.core.site_schema_views import site_schema_view
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(cfg=None):
    return TenantFactory(slug="schema1", name="Schema", site_config=cfg or {})


def _ids(tenant, host):
    cfg = siteconfig.normalize(tenant.site_config)
    return [b.get("id") or b.get("key") for b in cfg["page_blocks"].get(host, [])]


def test_add_move_toggle_delete_on_a_page():
    t = _tenant()
    site_schema.apply(t, "catalog", "add", block_type="text")
    site_schema.apply(t, "catalog", "add", block_type="banner")
    blocks = site_schema.blocks_for(siteconfig.normalize(t.site_config), "catalog")
    assert blocks[0]["main"]  # основной список виден в схеме
    text_ref, banner_ref = blocks[1]["ref"], blocks[2]["ref"]
    site_schema.apply(t, "catalog", "up", ref=banner_ref)
    assert _ids(t, "catalog")[-2:] == [banner_ref, text_ref]
    site_schema.apply(t, "catalog", "toggle", ref=text_ref)
    cfg = siteconfig.normalize(t.site_config)
    assert (
        next(b for b in cfg["page_blocks"]["catalog"] if b.get("id") == text_ref)["enabled"]
        is False
    )
    site_schema.apply(t, "catalog", "delete", ref=text_ref)
    assert text_ref not in _ids(t, "catalog")


def test_fixed_sections_and_main_list_are_not_deletable():
    t = _tenant()
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "home", "delete", ref="hero")
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "catalog", "delete", ref=siteconfig.MAIN_LIST_KEY)
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "catalog", "add", block_type="evil")
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(t, "nope", "add", block_type="text")


def test_toggle_home_section():
    t = _tenant()
    before = next(s for s in siteconfig.normalize(t.site_config)["sections"] if s["key"] == "hero")
    site_schema.apply(t, "home", "toggle", ref="hero")
    after = next(s for s in siteconfig.normalize(t.site_config)["sections"] if s["key"] == "hero")
    assert after["enabled"] is not before["enabled"]


def test_translations_of_other_pages_survive_a_move():
    cfg = {
        "page_blocks": {
            "catalog": [
                {"key": "text", "id": "a1", "data": {"title": "A"}},
                {"key": "text", "id": "b2", "data": {"title": "B"}},
            ],
            "info": [{"key": "text", "id": "c3", "data": {"title": "C"}}],
        },
        "i18n": {
            "ru": {
                "page_blocks": {
                    "catalog": [{"data": {"title": "А"}}, {"data": {"title": "Б"}}],
                    "info": [{"data": {"title": "В"}}],
                }
            }
        },
    }
    t = _tenant(cfg)
    site_schema.apply(t, "catalog", "up", ref="b2")
    ru = siteconfig.normalize(t.site_config)["i18n"]["ru"]["page_blocks"]
    assert ru["info"] == [{"data": {"title": "В"}}], "переводы другой страницы не стёрты"
    titles = [row["data"]["title"] for row in ru["catalog"] if row]
    assert titles[-2:] == ["Б", "А"], "перевод едет за своим блоком"


def test_screen_renders_pages_and_preview():
    t = _tenant()
    req = RequestFactory().get("/dashboard/site/aufbau/", {"seite": "catalog"})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = t
    body = site_schema_view(req).content.decode()
    assert "data-schema-blocks" in body and "data-schema-frame" in body
    assert "/sortiment/?preview=1" in body
    assert 'aria-current="page"' in body
