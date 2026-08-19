"""X3 «главная-кокпит» (план cabinet-cleanup-2026-08-19 §6, вариант B).

Замки ставятся ДО рефактора: тело единой страницы продаж извлекается в партиал
и переиспользуется главной, поэтому сначала фиксируем ТЕКУЩИЙ рендер Verkäufe
для всех сочетаний (kind, view) — рефактор обязан быть паритетным.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant, path="/dashboard/verkaeufe/", data=None):
    req = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    return req


def _tenant(bt, **kw):
    return TenantFactory(slug=f"x3-{bt[:6]}-{uuid4().hex[:4]}", name="X3", business_type=bt, **kw)


# --- характеризация: тело Verkäufe по видам (паритет рефактора) ---------------


@pytest.mark.parametrize(
    ("business_type", "tab", "view", "marker"),
    [
        ("hotel", "stay", "kalender", "data-unit"),  # Belegungsplan (шахматка)
        ("friseur", "booking", "kalender", "Tage blockieren"),  # Tagesplan
        ("bakery", "order", "board", "data-drop-stage"),  # канбан
        ("bakery", "order", "liste", "Alle Status"),  # список заказов (DE-рендер)
    ],
)
def test_verkaeufe_body_renders_expected_engine(business_type, tab, view, marker):
    t = _tenant(business_type, disabled_modules=[])
    html = core_views.verkaeufe(_req(t, data={"tab": tab, "view": view})).content.decode()
    assert marker in html, f"{business_type}/{tab}/{view}: тело движка не отрендерилось"
