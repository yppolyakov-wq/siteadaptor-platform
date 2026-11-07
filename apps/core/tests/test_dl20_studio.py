"""DL-20.2 — выбор ШАБЛОНА СТРАНИЦЫ категории: общий дефолт в Studio и плитки
в карточке категории.

Запрос владельца 2026-09-03: «такая же механика выбора шаблона и наследования
если нужно через общие настройки». Замки держат оба конца — контрол в Studio →
save → черновик, и плитки в форме категории (приоритет проверяет
apps/catalog/tests/test_dl20_category_layouts.py).
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import category_styles
from apps.core import views
from apps.promotions import group_styles
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


# STU-19e-2 (deliberate rewrite): the site-wide category / offer-group templates are
# chosen on the cabinet screen "Seitenvorlage" (one writer: page_settings). The Studio
# row became a summary + link, and a Studio Save / draft can no longer change them.


def _cabinet(tenant, view, typ):
    from apps.core import page_templates

    resp = getattr(page_templates, view)(
        _request("get", f"/dashboard/seitenvorlagen/?typ={typ}", {"typ": typ}, tenant)
    )
    assert resp.status_code == 200
    return resp.content.decode()


def _tiles(body, code):
    i = body.index(f'data-pt-setting="{code}"')
    return body[i : body.index("</form>", i)]


def test_cabinet_shows_a_tile_for_every_category_template():
    tenant = TenantFactory(schema_name="public", slug="dl20s", name="DL20S")
    form = _tiles(_cabinet(tenant, "page_templates_website", "category"), "category_page_style")
    for code, _label, _hint in category_styles.CATEGORY_PAGE_STYLES:
        assert f'name="value" value="{code}"' in form, code


def test_studio_row_is_a_summary_not_a_picker():
    tenant = TenantFactory(schema_name="public", slug="dl20e", name="DL20E")
    body = _body(tenant)
    assert 'name="sd_category_page_style"' not in body
    assert 'name="sd_promo_group_style"' not in body
    assert "/dashboard/seitenvorlagen/?typ=category" in body


def test_cabinet_saves_the_site_wide_page_template():
    from apps.core import page_settings

    tenant = TenantFactory(schema_name="public", slug="dl20v", name="DL20V")
    page_settings.write(tenant, "category_page_style", "magazin")
    assert siteconfig.normalize(tenant.site_config)["site_defaults"]["category_page_style"] == (
        "magazin"
    )
    # снятие выбора убирает ключ (presence-minimal → golden целы)
    page_settings.write(tenant, "category_page_style", "")
    assert "category_page_style" not in siteconfig.normalize(tenant.site_config)["site_defaults"]


def test_studio_save_and_draft_cannot_change_it():
    from apps.core import page_settings

    tenant = TenantFactory(schema_name="public", slug="dl20d", name="DL20D")
    page_settings.write(tenant, "category_page_style", "magazin")
    cfg = _save(tenant, {"home_form": "1", "sd_category_page_style": "kompakt"})
    assert cfg["site_defaults"]["category_page_style"] == "magazin"
    assert "sdCatPage" not in _body(tenant)


def test_cabinet_shows_and_saves_the_group_page_default():
    from apps.core import page_settings

    tenant = TenantFactory(
        schema_name="public",
        slug="dl20g2",
        name="DL20G2",
        enabled_modules=["catalog", "promotions"],
    )
    form = _tiles(_cabinet(tenant, "page_templates_website", "promo_group"), "promo_group_style")
    for code, _label, _hint in group_styles.GROUP_PAGE_STYLES:
        assert f'name="value" value="{code}"' in form, code
    page_settings.write(tenant, "promo_group_style", "prospekt")
    assert siteconfig.normalize(tenant.site_config)["site_defaults"]["promo_group_style"] == (
        "prospekt"
    )
    cfg = _save(tenant, {"home_form": "1", "sd_promo_group_style": ""})
    assert cfg["site_defaults"]["promo_group_style"] == "prospekt"  # Studio cannot unset it
