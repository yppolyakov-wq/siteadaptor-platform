"""G8 / G8a: отзывы о бизнесе на порталах — отправка (PortalUser, один на
бизнес), агрегат рейтинга, модерация (hidden исключается), страница бизнеса."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.aggregator import auth, portal_views, reviews, reviews_views, views
from apps.aggregator.models import (
    AggregatorListing,
    AggregatorPortal,
    BusinessRating,
    BusinessReview,
    PortalUser,
)
from apps.tenants.tests.factories import TenantFactory

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


def _business(slug="werkstatt-mueller"):
    return TenantFactory(slug=slug, name="Werkstatt Müller", city="München")


def _user():
    return PortalUser.objects.create(email=f"{uuid.uuid4().hex}@kunde.test")


def _req(method="get", path="/", data=None, user=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.portal = _portal()
    if user is not None:
        request.session[auth.SESSION_KEY] = user.pk
    return request


# --- отправка отзыва --------------------------------------------------------------


def test_submit_review_creates_and_aggregates():
    business, user = _business(), _user()
    resp = reviews_views.submit_review(
        _req("post", data={"rating": "5", "comment": "Top!"}, user=user), slug=business.slug
    )
    assert resp.status_code == 302
    review = BusinessReview.objects.get(tenant_schema=business.schema_name)
    assert review.rating == 5 and review.author == user
    rating = BusinessRating.objects.get(tenant_schema=business.schema_name)
    assert rating.avg_rating == Decimal("5.00") and rating.review_count == 1


def test_one_review_per_business_updates():
    business, user = _business(), _user()
    reviews_views.submit_review(_req("post", data={"rating": "3"}, user=user), slug=business.slug)
    reviews_views.submit_review(
        _req("post", data={"rating": "5", "comment": "besser"}, user=user), slug=business.slug
    )
    assert BusinessReview.objects.filter(tenant_schema=business.schema_name).count() == 1
    assert BusinessRating.objects.get(tenant_schema=business.schema_name).avg_rating == Decimal(
        "5.00"
    )


def test_submit_requires_login():
    business = _business()
    resp = reviews_views.submit_review(_req("post", data={"rating": "5"}), slug=business.slug)
    assert resp.url == "/konto/login/"
    assert not BusinessReview.objects.exists()


def test_submit_rejects_bad_rating():
    business, user = _business(), _user()
    reviews_views.submit_review(_req("post", data={"rating": "9"}, user=user), slug=business.slug)
    reviews_views.submit_review(_req("post", data={"rating": "x"}, user=user), slug=business.slug)
    assert not BusinessReview.objects.exists()


# --- страница бизнеса -------------------------------------------------------------


def test_business_page_404_unknown_slug():
    with pytest.raises(Http404):
        reviews_views.business_page(_req(), slug="does-not-exist")


def test_business_page_renders_with_reviews():
    business, user = _business(), _user()
    reviews_views.submit_review(
        _req("post", data={"rating": "4", "comment": "GuterService"}, user=user), slug=business.slug
    )
    body = reviews_views.business_page(_req(user=user), slug=business.slug).content.decode()
    assert "Werkstatt Müller" in body and "GuterService" in body


def test_business_page_emits_aggregaterating_jsonld():
    business, user = _business(), _user()
    reviews_views.submit_review(_req("post", data={"rating": "4"}, user=user), slug=business.slug)
    body = reviews_views.business_page(_req(user=user), slug=business.slug).content.decode()
    assert "AggregateRating" in body and '"reviewCount":1' in body


def test_verified_emails_matches_customer_case_insensitive():
    from django.db import connection

    from apps.promotions.models import Customer

    Customer.objects.create(name="Gast", email="Gast@Test.de")
    result = reviews.verified_emails(connection.schema_name, ["gast@test.de", "nobody@x.de"])
    assert result == {"gast@test.de"}


def test_verified_emails_empty_on_bad_schema():
    assert reviews.verified_emails("schema_does_not_exist_xyz", ["a@b.de"]) == set()


# --- агрегат / модерация ----------------------------------------------------------


def test_recompute_excludes_hidden():
    business = _business()
    u1, u2 = _user(), _user()
    BusinessReview.objects.create(
        tenant_schema=business.schema_name, tenant_slug=business.slug, author=u1, rating=4
    )
    BusinessReview.objects.create(
        tenant_schema=business.schema_name,
        tenant_slug=business.slug,
        author=u2,
        rating=2,
        status=BusinessReview.STATUS_HIDDEN,
    )
    reviews.recompute_rating(business.schema_name)
    rating = BusinessRating.objects.get(tenant_schema=business.schema_name)
    assert rating.review_count == 1 and rating.avg_rating == Decimal("4.00")


def test_ratings_for_batch_skips_unreviewed():
    b1, b2 = _business("a"), _business("b")
    user = _user()
    reviews_views.submit_review(_req("post", data={"rating": "5"}, user=user), slug=b1.slug)
    result = reviews.ratings_for([b1.schema_name, b2.schema_name])
    assert b1.schema_name in result
    assert b2.schema_name not in result  # без отзывов — нет строки рейтинга


# --- G8b: звёзды в выдаче ---------------------------------------------------------


def _listing(schema, slug, **kw):
    defaults = {
        "tenant_schema": schema,
        "tenant_slug": slug,
        "business_name": "Werkstatt Müller",
        "business_type": "other",
        "city": "München",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Ölwechsel-Aktion"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def test_portal_home_shows_stars_and_business_link():
    business = _business()
    _listing(schema=business.schema_name, slug=business.slug)
    BusinessRating.objects.create(
        tenant_schema=business.schema_name, avg_rating=Decimal("4.50"), review_count=3
    )
    body = portal_views.portal_home(_req("get", "/")).content.decode()
    # счётчик (int) локаль-стабилен; число avg в de-локали с запятой — не проверяем
    assert "(3)" in body  # звёзды + счётчик отзывов на карточке
    assert f"/unternehmen/{business.slug}/" in body  # ссылка на страницу бизнеса


def test_city_listing_shows_stars(settings):
    settings.ROOT_URLCONF = "config.urls_public"
    _listing(schema="t9", slug="x9", city="Hilden")
    BusinessRating.objects.create(tenant_schema="t9", avg_rating=Decimal("4.00"), review_count=2)
    request = RequestFactory().get("/entdecken/Hilden/")
    body = views.city_listing(request, city="Hilden").content.decode()
    assert "(2)" in body  # счётчик отзывов на карточке (locale-safe)


def test_business_page_renders_on_main_domain_without_portal(settings):
    """A8/E-2: страница бизнеса доступна и на главном /entdecken (portal=None):
    база _base.html, отзывы read-only (без portal-login), url-name
    'portal-business' резолвится и в urls_public."""
    from django.urls import reverse

    settings.ROOT_URLCONF = "config.urls_public"
    business = _business(slug="haupt-domain")
    user = _user()
    # отзыв создаём портальным запросом (сабмит остаётся портал-only)
    reviews_views.submit_review(
        _req("post", data={"rating": "5", "comment": "TopService"}, user=user),
        slug=business.slug,
    )
    assert reverse("portal-business", kwargs={"slug": "haupt-domain"}).startswith(
        "/entdecken/unternehmen/"
    )
    request = RequestFactory().get("/entdecken/unternehmen/haupt-domain/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    # главный домен: request.portal отсутствует
    body = reviews_views.business_page(request, slug="haupt-domain").content.decode()
    assert "Werkstatt Müller" in body
    assert "TopService" in body  # отзывы читаются
    assert "portal-login" not in body and "Log in" not in body  # логина нет
    assert "city portal" in body  # хинт про сабмит на портале
