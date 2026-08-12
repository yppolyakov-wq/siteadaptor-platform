"""DS-3b (Fokus): композиция первого экрана — split-hero, CTA в шапке (nav.cta),
секция anfrage на главной, trust compact. План ds3-fokus-output-views-plan §DS-3b.
Характеризация: без новых ключей всё рендерится как раньше."""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _home(tenant):
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.storefront_home(request).content.decode()


# ── split-hero ───────────────────────────────────────────────────────────────


def test_hero_split_renders_photo_and_text_panel():
    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "hero", "enabled": True}],  # hero в реестре off-дефолт
            "hero_style": "split",
            "hero_title": "Ihr Fest",
            "hero_text": "Unser Buffet.",
            "hero_image": "/media/hero.jpg",
        }
    )
    html = _home(tenant)
    assert "data-hero-split" in html
    assert "Ihr Fest" in html and "Unser Buffet." in html
    assert 'src="/media/hero.jpg"' in html
    assert "data-hero-slider" not in html  # слайдер при split не рендерится


def test_hero_split_takes_first_slide_when_no_flat_image():
    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "hero", "enabled": True}],
            "hero_style": "split",
            "heroes": [{"image": "/media/slide1.jpg", "title": "A"}],
        }
    )
    html = _home(tenant)
    assert "data-hero-split" in html and 'src="/media/slide1.jpg"' in html


def test_hero_slider_unchanged_without_split():
    # Характеризация: heroes без split — прежний full-bleed слайдер.
    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "hero", "enabled": True}],
            "heroes": [{"image": "/media/a.jpg"}, {"image": "/media/b.jpg"}],
        }
    )
    html = _home(tenant)
    assert "data-hero-slider" in html and "data-hero-split" not in html


def test_normalize_hero_split_valid():
    assert siteconfig.normalize({"hero_style": "split"})["hero_style"] == "split"
    assert siteconfig.normalize({"hero_style": "junk"})["hero_style"] == "plain"


# ── nav.cta ──────────────────────────────────────────────────────────────────


def test_nav_cta_presence_minimal():
    assert "cta" not in siteconfig.normalize({})["nav"]
    assert "cta" not in siteconfig.normalize({"nav": {"cta": False}})["nav"]
    assert siteconfig.normalize({"nav": {"cta": True}})["nav"]["cta"] is True


def test_nav_cta_button_rendered_for_primary_action():
    # jobs-primary (booking/orders выключены) → CTA шапки ведёт на /anfrage/.
    tenant = TenantFactory.build(
        site_config={"nav": {"cta": True}, "primary_module": "jobs"},
        disabled_modules=["orders", "booking", "stays", "events"],
    )
    html = _home(tenant)
    assert "data-nav-cta" in html
    assert 'href="/anfrage/"' in html


def test_no_nav_cta_by_default():
    tenant = TenantFactory.build()
    assert "data-nav-cta" not in _home(tenant)


# ── секция anfrage на главной ────────────────────────────────────────────────


def test_anfrage_section_off_by_default_and_module_gated():
    # Дефолт: секция в реестре, но выключена → формы на главной нет.
    tenant = TenantFactory.build()
    assert 'action="/anfrage/"' not in _home(tenant)
    # Включена + jobs активен → мини-форма AF-2 на главной.
    on = TenantFactory.build(
        site_config={
            "sections": [{"key": "hero", "enabled": True}, {"key": "anfrage", "enabled": True}]
        }
    )
    assert 'action="/anfrage/"' in _home(on)
    # Включена, но jobs выключен → fail-closed пусто.
    off = TenantFactory.build(
        site_config={"sections": [{"key": "anfrage", "enabled": True}]},
        disabled_modules=["jobs"],
    )
    assert 'action="/anfrage/"' not in _home(off)


# ── trust compact ────────────────────────────────────────────────────────────


def test_trust_compact_band_with_quotes():
    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "trust", "enabled": True, "style": "compact"}],
            "trust": {"since": "2012", "marks": ["Bio"]},
            "testimonials": [
                {"name": "Familie Sommer", "text": "Alles frisch!", "stars": 5},
                {"name": "Miriam K.", "text": "Angebot am nächsten Tag.", "stars": 5},
                {"name": "Dritte Person", "text": "Nicht im Band.", "stars": 5},
            ],
        }
    )
    html = _home(tenant)
    assert "Alles frisch!" in html and "Angebot am nächsten Tag." in html
    assert "Nicht im Band." not in html  # compact берёт ДВЕ первые цитаты
    assert "✓ Bio" in html
    assert siteconfig.normalize(
        {"sections": [{"key": "trust", "enabled": True, "style": "compact"}]}
    )
