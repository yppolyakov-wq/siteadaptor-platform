"""T-8.31b «So sehen Kunden die Aktion» (план docs/t8-31-mein-laden-plan-2026-10-20.md §2)."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.aggregator.models import AggregatorListing
from apps.promotions import lite_views, views
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    slug = f"pv-{uuid4().hex[:6]}"
    t = TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name="Krume", **kw)
    t.site_config = {"profile": "aktionen"}
    t.save()
    return t


def _req(tenant, method="get", path="/promotions/x/ansicht/", data=None):
    rf = RequestFactory()
    req = rf.post(path, data or {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"pv-{o}", password="pw12345678")
    req.tenant = tenant
    return req


def _body(tenant, promo):
    resp = lite_views.promotion_preview(_req(tenant), pk=promo.pk)
    assert resp.status_code == 200
    return resp.content.decode()


@pytest.mark.parametrize("status", ["draft", "scheduled", "active", "paused"])
def test_preview_renders_for_every_status(status):
    t = _tenant()
    promo = PromotionFactory(status=status, title={"de": "Brötchen −30 %"})
    body = _body(t, promo)
    assert "data-promo-preview" in body and "Brötchen −30 %" in body
    assert body.count("data-lite-preview") == 2  # обе панели: витрина и портал
    assert 'inert aria-hidden="true"' in body
    assert f"/p/{promo.pk}/" in body  # настоящая карточка витрины


def test_portal_listing_is_never_saved_and_not_featured():
    t = _tenant()
    promo = PromotionFactory(status="active")
    AggregatorListing.objects.create(
        tenant_schema=t.schema_name,
        listing_kind=AggregatorListing.KIND_PROMOTION,
        source_ref=str(promo.pk),
        title={"de": "x"},
        featured_until=timezone.now() + timedelta(days=3),
    )
    listing = lite_views.portal_listing(t, promo)
    assert listing.pk is None and not listing.is_featured_now
    before = AggregatorListing.objects.count()
    _body(t, promo)
    assert AggregatorListing.objects.count() == before


def test_mystery_price_not_in_portal_pane():
    t = _tenant()
    promo = PromotionFactory(
        status="active", compare_at_price="10.00", discount_percent=50, discount_style="mystery"
    )
    listing = lite_views.portal_listing(t, promo)
    assert listing.new_price is None and listing.old_price is None
    body = _body(t, promo)
    portal = body[body.index('data-preview-pane="portal"') : body.index("data-promo-where")]
    assert "10,00" not in portal and "5,00" not in portal


def test_listing_defaults_match_sync():
    """Превью = синк: строка, которую пишет sync_listing, совпадает с превью."""
    from apps.aggregator import tasks

    t = TenantFactory(schema_name="public", slug="pv-public", name="X", city="Solingen")
    promo = PromotionFactory(status="active", compare_at_price="3.00", discount_percent=20)
    assert tasks.sync_listing("public", str(promo.pk)) == "upserted"
    saved = AggregatorListing.objects.get(source_ref=str(promo.pk))
    preview = lite_views.portal_listing(t, promo)
    for field in (
        "title",
        "teaser",
        "new_price",
        "old_price",
        "discount_percent",
        "detail_url",
        "ends_at",
        "city",
        "business_name",
        "city_category",
    ):
        assert getattr(preview, field) == getattr(saved, field), field


def test_foreign_pk_is_404():
    with pytest.raises(Http404):
        lite_views.promotion_preview(_req(_tenant()), pk=uuid4())


def test_where_rows_on_page():
    t = _tenant()
    promo = PromotionFactory(status="paused")
    body = _body(t, promo)
    for key in ("website", "stadtportal", "telegram", "flyer"):
        assert f'data-where-row="{key}"' in body
    assert 'data-transition="active"' in body and 'data-transition="ended"' in body


def test_transition_next_returns_to_preview():
    t = _tenant()
    promo = PromotionFactory(status="active")
    nxt = reverse("promotions:promotion-preview", args=[promo.pk])
    resp = views.promotion_transition(
        _req(t, "post", "/x/", {"target": "paused", "next": nxt}), pk=promo.pk
    )
    assert resp.status_code == 302 and resp.url == nxt
    promo.refresh_from_db()
    assert promo.status == "paused"


@pytest.mark.parametrize("bad", ["//evil.example/", "https://evil.example/", "/\\evil"])
def test_transition_next_rejects_foreign(bad):
    t = _tenant()
    promo = PromotionFactory(status="active")
    resp = views.promotion_transition(
        _req(t, "post", "/x/", {"target": "paused", "next": bad}), pk=promo.pk
    )
    assert resp.url == reverse("promotions:promotion-edit", args=[promo.pk])


def test_transition_without_next_unchanged():
    t = _tenant()
    promo = PromotionFactory(status="active")
    resp = views.promotion_transition(_req(t, "post", "/x/", {"target": "paused"}), pk=promo.pk)
    assert resp.url == reverse("promotions:promotion-edit", args=[promo.pk])


def test_accent_only_hex():
    t = _tenant()
    t.primary_color = "red;background:url(x)"
    assert lite_views._accent(t) == "#4f46e5"
    t.primary_color = "#aabbcc"
    assert lite_views._accent(t) == "#aabbcc"


def test_start_and_lite_list_link_to_preview():
    from apps.core import views as core_views
    from apps.promotions import views as promo_views
    from apps.tenants import onboarding

    t = _tenant()
    onboarding.mark_complete(t)
    promo = PromotionFactory(status="active", ends_at=timezone.now() + timedelta(hours=2))
    url = reverse("promotions:promotion-preview", args=[promo.pk])
    assert url in core_views.dashboard(_req(t, path="/dashboard/")).content.decode()
    assert url in promo_views.promotion_list(_req(t, path="/promotions/")).content.decode()


def test_preview_query_budget(django_assert_max_num_queries):
    t = _tenant()
    promo = PromotionFactory(status="active")
    req = _req(t)
    with django_assert_max_num_queries(25):
        lite_views.promotion_preview(req, pk=promo.pk)
