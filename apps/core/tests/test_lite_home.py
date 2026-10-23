"""T-8.31a «Start» лёгкого кабинета (план docs/t8-31-mein-laden-plan-2026-10-20.md §2)."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import Resolver404, resolve
from django.utils import timezone

from apps.core import lite_home, modules, views
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(lite=True):
    from apps.tenants import onboarding

    slug = f"lh-{uuid4().hex[:6]}"
    t = TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name="Bäckerei Krume")
    t.site_config = {"profile": "aktionen"} if lite else {}
    t.save()
    onboarding.mark_complete(t)
    return t


def _user():
    o = uuid4().hex[:8]
    return get_user_model().objects.create_user(username=f"lh-{o}", password="pw12345678")


def _req(tenant, user=None):
    req = RequestFactory().get("/dashboard/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user, req.tenant = user or _user(), tenant
    return req


def _body(tenant):
    resp = views.dashboard(_req(tenant))
    assert resp.status_code == 200
    return resp.content.decode()


def test_lite_dashboard_renders_start():
    body = _body(_tenant())
    assert "data-lite-home" in body
    assert "Bäckerei Krume" in body
    assert "/promotions/schnell/" in body  # «＋ Neue Aktion»


def test_full_dashboard_is_not_lite_home():
    body = _body(_tenant(lite=False))
    assert "data-lite-home" not in body


def test_untouched_onboarding_still_redirects_to_setup():
    """Порядок в dashboard(): мастер раньше лёгкой главной."""
    slug = f"lh-{uuid4().hex[:6]}"
    t = TenantFactory(schema_name=slug.replace("-", "_"), slug=slug)
    t.site_config = {"profile": "aktionen"}
    t.save()
    resp = views.dashboard(_req(t))
    assert resp.status_code == 302 and resp.url == "/dashboard/setup/"


def test_promo_counts_and_featured_is_soonest_ending_active():
    t = _tenant()
    now = timezone.now()
    PromotionFactory(status="active", ends_at=now + timedelta(days=5), title={"de": "Später"})
    soon = PromotionFactory(status="active", ends_at=now + timedelta(hours=3), title={"de": "Bald"})
    PromotionFactory(status="active", ends_at=None, title={"de": "Ohne Ende"})
    PromotionFactory(status="scheduled", title={"de": "Geplant"})
    PromotionFactory(status="ended", title={"de": "Vorbei"})
    counts = lite_home.promo_counts()
    assert counts == {"active": 3, "scheduled": 1}
    assert lite_home.featured_promo().pk == soon.pk
    body = _body(t)
    assert "data-lite-featured" in body and "Bald" in body


def test_featured_is_none_without_active():
    PromotionFactory(status="draft")
    assert lite_home.featured_promo() is None


def test_product_counts_total_and_without_photo():
    from apps.catalog.models import Product

    Product.objects.create(name={"de": "Mit"}, base_price=1, images=[{"url": "/x.jpg"}])
    Product.objects.create(name={"de": "Ohne"}, base_price=1, images=[])
    Product.objects.create(name={"de": "Aus"}, base_price=1, images=[], is_active=False)
    assert lite_home.product_counts() == {"total": 2, "no_photo": 1}


def test_chips_website_only_when_active_and_telegram_off_without_channel():
    t = _tenant()
    active = PromotionFactory(status="active")
    draft = PromotionFactory(status="draft")
    chips = {c["key"]: c["ok"] for c in lite_home.visibility_chips(t, active)}
    assert chips["website"] is True
    assert chips["stadtportal"] is False  # листинга нет
    assert chips["telegram"] is False
    assert {c["key"]: c["ok"] for c in lite_home.visibility_chips(t, draft)}["website"] is False


def test_chips_stadtportal_only_when_listing_public():
    from apps.aggregator.models import AggregatorListing

    t = _tenant()
    t.in_city_catalog = True
    t.email_pending = False
    t.save()
    promo = PromotionFactory(status="active")
    AggregatorListing.objects.create(
        tenant_schema=t.schema_name,
        listing_kind=AggregatorListing.KIND_PROMOTION,
        source_ref=str(promo.pk),
        title={"de": "x"},
    )
    chip = {c["key"]: c["ok"] for c in lite_home.visibility_chips(t, promo)}["stadtportal"]
    expected = AggregatorListing.objects.public().filter(source_ref=str(promo.pk)).exists()
    assert expected is True and chip is True
    promo.status = "paused"
    assert not {c["key"]: c["ok"] for c in lite_home.visibility_chips(t, promo)}["stadtportal"]


def _resolves(path):
    try:
        resolve(path.split("?")[0].split("#")[0])
    except Resolver404:
        return False
    return True


def test_next_step_without_active_promo_points_to_assistant():
    t = _tenant()
    step = lite_home.next_step(t, counts={"active": 0, "scheduled": 0}, products=None)
    assert step["key"] == "first_promo" and "/promotions/schnell/" in step["url"]


def test_next_step_products_without_photo():
    t = _tenant()
    # KA-12 E7.2: Impressum заполнен — следующий шаг про фото.
    t.address, t.contact_email, t.small_business = "Markt 1, Solingen", "i@k.de", True
    step = lite_home.next_step(
        t, counts={"active": 1, "scheduled": 0}, products={"total": 3, "no_photo": 2}
    )
    assert step["key"] == "photos"


def test_next_step_incomplete_impressum_after_first_promo():
    """KA-12 E7.2: после первой акции — дозаполнить Impressum (предупреждение, не блок)."""
    t = _tenant()
    t.address = ""
    step = lite_home.next_step(
        t, counts={"active": 1, "scheduled": 0}, products={"total": 3, "no_photo": 2}
    )
    assert step["key"] == "impressum" and step["url"].endswith("#sec-recht")
    t.is_demo = True  # демо не пугаем предупреждением
    step = lite_home.next_step(
        t, counts={"active": 1, "scheduled": 0}, products={"total": 3, "no_photo": 2}
    )
    assert step["key"] == "photos"


def test_every_next_step_link_resolves():
    for rule in lite_home.NEXT_STEPS:
        url = lite_home._step_url(rule)
        assert _resolves(url), (rule, url)


def test_lite_nav_is_start_first_and_tabbar_four():
    nav = [i["url_name"] for i in modules.sidebar_nav(_tenant())]
    assert nav[:4] == [
        "dashboard",
        "promotions:promotion-list",
        # T-8.32b (KA-3 В-1): у «Aktionen» вместо «Angebot» — «Nachrichten»
        "inbox:list",
        "lite-visibility",
    ]
    assert "lite-business" in nav and "lite-share" in nav


def test_start_query_budget(django_assert_max_num_queries):
    t = _tenant()
    PromotionFactory(status="active", ends_at=timezone.now() + timedelta(hours=2))
    req = _req(t)
    with django_assert_max_num_queries(16):
        views.dashboard(req)


def test_start_survives_broken_visibility_status():
    """Ревью T-8.31: сломанный статус каталога не роняет главную лёгкого кабинета."""
    from unittest import mock

    t = _tenant()
    PromotionFactory(status="active")
    with mock.patch("apps.promotions.where._catalog_state", side_effect=RuntimeError("x")):
        assert lite_home.visibility_chips(t, lite_home.featured_promo()) == []
        assert views.dashboard(_req(t)).status_code == 200
