"""T-8.2 «Zurücklegen» — отклик акции и старый движок резерва на витрине.

План — docs/t8-2-zuruecklegen-plan-2026-10-10.md.
"""

import re
import uuid
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages.middleware import MessageMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.orders.models import Order
from apps.promotions import public_views, response, services
from apps.promotions.models import Promotion, Reservation
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(slug, *, disabled=(), profile=""):
    tenant = TenantFactory(
        schema_name=slug.replace("-", "_"), slug=slug, name=slug, disabled_modules=list(disabled)
    )
    if profile:
        tenant.site_config = {**(tenant.site_config or {}), "profile": profile}
        tenant.save(update_fields=["site_config"])
    return tenant


def _request(method, path, tenant, data=None):
    rf = RequestFactory()
    request = rf.post(path, data or {}) if method == "post" else rf.get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    request.META["REMOTE_ADDR"] = f"10.8.2.{abs(hash(path)) % 250}"
    return request


def _promo(**kw):
    kw.setdefault("status", "active")
    kw.setdefault("available_quantity", 5)
    kw.setdefault("promo_type", Promotion.DISCOUNT)
    return PromotionFactory(**kw)


# --- резолвер ------------------------------------------------------------------


def test_no_tenant_keeps_previous_behaviour():
    assert response.response_for(_promo(), None) == response.BUY


def test_service_or_stay_target_goes_to_booking():
    promo = SimpleNamespace(target_kind="service", metadata={})
    assert response.response_for(promo, object()) == response.BOOKING


def test_without_orders_module_promo_is_put_aside():
    tenant = _tenant("t82-cafe", disabled=["orders"])
    assert response.response_for(_promo(), tenant) == response.RESERVE


def test_with_orders_module_promo_is_bought():
    tenant = _tenant("t82-shop")
    assert response.response_for(_promo(), tenant) == response.BUY


def test_nur_aktionen_storefront_never_sells_online():
    tenant = _tenant("t82-lite", profile="aktionen")
    assert tenant.is_module_active("orders")
    assert response.response_for(_promo(), tenant) == response.RESERVE


def test_owner_choice_wins_and_falls_back_when_impossible():
    tenant = _tenant("t82-choice", disabled=["orders", "jobs"])
    assert response.response_for(_promo(metadata={"response": "show"}), tenant) == response.SHOW
    # заявка без модуля заявок / покупка без модуля заказов → автоматика
    assert response.response_for(_promo(metadata={"response": "inquire"}), tenant) == "reserve"
    assert response.response_for(_promo(metadata={"response": "buy"}), tenant) == "reserve"
    shop = _tenant("t82-choice2")
    assert response.response_for(_promo(metadata={"response": "inquire"}), shop) == "inquire"
    assert response.response_for(_promo(metadata={"response": "reserve"}), shop) == "reserve"
    assert response.response_for(_promo(metadata={"response": "bogus"}), shop) == "buy"


# --- витрина -------------------------------------------------------------------


def _forms(body):
    return re.findall(r"<form[^>]*>.*?</form>", body, flags=re.S)


def test_reserve_page_posts_to_reserve_without_delivery_or_payment():
    tenant = _tenant("t82-page", disabled=["orders"])
    promo = _promo()
    body = public_views.promotion_detail(
        _request("get", f"/p/{promo.pk}/", tenant), pk=promo.pk
    ).content.decode()
    assert "data-promo-reserve" in body
    assert f"/p/{promo.pk}/kaufen/" not in body
    form = next(f for f in _forms(body) if f"/p/{promo.pk}/reserve/" in f[: f.index(">")])
    fields = set(re.findall(r'name="([^"]+)"', form))
    assert fields == {
        "csrfmiddlewaretoken",
        "website",
        "form_token",
        "channel",
        "name",
        "email",
        "phone",
        "quantity",
    }
    assert "Zurücklegen lassen" in body or "Put aside for me" in body


def test_show_response_renders_no_form_and_no_buybar():
    tenant = _tenant("t82-show", disabled=["orders"])
    promo = _promo(metadata={"response": "show"}, price_override="2.00")
    body = public_views.promotion_detail(
        _request("get", f"/p/{promo.pk}/", tenant), pk=promo.pk
    ).content.decode()
    assert "data-promo-show" in body
    assert 'data-modal-open="promo-reserve-modal"' not in body
    assert "data-buybar" not in body


def test_inquire_response_opens_request_with_promo_subject():
    tenant = _tenant("t82-inq")
    promo = _promo(metadata={"response": "inquire"})
    body = public_views.promotion_detail(
        _request("get", f"/p/{promo.pk}/", tenant), pk=promo.pk
    ).content.decode()
    assert "data-promo-inquire" in body
    assert "betreff=" in body


def test_reserve_conditions_shown_for_discount_type_promo():
    tenant = _tenant("t82-cond", disabled=["orders"])
    promo = _promo(max_per_customer=2, reservation_ttl_hours=3)
    body = public_views.promotion_detail(
        _request("get", f"/p/{promo.pk}/", tenant), pk=promo.pk
    ).content.decode()
    assert "📦" in body and "👤" in body


# --- приёмники POST ----------------------------------------------------------------


def test_kaufen_without_orders_module_creates_no_order_and_no_404():
    tenant = _tenant("t82-404", disabled=["orders"])
    promo = _promo()
    resp = public_views.promotion_purchase(
        _request(
            "post",
            f"/p/{promo.pk}/kaufen/",
            tenant,
            {
                "name": "Anna",
                "email": "a@example.de",
                "quantity": "1",
                "form_token": uuid.uuid4().hex,
            },
        ),
        pk=promo.pk,
    )
    assert resp.status_code == 302 and resp.url == f"/p/{promo.pk}/"
    assert not Order.objects.exists()


def test_reserve_requires_email_or_phone():
    tenant = _tenant("t82-contact", disabled=["orders"])
    promo = _promo()
    resp = public_views.reservation_create(
        _request(
            "post",
            f"/p/{promo.pk}/reserve/",
            tenant,
            {"name": "Anna", "quantity": "1", "form_token": uuid.uuid4().hex},
        ),
        pk=promo.pk,
    )
    assert resp.status_code == 200
    assert not Reservation.objects.exists()


def test_reserve_with_phone_only_creates_reservation():
    tenant = _tenant("t82-phone", disabled=["orders"])
    promo = _promo()
    resp = public_views.reservation_create(
        _request(
            "post",
            f"/p/{promo.pk}/reserve/",
            tenant,
            {"name": "Anna", "phone": "0212 123", "quantity": "1", "form_token": uuid.uuid4().hex},
        ),
        pk=promo.pk,
    )
    assert resp.status_code == 302 and resp.url.startswith("/r/")
    assert Reservation.objects.count() == 1


def test_reserve_rejects_service_target():
    from apps.booking.models import Service

    tenant = _tenant("t82-svc", disabled=["orders"])
    service = Service.objects.create(name="Schnitt", price_cents=2000)
    promo = _promo(service=service)
    resp = public_views.reservation_create(
        _request("post", f"/p/{promo.pk}/reserve/", tenant, {"name": "A", "phone": "1"}),
        pk=promo.pk,
    )
    assert resp.status_code == 302 and resp.url == f"/p/{promo.pk}/"
    assert not Reservation.objects.exists()


# --- движок --------------------------------------------------------------------------


def test_limit_per_customer_holds_for_phone_only_customers():
    promo = _promo(max_per_customer=1)
    services.reserve(promo, name="A", phone="0212 555")
    with pytest.raises(services.ReservationLimitReached):
        services.reserve(promo, name="A", phone="0212 555")


def test_hold_never_outlives_the_promotion():
    ends = timezone.now() + timedelta(hours=1)
    promo = _promo(reservation_ttl_hours=24, ends_at=ends)
    res = services.reserve(promo, name="A", email="a@example.de")
    assert res.expires_at == ends


def test_scanner_hands_out_unconfirmed_reservation():
    promo = _promo(auto_confirm=False)
    res = services.reserve(promo, name="A", email="b@example.de")
    assert res.status == "pending"
    res = services.fulfill(res)
    assert res.status == "fulfilled"


def test_confirmation_page_shows_hold_until():
    tenant = _tenant("t82-conf", disabled=["orders"])
    promo = _promo()
    res = services.reserve(promo, name="A", email="c@example.de")
    body = public_views.reservation_confirmation(
        _request("get", f"/r/{res.reference_code}/", tenant), code=res.reference_code
    ).content.decode()
    assert "data-hold-until" in body
