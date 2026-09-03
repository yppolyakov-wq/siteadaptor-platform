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


def test_studio_shows_a_tile_with_a_preview_for_every_page_template():
    tenant = TenantFactory(schema_name="public", slug="dl20s", name="DL20S")
    body = _body(tenant)
    assert 'name="sd_category_page_style"' in body
    for code, _label, _hint in category_styles.CATEGORY_PAGE_STYLES:
        assert f'data-cf-key="{code}"' in body, code


def test_page_template_picker_is_not_hidden_behind_expert_mode():
    """Прецедент W11-5/DL-19: настройка в expert-блоке в Простом режиме не видна."""
    tenant = TenantFactory(schema_name="public", slug="dl20e", name="DL20E")
    body = _body(tenant)
    idx = body.index('name="sd_category_page_style"')
    expert_open = body.rfind('data-expert="1"', 0, idx)
    assert expert_open != -1
    assert "</div>" in body[expert_open:idx], "плитки шаблона страницы попали в expert-блок"


def test_studio_saves_the_site_wide_page_template():
    tenant = TenantFactory(schema_name="public", slug="dl20v", name="DL20V")
    cfg = _save(tenant, {"home_form": "1", "sd_category_page_style": "magazin"})
    assert cfg["site_defaults"]["category_page_style"] == "magazin"
    # снятие выбора убирает ключ (presence-minimal → golden целы)
    cfg = _save(tenant, {"home_form": "1", "sd_category_page_style": ""})
    assert "category_page_style" not in cfg["site_defaults"]


def test_draft_channel_carries_the_page_template():
    """Живой черновик: без этого правка видна только после Save (класс DL-17.3)."""
    tenant = TenantFactory(schema_name="public", slug="dl20d", name="DL20D")
    body = _body(tenant)
    assert "sd_category_page_style" in body
    assert "category_page_style: sdCatPage" in body


def test_studio_shows_the_group_page_default_too():
    tenant = TenantFactory(schema_name="public", slug="dl20g2", name="DL20G2")
    body = _body(tenant)
    assert 'name="sd_promo_group_style"' in body
    for code, _label, _hint in group_styles.GROUP_PAGE_STYLES:
        assert f'data-cf-key="{code}"' in body, code


def test_studio_saves_and_drafts_the_group_page_default():
    tenant = TenantFactory(schema_name="public", slug="dl20g3", name="DL20G3")
    cfg = _save(tenant, {"home_form": "1", "sd_promo_group_style": "prospekt"})
    assert cfg["site_defaults"]["promo_group_style"] == "prospekt"
    cfg = _save(tenant, {"home_form": "1", "sd_promo_group_style": ""})
    assert "promo_group_style" not in cfg["site_defaults"]
    assert "promo_group_style: sdGrpPage" in _body(tenant)
