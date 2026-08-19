"""ST-4a: админ-хоум — виджеты «что сегодня» + 5 хаб-плиток + SVG-иконсет.

План st4-admin-home-plan-2026-07-19.md §1: виджеты уважают модульные гейты и
все плитки ведут на живые URL.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.core import dashboard as dash
from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_TOUCHED = {"v": 2, "step": "language", "done": ["start"], "skipped": [], "completed": False}


def _req(tenant):
    request = RequestFactory().get("/dashboard/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant
    return request


def _tenant(**kw):
    kw.setdefault("site_config", {"onboarding": dict(_TOUCHED)})
    kw.setdefault("schema_name", kw.get("slug", "public"))
    return TenantFactory(business_type="bakery", **kw)


def test_home_widgets_gated_by_modules():
    """X2a (осознанная переписка): хаб-плитки удалены как дубль сайдбара —
    остаётся проверка виджетов «что сегодня» и их гейтов по модулям."""
    tenant = _tenant(slug="st4a", name="St4a", disabled_modules=[])
    widgets = dash.home_widgets(tenant)
    keys = {w["key"] for w in widgets}
    assert {"umsatz", "ready", "puls", "reviews"} <= keys
    for w in widgets:  # smoke: каждый виджет ведёт на живой URL
        assert reverse(w["url_name"])
    # Гейт модуля: без finance/orders виджеты исчезают.
    off = _tenant(slug="st4b", name="St4b", disabled_modules=["finance", "orders"])
    keys_off = {w["key"] for w in dash.home_widgets(off)}
    assert "umsatz" not in keys_off and "ready" not in keys_off


def test_home_renders_widgets_without_duplicate_tiles():
    """X2a: первый экран главной — виджеты и работа дня, БЕЗ плиток-дублей
    сайдбара. Ассерт на спрайт («ic-orders») снят осознанно: он оставался бы
    зелёным и без плиток (спрайт подключает базовый шаблон) — ложное покрытие."""
    tenant = _tenant(slug="st4c", name="St4c", disabled_modules=[])
    html = core_views.dashboard(_req(tenant)).content.decode()
    assert "Umsatz heute" in html and "<polyline" in html  # спарклайн
    assert 'href="#ic-orders"' not in html  # плиток-хабов больше нет


def test_sparkline_points_safe():
    assert dash._sparkline_points([]) == ""
    flat = dash._sparkline_points([0, 0, 0])
    assert flat.count(",") == 3  # три точки, не падает на нулях
    pts = dash._sparkline_points([1, 5, 3])
    assert len(pts.split()) == 3


def test_integrations_landing_gates_by_modules():
    tenant = _tenant(slug="st4e", name="St4e", disabled_modules=["publishing", "stays"])
    html = core_views.integrations_home(_req(tenant)).content.decode()
    assert "Zahlung &amp; Stripe" in html and "Eigene Domain" in html  # HTML-escape &
    assert "Channel Manager" not in html and "Publishing" not in html


def test_hotel_home_leads_to_belegungsplan_first():
    """Фидбэк 2026-07-28: отель — Belegungsplan главный вид продаж (вход
    первым), встроенный канбан остаётся дополнением."""
    tenant = TenantFactory(
        business_type="hotel",
        slug="st4h",
        name="St4h",
        schema_name="st4h",
        disabled_modules=["events", "booking"],
        site_config={"onboarding": dict(_TOUCHED)},
    )
    html = core_views.dashboard(_req(tenant)).content.decode()
    assert "Belegungsplan" in html
    assert "/dashboard/stays/" in html  # вход в календарь с главной

    bakery = _tenant(slug="st4i", name="St4i", disabled_modules=[])
    html = core_views.dashboard(_req(bakery)).content.decode()
    assert "Belegungsplan" not in html
