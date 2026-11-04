"""UX-D D8.1: главная = сводка дня у заказов, записей, заявок и билетов.

План — docs/ux-d8-archetype-parity-plan-2026-11-04.md. Числа сводки — из тех же
источников, что экраны, куда ведут ссылки (Offene Posten, вид «Heute», доска).
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.core import day_home
from apps.core import views as core_views
from apps.core.models import Membership
from apps.crm.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_TOUCHED = {"v": 2, "step": "company", "done": ["start"], "skipped": [], "completed": False}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(bt):
    from apps.core.modules import default_disabled_for

    return TenantFactory(
        slug=f"d8-{bt[:5]}-{uuid4().hex[:4]}",
        name="D8",
        business_type=bt,
        site_config={"onboarding": dict(_TOUCHED)},
        disabled_modules=list(default_disabled_for(bt)),
    )


def _req(tenant, role=Membership.ROLE_OWNER):
    req = RequestFactory().get("/dashboard/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    tag = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"d8-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


def _customer():
    return Customer.objects.create(name="Erika Muster", email=f"e-{uuid4().hex[:6]}@t.de")


def _order(**kw):
    from apps.orders.models import Order

    code = "O-" + uuid4().hex[:6].upper()
    return Order.objects.create(
        customer=_customer(), total=Decimal("12.50"), reference_code=code, **kw
    )


@pytest.mark.parametrize(
    ("business_type", "kind"),
    [("bakery", "order"), ("friseur", "booking"), ("catering", "job"), ("tour_operator", "ticket")],
)
def test_home_is_day_summary_for_every_sales_kind(business_type, kind):
    html = core_views.dashboard(_req(_tenant(business_type))).content.decode()
    assert f'data-day-home="{kind}"' in html
    assert "Braucht Aufmerksamkeit" in html and "Nicht bezahlt" in html
    # рабочая поверхность — на «Verkäufe», а не второй раз на главной
    assert f"/dashboard/verkaeufe/?tab={kind}" in html
    assert "data-drop-stage" not in html


def test_hotel_keeps_its_own_summary():
    html = core_views.dashboard(_req(_tenant("hotel"))).content.decode()
    assert "data-hotel-home" in html and "data-day-home" not in html


def test_unpaid_equals_open_items_rows():
    """«Nicht bezahlt» — ровно строки Offene Posten (одно правило, числа не расходятся)."""
    from apps.finance import bank

    t = _tenant("bakery")
    _order(status="new", payment_method="vorkasse", payment_state="unpaid")
    req = _req(t)
    ctx = day_home.summary(req, "order")
    rows = bank.deal_open_items(t, "order")
    assert ctx["dh_unpaid"]["count"] == len(rows)
    assert ctx["dh_unpaid"]["amount"] == sum((r["amount"] for r in rows), Decimal("0"))


def test_new_count_follows_pipeline_stage():
    t = _tenant("bakery")
    _order(status="new")
    _order(status="new")
    ctx = day_home.summary(_req(t), "order")
    assert ctx["dh_new_n"] == 2 and len(ctx["dh_new"]) == 2
    # код заказа не повторяется дважды в подписи
    sub = ctx["dh_new"][0]["subtitle"]
    assert sub.count(sub.split(" · ")[-1]) == 1


def test_week_counts_by_event_date():
    t = _tenant("bakery")
    tomorrow = timezone.now() + timedelta(days=1)
    _order(status="confirmed", pickup_slot=tomorrow)
    week = day_home.summary(_req(t), "order")["dh_week"]
    assert len(week) == 7 and week[1]["n"] == 1 and week[0]["n"] == 0


def test_job_upcoming_has_no_seven_day_cap():
    """Кейтеринг планирует на месяцы вперёд — ближайшая заявка видна и через 40 дней."""
    from apps.jobs.models import Job

    t = _tenant("catering")
    Job.objects.create(
        customer=_customer(),
        title="Hochzeit",
        reference_code="A-" + uuid4().hex[:6].upper(),
        event_date=timezone.localdate() + timedelta(days=40),
    )
    items = day_home.summary(_req(t), "job")["dh_items"]
    assert any("Hochzeit" in (i["subtitle"] or "") for i in items)


def test_broken_source_does_not_break_home(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(day_home, "_stage_counts", boom)
    monkeypatch.setattr(day_home, "_week", boom)
    html = core_views.dashboard(_req(_tenant("bakery"))).content.decode()
    assert 'data-day-home="order"' in html


def test_query_count_does_not_grow_with_orders():
    t = _tenant("bakery")
    req = _req(t)

    def run():
        with CaptureQueriesContext(connection) as ctx:
            day_home.summary(req, "order")
        return len(ctx.captured_queries)

    _order(status="new")
    run()
    few = run()
    for _i in range(6):
        _order(status="new")
    assert run() <= few + 2  # список «Neu» ограничен NEW_LIMIT


def test_without_sales_right_no_summary(monkeypatch):
    from apps.core import permissions

    monkeypatch.setattr(permissions, "chrome_allows", lambda user, key: key != "verkaeufe.view")
    html = core_views.dashboard(_req(_tenant("bakery"))).content.decode()
    assert "data-day-home" not in html


def test_kpi_today_label_says_today():
    html = core_views.dashboard(_req(_tenant("bakery"))).content.decode()
    assert "Abholungen heute" in html


def test_staff_without_finance_right_gets_no_finance_link():
    """Цифра «Nicht bezahlt» не ведёт в 403: ссылка — только при праве на Offene Posten."""
    t = _tenant("bakery")
    t.disabled_modules = [m for m in t.disabled_modules if m != "finance"]
    t.save(update_fields=["disabled_modules"])
    assert t.is_module_active("finance")
    owner = day_home.summary(_req(t), "order")
    staff = day_home.summary(_req(t, role=Membership.ROLE_STAFF), "order")
    assert owner["dh_finance_link"] is True
    assert staff["dh_finance_link"] is False
    html = core_views.dashboard(_req(t, role=Membership.ROLE_STAFF)).content.decode()
    assert "/finance/offene/" not in html


def test_heute_list_reads_only_own_columns(monkeypatch):
    """Сводка заказов не считает колонки записей/номеров (M1 ревью)."""
    from apps.core import sales_page

    seen = {}
    real = sales_page.heute_columns

    def spy(tenant, user=None, sections=None):
        seen["sections"] = sections
        return real(tenant, user, sections=sections)

    monkeypatch.setattr(sales_page, "heute_columns", spy)
    day_home.summary(_req(_tenant("bakery")), "order")
    assert seen["sections"] == {"orders"}
