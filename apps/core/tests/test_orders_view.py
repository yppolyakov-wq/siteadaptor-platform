"""ST-5b: представление раздела заказов — Канбан ⇄ Календарь ⇄ Лента.

Замки: normalize хранит ключ presence-minimal, дефолт по архетипу (услуги/
отель → календарь, магазин → лента, прочее → канбан), недостижимое →
kanban-фолбэк, сеттер персистит и редиректит, сегмент-контрол рендерится на
доске и НЕ рендерится в classic_ui, хаб-плитка уважает выбор.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import dashboard as dash
from apps.core import orders_view as ov
from apps.core import views as core_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, tenant=None, path="/dashboard/board/"):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    req.tenant = tenant
    return req


def test_normalize_orders_view_presence_minimal():
    assert siteconfig.normalize({"orders_view": "feed"})["orders_view"] == "feed"
    assert "orders_view" not in siteconfig.normalize({"orders_view": "bogus"})
    assert "orders_view" not in siteconfig.normalize({})


def test_default_view_by_archetype():
    # primary_module идёт по _PRIORITY среди активных → архетип задаём
    # отключением модулей с бо́льшим приоритетом (не-premium активны у всех).
    services = TenantFactory(slug="ovb", name="OvB", disabled_modules=["events", "stays"])
    assert ov.resolve_view(services) == "calendar"  # услуги → календарь
    shop = TenantFactory(
        slug="ovs", name="OvS", disabled_modules=["events", "stays", "booking", "jobs"]
    )
    assert ov.resolve_view(shop) == "feed"  # магазин → лента
    events = TenantFactory(slug="ove", name="OvE")
    assert ov.resolve_view(events) == "kanban"  # events первым в _PRIORITY


def test_unreachable_choice_falls_back_to_kanban():
    t = TenantFactory(
        slug="ovf",
        name="OvF",
        disabled_modules=["booking", "stays"],  # календарь недостижим
        site_config={"orders_view": "calendar"},
    )
    assert ov.resolve_view(t) == "kanban"
    assert ov.entry_url_name(t) == "board"


def test_setter_persists_and_redirects_to_view():
    t = TenantFactory(slug="ovp", name="OvP", enabled_modules=["catalog", "orders"])
    resp = core_views.set_orders_view(
        _req("post", {"view": "kanban"}, t, path="/dashboard/orders-view/")
    )
    assert resp.status_code == 302 and resp.url.endswith("/board/")
    t.refresh_from_db()
    assert t.site_config["orders_view"] == "kanban"
    # невалидное значение = сброс на архетип-дефолт (ключ удаляется)
    core_views.set_orders_view(_req("post", {"view": "zzz"}, t, path="/dashboard/orders-view/"))
    t.refresh_from_db()
    assert "orders_view" not in t.site_config


def test_switch_renders_on_board_and_hidden_in_classic():
    t = TenantFactory(slug="ovr", name="OvR", enabled_modules=["catalog", "orders"])
    body = core_views.board(_req(tenant=t)).content.decode()
    assert "/dashboard/orders-view/" in body and "Liste" in body
    classic = TenantFactory(
        slug="ovc",
        name="OvC",
        enabled_modules=["catalog", "orders"],
        site_config={"classic_ui": True},
    )
    body_c = core_views.board(_req(tenant=classic)).content.decode()
    assert "/dashboard/orders-view/" not in body_c


def test_hub_tile_orders_honors_choice():
    t = TenantFactory(
        slug="ovh",
        name="OvH",
        enabled_modules=["catalog", "orders"],
        site_config={"orders_view": "feed"},
    )
    tiles = dash.hub_tiles(t)
    assert tiles[0]["key"] == "orders" and tiles[0]["url_name"] == "orders:order-list"
