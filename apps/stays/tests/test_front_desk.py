"""PMS-A «стойка»: walk-in паритет с витриной, экран «Heute», оплата на стойке.

План docs/pms-a-front-desk-plan-2026-07-28.md."""

import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.stays import services, views
from apps.stays.models import RatePlan, StayBooking, StayUnit

pytestmark = pytest.mark.django_db

D0 = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/stays/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _cal(req):
    """W10-6: stays:calendar — 302; тело Belegungsplan характеризуем через
    вкладку stay единой страницы (тот же calendar_context)."""
    from apps.core import views as core_views
    from apps.core.modules import default_disabled_for
    from apps.tenants.tests.factories import TenantFactory

    get = req.GET.copy()
    get["tab"], get["view"] = "stay", "kalender"
    req.GET = get
    if getattr(req, "tenant", None) is None:  # тест мог выставить своего (site_config)
        req.tenant = TenantFactory.build(
            business_type="hotel", disabled_modules=list(default_disabled_for("hotel"))
        )
    return core_views.verkaeufe(req)


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 8000)
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kwargs)


# --- A1: walk-in паритет ------------------------------------------------------


def test_walkin_full_parity_rate_extras_children_note():
    from apps.core.models import Extra

    unit = _unit(max_guests=4)
    rate = RatePlan.objects.create(name="Mit Frühstück", surcharge_cents=1200)
    extra = Extra.objects.create(label="Sekt", price_cents=500, scope="stays")
    resp = views.stay_create(
        _req(
            "post",
            "/dashboard/stays/new/",
            {
                "unit": str(unit.pk),
                "arrival": D0.isoformat(),
                "departure": (D0 + timedelta(days=2)).isoformat(),
                "name": "Familie Korn",
                "erw": "2",
                "kinder": "1",
                "rate_plan": str(rate.pk),
                "extra": [str(extra.pk)],
                "note": "Späte Anreise",
            },
        )
    )
    assert resp.status_code == 302
    b = StayBooking.objects.get()
    assert (b.adults, b.children, b.guests) == (2, 1, 3)
    assert b.rate_plan_id == rate.pk and b.rate_snapshot["name"] == "Mit Frühstück"
    assert [x["label"] for x in b.extras] == ["Sekt"]
    assert b.note == "Späte Anreise"
    # 2 ночи × (8000 + 1200 тариф) + 500 extra (без Kurtaxe в дефолте)
    assert b.total_cents == 2 * 9200 + 500
    assert b.status == StayBooking.STATUS_CONFIRMED  # walk-in сразу confirmed


def test_walkin_legacy_guests_field_still_works():
    unit = _unit()
    resp = views.stay_create(
        _req(
            "post",
            "/dashboard/stays/new/",
            {
                "unit": str(unit.pk),
                "arrival": D0.isoformat(),
                "departure": (D0 + timedelta(days=1)).isoformat(),
                "guests": "2",
            },
        )
    )
    assert resp.status_code == 302
    b = StayBooking.objects.get()
    assert (b.adults, b.children, b.guests) == (2, 0, 2)


def test_walkin_invalid_voucher_is_error_not_500():
    unit = _unit()
    resp = views.stay_create(
        _req(
            "post",
            "/dashboard/stays/new/",
            {
                "unit": str(unit.pk),
                "arrival": D0.isoformat(),
                "departure": (D0 + timedelta(days=1)).isoformat(),
                "voucher_code": "GIBTS-NICHT",
            },
        )
    )
    assert resp.status_code == 302  # редирект с ошибкой, раньше — 500
    assert not StayBooking.objects.exists()


def test_calendar_form_shows_rate_and_extras():
    from apps.core.models import Extra

    _unit()
    RatePlan.objects.create(name="Halbpension Plus", surcharge_cents=2500)
    Extra.objects.create(label="Parkplatz", price_cents=700, scope="stays")
    body = _cal(_req()).content.decode()
    assert "Halbpension Plus" in body and "Parkplatz" in body
    assert 'name="erw"' in body and 'name="kinder"' in body and 'name="note"' in body


# --- A3: оплата на стойке -----------------------------------------------------


def test_mark_paid_and_refunded_guard():
    unit = _unit()
    b = services.book_stay(
        unit,
        arrival=D0,
        departure=D0 + timedelta(days=1),
        name="Gast Bar",
        auto_confirm=True,
    )
    assert b.payment_state == StayBooking.PAYMENT_NONE
    resp = views.stay_action(
        _req("post", f"/dashboard/stays/{b.pk}/action/", {"action": "mark_paid"}), pk=b.pk
    )
    assert resp.status_code == 302 and f"buchung={b.pk}" in resp["Location"]
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_PAID

    b.payment_state = StayBooking.PAYMENT_REFUNDED
    b.save(update_fields=["payment_state"])
    views.stay_action(
        _req("post", f"/dashboard/stays/{b.pk}/action/", {"action": "mark_paid"}), pk=b.pk
    )
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_REFUNDED  # не перетирается


# --- A2: экран «Heute» --------------------------------------------------------


def test_today_view_sections():
    unit = _unit(quantity=5)
    today = timezone.localdate()

    def _b(name, arr, dep, **kw):
        return services.book_stay(
            unit,
            arrival=arr,
            departure=dep,
            name=name,
            auto_confirm=kw.pop("auto_confirm", True),
            **kw,
        )

    _b("Ankunft Heute", today, today + timedelta(days=2))
    _b("Abreise Heute", today - timedelta(days=2), today)
    _b("Im Haus Gast", today - timedelta(days=1), today + timedelta(days=1))
    _b("Zukunft Gast", today + timedelta(days=5), today + timedelta(days=7))
    cancelled = _b("Storniert Gast", today, today + timedelta(days=1))
    from apps.stays.state_machine import StayBookingSM

    StayBookingSM().apply(cancelled, "cancelled")

    # W10-6: stays:today — 302; секции (вкл. «Im Haus» — паритет!) живут на
    # виде «Heute» единой страницы.
    resp = views.today_view(_req(path="/dashboard/stays/heute/"))
    assert resp.status_code == 302 and "view=heute" in resp["Location"]

    from apps.core import views as core_views
    from apps.core.modules import default_disabled_for
    from apps.tenants.tests.factories import TenantFactory

    req = _req(path="/dashboard/verkaeufe/", data={"view": "heute"})
    req.tenant = TenantFactory.build(
        business_type="hotel", disabled_modules=list(default_disabled_for("hotel"))
    )
    body = core_views.verkaeufe(req).content.decode()
    assert "Ankunft Heute" in body
    assert "Abreise Heute" in body
    assert "Im Haus Gast" in body
    assert "Zukunft Gast" not in body
    assert "Storniert Gast" not in body


def test_home_widget_counts_arrivals_and_departures():
    from apps.core import dashboard as dash
    from apps.tenants.tests.factories import TenantFactory

    unit = _unit(quantity=5)
    today = timezone.localdate()
    services.book_stay(
        unit, arrival=today, departure=today + timedelta(days=2), name="A", auto_confirm=True
    )
    services.book_stay(
        unit, arrival=today - timedelta(days=2), departure=today, name="B", auto_confirm=True
    )
    tenant = TenantFactory(slug="fdesk", name="FDesk", business_type="hotel")
    widgets = {w["key"]: w for w in dash.home_widgets(tenant)}
    assert widgets["stays_today"]["value"] == "1"
    assert "1" in widgets["stays_today"]["hint"]

    off = TenantFactory(slug="fdesk2", name="FDesk2", disabled_modules=["stays"])
    assert "stays_today" not in {w["key"] for w in dash.home_widgets(off)}
