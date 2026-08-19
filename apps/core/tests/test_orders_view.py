"""ST-5b → W10-1: архетип-дефолт представления продаж + смерть сегмента.

Замки: resolve_view даёт архетип-дефолт (услуги/отель → календарь, магазин →
лента, прочее → канбан), недостижимое → kanban-фолбэк; легаси-ключ orders_view
дропается нормализацией; W10-1 — сегмент ST-5b удалён (легаси-страницы несут
только мостик на Verkäufe), переключение вида на Verkäufe сохраняет GET.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

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
    # Демо-отель: booking И stays активны, primary = stays → архетип-дефолт
    # календарь; вход «Verkäufe» — всегда единая страница (W-CL).
    t = TenantFactory(slug="ovb2", name="OvB2", disabled_modules=["events"])
    assert t.is_module_active("booking") and t.is_module_active("stays")
    assert ov.entry_url_name(t) == "verkaeufe"
    assert ov.resolve_view(t) == "calendar"


def test_segment_removed_bridge_remains():
    # W10-1: сегмент ST-5b мёртв — на легаси-доске только мостик на Verkäufe.
    t = TenantFactory(slug="ovr", name="OvR", enabled_modules=["catalog", "orders"])
    body = core_views.board(_req(tenant=t)).content.decode()
    assert "data-ov-switch" not in body
    assert "Alles auf einer Seite" in body
    assert not hasattr(ov, "switch_options")  # API удалён, не «забыт»


def test_verkaeufe_view_switch_preserves_get_params():
    # W10-1: переключение вида возвращает на ПОЛНЫЙ исходный путь (next=).
    t = TenantFactory(slug="ovg", name="OvG", disabled_modules=["events", "booking"])
    resp = core_views.verkaeufe_view_set(
        _req(
            "post",
            {
                "kind": "stay",
                "view": "board",
                "next": "/dashboard/verkaeufe/?tab=stay&von=2026-09-01",
            },
            tenant=t,
            path="/dashboard/verkaeufe/view/",
        )
    )
    assert resp["Location"] == "/dashboard/verkaeufe/?tab=stay&von=2026-09-01"
    t.refresh_from_db()
    assert t.site_config["sales_views"]["stay"] == "board"
    # внешний/протокол-относительный next отбрасывается
    resp = core_views.verkaeufe_view_set(
        _req(
            "post",
            {"kind": "stay", "view": "kalender", "next": "//evil.example/x"},
            tenant=t,
            path="/dashboard/verkaeufe/view/",
        )
    )
    assert resp["Location"].startswith("/dashboard/verkaeufe/")


# X2a: плитка «Bestellungen» удалена (дубль якоря «Verkäufe» под другим именем);
# entry_url_name остаётся под замками test_verkaeufe/test_orders_view выше.
