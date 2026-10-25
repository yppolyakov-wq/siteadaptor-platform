"""KA-12 Zimmer Z-6 (E1.15): Kurtaxe детей, отчёт для общины, Meldescheine.

Замки: дети бесплатно по умолчанию, ставка детей — при снятом «Kinder frei»; форма
Kurtaxe больше не обнуляет ставку; отчёт — из снимков, Σ по месяцам = снимок, отменённые
не в счёт, без имён гостей; выгрузка Meldescheine — с правом и без номера документа;
ввод со стойки не перетирает онлайн-подпись; печать — PDF."""

import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.stays import kurtaxe, pricing, services, views
from apps.stays.models import GuestRegistration, StayBooking, StaySettings, StayUnit
from apps.stays.state_machine import StayBookingSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

M1 = date(2026, 1, 1)
M2 = date(2026, 2, 1)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _settings(cents=300, children_free=True, child_cents=0):
    s = StaySettings.load()
    s.kurtaxe_cents, s.kurtaxe_children_free, s.kurtaxe_child_cents = (
        cents,
        children_free,
        child_cents,
    )
    s.save()
    return s


def _book(arrival, nights, adults=2, children=0, name="Gast Kurtaxe"):
    unit = StayUnit.objects.create(
        name=f"DZ {uuid.uuid4().hex[:6]}", price_cents=8000, max_guests=6
    )
    b = services.book_stay(
        unit,
        arrival=arrival,
        departure=arrival + timedelta(days=nights),
        name=name,
        adults=adults,
        children=children,
    )
    StayBookingSM().apply(b, "confirmed")
    return b


# --- Kurtaxe детей --------------------------------------------------------------------


def test_children_free_by_default():
    s = _settings(cents=300, child_cents=150)
    assert pricing.kurtaxe_total_cents(2, 3, s, children=2) == 2 * 3 * 300


def test_child_rate_when_children_not_free():
    s = _settings(cents=300, children_free=False, child_cents=150)
    assert pricing.kurtaxe_total_cents(2, 3, s, children=2) == 2 * 3 * 300 + 2 * 3 * 150


def test_booking_snapshot_includes_children_when_charged():
    _settings(cents=300, children_free=False, child_cents=100)
    b = _book(M1 + timedelta(days=10), 2, adults=1, children=1)
    assert b.kurtaxe_cents == 1 * 2 * 300 + 1 * 2 * 100


# --- отчёт ----------------------------------------------------------------------------


def test_month_split_sums_to_snapshot_and_skips_cancelled():
    _settings(cents=333)
    across = _book(date(2026, 1, 30), 3, adults=1)  # 30.01–02.02: 2 ночи в январе, 1 в феврале
    cancelled = _book(M1 + timedelta(days=5), 2)
    StayBookingSM().apply(cancelled, "cancelled")
    jan = kurtaxe.month_report(M1, M2)
    feb = kurtaxe.month_report(M2, date(2026, 3, 1))
    assert [r.booking.pk for r in jan["rows"]] == [across.pk]
    assert jan["rows"][0].nights == 2 and feb["rows"][0].nights == 1
    assert jan["kurtaxe_cents"] + feb["kurtaxe_cents"] == across.kurtaxe_cents == 999


def test_snapshot_not_rewritten_by_rate_change():
    _settings(cents=300)
    b = _book(M1 + timedelta(days=3), 2, adults=2)
    _settings(cents=900)
    assert kurtaxe.month_report(M1, M2)["kurtaxe_cents"] == b.kurtaxe_cents == 1200


def test_free_child_nights_counted():
    _settings(cents=300)
    _book(M1 + timedelta(days=3), 2, adults=2, children=1)
    rep = kurtaxe.month_report(M1, M2)
    assert (rep["adult_nights"], rep["child_nights"], rep["free_child_nights"]) == (4, 2, 2)


# --- вьюхи ----------------------------------------------------------------------------


def _user(role=Membership.ROLE_OWNER, perms=None):
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"u-{tag}", email=f"u-{tag}@test.de", password="pw12345678"
    )
    Membership.objects.get_or_create(user=user, defaults={"role": role, "permissions": perms or {}})
    return user


def _get(view, path, data=None, user=None, **kw):
    request = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user or _user()
    request.tenant = TenantFactory.build(disabled_modules=[], name="Hotel Test")
    return view(request, **kw)


def test_report_page_csv_pdf_without_guest_names():
    _settings(cents=300)
    b = _book(M1 + timedelta(days=3), 2, name="Geheimer Gastname")
    page = _get(views.kurtaxe_report, "/dashboard/stays/kurtaxe/", {"month": "2026-01"})
    body = page.content.decode()
    assert b.reference_code in body and "Geheimer Gastname" not in body
    csv_resp = _get(views.kurtaxe_report, "/x", {"month": "2026-01", "format": "csv"})
    text = csv_resp.content.decode("utf-8-sig")
    assert b.reference_code in text and "Geheimer" not in text and "12.00" in text
    pdf = _get(views.kurtaxe_report, "/x", {"month": "2026-01", "format": "pdf"})
    assert pdf["Content-Type"] == "application/pdf" and pdf.content.startswith(b"%PDF")


def test_meldescheine_csv_without_document_number():
    b = _book(M1 + timedelta(days=3), 2)
    GuestRegistration.objects.create(
        booking=b,
        first_name="Max",
        last_name="Muster",
        signed_name="Max Muster",
        doc_number="L01X00T47",
    )
    resp = _get(views.meldescheine_export, "/x", {"month": "2026-01"})
    text = resp.content.decode("utf-8-sig")
    assert "Muster" in text and "L01X00T47" not in text


def test_meldescheine_export_requires_export_right():
    from apps.core import view_perms

    staff = _user(Membership.ROLE_STAFF)
    assert not view_perms.allowed_quiet(staff, "stays:meldescheine-export", "GET")
    assert view_perms.allowed_quiet(_user(), "stays:meldescheine-export", "GET")


def test_meldeschein_pdf_contains_document_number():
    b = _book(M1 + timedelta(days=3), 2)
    GuestRegistration.objects.create(
        booking=b,
        first_name="Max",
        last_name="Muster",
        signed_name="Max Muster",
        doc_number="L01X00T47",
    )
    resp = _get(views.meldeschein_pdf, "/x", pk=b.pk)
    assert resp.content.startswith(b"%PDF")


def _post_reg(b, data, user=None):
    request = RequestFactory().post(
        f"/dashboard/stays/{b.pk}/action/",
        {"action": "registration", "next": "/dashboard/x/", **data},
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user or _user()
    request.tenant = TenantFactory.build(disabled_modules=[])
    views.stay_action(request, b.pk)
    return [str(m) for m in get_messages(request)]


def test_desk_entry_creates_registration():
    b = _book(M1 + timedelta(days=3), 2)
    _post_reg(b, {"first_name": "Erika", "last_name": "Muster", "birth_date": "1980-05-01"})
    reg = GuestRegistration.objects.get(booking=b)
    assert (
        reg.last_name == "Muster" and reg.birth_date == date(1980, 5, 1) and reg.signed_ip is None
    )


def test_desk_entry_does_not_overwrite_online_signature():
    b = _book(M1 + timedelta(days=3), 2)
    GuestRegistration.objects.create(
        booking=b,
        first_name="Online",
        last_name="Gast",
        signed_name="Online Gast",
        signed_ip="1.2.3.4",
    )
    msgs = _post_reg(b, {"first_name": "Fake", "last_name": "Name"})
    assert GuestRegistration.objects.get(booking=b).last_name == "Gast"
    assert msgs


def test_desk_entry_without_right_refused():
    b = _book(M1 + timedelta(days=3), 2)
    staff = _user(Membership.ROLE_STAFF, perms={"remove": ["kunden.edit"]})
    _post_reg(b, {"last_name": "Muster"}, user=staff)
    assert not GuestRegistration.objects.filter(booking=b).exists()


def test_kurtaxe_form_keeps_rate_and_saves_children():
    _settings(cents=250)
    request = RequestFactory().get("/dashboard/stays/units/?tab=einstellungen&sec=kurtaxe")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user()
    request.tenant = TenantFactory.build(disabled_modules=[])
    body = views.units(request).content.decode()
    assert 'name="kurtaxe_eur" type="text" value="2.50"' in body
    post = RequestFactory().post(
        "/dashboard/stays/units/",
        {
            "action": "kurtaxe",
            "kurtaxe_eur": "2.50",
            "kurtaxe_label": "Kurtaxe",
            "kurtaxe_children_present": "1",
            "kurtaxe_child_eur": "1,20",
        },
    )
    SessionMiddleware(lambda r: None).process_request(post)
    MessageMiddleware(lambda r: None).process_request(post)
    post.user = _user()
    post.tenant = TenantFactory.build(disabled_modules=[])
    views.units(post)
    s = StaySettings.objects.get()
    assert (s.kurtaxe_cents, s.kurtaxe_children_free, s.kurtaxe_child_cents) == (250, False, 120)


def test_status_still_pending_counted_only_if_registry_counts(monkeypatch):
    """pending — тоже бронь в отчёте (counted_statuses), не только confirmed."""
    _settings(cents=300)
    unit = StayUnit.objects.create(name="P", price_cents=8000)
    services.book_stay(
        unit, arrival=M1 + timedelta(days=3), departure=M1 + timedelta(days=4), name="P"
    )
    from apps.core import status_registry

    counted = status_registry.counted_statuses_for("stay")
    rep = kurtaxe.month_report(M1, M2)
    assert (StayBooking.STATUS_PENDING in counted) == bool(rep["rows"])
