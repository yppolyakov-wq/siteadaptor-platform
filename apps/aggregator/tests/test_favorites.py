"""P2.3b: избранное клиента портала (toggle + /konto/ + сердечки на выдаче)."""

import uuid

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.aggregator import account_views, auth, portal_views
from apps.aggregator.models import AggregatorListing, AggregatorPortal, FavoriteListing, PortalUser

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _portal_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_portal"


def _portal():
    portal, _ = AggregatorPortal.objects.get_or_create(
        host="muenchen.siteadaptor.de",
        defaults={"kind": "city", "city": "München", "title": {"de": "Angebote München"}},
    )
    return portal


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "X",
        "business_type": "bakery",
        "city": "München",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot -20%"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _user():
    return PortalUser.objects.create(email=f"{uuid.uuid4().hex}@kunde.test")


def _req(method="get", path="/konto/", data=None, user=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    request.portal = _portal()
    if user is not None:
        request.session[auth.SESSION_KEY] = user.pk
    return request


def test_toggle_adds_then_removes():
    user, listing = _user(), _listing()
    resp = account_views.favorite_toggle(
        _req("post", data={"listing": listing.pk, "next": "/"}, user=user)
    )
    assert resp.status_code == 302
    assert FavoriteListing.objects.filter(user=user, listing=listing).exists()

    account_views.favorite_toggle(
        _req("post", data={"listing": listing.pk, "next": "/"}, user=user)
    )
    assert not FavoriteListing.objects.filter(user=user, listing=listing).exists()


def test_toggle_requires_login():
    listing = _listing()
    resp = account_views.favorite_toggle(_req("post", data={"listing": listing.pk}))
    assert resp.status_code == 302
    assert resp.url == "/konto/login/"
    assert FavoriteListing.objects.count() == 0


def test_toggle_ignores_garbage_listing():
    user = _user()
    resp = account_views.favorite_toggle(
        _req("post", data={"listing": "abc", "next": "/"}, user=user)
    )
    assert resp.status_code == 302
    assert FavoriteListing.objects.count() == 0


def test_toggle_rejects_external_next():
    user, listing = _user(), _listing()
    resp = account_views.favorite_toggle(
        _req("post", data={"listing": listing.pk, "next": "https://evil.test/"}, user=user)
    )
    assert resp.url == "/"
    resp = account_views.favorite_toggle(
        _req("post", data={"listing": listing.pk, "next": "//evil.test/"}, user=user)
    )
    assert resp.url == "/"


def test_account_lists_saved_offers():
    user = _user()
    saved = _listing(title={"de": "GespeichertesBrot"})
    _listing(title={"de": "AnderesBrot"})
    FavoriteListing.objects.create(user=user, listing=saved)

    resp = account_views.account(_req(user=user))
    body = resp.content.decode()
    assert "GespeichertesBrot" in body
    assert "AnderesBrot" not in body


def test_account_hides_inactive_favorites():
    user = _user()
    gone = _listing(title={"de": "WegDamit"}, is_active=False)
    FavoriteListing.objects.create(user=user, listing=gone)
    resp = account_views.account(_req(user=user))
    assert "WegDamit" not in resp.content.decode()


def test_portal_home_marks_favorites_for_logged_in():
    user = _user()
    fav = _listing(title={"de": "Lieblingsbrot"})
    _listing(title={"de": "NormalesBrot"})
    FavoriteListing.objects.create(user=user, listing=fav)

    request = _req("get", "/")
    request.session[auth.SESSION_KEY] = user.pk
    body = portal_views.portal_home(request).content.decode()
    assert "♥" in body  # избранное закрашено
    assert "♡" in body  # не избранное — контур
    assert "/konto/favoriten/" in body


def test_portal_home_no_hearts_for_anonymous():
    _listing()
    body = portal_views.portal_home(_req("get", "/")).content.decode()
    assert "♥" not in body
    assert "♡" not in body
