"""ST-5b (ревизия по фидбэку 2026-07-28): фиксированный маппинг раздела заказов.

Замки: «Verkäufе»/хаб-плитка всегда открывают архетип-дефолт (услуги/отель →
календарь, магазин → лента, прочее → канбан), недостижимое → kanban-фолбэк;
сегмент-контрол — чистая навигация ссылками (персист удалён, легаси-ключ
orders_view дропается нормализацией) + «＋ Buchung/Termin» третьим пунктом;
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


def test_normalize_drops_retired_orders_view_key():
    # Персист удалён (фидбэк 2026-07-28) — легаси-значения самоочищаются.
    assert "orders_view" not in siteconfig.normalize({"orders_view": "feed"})
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


def test_stored_choice_is_ignored_fixed_mapping():
    # Ключ в site_config (легаси после прежнего персиста) больше НЕ влияет:
    # отель с сохранённым "kanban" всё равно входит через Belegungsplan.
    t = TenantFactory(
        slug="ovp",
        name="OvP",
        disabled_modules=["events", "booking"],
        site_config={"orders_view": "kanban"},
    )
    assert ov.resolve_view(t) == "calendar"


def test_hotel_with_both_calendar_modules_enters_belegungsplan():
    # Демо-отель: booking И stays активны, primary = stays → «Verkäufe» обязан
    # открывать Belegungsplan (не booking-календарь), «＋» ведёт на walk-in.
    t = TenantFactory(slug="ovb2", name="OvB2", disabled_modules=["events"])
    assert t.is_module_active("booking") and t.is_module_active("stays")
    assert ov.entry_url_name(t) == "verkaeufe"  # W-CL: вход всегда единая страница
    assert ov.create_option(t)["url"].endswith("/stays/neu/")


def test_create_option_third_in_switch():
    # Отель → «＋ Buchung» — отдельная страница только с формой (stays:stay-new).
    hotel = TenantFactory(slug="ovn", name="OvN", disabled_modules=["events", "booking"])
    opts = ov.switch_options(hotel, "calendar")
    assert opts[-1]["view"] == "create" and opts[-1]["url"].endswith("/stays/neu/")
    # на самой странице «＋ Buchung» вкладка подсвечена
    assert ov.switch_options(hotel, "create")[-1]["active"] is True
    # Услуги (booking) → «＋ Termin» с якорем #neu.
    services = TenantFactory(slug="ovt", name="OvT", disabled_modules=["events", "stays"])
    opts = ov.switch_options(services, "calendar")
    assert opts[-1]["view"] == "create" and opts[-1]["url"].endswith("#neu")
    # Чистый магазин (без календарей) — третьего пункта нет.
    shop = TenantFactory(
        slug="ovm", name="OvM", disabled_modules=["events", "stays", "booking", "jobs"]
    )
    assert all(o["view"] != "create" for o in ov.switch_options(shop, "feed"))


def test_switch_renders_on_board():
    t = TenantFactory(slug="ovr", name="OvR", enabled_modules=["catalog", "orders"])
    body = core_views.board(_req(tenant=t)).content.decode()
    assert "data-ov-switch" in body and "Liste" in body


def test_hub_tile_orders_always_unified_page():
    # W-CL: плитка «Bestellungen» всегда ведёт на единую страницу продаж.
    t = TenantFactory(
        slug="ovh", name="OvH", disabled_modules=["events", "stays", "booking", "jobs"]
    )
    tiles = dash.hub_tiles(t)
    assert tiles[0]["key"] == "orders" and tiles[0]["url_name"] == "verkaeufe"
