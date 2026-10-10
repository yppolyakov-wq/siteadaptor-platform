"""T-8.6 «Чистый каталог города»: согласие, снятие, «Melden», атрибуция, воронка.

План — docs/t8-6-catalog-hygiene-plan-2026-10-10.md §2.
"""

from importlib import import_module
from unittest import mock

import pytest
from django.conf import settings as dj_settings
from django.core.cache import cache
from django.test import RequestFactory

from apps.aggregator import reports, tasks, visibility
from apps.aggregator.models import AggregatorListing, ListingReport
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _listing(schema="biz_a", **kw):
    kw.setdefault("title", {"de": "Brötchen"})
    kw.setdefault("detail_url", f"https://{schema}.siteadaptor.de/p/x/")
    return AggregatorListing.objects.create(
        tenant_schema=schema,
        tenant_slug=schema,
        business_name=schema,
        city="Solingen",
        source_ref=f"{schema}-{AggregatorListing.objects.count()}",
        **kw,
    )


# --- кто попадает в каталог ---------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"is_active": False},
        {"subscription_status": "suspended"},
        {"email_pending": True},
        {"in_city_catalog": False},
    ],
)
def test_each_condition_withholds(fields):
    ok = TenantFactory(schema_name="biz_ok", slug="biz-ok")
    assert visibility.listable(ok)
    bad = TenantFactory(schema_name="biz_bad", slug="biz-bad", **fields)
    assert not visibility.listable(bad)
    _listing("biz_ok")
    _listing("biz_bad")
    shown = set(AggregatorListing.objects.public().values_list("tenant_schema", flat=True))
    assert shown == {"biz_ok"}


def test_trial_expired_stays_listed():
    t = TenantFactory(
        schema_name="biz_grace", slug="biz-grace", subscription_status="trial_expired"
    )
    assert visibility.listable(t)


def test_sync_does_not_write_listing_of_withheld_tenant():
    TenantFactory(schema_name="public", slug="ohne", in_city_catalog=False)
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    assert tasks.sync_listing("public", str(promo.pk)) == "removed"


def test_hidden_by_moderation_is_not_public_and_survives_sync():
    TenantFactory(schema_name="public", slug="mod")
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    tasks.sync_listing("public", str(promo.pk))
    listing = AggregatorListing.objects.get(promo_uuid=promo.pk)
    AggregatorListing.objects.filter(pk=listing.pk).update(hidden_at="2026-10-10T10:00Z")
    tasks.sync_listing("public", str(promo.pk))  # правка акции владельцем
    listing.refresh_from_db()
    assert listing.hidden_at is not None
    assert not AggregatorListing.objects.public().filter(pk=listing.pk).exists()


def test_apply_visibility_removes_all_kinds_or_queues_reconcile():
    t = TenantFactory(schema_name="biz_v", slug="biz-v", in_city_catalog=False)
    _listing("biz_v", listing_kind="promotion")
    _listing("biz_v", listing_kind="stay")
    assert visibility.apply_visibility(t) == "removed"
    assert not AggregatorListing.objects.filter(tenant_schema="biz_v").exists()
    t.in_city_catalog = True
    with mock.patch("django.db.transaction.on_commit", side_effect=lambda f: f()):
        with mock.patch("apps.aggregator.tasks.reconcile_aggregator_schema.delay") as delay:
            assert visibility.apply_visibility(t) == "queued"
    delay.assert_called_once_with("biz_v")


def test_email_confirmation_republishes_every_kind():
    """Регресс T-8.5: раньше пересинхронизировались только акции."""
    from apps.core import owner_login

    t = TenantFactory(schema_name="biz_c", slug="biz-c", email_pending=True)
    with mock.patch("apps.aggregator.visibility.apply_visibility") as apply:
        assert owner_login.confirm_tenant_email(t) is True
    apply.assert_called_once_with(t)


def test_subscription_suspend_removes_listings():
    from apps.billing.state_machine import SubscriptionSM

    t = TenantFactory(schema_name="biz_s", slug="biz-s", subscription_status="past_due")
    _listing("biz_s")
    SubscriptionSM().apply(t, "suspended")
    t.refresh_from_db()
    assert not t.is_active
    assert not AggregatorListing.objects.filter(tenant_schema="biz_s").exists()


def test_settings_toggle_off_removes_listings():
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core.views import settings_view
    from apps.tenants.forms import BusinessSettingsForm

    t = TenantFactory(schema_name="biz_t", slug="biz-t")
    _listing("biz_t")
    form = BusinessSettingsForm(instance=t)
    data = {}
    for name in form.fields:
        value = form[name].value()
        if value in (None, False):
            continue
        data[name] = "on" if value is True else value
    data.pop("in_city_catalog", None)  # снятая галочка в POST не приходит
    request = RequestFactory().post("/dashboard/settings/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(username="owner-t", password="x")
    request.tenant = t
    response = settings_view(request)
    assert response.status_code == 302, response.content[:500]
    t.refresh_from_db()
    assert t.in_city_catalog is False
    assert not AggregatorListing.objects.filter(tenant_schema="biz_t").exists()


# --- «Melden» -----------------------------------------------------------------------


def _report_request(listing, ip, **data):
    request = RequestFactory().post(f"/entdecken/melden/{listing.pk}/", data)
    request.META["REMOTE_ADDR"] = ip
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.portal = None
    return request


@pytest.mark.urls("config.urls_public")
def test_report_saved_and_three_voices_hide_listing():
    TenantFactory(schema_name="biz_r", slug="biz-r")
    listing = _listing("biz_r")
    for n, ip in enumerate(("10.86.0.1", "10.86.0.2"), start=1):
        body = reports.report_listing(
            _report_request(listing, ip, reason="spam"), pk=listing.pk
        ).content.decode()
        assert "data-report-sent" in body
        assert ListingReport.objects.count() == n
    listing.refresh_from_db()
    assert listing.hidden_at is None
    reports.report_listing(_report_request(listing, "10.86.0.3", reason="wrong"), pk=listing.pk)
    listing.refresh_from_db()
    assert listing.hidden_at is not None


def test_one_person_cannot_hide_alone():
    TenantFactory(schema_name="biz_one", slug="biz-one")
    listing = _listing("biz_one")
    for _ in range(3):
        reports.file_report(listing, reason="spam", ip_hash="same")
    listing.refresh_from_db()
    assert listing.hidden_at is None


@pytest.mark.urls("config.urls_public")
def test_honeypot_and_bad_reason_store_nothing():
    TenantFactory(schema_name="biz_h", slug="biz-h")
    listing = _listing("biz_h")
    reports.report_listing(
        _report_request(listing, "10.86.1.1", reason="spam", website="x"), pk=listing.pk
    )
    body = reports.report_listing(
        _report_request(listing, "10.86.1.2", reason="nope"), pk=listing.pk
    ).content.decode()
    assert "data-report-sent" not in body
    assert not ListingReport.objects.exists()


def test_portal_route_is_not_eaten_by_catch_all():
    from django.urls import resolve

    match = resolve("/melden/7/", urlconf="config.urls_portal")
    assert match.func is reports.report_listing


# --- атрибуция ----------------------------------------------------------------------


def test_portal_links_carry_channel():
    TenantFactory(schema_name="biz_p", slug="biz-p")
    listing = _listing("biz_p")
    assert listing.portal_url.endswith("/p/x/?ch=portal")
    listing.detail_url = "https://x.siteadaptor.de/unterkunft/1/?von=2026-10-11"
    assert listing.portal_url.endswith("&ch=portal")
    listing.detail_url = "https://x.siteadaptor.de/p/1/?ch=flyer"
    assert listing.portal_url.endswith("?ch=flyer")  # чужой канал не перезаписываем


@pytest.mark.urls("config.urls_public")
def test_cards_link_with_channel_and_report():
    from django.template.loader import render_to_string

    TenantFactory(schema_name="biz_k", slug="biz-k")
    listing = _listing("biz_k")
    html = render_to_string("aggregator/_cards.html", {"items": [listing]})
    assert "?ch=portal" in html
    assert "data-report-link" in html
