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
    # FB-31.7 B1b: прежние виды сняты, выбранный шаблон записан строками осей
    assert siteconfig.page_template_code(siteconfig.normalize(out), "promo_page_style") == "regale"
    assert "promo_page_style" not in out


def test_detail_style_write_drops_the_offer_view():
    cfg = {"page_blocks": {"promo_detail": [{"key": "offer", "style": "plakat"}]}}
    out = page_settings.apply_override(cfg, "promo_detail_style", "kompakt")
    # FB-31.7 B1b: прежний вид снят, новый — строкой оси (не ключом)
    assert out["page_blocks"]["promo_detail"] == [{"key": "offer", "style": "kompakt"}]


def test_cabinet_mode_form_no_longer_writes_templates():
    """FB-31.7 B1b: шаблон обзора — строками «Seitenaufbau»; форма вида акций (шлёт `mode`)
    больше не пишет `promo_page_style` и не снимает виды (скрытый писатель снят)."""
    from apps.promotions import views

    tenant = TenantFactory(
        schema_name="public",
        slug="fb31p3w",
        name="W",
        site_config={"page_blocks": {"promos": ROWS}},
    )
    r = RequestFactory().post("/promotions/", {"page_style": "regale"})
    SessionMiddleware(lambda x: None).process_request(r)
    MessageMiddleware(lambda x: None).process_request(r)
    r.user = get_user_model()(is_active=True)
    r.tenant = tenant
    assert views.promotion_page_mode(r).status_code == 302
    tenant.refresh_from_db()
    assert "promo_page_style" not in tenant.site_config
    assert any(r.get("key") == "groups" for r in _rows(tenant.site_config)), "виды целы"


def test_b1b2_promo_form_has_no_own_template_field():
    # FB-31.7 B1b-2: шаблон акции — только строками её схемы («Seitenaufbau»); форма его не
    # пишет, поэтому и «снимать вид своих блоков при смене шаблона» больше нечем
    from apps.promotions import views
    from apps.promotions.forms import PromotionForm

    assert "page_style" not in PromotionForm.base_fields
    assert "page_style" not in PromotionForm._meta.fields
    assert not hasattr(views, "_drop_own_offer_view")
