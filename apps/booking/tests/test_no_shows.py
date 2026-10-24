"""KA-12 E6.4a: счётчик неявок — из статусов, одним запросом, без N+1."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking import no_shows, services
from apps.booking.models import Booking
from apps.booking.tests.test_services import _resource, _service

pytestmark = pytest.mark.django_db


def _visit(email, status, days_ago):
    start = timezone.now() - timedelta(days=days_ago)
    b = services.book(
        _resource(),
        start=start,
        end=start + timedelta(hours=1),
        name="G",
        email=email,
        service=_service(),
    )
    Booking.objects.filter(pk=b.pk).update(status=status)
    return b


def test_summary_counts_only_no_show():
    a = _visit("a@t.de", "no_show", 30)
    last = _visit("a@t.de", "no_show", 5)
    _visit("a@t.de", "cancelled", 3)
    for d in (60, 50, 40):
        _visit("a@t.de", "fulfilled", d)
    s = no_shows.summary(a.customer)
    assert s["n"] == 2 and s["visits"] == 3 and s["last"] == last.start


def test_summary_empty_customer():
    assert no_shows.summary(None) == {"n": 0, "last": None, "visits": 0}


def test_counts_for_one_query(django_assert_num_queries):
    a = _visit("a@t.de", "no_show", 9)
    _visit("a@t.de", "no_show", 8)
    b = _visit("b@t.de", "no_show", 7)
    c = _visit("c@t.de", "fulfilled", 6)
    with django_assert_num_queries(1):
        got = no_shows.counts_for({a.customer_id, b.customer_id, c.customer_id})
    assert got == {a.customer_id: 2, b.customer_id: 1}


def test_counts_for_empty_makes_no_query(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert no_shows.counts_for(set()) == {}


def test_badges_on_card_tagesplan_and_customer(rf, settings, monkeypatch):
    from django.contrib.auth import get_user_model
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.booking import views
    from apps.crm import customer360
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    _visit("a@t.de", "no_show", 9)
    _visit("a@t.de", "no_show", 8)
    future = timezone.now() + timedelta(days=1)
    b = services.book(
        _resource(),
        start=future,
        end=future + timedelta(hours=1),
        name="G",
        email="a@t.de",
        service=_service(),
    )
    clean = services.book(
        _resource(),
        start=future,
        end=future + timedelta(hours=1),
        name="H",
        email="h@t.de",
        service=_service(),
    )
    user = get_user_model().objects.create_user("o@t.de", "o@t.de", "pw")

    def req(path, data=None):
        r = rf.get(path, data or {})
        r.user = user
        SessionMiddleware(lambda x: None).process_request(r)
        r._messages = FallbackStorage(r)
        r.tenant = TenantFactory.build(business_type="friseur")
        return r

    body = views.booking_detail.__wrapped__(req("/"), b.pk).content.decode()
    assert "data-no-show-card" in body and "2× nicht erschienen" in body
    body = views.booking_detail.__wrapped__(req("/"), clean.pk).content.decode()
    assert "data-no-show-card" not in body

    ctx = views.calendar_context(req("/", {"tag": timezone.localdate(future).isoformat()}))
    by_pk = {x.pk: x.no_show_n for x in ctx["bookings"]}
    assert by_pk[b.pk] == 2 and by_pk[clean.pk] == 0

    tenant = TenantFactory.build(business_type="friseur")
    monkeypatch.setattr(customer360, "_active", lambda t, key: True)
    counts = customer360.kpis(tenant, b.customer)["counts"]
    assert {"label": "Nicht erschienen", "n": 2} in [
        {"label": str(c["label"]), "n": c["n"]} for c in counts
    ]


def test_tagesplan_no_show_badge_query_count_flat(rf, django_assert_max_num_queries):
    """N+1-замок: число запросов calendar_context не растёт с числом клиентов дня."""
    from django.contrib.auth.models import AnonymousUser

    from apps.booking import views
    from apps.tenants.tests.factories import TenantFactory

    day = timezone.localdate() + timedelta(days=2)
    base = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))

    def make(n):
        for i in range(n):
            start = base + timedelta(hours=8 + i)
            services.book(
                _resource(),
                start=start,
                end=start + timedelta(minutes=30),
                name=f"G{i}",
                email=f"g{i}-{n}@t.de",
                service=_service(),
            )

    def count():
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        r = rf.get("/", {"tag": day.isoformat()})
        r.user = AnonymousUser()
        r.tenant = TenantFactory.build(business_type="friseur")
        with CaptureQueriesContext(connection) as c:
            views.calendar_context(r)
        return len(c)

    make(2)
    few = count()
    make(6)
    assert count() <= few + 1


def test_tagesplan_template_renders_badge():
    from django.template.loader import render_to_string

    from apps.booking.tests.test_services import _aware, _future_day, _rule

    day = _future_day()
    r = _resource()
    _rule(r, day, "09:00", "18:00", slot=30)
    _visit("z@t.de", "no_show", 9)
    b = services.book(
        r, start=_aware(day, 10), end=_aware(day, 11), name="Z", email="z@t.de", service=_service()
    )
    b.no_show_n = 1
    html = render_to_string("booking/_tagesplan_body.html", {"bookings": [b], "day": day})
    assert "data-no-show" in html and "nicht erschienen" in html
