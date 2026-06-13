"""G8 / G8a: отзывы о бизнесе на порталах — отправка (PortalUser, один на
бизнес), агрегат рейтинга, модерация (hidden исключается), страница бизнеса."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.aggregator import auth, reviews, reviews_views
from apps.aggregator.models import (
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
