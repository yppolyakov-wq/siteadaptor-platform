"""GK-4: C-блок «stats» (полоса цифр) — санитизация, рендер, round-trip билдера.

Ключ данных — `rows` (НЕ items: у dict в Django-шаблоне .items — метод).
Строковый вход (textarea «wert | label») канонизируется в список — этим же
путём живёт live-draft канал (collect() шлёт сырое поле формы)."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.template import Context
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants import siteconfig
from apps.tenants.templatetags import siteui
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- санитизация -------------------------------------------------------------


def test_stats_clean_caps_and_drops_junk():
    rows = [{"value": f"{i}", "label": "x" * 100} for i in range(9)]
    rows.insert(0, "junk")
    rows.insert(1, {"label": "ohne wert"})  # без value — отброшен
    out = siteconfig._clean_cblock_data("stats", {"rows": rows})
    assert len(out["rows"]) == 4  # кап _MAX_STAT_ITEMS
    assert all(len(r["label"]) <= 40 for r in out["rows"])


def test_stats_clean_parses_textarea_string():
    out = siteconfig._clean_cblock_data(
        "stats", {"rows": "12 | Jahre Erfahrung\n500+ | Kunden\n\nohne-pipe\n"}
    )
    assert out["rows"][0] == {"value": "12", "label": "Jahre Erfahrung"}
    assert out["rows"][1] == {"value": "500+", "label": "Kunden"}
    # строка без «|» — value без подписи (не мусор: честный ввод); value ≤ 12 симв.
    assert out["rows"][2] == {"value": "ohne-pipe", "label": ""}


def test_stats_empty_gives_no_data():
    assert siteconfig._clean_cblock_data("stats", {}) == {}
    assert siteconfig._clean_cblock_data("stats", {"rows": []}) == {}
    assert siteconfig._clean_cblock_data("stats", {"rows": "   \n  "}) == {}


def test_stats_to_text_round_trip():
    rows = [{"value": "12", "label": "Jahre"}, {"value": "4,9 ★", "label": ""}]
    text = siteconfig.stats_to_text(rows)
    assert siteconfig._clean_cblock_data("stats", {"rows": text})["rows"] == rows


def test_stats_valid_on_home_and_pages():
    cfg = siteconfig.normalize(
        {
            "sections": [{"key": "stats", "id": "s1", "data": {"rows": [{"value": "7"}]}}],
            "page_blocks": {"info": [{"key": "stats", "id": "s2", "data": {"rows": "1 | a"}}]},
        }
    )
    home = [s for s in cfg["sections"] if s.get("key") == "stats"]
    assert home and home[0]["data"]["rows"][0]["value"] == "7"
    assert cfg["page_blocks"]["info"][0]["data"]["rows"] == [{"value": "1", "label": "a"}]


# --- рендер ------------------------------------------------------------------


def _render(rows):
    req = RequestFactory().get("/")
    req.tenant = TenantFactory.build()
    return siteui.render_block(
        Context({"request": req}), {"key": "stats", "id": "s1", "data": {"rows": rows}}
    )


def test_stats_renders_grid_by_count():
    two = _render([{"value": "A", "label": "a"}, {"value": "B", "label": "b"}])
    assert "grid-cols-2" in two and "sm:grid-cols-4" not in two
    four = _render([{"value": str(i), "label": ""} for i in range(4)])
    assert "sm:grid-cols-4" in four
    three = _render([{"value": "12", "label": "Jahre"}, {"value": "2"}, {"value": "3"}])
    assert "grid-cols-3" in three and "12" in three and "Jahre" in three


def test_stats_empty_renders_nothing():
    assert _render([]).strip() == ""


# --- билдер: round-trip + вставка --------------------------------------------


def _req(method="post", data=None, tenant=None):
    req = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    req.tenant = tenant
    return req


def test_builder_add_block_inserts_demo_stats():
    tenant = TenantFactory(schema_name="public", slug="st1", name="St1", site_config={})
    core_views.home_builder_view(
        _req(data={"action": "add_block", "block_type": "stats"}, tenant=tenant)
    )
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    block = next(s for s in cfg["sections"] if s.get("key") == "stats")
    assert block["data"] == siteconfig.CBLOCK_DEMO_DATA["stats"]  # демо переживает normalize


def test_builder_save_textarea_persists_rows():
    tenant = TenantFactory(
        schema_name="public",
        slug="st2",
        name="St2",
        site_config={"sections": [{"key": "stats", "id": "cb1", "data": {}, "enabled": True}]},
    )
    body = core_views.home_builder_view(_req("get", tenant=tenant)).content.decode()
    assert 'name="cb_cb1_rows"' in body  # textarea в строке редактора
    core_views.home_builder_view(
        _req(
            data={
                "cb_id": "cb1",
                "cb_type_cb1": "stats",
                "enabled_cb_cb1": "on",
                "order_cb_cb1": "1",
                "cb_cb1_rows": "12 | Jahre Erfahrung\n500+ | Kunden",
            },
            tenant=tenant,
        )
    )
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    block = next(s for s in cfg["sections"] if s.get("key") == "stats")
    assert block["data"]["rows"] == [
        {"value": "12", "label": "Jahre Erfahrung"},
        {"value": "500+", "label": "Kunden"},
    ]
