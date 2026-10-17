"""Д1-4 (T-8.10c): показ «Was heute starten?» и один тап → заполненный ассистент.

План — docs/d1-ai-photo-promo-today-plan-2026-10-17.md §7 (замки 20–24)."""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.models import Product
from apps.inventory.models import Lot
from apps.promotions import today, views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]

TODAY = timezone.localdate()


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="heute", password="pw12345678")


def _tenant(**kw):
    kw.setdefault("site_config", {"lots_enabled": True})
    kw.setdefault("schema_name", f"h_{uuid.uuid4().hex[:8]}")
    kw.setdefault("slug", kw["schema_name"].replace("_", "-"))
    return TenantFactory(**kw)


def _req(method, path, user, tenant, data=None):
    rf = RequestFactory()
    request = rf.post(path, data or {}) if method == "post" else rf.get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def _mhd_lot():
    product = Product.objects.create(name={"de": "Joghurt"}, base_price=Decimal("1.99"))
    return product, Lot.objects.create(
        product=product, mhd=TODAY + timedelta(days=1), qty_received=8, qty_remaining=8
    )


def _service():
    from apps.booking.models import Service

    return Service.objects.create(name="Haarschnitt", duration_minutes=30, price_cents=3000)


def _slots():
    tomorrow = TODAY + timedelta(days=1)
    return [timezone.make_aware(datetime.combine(tomorrow, time(10, m))) for m in (0, 20, 40)]


def test_link_prefills_assistant_from_db(user):
    tenant = _tenant()
    product, lot = _mhd_lot()
    html = views.promotion_quick(
        _req("get", "/promotions/schnell/", user, tenant, {"vorschlag": f"mhd:{lot.pk}"})
    ).content.decode()
    assert 'value="Joghurt"' in html and f'value="mhd:{lot.pk}"' in html
    assert 'name="percent" value="50"' in html


def test_forged_or_stale_key_gives_empty_form_and_message(user):
    tenant = _tenant()
    html = views.promotion_quick(
        _req("get", "/promotions/schnell/", user, tenant, {"vorschlag": "mhd:999999"})
    ).content.decode()
    assert 'value="mhd:999999"' not in html


def test_post_takes_target_from_recomputed_suggestion_not_from_form(user):
    tenant = _tenant()
    product, lot = _mhd_lot()
    other = Product.objects.create(name={"de": "Fremd"}, base_price=Decimal("9"))
    data = {
        "vorschlag": f"mhd:{lot.pk}",
        "title": "Joghurt",
        "percent": "50",
        "term": "week",
        "customer_response": "reserve",
        "product": str(other.pk),  # подмена цели в форме
        "publish": "draft",
    }
    views.promotion_quick(_req("post", "/promotions/schnell/", user, tenant, data))
    promo = Promotion.objects.get()
    assert promo.product_id == product.pk
    assert promo.metadata["suggestion"] == "mhd"


def test_stale_key_on_post_does_not_save(user):
    tenant = _tenant()
    data = {
        "vorschlag": "mhd:424242",
        "title": "X",
        "term": "week",
        "customer_response": "reserve",
        "publish": "draft",
    }
    resp = views.promotion_quick(_req("post", "/promotions/schnell/", user, tenant, data))
    assert resp.status_code == 200 and not Promotion.objects.exists()


def test_service_target_creates_no_product_and_needs_no_response(user):
    tenant = _tenant()
    service = _service()
    key = f"slots:{service.pk}:{(TODAY + timedelta(days=1)).isoformat()}"
    data = {
        "vorschlag": key,
        "title": "Haarschnitt – Happy Hour",
        "percent": "20",
        "new_price": "",
        "old_price": "30",  # цена услуги: attach_product создал бы товар
        "term": "week",
        "publish": "draft",
    }
    before = Product.objects.count()
    with mock.patch("apps.booking.availability.service_slots", return_value=_slots()):
        views.promotion_quick(_req("post", "/promotions/schnell/", user, tenant, data))
    promo = Promotion.objects.get()
    assert Product.objects.count() == before
    assert promo.service_id == service.pk and promo.product_id is None
    assert promo.target_rules["hour_from"] == 10
    assert "response" not in promo.metadata


def test_limit_still_applies_when_saving_from_suggestion(user):
    from apps.promotions import limits

    tenant = _tenant()
    product, lot = _mhd_lot()
    data = {
        "vorschlag": f"mhd:{lot.pk}",
        "title": "Joghurt",
        "percent": "50",
        "term": "week",
        "customer_response": "reserve",
        "publish": "now",
    }
    with mock.patch.object(limits, "activate", side_effect=limits.ActivationLimit("x")) as act:
        views.promotion_quick(_req("post", "/promotions/schnell/", user, tenant, data))
    act.assert_called_once()
    assert Promotion.objects.get().status == "draft"


def test_card_on_promotion_list(user):
    tenant = _tenant()
    _mhd_lot()
    html = views.promotion_list(_req("get", "/promotions/", user, tenant)).content.decode()
    assert "data-today-suggestions" in html and "?vorschlag=mhd" in html
    assert today.card_context(_req("get", "/dashboard/", user, tenant))


def test_dashboard_context_has_card(user):
    from apps.core import views as core_views

    tenant = _tenant()
    _mhd_lot()
    assert core_views._today_suggestions(_req("get", "/dashboard/", user, tenant))
    off = _tenant(disabled_modules=["promotions"])
    assert core_views._today_suggestions(_req("get", "/dashboard/", user, off)) == []


def test_dismiss_hides_card_and_rejects_foreign_next(user):
    tenant = _tenant()
    _product, lot = _mhd_lot()
    resp = views.today_dismiss(
        _req(
            "post",
            "/promotions/heute/ausblenden/",
            user,
            tenant,
            {"key": f"mhd:{lot.pk}", "next": "//evil.example/"},
        )
    )
    assert resp.status_code == 302 and "evil" not in resp["Location"]
    assert today.suggestions(tenant) == []


def test_dismiss_is_post_only(user):
    tenant = _tenant()
    assert views.today_dismiss(_req("get", "/x/", user, tenant)).status_code == 405
