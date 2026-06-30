"""V3: inline-редактирование текста на превью — endpoint + data-edit маркеры."""

import json
from types import SimpleNamespace

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _post(field, value, tenant):
    body = json.dumps({"field": field, "value": value})
    req = RequestFactory().post(
        "/dashboard/site/preview/edit/", body, content_type="application/json"
    )
    SessionMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return views.site_inline_edit(req)


def test_inline_edit_saves_whitelisted_field():
    tenant = TenantFactory(schema_name="public", slug="ie", name="IE")
    resp = _post("hero_title", "  Pranasy ist da  ", tenant)
    assert resp.status_code == 204
    tenant.refresh_from_db()
    assert siteconfig.normalize(tenant.site_config)["hero_title"] == "Pranasy ist da"


def test_inline_edit_rejects_unknown_field():
    tenant = TenantFactory(schema_name="public", slug="ie2", name="IE2")
    assert _post("status", "hacked", tenant).status_code == 400  # не в TEXT_FIELDS
    tenant.refresh_from_db()
    assert "status" not in tenant.site_config


def test_inline_edit_saves_nested_cta_field():
    """M20: вложенное поле секции (cta.title) пишется в дочерний словарь."""
    tenant = TenantFactory(schema_name="public", slug="ie3", name="IE3")
    resp = _post("cta.title", "  Jetzt buchen  ", tenant)
    assert resp.status_code == 204
    tenant.refresh_from_db()
    assert siteconfig.normalize(tenant.site_config)["cta"]["title"] == "Jetzt buchen"


def test_inline_edit_rejects_nonwhitelisted_nested_field():
    """Только NESTED_TEXT_FIELDS — нельзя переписать, например, ссылку кнопки."""
    tenant = TenantFactory(schema_name="public", slug="ie4", name="IE4")
    assert _post("cta.button_url", "https://evil.example", tenant).status_code == 400
    tenant.refresh_from_db()
    assert (tenant.site_config.get("cta") or {}).get("button_url", "") != "https://evil.example"


def test_inline_edit_saves_section_title():
    """V3+: заголовок секции (section_titles.products) правится на превью."""
    tenant = TenantFactory(schema_name="public", slug="ie5", name="IE5")
    resp = _post("section_titles.products", "  Unsere Karte  ", tenant)
    assert resp.status_code == 204
    tenant.refresh_from_db()
    assert siteconfig.normalize(tenant.site_config)["section_titles"]["products"] == "Unsere Karte"


def test_inline_edit_rejects_unknown_section_title_key():
    tenant = TenantFactory(schema_name="public", slug="ie6", name="IE6")
    assert _post("section_titles.evil", "x", tenant).status_code == 400


def test_inline_edit_saves_section_intro():
    """H1: описание секции (section_intros.products) правится на превью."""
    tenant = TenantFactory(schema_name="public", slug="ii1", name="II1")
    resp = _post("section_intros.products", "  Täglich frisch gebacken  ", tenant)
    assert resp.status_code == 204
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["section_intros"]["products"] == "Täglich frisch gebacken"


def test_inline_edit_rejects_unknown_section_intro_key():
    tenant = TenantFactory(schema_name="public", slug="ii2", name="II2")
    assert _post("section_intros.evil", "x", tenant).status_code == 400


def test_inline_edit_empty_section_intro_dropped():
    """Пустое описание → normalize убирает ключ (на витрине описания нет)."""
    tenant = TenantFactory(schema_name="public", slug="ii3", name="II3")
    assert _post("section_intros.products", "Da", tenant).status_code == 204
    assert _post("section_intros.products", "   ", tenant).status_code == 204
    tenant.refresh_from_db()
    assert "products" not in siteconfig.normalize(tenant.site_config)["section_intros"]


def test_section_intro_renders_with_marker():
    """H1: непустое описание секции рендерится на витрине с data-edit-маркером."""
    from apps.catalog.models import Product

    tenant = TenantFactory(schema_name="public", slug="ii4", name="II4")
    Product.objects.create(name={"de": "Brot"}, base_price="2.00", is_active=True, is_featured=True)
    tenant.site_config = {
        "sections": [{"key": "products", "enabled": True}],
        "section_intros": {"products": "Täglich frisch"},
    }
    tenant.save(update_fields=["site_config"])
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert 'data-edit="section_intros.products"' in body
    assert "Täglich frisch" in body


def test_section_headers_carry_data_edit_markers():
    """Заголовок секции products несёт data-edit (кликом на «heading» правится)."""
    from apps.catalog.models import Product

    tenant = TenantFactory(schema_name="public", slug="ie7", name="IE7")
    Product.objects.create(
        name={"de": "Burger"}, base_price="5.00", is_active=True, is_featured=True
    )
    tenant.site_config = {"sections": [{"key": "products", "enabled": True}]}
    tenant.save(update_fields=["site_config"])
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert 'data-edit="section_titles.products"' in body


def test_cta_carries_data_edit_markers():
    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "cta", "enabled": True}],
            "cta": {"title": "T", "text": "B", "button_label": "Go", "button_url": "/sortiment/"},
        }
    )
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert 'data-edit="cta.title"' in body and 'data-edit="cta.text"' in body


def test_inline_edit_saves_catalog_title_and_intro():
    """H1.2: заголовок/интро страницы каталога (catalog_title/catalog_intro) — в TEXT_FIELDS."""
    tenant = TenantFactory(schema_name="public", slug="iec", name="IEC")
    assert _post("catalog_title", "  Unsere Backwaren  ", tenant).status_code == 204
    assert _post("catalog_intro", "Täglich frisch", tenant).status_code == 204
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["catalog_title"] == "Unsere Backwaren"
    assert cfg["catalog_intro"] == "Täglich frisch"


def test_catalog_page_carries_data_edit_markers():
    """H1.2: страница каталога несёт data-edit для заголовка/интро; кастомные значения рендерятся."""
    from apps.catalog.models import Product

    tenant = TenantFactory.build(
        site_config={"catalog_title": "Unsere Backwaren", "catalog_intro": "Täglich frisch"}
    )
    Product.objects.create(name={"de": "Brot"}, base_price="2.00", is_active=True)
    req = RequestFactory().get("/sortiment/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    body = public_views.product_list(req).content.decode()
    assert 'data-edit="catalog_title"' in body and 'data-edit="catalog_intro"' in body
    assert "Unsere Backwaren" in body and "Täglich frisch" in body


def test_inline_edit_saves_footer_text():
    """H1.2: тэглайн подвала (footer_text) — в TEXT_FIELDS, правится инлайн."""
    tenant = TenantFactory(schema_name="public", slug="ieft", name="IEFT")
    assert _post("footer_text", "  Handgemacht seit 1990  ", tenant).status_code == 204
    tenant.refresh_from_db()
    assert siteconfig.normalize(tenant.site_config)["footer_text"] == "Handgemacht seit 1990"


def test_footer_tagline_renders_with_marker():
    """H1.2: подвал (_base.html) несёт тэглайн с data-edit="footer_text" (виден на всех страницах)."""
    tenant = TenantFactory.build(site_config={"footer_text": "Handgemacht seit 1990"})
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert 'data-edit="footer_text"' in body
    assert "Handgemacht seit 1990" in body


def test_hero_about_carry_data_edit_markers():
    tenant = TenantFactory.build(
        site_config={
            "sections": [
                {"key": "hero", "enabled": True},
                {"key": "about", "enabled": True},
            ],
            "hero_title": "H",
            "about_title": "A",
            "about_text": "B",
        }
    )
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert 'data-edit="hero_title"' in body
    assert 'data-edit="about_title"' in body and 'data-edit="about_text"' in body
