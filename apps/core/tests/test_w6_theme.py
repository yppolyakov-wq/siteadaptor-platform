"""W6: единый источник темы + фикс потери данных при сохранении конфига витрины.

Исторически site_view пересобирал config из подмножества → сохранение «Your site»
роняло чужие ключи: notify, board (W5), seo, типографику, стиль карточек. W11-5: страница
«Site» умерла (302 на Studio), её сохранение — тоже; инвариант «save не роняет
чужие ключи» переехал на единственный оставшийся save — конструктор главной.
Тема (цвет/шрифт/стиль баннера) — его же единый источник.
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
    request = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def _user(n):
    return get_user_model().objects.create_user(n, f"{n}@test.de", "pw12345678")


def test_builder_save_preserves_foreign_keys():
    """Фикс потери: сохранение витрины НЕ роняет ЧУЖИЕ ключи конфига — те, которыми
    билдер не владеет (notify / board W5 / seo / page_blocks).

    Своими ключами (typography, site_defaults, font, hero_style) билдер владеет:
    его форма всегда несёт эти контролы (W0-инвариант «все поля в DOM»), поэтому
    их значение задаёт POST — это единый источник, а не потеря данных.
    """
    tenant = TenantFactory(
        disabled_modules=[],
        site_config={
            "notify": {"customer": {"email": True}},
            "board": {"labels": {"intake": "Posteingang"}, "hidden": ["terminal"]},
            "seo": {"templates": {"home": {"title": "Mein Titel"}}},
            "page_blocks": {"info": [{"id": "pb-x", "key": "text", "text": "Hi"}]},
        },
    )
    resp = core_views.home_builder_view(
        _req("post", _user("w6a"), tenant, {"hero_title": "Hallo", "hero_text": ""})
    )
    assert resp.status_code in (301, 302)
    tenant.refresh_from_db()
    cfg = tenant.site_config
    assert cfg.get("notify") == {"customer": {"email": True}}  # чужой ключ не слетел
    assert cfg.get("board", {}).get("labels", {}).get("intake") == "Posteingang"  # W5 цел
    assert cfg.get("board", {}).get("hidden") == ["terminal"]
    assert cfg.get("seo", {}).get("templates", {}).get("home", {}).get("title") == "Mein Titel"
    # UC6-7a: C-блоки страниц живут за presence-guard (pb_present) — форма без него
    # их не трогает.
    assert [b["id"] for b in cfg.get("page_blocks", {}).get("info", [])] == ["pb-x"]
    assert cfg.get("hero_title") == "Hallo"  # редактируемое поле применилось


def test_builder_theme_controls_are_the_single_source():
    """Тема живёт ТОЛЬКО в конструкторе главной: его форма всегда несёт font/
    hero_accent, и они применяются (единый источник W6)."""
    tenant = TenantFactory(
        disabled_modules=[], site_config={"font": "rounded", "hero_style": "accent"}
    )
    core_views.home_builder_view(
        _req("post", _user("w6b"), tenant, {"hero_title": "X", "font": "serif"})
    )
    tenant.refresh_from_db()
    assert tenant.site_config.get("font") == "serif"
    assert tenant.site_config.get("hero_style") == "plain"  # hero_accent не прислан


def test_theme_pickers_live_only_in_builder(settings):
    """W6/W11-5: контролы темы существуют в ОДНОМ месте — конструкторе главной."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(disabled_modules=[])
    html = core_views.home_builder_view(_req("get", _user("w6c"), tenant)).content.decode()
    assert 'name="hero_accent"' in html
    assert 'name="font"' in html
