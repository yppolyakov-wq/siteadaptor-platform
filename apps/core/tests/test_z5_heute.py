"""KA-12 Zimmer Z-5e (DF-Z4, Р-9): «Heute» и виджет главной — одна точка списков.

Замки: свой «активный» статус виден в Abreisen/Im Haus и в виджете; неподтверждённая
заявка — в Anreisen с бейджем, но не в Im Haus; заселённый/выехавший гость остаётся
в своей колонке с ✓; карточка показывает комнаты, оплату, Meldeschein; кнопки —
POST на stays:stay-action; число запросов не растёт с числом броней; сломанная
колонка видна как «Konnte nicht geladen werden», а не как пустой день."""

import logging
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import dashboard as dash
from apps.core import sales_page
from apps.core.models import Membership
from apps.stays import front_desk, services
from apps.stays.models import GuestRegistration, Room, StayBooking, StayUnit
from apps.stays.state_machine import StayBookingSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
CUSTOM = {
    "status_defs": {"stay": [{"code": "anzahlung", "role": "active", "blocks_capacity": True}]}
}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit():
    return StayUnit.objects.create(
        name=f"DZ {uuid.uuid4().hex[:6]}", price_cents=10000, quantity=20
    )


def _b(unit, arr, dep, name, *, confirm=True):
    b = services.book_stay(
        unit,
        arrival=TODAY + timedelta(days=arr),
        departure=TODAY + timedelta(days=dep),
        name=name,
    )
    if confirm:
        StayBookingSM().apply(b, "confirmed")
    return b


def _tenant(**kw):
    kw.setdefault("business_type", "hotel")
    kw.setdefault("disabled_modules", [])
    return TenantFactory.build(**kw)


def _user():
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"u-{tag}", email=f"u-{tag}@test.de", password="pw12345678"
    )
    Membership.objects.get_or_create(user=user, defaults={"role": Membership.ROLE_STAFF})
    return user


def _cols(tenant=None, user=None):
    return {c["key"]: c for c in sales_page.heute_columns(tenant or _tenant(), user)}


def _titles(col):
    return [it["title"] for it in col["items"]]


def test_custom_active_status_visible_in_departures_and_in_house():
    unit = _unit()
    leaving = _b(unit, -2, 0, "Abreise Anzahlung")
    staying = _b(unit, -1, 2, "ImHaus Anzahlung")
    StayBooking.objects.filter(pk__in=[leaving.pk, staying.pk]).update(status="anzahlung")
    tenant = _tenant(site_config=CUSTOM)
    cols = _cols(tenant)
    assert "Abreise Anzahlung" in _titles(cols["abreise"])
    assert "ImHaus Anzahlung" in _titles(cols["im_haus"])
    lists = front_desk.today_lists(tenant)
    assert lists["departures"].count() == 1


def test_pending_arrival_has_badge_and_is_not_in_house():
    unit = _unit()
    _b(unit, 0, 2, "Unbestaetigt Gast", confirm=False)
    cols = _cols()
    item = next(it for it in cols["anreise"]["items"] if it["title"] == "Unbestaetigt Gast")
    assert any(b["text"] == "unbestätigt" for b in item["badges"])
    assert "Unbestaetigt Gast" not in _titles(cols["im_haus"])
    assert not item["actions"]


def test_checked_in_today_in_arrivals_and_in_house_checked_out_only_in_departures():
    unit = _unit()
    arriving = _b(unit, 0, 2, "Heute Eingecheckt")
    front_desk.check_in(arriving)
    leaving = _b(unit, -2, 0, "Heute Ausgecheckt")
    front_desk.check_out(leaving)
    cols = _cols()
    arr = next(it for it in cols["anreise"]["items"] if it["title"] == "Heute Eingecheckt")
    assert any("Eingecheckt" in str(b["text"]) for b in arr["badges"])
    assert "Heute Eingecheckt" in _titles(cols["im_haus"])
    dep = next(it for it in cols["abreise"]["items"] if it["title"] == "Heute Ausgecheckt")
    assert any("Ausgecheckt" in str(b["text"]) for b in dep["badges"])
    assert "Heute Ausgecheckt" not in _titles(cols["im_haus"])


def test_card_shows_rooms_payment_and_meldeschein():
    unit = _unit()
    room = Room.objects.create(unit=unit, number="204")
    b = _b(unit, 0, 1, "Karte Gast")
    services.assign_room(b, room)
    StayBooking.objects.filter(pk=b.pk).update(payment_method="vorkasse")
    item = next(it for it in _cols()["anreise"]["items"] if it["title"] == "Karte Gast")
    assert "204" in item["subtitle"]
    texts = [str(x["text"]) for x in item["badges"]]
    assert any("Vorkasse" in t for t in texts)
    assert any(t.endswith("—") for t in texts)
    GuestRegistration.objects.create(booking=b, first_name="K", last_name="G", signed_name="K G")
    item = next(it for it in _cols()["anreise"]["items"] if it["title"] == "Karte Gast")
    assert any(str(x["text"]).endswith("✓") for x in item["badges"])


def test_buttons_post_to_stay_action_with_next():
    unit = _unit()
    b = _b(unit, 0, 1, "Knopf Gast")
    request = RequestFactory().get("/dashboard/verkaeufe/", {"view": "heute"})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user()
    request.tenant = _tenant()
    from apps.core import views as core_views

    body = core_views.verkaeufe(request).content.decode()
    assert f'action="/dashboard/stays/{b.pk}/action/"' in body
    assert 'value="check_in"' in body and "view=heute" in body


def test_no_buttons_without_rezeption_right():
    unit = _unit()
    _b(unit, 0, 1, "Ohne Recht")
    item = next(it for it in _cols(user=None)["anreise"]["items"] if it["title"] == "Ohne Recht")
    assert item["actions"] == []


def test_query_budget_does_not_grow_with_bookings(django_assert_max_num_queries):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    unit = _unit()
    for i in range(3):
        b = _b(unit, -1, 1, f"Gast {i}")
        services.assign_room(b, Room.objects.create(unit=unit, number=f"1{i}"))
    with CaptureQueriesContext(connection) as small:
        _cols()
    for i in range(3, 10):
        b = _b(unit, -1, 1, f"Gast {i}")
        services.assign_room(b, Room.objects.create(unit=unit, number=f"1{i}"))
    with CaptureQueriesContext(connection) as big:
        _cols()
    assert len(big) == len(small)


def test_broken_column_is_logged_and_shown(monkeypatch, caplog):
    def boom(*a, **kw):
        raise RuntimeError("today lists down")

    monkeypatch.setattr(front_desk, "today_lists", boom)
    with caplog.at_level(logging.ERROR):
        cols = _cols()
    assert cols["anreise"]["error"] and cols["im_haus"]["error"]
    assert any("heute column" in r.getMessage() for r in caplog.records)
    from django.template.loader import render_to_string

    html = render_to_string("core/_sales_heute.html", {"heute_columns": list(_cols().values())})
    assert "Konnte nicht geladen werden" in html
    assert (
        "Nichts für heute"
        not in html.split('data-heute-col="anreise"')[1].split("data-heute-col")[0]
    )


def test_home_widget_counts_same_lists_including_custom_status():
    unit = _unit()
    leaving = _b(unit, -2, 0, "Widget Abreise")
    StayBooking.objects.filter(pk=leaving.pk).update(status="anzahlung")
    _b(unit, 0, 2, "Widget Anreise")
    tenant = TenantFactory(
        slug=f"z5{uuid.uuid4().hex[:6]}", name="Z5", business_type="hotel", site_config=CUSTOM
    )
    widgets = {w["key"]: w for w in dash.home_widgets(tenant)}
    assert widgets["stays_today"]["value"] == "1"
    assert "1" in str(widgets["stays_today"]["hint"])
