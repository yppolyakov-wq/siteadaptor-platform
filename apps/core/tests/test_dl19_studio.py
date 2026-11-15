"""DL-19.4/19.5 — выбор ФОРМЫ карточки: плитки с предпросмотром в Studio и
per-объект поле в формах кабинета.

Запрос владельца 2026-09-03: «настройка вид карточки товара и там выбор из
вариантов и предпросмотр; можно в карточке акции/товара выбрать только для этого
товара или в общих настройках задать для всех; если в карточке выбираем — оно
приоритетнее». Замки держат оба конца: контрол в Studio → save → черновик, и
поле формы → модель → рендер (приоритет проверяет test_dl19_card_forms).
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import card_forms, views
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


# --- кабинет (FB-31 P2: выбор формы — на «Design») ------------
def _design(tenant):
    from apps.core.design_page import design_view

    req = _request("get", "/dashboard/design/", {"tab": "karten"}, tenant)
    resp = design_view(req)
    assert resp.status_code == 200
    return resp.content.decode()


def test_cabinet_shows_a_tile_with_a_preview_for_every_form():
    """FB-31 P2 (осознанно): плитки форм карточек — на экране «Design», «Für alle Seiten»."""
    tenant = TenantFactory(
        schema_name="public", slug="dl19s", name="DL19S", enabled_modules=["catalog", "promotions"]
    )
    body = _design(tenant)
    form = body.split('data-design-default="product_card_form"', 1)[1].split("</fieldset>", 1)[0]
    for key, _label, _hint in card_forms.forms_for("product"):
        assert f'value="{key}"' in form, key
    assert 'aria-hidden="true"' in form  # мини-макет у плитки, а не только подпись
    pform = body.split('data-design-default="promo_card_form"', 1)[1].split("</fieldset>", 1)[0]
    for key, _label, _hint in card_forms.forms_for("promo"):
        assert f'value="{key}"' in pform, key


def test_studio_shows_a_summary_instead_of_the_pickers():
    tenant = TenantFactory(schema_name="public", slug="dl19e", name="DL19E")
    body = _body(tenant)
    assert body.count("data-cardform-picker>") == 0
    assert 'name="sd_card_style"' not in body and 'name="sd_promo_card"' not in body
    row = body.split('data-stu-setting="product_card_form"', 1)[1][:600]
    assert "data-stu19-summary" in row


def test_cabinet_saves_the_forms_and_the_studio_cannot_change_them():
    from apps.core import page_settings

    tenant = TenantFactory(schema_name="public", slug="dl19t", name="DL19T")
    page_settings.write(tenant, "product_card_form", "regal")
    page_settings.write(tenant, "promo_card_form", "coupon")
    cfg = _save(tenant, {"sd_card_style": "", "sd_promo_card": "", "sd_card_radius": "0"})
    assert cfg["site_defaults"]["card_style"] == "regal"
    assert cfg["site_defaults"]["promo_card"] == "coupon"
    # снятие формы законно (плитка «Standard») → ключа снова нет
    page_settings.write(tenant, "product_card_form", "")
    page_settings.write(tenant, "promo_card_form", "")
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert "card_style" not in cfg["site_defaults"]
    assert "promo_card" not in cfg["site_defaults"]


def test_studio_draft_does_not_carry_card_forms():
    tenant = TenantFactory(schema_name="public", slug="dl19d", name="DL19D")
    body = _body(tenant)
    assert "[name='sd_card_style']" not in body and "[name='sd_promo_card']" not in body


# --- кабинет: per-объект --------------------------------------------------------
def test_product_form_offers_the_registry_and_saves_the_choice():
    from apps.catalog.forms import ProductForm
    from apps.catalog.tests.factories import ProductFactory

    p = ProductFactory()
    form = ProductForm(instance=p)
    keys = [k for k, _label in form.fields["card_style"].choices]
    assert keys == [k for k, _l, _h in card_forms.forms_for("product")]
    assert not form.fields["card_style"].required  # пусто = как в настройках сайта
    # форма акции товару не предлагается
    assert "coupon" not in keys


def test_promotion_form_offers_the_promo_registry():
    from apps.promotions.forms import PromotionForm

    form = PromotionForm()
    keys = [k for k, _label in form.fields["card_style"].choices]
    assert keys == [k for k, _l, _h in card_forms.forms_for("promo")]
    assert "coupon" in keys and "overlay" not in keys
