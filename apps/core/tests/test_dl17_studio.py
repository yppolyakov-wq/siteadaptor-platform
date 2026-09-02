"""DL-17.3: полнота Studio — визуальные ключи правятся из конструктора.

Разведка плана `docs/dl17-feedback-plan-2026-09-02.md` §17.3: часть ключей
site_config нельзя было настроить из билдера вообще (promo_layout,
promo_grouping, site_defaults.card_chrome/page_bg, layout.tail == "fill"), а
часть имела контрол, но не ехала в live-draft (правка была видна только после
Save). Замки ниже держат все три звена каждой опции: контрол → save → черновик.
"""

import json
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"  # reverse("site-home") в редиректе


def _request(method, path, data=None, tenant=None, **kwargs):
    req = getattr(RequestFactory(), method)(path, data or {}, **kwargs)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)  # обойти login_required
    req.tenant = tenant
    return req


def _builder_body(tenant):
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    assert resp.status_code == 200
    return resp.content.decode()


def _save(tenant, data):
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


# --- A. контролы отрисованы -------------------------------------------------


def test_builder_renders_missing_visual_controls():
    """Каждый ключ из карты разведки имеет СВОЙ контрол в билдере."""
    tenant = TenantFactory(schema_name="public", slug="dl17a", name="DL17A")
    body = _builder_body(tenant)
    # страница акций: раскладка групп + режим группировки
    assert 'name="promo_layout"' in body
    assert 'name="promo_grouping"' in body
    assert 'value="slider"' in body and 'value="time"' in body
    # хром карточек — видимый селект (был hidden под Look-клик)
    assert 'name="sd_card_chrome"' in body
    assert '<select name="sd_card_chrome"' in body
    for chrome in ("hard", "hairline", "line"):
        assert f'value="{chrome}"' in body
    # фон страницы — видимый color-инпут + тумблер и сентинел присутствия
    assert '<input type="color" name="sd_page_bg"' in body
    assert 'name="sd_page_bg_on"' in body
    assert 'name="sd_page_bg_present"' in body
    # хвост неполного ряда: недостающий вид «добить плиткой-подсказкой»
    assert 'value="fill"' in body


def test_builder_no_longer_ships_hidden_only_design_keys():
    """Замена hidden → видимый контрол: скрытых полей фона/хрома больше нет
    (иначе в POST ушли бы ДВА значения одного имени)."""
    tenant = TenantFactory(schema_name="public", slug="dl17h", name="DL17H")
    body = _builder_body(tenant)
    assert '<input type="hidden" name="sd_page_bg"' not in body
    assert '<input type="hidden" name="sd_card_chrome"' not in body


# --- B. Save ----------------------------------------------------------------


def test_save_promo_page_keys():
    tenant = TenantFactory(schema_name="public", slug="dl17p", name="DL17P")
    cfg = _save(
        tenant,
        {"promo_layout": "slider", "promo_grouping": "time", "font": "system"},
    )
    assert cfg["promo_layout"] == "slider"
    assert cfg["promo_grouping"] == "time"
    # "" законно снимает ключ (presence-minimal)
    cfg = _save(tenant, {"promo_layout": "", "promo_grouping": "", "font": "system"})
    assert "promo_layout" not in cfg and "promo_grouping" not in cfg


def test_save_card_chrome_and_page_bg_from_visible_controls():
    tenant = TenantFactory(schema_name="public", slug="dl17c", name="DL17C")
    cfg = _save(
        tenant,
        {
            "font": "system",
            "sd_card_chrome": "hairline",
            "sd_page_bg_present": "1",
            "sd_page_bg_on": "on",
            "sd_page_bg": "#faf6ef",
        },
    )
    assert cfg["site_defaults"]["card_chrome"] == "hairline"
    assert cfg["site_defaults"]["page_bg"] == "#faf6ef"
    # снятый тумблер при сентинеле = «фон не задан» (color-инпут пустое не умеет)
    cfg = _save(
        tenant,
        {
            "font": "system",
            "sd_card_chrome": "",
            "sd_page_bg_present": "1",
            "sd_page_bg": "#faf6ef",
        },
    )
    assert "card_chrome" not in cfg["site_defaults"]
    assert "page_bg" not in cfg["site_defaults"]


def test_save_layout_tail_fill():
    tenant = TenantFactory(schema_name="public", slug="dl17t", name="DL17T")
    cfg = _save(
        tenant,
        {"order_products": "1", "enabled_products": "on", "tail_products": "fill"},
    )
    products = next(s for s in cfg["sections"] if s["key"] == "products")
    assert products["layout"]["tail"] == "fill"


def test_foreign_save_keeps_studio_keys():
    """W0/W6: форма билдера без этих полей не роняет уже сохранённый выбор
    (у promo_*-ключей есть второй писатель — панель на списке акций)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="dl17w",
        name="DL17W",
        site_config={
            "promo_layout": "slider",
            "promo_grouping": "time",
            "site_defaults": {"page_bg": "#faf6ef", "card_chrome": "hard"},
            "sections": [{"key": "products", "enabled": True, "layout": {"tail": "fill"}}],
        },
    )
    cfg = _save(tenant, {"font": "system"})  # чужая область билдера
    assert cfg["promo_layout"] == "slider"
    assert cfg["promo_grouping"] == "time"
    assert cfg["site_defaults"]["page_bg"] == "#faf6ef"
    assert cfg["site_defaults"]["card_chrome"] == "hard"


# --- C. live-draft ----------------------------------------------------------


def _draft(tenant, payload):
    req = _request(
        "post",
        "/dashboard/site/preview/draft/",
        json.dumps(payload),
        tenant,
        content_type="application/json",
    )
    resp = views.site_preview_draft(req)
    assert resp.status_code == 204
    return req.session["site_preview_draft"]


def test_draft_carries_new_visual_keys():
    tenant = TenantFactory(schema_name="public", slug="dl17d", name="DL17D")
    draft = _draft(
        tenant,
        {
            "sections": [{"key": "products", "enabled": True, "layout": {"tail": "fill"}}],
            "promo_layout": "slider",
            "promo_grouping": "time",
            "product_detail": {"hidden": [], "layout": "tabs"},
            "site_defaults": {
                "promo_card": "preis",
                "card_slider": "on",
                "variant_style": "buttons",
                "card_chrome": "line",
                "page_bg": "#faf6ef",
            },
        },
    )
    products = next(s for s in draft["sections"] if s["key"] == "products")
    assert products["layout"]["tail"] == "fill"
    assert draft["promo_layout"] == "slider"
    assert draft["promo_grouping"] == "time"
    assert siteconfig.product_detail_layout(draft) == "tabs"
    sd = draft["site_defaults"]
    assert sd["promo_card"] == "preis"
    assert sd["card_slider"] == "on"
    assert sd["variant_style"] == "buttons"
    assert sd["card_chrome"] == "line"
    assert sd["page_bg"] == "#faf6ef"
    # опубликованный конфиг не тронут — правки живут под `_draft`
    tenant.refresh_from_db()
    assert "promo_layout" not in tenant.site_config


def test_draft_empty_promo_keys_clear_them():
    """Пустое значение селекта законно снимает ключ и в черновике (иначе
    «выключить слайдер» было бы видно только после Save)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="dl17dc",
        name="DL17DC",
        site_config={"promo_layout": "slider", "promo_grouping": "time"},
    )
    draft = _draft(tenant, {"promo_layout": "", "promo_grouping": ""})
    assert "promo_layout" not in draft and "promo_grouping" not in draft


def test_builder_payload_collects_new_keys():
    """Сборщик payload шлёт новые ключи (иначе серверная ветка черновика
    никогда бы их не увидела)."""
    tenant = TenantFactory(schema_name="public", slug="dl17j", name="DL17J")
    body = _builder_body(tenant)
    assert "payload.promo_layout = plSel.value" in body
    assert "payload.promo_grouping = pgSel.value" in body
    assert "if (tailSel && tailSel.value) lay.tail = tailSel.value;" in body
    assert 'promo_card: sdPromoCard ? sdPromoCard.value : "",' in body
    assert 'card_slider: sdSlider && sdSlider.checked ? "on" : "",' in body
    assert 'variant_style: sdVariant ? sdVariant.value : "",' in body
    assert 'layout: pdLay ? pdLay.value : ""' in body
