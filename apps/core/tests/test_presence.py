"""LS-2 «Jetzt erreichbar»: presence-резолвер + normalize + бейдж + кабинет.

План docs/ls2-jetzt-erreichbar-plan-2026-07-19.md: авто по часам работы
(openinghours.open_status) + override on/off (presence-minimal в normalize);
бейдж витрины — wa.me-CTA, без Tenant.whatsapp_number не показывается.
"""

import uuid
from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory
from django.utils import timezone

from apps.core import presence
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ALL_HOURS = {str(d): ["00:00", "23:59"] for d in range(7)}


# --- normalize (presence-minimal, golden цел) ---------------------------------------


def test_normalize_presence_minimal():
    assert "presence" not in siteconfig.normalize({})
    assert "presence" not in siteconfig.normalize({"presence": {}})
    assert "presence" not in siteconfig.normalize({"presence": {"mode": "auto"}})
    assert "presence" not in siteconfig.normalize({"presence": {"mode": "junk"}})
    assert "presence" not in siteconfig.normalize({"presence": "garbage"})
    assert siteconfig.normalize({"presence": {"mode": "on"}})["presence"] == {"mode": "on"}
    assert siteconfig.normalize({"presence": {"mode": "off"}})["presence"] == {"mode": "off"}


# --- резолвер -----------------------------------------------------------------------


def test_available_now_modes():
    on = TenantFactory.build(site_config={"presence": {"mode": "on"}})
    off = TenantFactory.build(
        site_config={"presence": {"mode": "off"}}, opening_hours_structured=ALL_HOURS
    )
    assert presence.mode(on) == "on" and presence.available_now(on) is True
    assert presence.mode(off) == "off" and presence.available_now(off) is False


def test_available_now_auto_follows_hours():
    open_now = TenantFactory.build(opening_hours_structured=ALL_HOURS)
    assert presence.mode(open_now) == "auto"
    assert presence.available_now(open_now) is True
    # Часы есть, но не сейчас (окно в 1 минуту в полночь — почти наверняка закрыто).
    closed = TenantFactory.build(
        opening_hours_structured={str(timezone.localtime().weekday()): ["00:00", "00:01"]}
    )
    if timezone.localtime().strftime("%H:%M") > "00:01":
        assert presence.available_now(closed) is False
    # Часов нет → auto недоступен (владелец включает on вручную).
    assert presence.available_now(TenantFactory.build()) is False


# --- витрина: бейдж -----------------------------------------------------------------


def _home_html(tenant):
    from apps.promotions import public_views

    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.storefront_home(request).content.decode()


def test_storefront_badge_gates(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    # Доступен + номер → зелёный бейдж с wa.me.
    ready = TenantFactory.build(
        site_config={"presence": {"mode": "on"}}, whatsapp_number="+49 171 1234567"
    )
    html = _home_html(ready)
    assert "https://wa.me/491711234567" in html and "Jetzt erreichbar" in html
    # Режим on, но БЕЗ номера → бейджа нет.
    no_number = TenantFactory.build(site_config={"presence": {"mode": "on"}})
    assert "Jetzt erreichbar" not in _home_html(no_number)
    # Номер есть, но off → бейджа нет.
    off = TenantFactory.build(
        site_config={"presence": {"mode": "off"}}, whatsapp_number="+49 171 1234567"
    )
    assert "Jetzt erreichbar" not in _home_html(off)


# --- кабинет: endpoint (targeted-write) ---------------------------------------------


def test_set_presence_targeted_write(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core import views as core_views

    tenant = TenantFactory(
        schema_name="public",
        slug="prs",
        name="Prs",
        site_config={"classic_ui": True, "hero_title": "Hallo"},
    )

    def _req(mode_value):
        request = RequestFactory().post("/dashboard/presence/", {"mode": mode_value})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        o = uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
        request.tenant = tenant
        return request

    core_views.set_presence_view(_req("on"))
    tenant.refresh_from_db()
    assert tenant.site_config["presence"] == {"mode": "on"}
    assert tenant.site_config["classic_ui"] is True  # чужие ключи целы
    assert tenant.site_config["hero_title"] == "Hallo"

    core_views.set_presence_view(_req("auto"))
    tenant.refresh_from_db()
    assert "presence" not in tenant.site_config  # auto = ключа нет
