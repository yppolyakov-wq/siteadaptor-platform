"""DL-21.1 — плитки шаблона КОРНЕВОЙ страницы каталога в строке «Katalog» Studio:
свой ключ `catalog_page_style` (presence по полю, "" снимает), живой черновик.
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import category_styles
from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _request(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _body(tenant):
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    assert resp.status_code == 200
    return resp.content.decode()


def _save(tenant, data):
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


# STU-19e-2 (deliberate rewrite): both page templates are chosen on the cabinet screen
# "Seitenvorlage"; the Studio shows a summary + link and cannot change them.


def _cabinet_form(tenant, view, typ, code):
    from apps.core.tests.schema_settings import settings_screen

    body = settings_screen(
        _request("get", "/dashboard/seitenvorlagen/", {"typ": typ}, tenant)
    ).content.decode()
    i = body.index(f'data-pt-setting="{code}"')
    return body[i : body.index("</form>", i)]


def test_cabinet_has_the_root_template_tiles_without_preisliste():
    tenant = TenantFactory(schema_name="public", slug="dl21s", name="DL21S")
    form = _cabinet_form(tenant, "page_templates_website", "catalog", "catalog_page_style")
    for code, _l, _h in category_styles.root_styles():
        assert f'name="value" value="{code}"' in form, code
    assert 'value="preisliste"' not in form  # прайс-вид — ось сетки, не шаблон


def test_root_template_saves_and_unsets():
    from apps.core import page_settings

    tenant = TenantFactory(schema_name="public", slug="dl21v", name="DL21V")
    page_settings.write(tenant, "catalog_page_style", "magazin")
    assert siteconfig.normalize(tenant.site_config)["catalog_page_style"] == "magazin"
    page_settings.write(tenant, "catalog_page_style", "")
    assert "catalog_page_style" not in siteconfig.normalize(tenant.site_config)
    # мусор не сохраняется (реестр — единственный источник)
    with pytest.raises(page_settings.PageSettingError):
        page_settings.write(tenant, "catalog_page_style", "erfunden")


def test_studio_no_longer_sends_the_root_template():
    tenant = TenantFactory(schema_name="public", slug="dl21d", name="DL21D")
    body = _body(tenant)
    assert "cpsInp" not in body and 'name="catalog_page_style"' not in body
    # the per-page payload helper itself is unchanged (other callers)
    cfg = {}
    siteconfig.apply_page_payload(cfg, {"catalog_page_style": "tabs"})
    assert cfg["catalog_page_style"] == "tabs"
    siteconfig.apply_page_payload(cfg, {"catalog_page_style": ""})
    assert "catalog_page_style" not in cfg


def test_overview_template_tiles_save_in_the_cabinet():
    """DL-21.2: шаблон обзорной /aktionen/ — плитки и запись в кабинете."""
    from apps.core import page_settings
    from apps.promotions import group_styles

    tenant = TenantFactory(
        schema_name="public", slug="dl21p", name="DL21P", enabled_modules=["catalog", "promotions"]
    )
    form = _cabinet_form(tenant, "page_templates_website", "promos", "promo_page_style")
    for code, _l, _h in group_styles.PROMO_PAGE_STYLES:
        assert f'name="value" value="{code}"' in form, code
    page_settings.write(tenant, "promo_page_style", "magazin")
    assert siteconfig.normalize(tenant.site_config)["promo_page_style"] == "magazin"
    cfg = _save(tenant, {"home_form": "1", "promo_page_style": ""})
    assert cfg["promo_page_style"] == "magazin"  # Studio Save cannot unset it
