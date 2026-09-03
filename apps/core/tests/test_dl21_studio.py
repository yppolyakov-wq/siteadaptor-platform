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


def test_catalog_row_has_the_root_template_tiles_without_preisliste():
    tenant = TenantFactory(schema_name="public", slug="dl21s", name="DL21S")
    body = _body(tenant)
    i = body.index('name="catalog_page_style"')
    # окно до следующей строки страницы (11 плиток × ~500 символов — не 6000)
    end = body.find('data-page-key="', i)
    row = body[body.rfind('data-page-key="catalog"', 0, i) : end if end != -1 else i + 30000]
    assert 'data-page-key="catalog"' in row  # плитки живут в строке каталога
    for code, _l, _h in category_styles.root_styles():
        assert f'data-cf-key="{code}"' in row, code
    assert 'data-cf-key="preisliste"' not in row  # прайс-вид — селект той же строки


def test_root_template_saves_and_unsets():
    tenant = TenantFactory(schema_name="public", slug="dl21v", name="DL21V")
    cfg = _save(tenant, {"home_form": "1", "catalog_page_style": "regale"})
    assert cfg["catalog_page_style"] == "regale"
    cfg = _save(tenant, {"home_form": "1", "catalog_page_style": ""})
    assert "catalog_page_style" not in cfg
    # мусор не сохраняется (реестр — единственный источник)
    cfg = _save(tenant, {"home_form": "1", "catalog_page_style": "erfunden"})
    assert "catalog_page_style" not in cfg


def test_draft_channel_and_page_payload_carry_the_root_template():
    tenant = TenantFactory(schema_name="public", slug="dl21d", name="DL21D")
    assert "payload.catalog_page_style = cpsInp.value" in _body(tenant)
    cfg = {}
    siteconfig.apply_page_payload(cfg, {"catalog_page_style": "tabs"})
    assert cfg["catalog_page_style"] == "tabs"
    siteconfig.apply_page_payload(cfg, {"catalog_page_style": ""})
    assert "catalog_page_style" not in cfg


def test_overview_template_tiles_save_and_draft():
    """DL-21.2: плитки шаблона обзорной /aktionen/ в Studio (top-level ключ, как
    promo_layout) — Save, снятие и живой черновик."""
    from apps.promotions import group_styles

    tenant = TenantFactory(schema_name="public", slug="dl21p", name="DL21P")
    body = _body(tenant)
    assert 'name="promo_page_style"' in body
    for code, _l, _h in group_styles.PROMO_PAGE_STYLES:
        assert f'data-cf-key="{code}"' in body, code
    assert "payload.promo_page_style = ppInp.value" in body
    cfg = _save(tenant, {"home_form": "1", "promo_page_style": "tabs"})
    assert cfg["promo_page_style"] == "tabs"
    cfg = _save(tenant, {"home_form": "1", "promo_page_style": ""})
    assert "promo_page_style" not in cfg
