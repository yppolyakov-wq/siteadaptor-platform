"""Фидбэк владельца 2026-08-25: блог — «поделиться и выбрать канал где»;
страница каналов — личные каналы связи (соцсети, Telegram и т. д.).
"""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _tenant(**kw):
    kw.setdefault("business_type", "retail")
    kw.setdefault("disabled_modules", [])
    return TenantFactory(schema_name=f"t{uuid.uuid4().hex[:8]}", **kw)


def _req(path="/dashboard/", tenant=None):
    req = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant or _tenant()
    return req


def test_share_targets_build_direct_links():
    from apps.core.share_links import share_targets

    rows = {t["key"]: t["url"] for t in share_targets("Neue Torte", "https://x.de/blog/torte")}
    assert rows["whatsapp"].startswith("https://wa.me/?text=")
    assert "t.me/share/url" in rows["telegram"]
    assert "facebook.com/sharer" in rows["facebook"]
    assert rows["email"].startswith("mailto:")
    assert "https%3A%2F%2Fx.de%2Fblog%2Ftorte" in rows["whatsapp"]  # ссылка закодирована


def test_blog_row_offers_channel_choice():
    """«Кнопка поделиться и выбрать канал где» — меню каналов у статьи."""
    from apps.events import views as event_views
    from apps.events.models import BlogPost

    BlogPost.objects.create(title="Neue Torte", slug="neue-torte", is_published=True)
    html = event_views.blog_list(_req("/dashboard/blog/")).content.decode()
    assert "data-share-menu" in html
    assert "wa.me" in html and "t.me/share/url" in html
    assert "＋" in html or "New post" in html  # кнопка создания на месте


def test_channels_page_lists_personal_channels():
    """Страница каналов показывает и личные каналы связи."""
    from apps.publishing import views as pub_views

    tenant = _tenant(whatsapp_number="+4915112345678", instagram="backhaus")
    html = pub_views.channels(_req("/publishing/channels/", tenant)).content.decode()
    assert "Persönliche Kanäle" in html
    assert "WhatsApp" in html and "Telegram" in html
    assert "+4915112345678" in html  # готовый канал показывает значение
    assert "Instagram" in html  # соцпрофиль из GK-9


def test_personal_channels_are_fail_safe_without_settings():
    from apps.core.personal_channels import personal_channels

    rows = personal_channels(_tenant())
    keys = {r["key"] for r in rows}
    assert {"whatsapp", "telegram", "email", "inbox"} <= keys
    assert all(r["url"].startswith("/") for r in rows)  # каждая карточка ведёт на экран
    assert personal_channels(None) == []
