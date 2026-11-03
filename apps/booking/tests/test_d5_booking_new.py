"""UX-D D5.0: «＋ Neuer Termin» — ручная запись шторкой со строгим разбором.

Старая форма под Tagesplan разбирала мягко: мусор в «Personen» молча давал 1 гостя,
устаревшая услуга — запись без услуги на 0 €; «Trotzdem eintragen» был флажком, который
надо было найти заранее."""

import json
import re
import uuid
from datetime import date, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.booking import booking_new_views as v
from apps.booking.models import AvailabilityRule, Booking, Resource, Service
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
URL = "/dashboard/booking/termin/neu/"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, drawer=True):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(URL, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(business_type="friseur", disabled_modules=[])
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    return req


def _day():
    d = date.today() + timedelta(days=7)
    while d.weekday() != 1:  # вторник
        d += timedelta(days=1)
    return d


def _master(**kw):
    r = Resource.objects.create(name="Anna", type=Resource.TYPE_STAFF, **kw)
    AvailabilityRule.objects.create(resource=r, weekday=1, start_time=time(9), end_time=time(18))
    return r


def _post(data, drawer=True):
    return v.booking_new(_req("post", data, drawer=drawer))


def test_fragment_is_marked_and_has_no_scripts():
    _master()
    resp = v.booking_new(_req())
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "<script" not in html
    assert not re.search(r"\son[a-z]+=", html)
    assert "data-drawer-title=" in html and "data-drawer-form" in html


def test_every_field_has_a_visible_label():
    _master()
    Service.objects.create(name="Haarschnitt", duration_minutes=30)
    html = v.booking_new(_req()).content.decode()
    for field in ("resource", "date", "time", "service", "name", "phone", "email", "minutes"):
        assert f'for="bn-{field}"' in html, field


def test_prefill_from_free_slot():
    r = _master()
    html = v.booking_new(
        _req(data={"resource": str(r.pk), "start": f"{_day().isoformat()}T10:30"})
    ).content.decode()
    assert re.search(rf'<option value="{r.pk}" selected', html)
    assert f'value="{_day().isoformat()}"' in html and 'value="10:30"' in html


def test_foreign_resource_prefill_is_not_selected_silently():
    _master()
    html = v.booking_new(_req(data={"resource": str(uuid.uuid4())})).content.decode()
    assert '<option value="">—</option>' in html and " selected" not in html.split("bn-date")[0]


def test_create_in_drawer_opens_the_booking_without_navigate():
    r = _master()
    resp = _post(
        {
            "resource": str(r.pk),
            "start_date": _day().isoformat(),
            "start_time": "10:00",
            "name": "Frau Weber",
            "next": "/dashboard/verkaeufe/?tab=booking",
        }
    )
    data = json.loads(resp.content)
    b = Booking.objects.get(customer__name="Frau Weber")
    assert data["ok"] is True and not data.get("navigate")
    assert data["open"] == f"/dashboard/booking/termin/{b.pk}/"


@pytest.mark.parametrize(
    "extra, field",
    [
        ({"party_size": "abc"}, "party"),
        ({"party_size": "99"}, "party"),
        ({"minutes": "3"}, "minutes"),
        ({"start_time": ""}, "time"),
        ({"service": str(uuid.uuid4())}, "service"),
    ],
)
def test_errors_are_at_the_field_and_nothing_is_created(extra, field):
    r = _master()
    Resource.objects.create(name="Tisch 1", type=Resource.TYPE_TABLE, seats=4)  # «Personen» видно
    Service.objects.create(name="Haarschnitt", duration_minutes=30)
    data = {
        "resource": str(r.pk),
        "start_date": _day().isoformat(),
        "start_time": "10:00",
        "name": "Frau Weber",
        **extra,
    }
    resp = _post(data)
    html = resp.content.decode()
    assert resp.status_code == 200 and resp["X-Sf-Fragment"] == "1"
    assert f'id="bn-{field}-err"' in html and 'value="Frau Weber"' in html
    assert not Booking.objects.exists()


def test_outside_hours_offers_override_and_override_creates():
    r = _master()
    data = {
        "resource": str(r.pk),
        "start_date": _day().isoformat(),
        "start_time": "20:00",
        "name": "Spät",
    }
    html = _post(data).content.decode()
    assert 'name="override_hours"' in html and "data-override" in html
    assert not Booking.objects.exists()
    _post({**data, "override_hours": "1"})
    assert Booking.objects.filter(customer__name="Spät").exists()


def test_taken_slot_has_no_override():
    r = _master()
    data = {"resource": str(r.pk), "start_date": _day().isoformat(), "start_time": "10:00"}
    _post({**data, "name": "Erste"})
    html = _post({**data, "name": "Zweite"}).content.decode()
    assert "data-override" not in html and 'id="bn-time-err"' in html
    assert Booking.objects.count() == 1


def test_without_js_success_opens_the_booking_page():
    r = _master()
    resp = _post(
        {"resource": str(r.pk), "start_date": _day().isoformat(), "start_time": "11:00"},
        drawer=False,
    )
    b = Booking.objects.get()
    assert resp.status_code == 302 and resp.url == f"/dashboard/booking/termin/{b.pk}/"


def test_refusal_codes_are_set_by_the_core():
    from apps.booking import services

    assert services.ManualBookingRefused.OVERRIDABLE == {"outside_hours", "seats"}
    assert services.ManualBookingRefused("x").code == ""


def test_drawer_aware_is_innermost_and_permissions_match_create():
    from apps.core import drawer, view_perms

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [v.booking_new]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    assert chain[-2].__code__ is code
    assert view_perms.RULES["booking:booking-new"] == view_perms.RULES["booking:booking-create"]


# --- D5.3: постоянной формы записи больше нет ------------------------------------


def _body(role=Membership.ROLE_OWNER):
    from django.template.loader import render_to_string

    from apps.booking import views

    req = _req(drawer=False)
    Membership.objects.filter(user=req.user).update(role=role)
    ctx = views.calendar_context(req)
    return render_to_string("booking/_tagesplan_body.html", ctx, request=req)


def test_day_plan_has_no_open_booking_form_but_a_drawer_button():
    _master()
    html = _body()
    assert "/dashboard/booking/new/" not in html  # форма booking-create снята
    assert "data-skip-neu" not in html
    btn = re.search(r'<a id="neu" [^>]*>', html).group(0)
    assert "data-drawer" in btn and "/dashboard/booking/termin/neu/" in btn


def test_create_target_and_drawer_flag():
    from apps.core import sales_page

    url = sales_page.create_target("booking")
    assert url == "/dashboard/booking/termin/neu/" and sales_page.opens_in_drawer(url)
    assert sales_page.opens_in_drawer("/dashboard/stays/neu/")
    assert not sales_page.opens_in_drawer("/dashboard/jobs/neu/")
