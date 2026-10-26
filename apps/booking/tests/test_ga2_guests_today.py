"""KA-12 GA-2 (Gastro): «Gäste heute» на главной, бейдж «Gruppenanfrage» на доске,
в списке, Tagesplan и карточке; гости в «Termine heute» и в строке «когда»."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Booking, Resource
from apps.core import dashboard, transactions
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant():
    return TenantFactory.build(business_type="restaurant", disabled_modules=[])


def _table(**kw):
    return Resource.objects.create(
        name=f"Tisch {uuid.uuid4().hex[:4]}", capacity=40, counts_party_size=True, **kw
    )


def _book(resource, hours, party, **kw):
    start = (timezone.now() + timedelta(hours=hours)).replace(second=0, microsecond=0)
    return services.book(
        resource, start=start, end=start + timedelta(hours=1), name="Gast", party_size=party, **kw
    )


def _widget(tenant):
    return next((w for w in dashboard.home_widgets(tenant) if w["key"] == "guests_today"), None)


def test_widget_sums_guests_of_active_bookings_today():
    if timezone.localtime().hour >= 23:
        pytest.skip("почти полночь — брони через полчаса окажутся «завтра»")
    table = _table()
    _book(table, 0.5, 4)
    _book(table, 0.5, 2, is_large_party=True)
    gone = _book(table, 0.5, 9)
    Booking.objects.filter(pk=gone.pk).update(status="cancelled")
    widget = _widget(_tenant())
    assert widget["value"] == "6"
    assert "Gruppenanfragen: 1" in widget["hint"]
    assert "status=pending" in widget["url_query"]


def test_widget_hidden_without_tables():
    Resource.objects.create(name="Lea", type=Resource.TYPE_STAFF)
    assert _widget(_tenant()) is None


def test_widget_needs_sales_right():
    assert dashboard.WIDGET_PERMS["guests_today"] == "verkaeufe.view"


def test_transaction_carries_group_badge_and_guests():
    table = _table()
    b = _book(table, 30, 8, is_large_party=True)
    tx = transactions.transaction_for("booking", b)
    assert tx.large_party and tx.when_note == "8 Gäste"
    plain = _book(table, 31, 1)
    tx = transactions.transaction_for("booking", plain)
    assert not tx.large_party and tx.when_note == ""


def test_badge_rendered_on_board_card():
    from django.template.loader import render_to_string

    table = _table()
    b = _book(table, 30, 8, is_large_party=True)
    html = render_to_string(
        "core/_kanban_card.html",
        {"tx": transactions.transaction_for("booking", b), "kind": "booking"},
    )
    assert "data-large-party" in html
