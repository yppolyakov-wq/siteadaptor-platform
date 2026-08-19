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


# Свежий тенант вьюха главной уводит в мастер — помечаем онбординг тронутым.
_TOUCHED = {"v": 2, "step": "company", "done": ["start"], "skipped": [], "completed": False}


def _tenant(bt, **kw):
    from apps.core.modules import default_disabled_for

    kw.setdefault("site_config", {"onboarding": dict(_TOUCHED)})
    # Реальный набор модулей архетипа: при disabled_modules=[] активны ВСЕ
    # модули и primary становится events у любого типа — нежизненный случай.
    kw.setdefault("disabled_modules", list(default_disabled_for(bt)))
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
    t = _tenant(business_type)
    html = core_views.verkaeufe(_req(t, data={"tab": tab, "view": view})).content.decode()
    assert marker in html, f"{business_type}/{tab}/{view}: тело движка не отрендерилось"


# --- X3: главная = петля архетипа --------------------------------------------


@pytest.mark.parametrize(
    ("business_type", "marker"),
    [
        ("hotel", "data-unit"),  # шахматка номеров (Belegungsplan)
        ("friseur", "Tage blockieren"),  # дневной план записей (Tagesplan)
        ("bakery", "Alle Status"),  # очередь заказов списком (рыночный дефолт ритейла)
    ],
)
def test_home_renders_archetype_loop(business_type, marker):
    """Первый экран показывает РАБОТУ ДНЯ архетипа тем же телом, что Verkäufe."""
    t = _tenant(business_type)
    html = core_views.dashboard(_req(t, path="/dashboard/")).content.decode()
    assert marker in html, f"{business_type}: петля архетипа не отрендерилась"


def test_home_has_single_today_strip_and_no_duplicate_kanban():
    """X3: над петлёй ОДНА полоса чисел дня; отдельной сводки «Heute» и второго
    канбана «Tasks» больше нет — они показывали те же сделки."""
    t = _tenant("bakery")
    html = core_views.dashboard(_req(t, path="/dashboard/")).content.decode()
    assert "Jetzt erreichbar" in html or "Gerade nicht erreichbar" in html  # присутствие в полосе
    assert html.count("data-drop-stage") == 0 or "Tasks" not in html


def test_home_without_sales_modules_gives_honest_hint():
    """Пустая петля — не мёртвый экран: honest hint со ссылкой на «Funktionen»."""
    t = _tenant(
        "other",
        disabled_modules=["orders", "booking", "stays", "events", "jobs", "promotions"],
    )
    html = core_views.dashboard(_req(t, path="/dashboard/")).content.decode()
    assert "Noch keine Verkaufskanäle aktiv" in html
