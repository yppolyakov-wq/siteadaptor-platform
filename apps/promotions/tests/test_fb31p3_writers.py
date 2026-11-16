"""FB-31 P3 R4: шаблон страницы акций — последнее решение владельца: кто пишет прежний код
(«Seitenvorlage», кабинет акций), тот снимает виды блоков, выбранные в «Seitenaufbau»."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import page_settings
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROWS = [
    {"key": "groups", "style": "tabs"},
    {"key": "text", "id": "t1", "data": {"title": "x", "body": "y"}},
    {"key": "main", "style": "magazin", "grouping": "ohne"},
]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _rows(cfg, host="promos"):
    return siteconfig.normalize(cfg)["page_blocks"].get(host)


def test_page_setting_write_drops_the_overview_views():
    out = page_settings.apply_override(
        {"page_blocks": {"promos": ROWS}}, "promo_page_style", "regale"
    )
    rows = out["page_blocks"]["promos"]
    assert [r.get("id") for r in rows if r.get("id")] == ["t1"], "свои блоки остаются"
    assert {"key": "main"} in rows and not any(r.get("key") == "groups" for r in rows)


def test_detail_style_write_drops_the_offer_view():
    cfg = {"page_blocks": {"promo_detail": [{"key": "offer", "style": "plakat"}]}}
    out = page_settings.apply_override(cfg, "promo_detail_style", "kompakt")
    assert out["page_blocks"]["promo_detail"] == []


def test_cabinet_template_change_drops_the_views_but_same_template_keeps_them():
    from apps.promotions import views

    tenant = TenantFactory(
        schema_name="public",
        slug="fb31p3w",
        name="W",
        site_config={"promo_page_style": "tabs", "page_blocks": {"promos": ROWS}},
    )

    def _post(data):
        r = RequestFactory().post("/promotions/", data)
        SessionMiddleware(lambda x: None).process_request(r)
        MessageMiddleware(lambda x: None).process_request(r)
        r.user = get_user_model()(is_active=True)
        r.tenant = tenant
        assert views.promotion_page_mode(r).status_code == 302
        tenant.refresh_from_db()

    _post({"page_style": "tabs"})
    assert any(r.get("key") == "groups" for r in _rows(tenant.site_config)), "тот же шаблон"
    _post({"page_style": "regale"})
    assert not any(r.get("key") == "groups" for r in _rows(tenant.site_config))
