"""STU-12g (срез 2): глобальный дизайн — на экране кабинета «Design des Shops».

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12g, решение 1B): цвет,
шрифт, типографика, тема и «Карточки и фото» перестают быть настройками КАНВЫ и живут
на своём экране кабинета; туда же переезжает «Start» (шаблоны витрины + демо-контент).

Инварианты среза:
* сохранение — targeted-write (прецедент W9-3): пишем ТОЛЬКО свои ключи, чужие
  (`board`/`seo`/`page_blocks`/`sections`/`menus`) остаются нетронутыми — класс W6;
* presence-сентинелы переезжают вместе с полями: POST без поля не гасит значение;
* `sd_card_style` НЕ переносится — он живёт в реестре `studio_pages` (охват
  «для всех / только здесь») и остаётся настройкой страницы;
* прежняя семантика экрана цела: POST без валидного `bundle`/`look`/наших полей
  по-прежнему безопасен.
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import design_page
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(method, data=None, tenant=None):
    req = getattr(RequestFactory(), method)("/dashboard/design/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _html(tenant):
    return design_page.design_view(_req("get", tenant=tenant)).content.decode()


def _post(tenant, data):
    resp = design_page.design_view(_req("post", data, tenant=tenant))
    assert resp.status_code == 302, resp.status_code
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


def test_screen_shows_colour_font_and_card_controls():
    body = _html(TenantFactory(slug="dsg1", name="Dsg1"))
    for name in (
        "accent",
        "font",
        "typo_weight_head",
        "typo_line_height",
        "theme",
        "sd_card_radius",
        "sd_card_shadow",
        "sd_card_padding",
        "sd_page_bg",
        "sd_card_chrome",
        "sd_media_shape",
        "sd_variant_style",
        "quick_add",
        "wishlist",
    ):
        assert f'name="{name}"' in body, name
    # сентинелы переехали вместе с полями
    for sentinel in ("sd_page_bg_present", "quick_add_present", "wishlist_present"):
        assert f'name="{sentinel}"' in body, sentinel
    # форма карточки остаётся настройкой страницы (реестр studio_pages)
    assert 'name="sd_card_style"' not in body


def test_screen_carries_templates_and_demo_content():
    body = _html(TenantFactory(slug="dsg2", name="Dsg2"))
    assert 'value="apply_template"' in body
    assert 'value="load_demo"' in body or 'value="clear_demo"' in body


def test_saving_writes_the_design_keys():
    tenant = TenantFactory(slug="dsg3", name="Dsg3")
    cfg = _post(
        tenant,
        {
            "action": "design_settings",
            "accent": "#123456",
            "font": "serif",
            "typo_weight_head": "800",
            "typo_line_height": "1.6",
            "theme_present": "1",
            "theme": "dark",
            "sd_cards_present": "1",
            "sd_card_radius": "12",
            "sd_card_shadow": "on",
            "sd_card_padding": "8",
            "sd_page_bg_present": "1",
            "sd_page_bg_on": "on",
            "sd_page_bg": "#f5f5f4",
            "sd_card_chrome": "hairline",
            "sd_media_shape": "round",
            "sd_variant_style": "buttons",
            "quick_add_present": "1",
            "quick_add": "on",
            "wishlist_present": "1",
        },
    )
    tenant.refresh_from_db()
    assert tenant.primary_color == "#123456"
    assert cfg["font"] == "serif"
    assert str(cfg["typography"]["weight_head"]) == "800"
    assert cfg["typography"]["line_height"] == 1.6
    assert cfg.get("theme") == "dark"
    sd = cfg["site_defaults"]
    assert sd["card_radius"] == 12 and sd["card_shadow"] is True and sd["card_padding"] == 8
    assert sd["page_bg"] == "#f5f5f4"
    assert sd["card_chrome"] == "hairline"
    assert sd["media_shape"] == "round"
    assert sd["variant_style"] == "buttons"
    assert cfg["quick_add"] is True
    assert cfg["wishlist"] is False, "сентинел прислан, чекбокс снят → выключено"


def test_saving_keeps_foreign_config_keys():
    """W6: экран пишет ТОЛЬКО свои ключи — композиция и настройки канвы целы."""
    tenant = TenantFactory(
        slug="dsg4",
        name="Dsg4",
        site_config={
            "sections": [{"key": "faq", "enabled": True}, {"key": "hero", "enabled": False}],
            "notify": {"order_paid": {"email": False}},
            "ui_probe": "x",
        },
    )
    cfg = _post(tenant, {"action": "design_settings", "font": "serif"})
    assert [(s["key"], s["enabled"]) for s in cfg["sections"]][:2] == [
        ("faq", True),
        ("hero", False),
    ]
    assert cfg["notify"]["order_paid"]["email"] is False
    # (проба чужого ключа: normalize дропает неизвестные — берём известный `notify`)


def test_saving_without_a_field_keeps_its_value():
    """Presence: POST без `page_bg`/`quick_add` не гасит их (класс W0/W6)."""
    tenant = TenantFactory(slug="dsg5", name="Dsg5")
    _post(
        tenant,
        {
            "action": "design_settings",
            "sd_page_bg_present": "1",
            "sd_page_bg_on": "on",
            "sd_page_bg": "#eeeeee",
            "quick_add_present": "1",
            "quick_add": "on",
        },
    )
    cfg = _post(tenant, {"action": "design_settings", "font": "serif"})
    assert cfg["site_defaults"]["page_bg"] == "#eeeeee"
    assert cfg["quick_add"] is True


def test_unknown_post_is_still_safe():
    tenant = TenantFactory(slug="dsg6", name="Dsg6")
    before = siteconfig.normalize(tenant.site_config)
    cfg = _post(tenant, {"nonsense": "1"})
    assert cfg == before


def test_template_cards_render_section_labels_not_raw_dicts():
    """Стенд поймал сырое `{'key': 'hero', ...}` на карточке: `sections` — список словарей."""
    body = _html(TenantFactory(slug="dsg7", name="Dsg7"))
    assert "{'key':" not in body and "&#x27;key&#x27;:" not in body
    assert "Begrüßungsbanner" in body, "мини-мокап печатает МЕТКИ секций шаблона"


def test_dark_theme_can_be_switched_off_from_this_screen():
    """Снятый чекбокс браузер НЕ шлёт — без сентинела тёмную тему было не выключить.

    В Студии её гасило hidden-поле `theme`; срез 3 это поле уносит, поэтому экран
    обязан иметь свой сентинел (класс `quick_add_present`).
    """
    tenant = TenantFactory(slug="dsg8", name="Dsg8")
    assert (
        _post(tenant, {"action": "design_settings", "theme_present": "1", "theme": "dark"})["theme"]
        == "dark"
    )
    # чекбокс снят: в POST есть только сентинел
    cfg = _post(tenant, {"action": "design_settings", "theme_present": "1"})
    assert "theme" not in cfg, "тёмная тема обязана выключаться с этого экрана"
    body = _html(tenant)
    assert 'name="theme_present"' in body
