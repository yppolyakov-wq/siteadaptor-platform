"""W6: единый источник темы + фикс потери данных при сохранении «Site».

site_view раньше пересобирал config из подмножества → сохранение «Your site»
роняло ui_mode (S5), board (W5), seo, типографику, стиль карточек. Теперь стартует
с полной копии (как home_builder_view). Тема (цвет/шрифт/стиль баннера) — единый
источник в конструкторе главной; в site.html дублирующих контролов больше нет.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(method, user, tenant, data=None):
    request = getattr(RequestFactory(), method)("/dashboard/site/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def _user(n):
    return get_user_model().objects.create_user(n, f"{n}@test.de", "pw12345678")


def test_site_save_preserves_builder_only_keys():
    """Фикс потери: сохранение «Site» НЕ роняет ключи, которых нет в этой форме
    (ui_mode/board/seo/типографика/стиль карточек)."""
    tenant = TenantFactory(
        disabled_modules=[],
        site_config={
            "ui_mode": "simple",
            "board": {"labels": {"intake": "Posteingang"}, "hidden": ["terminal"]},
            "seo": {"templates": {"home": {"title": "Mein Titel"}}},
            "typography": {"weight_head": 800},
            "site_defaults": {"card_radius": 20},
            "font": "serif",
        },
    )
    resp = core_views.site_view(_req("post", _user("w6a"), tenant, {"hero_title": "Hallo"}))
    assert resp.status_code in (301, 302)
    tenant.refresh_from_db()
    cfg = tenant.site_config
    assert cfg.get("ui_mode") == "simple"  # S5 не слетел
    assert cfg.get("board", {}).get("labels", {}).get("intake") == "Posteingang"  # W5 цел
    assert cfg.get("board", {}).get("hidden") == ["terminal"]
    assert cfg.get("seo", {}).get("templates", {}).get("home", {}).get("title") == "Mein Titel"
    assert cfg.get("typography", {}).get("weight_head") == 800
    assert cfg.get("site_defaults", {}).get("card_radius") == 20
    assert cfg.get("font") == "serif"  # шрифт не сброшен (нет в форме → presence-guard)
    assert cfg.get("hero_title") == "Hallo"  # редактируемое поле применилось


def test_site_save_keeps_hero_style_and_font_when_absent():
    """Тема ушла из site.html → сохранение «Site» без font/hero_accent НЕ сбрасывает
    их (hero_style=accent, font=rounded остаются)."""
    tenant = TenantFactory(
        disabled_modules=[], site_config={"font": "rounded", "hero_style": "accent"}
    )
    core_views.site_view(_req("post", _user("w6b"), tenant, {"hero_title": "X"}))
    tenant.refresh_from_db()
    assert tenant.site_config.get("font") == "rounded"
    assert tenant.site_config.get("hero_style") == "accent"


def test_site_page_has_no_duplicate_theme_pickers(settings):
    """W6: в site.html больше нет дублирующих контролов темы (font-select/accent_color/
    hero_accent) — есть ссылка в конструктор главной."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(disabled_modules=[])
    html = core_views.site_view(_req("get", _user("w6c"), tenant)).content.decode()
    assert 'name="accent_color"' not in html
    assert 'name="hero_accent"' not in html
    assert 'name="font"' not in html  # селект шрифта убран
    assert "/dashboard/site/home/" in html  # ссылка на конструктор главной (Theme)
