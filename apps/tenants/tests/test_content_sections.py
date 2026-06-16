"""M20 ⑤a: контент-секции витрины (FAQ / CTA / Testimonials)."""

import pytest

from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def test_normalize_sanitizes_content_sections():
    cfg = siteconfig.normalize(
        {
            "faq": [{"q": "Parken?", "a": "Ja"}, {"q": "", "a": "ignore"}],  # пустой q → выкинут
            "testimonials": [{"name": "Anna", "text": "Top"}],
            "cta": {"title": "Jetzt buchen", "button_url": "/termin/", "button_label": "Los"},
        }
    )
    assert cfg["faq"] == [{"q": "Parken?", "a": "Ja"}]
    assert cfg["testimonials"] == [{"name": "Anna", "text": "Top"}]
    assert cfg["cta"]["title"] == "Jetzt buchen"
    assert cfg["cta"]["button_url"] == "/termin/"


def test_pairs_text_roundtrip():
    pairs = siteconfig.text_to_pairs("Frage? | Antwort\nNur Frage\n\n", "q", "a")
    assert pairs == [{"q": "Frage?", "a": "Antwort"}, {"q": "Nur Frage", "a": ""}]
    text = siteconfig.pairs_to_text(pairs, "q", "a")
    assert "Frage? | Antwort" in text
    assert "Nur Frage" in text


def test_content_sections_registered_default_off():
    cfg = siteconfig.normalize({})
    keys = {s["key"] for s in cfg["sections"]}
    assert {"faq", "cta", "testimonials"} <= keys
    # по умолчанию выключены (легаси-витрины не меняются)
    off = {s["key"]: s["enabled"] for s in cfg["sections"]}
    assert off["faq"] is False and off["cta"] is False and off["testimonials"] is False


def test_storefront_home_renders_faq_when_enabled():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.promotions import public_views
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "faq", "enabled": True}],
            "faq": [{"q": "Habt ihr Parkplätze?", "a": "Ja, direkt davor."}],
        }
    )
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    resp = public_views.storefront_home(req)
    assert resp.status_code == 200
    assert b"Habt ihr Parkpl" in resp.content


def test_normalize_keeps_hero_image():
    cfg = siteconfig.normalize({"hero_image": "  https://img.test/x.jpg  "})
    assert cfg["hero_image"] == "https://img.test/x.jpg"
    assert siteconfig.normalize({})["hero_image"] == ""


def test_storefront_home_renders_hero_photo_banner():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.promotions import public_views
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "hero", "enabled": True}],
            "hero_title": "Willkommen",
            "hero_image": "https://img.test/banner.jpg",
        }
    )
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    resp = public_views.storefront_home(req)
    assert resp.status_code == 200
    assert b"https://img.test/banner.jpg" in resp.content
