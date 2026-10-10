"""T-8.3 «Coupon holen»: купон акции, выдача и погашение на кассе.

План — docs/t8-3-coupon-plan-2026-10-10.md.
"""

import re
from datetime import timedelta
from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

from apps.loyalty.models import Voucher
from apps.promotions import public_views, quick, response, services, views
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_rate_limits():
    cache.clear()
    yield
    cache.clear()


def _tenant(slug="t83", disabled=("orders",)):
    return TenantFactory(
        schema_name=slug.replace("-", "_"), slug=slug, name=slug, disabled_modules=list(disabled)
    )


def _promo(**kw):
    kw.setdefault("status", "active")
    kw.setdefault("available_quantity", 3)
    kw.setdefault("metadata", {"response": "coupon"})
    kw.setdefault("promo_type", Promotion.DISCOUNT)
    kw.setdefault("ends_at", timezone.now() + timedelta(days=2))
    return PromotionFactory(**kw)


def _public(method, path, tenant, data=None, cookies=None, ip="10.83.0.1"):
    rf = RequestFactory()
    request = rf.post(path, data or {}) if method == "post" else rf.get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    request.META["REMOTE_ADDR"] = ip
    for key, value in (cookies or {}).items():
        request.COOKIES[key] = value
    return request


# --- сервис ------------------------------------------------------------------------


def test_issue_coupon_takes_one_from_limit_and_expires_with_promo():
    promo = _promo()
    coupon, created = services.issue_coupon(promo)
    promo.refresh_from_db()
    assert created and coupon.code.startswith("C-")
    assert coupon.promotion_id == promo.pk and coupon.max_uses == 1
    assert coupon.expires_at == promo.ends_at
    assert promo.available_quantity == 2


def test_same_browser_or_same_email_gets_the_same_coupon():
    promo = _promo()
    first, _ = services.issue_coupon(promo, email="a@example.de")
    again, created = services.issue_coupon(promo, existing_code=first.code)
    assert again.pk == first.pk and not created
    by_mail, created = services.issue_coupon(promo, email="A@example.de")
    assert by_mail.pk == first.pk and not created
    promo.refresh_from_db()
    assert promo.available_quantity == 2  # повтор лимит не трогает


def test_no_coupon_when_limit_is_gone_or_promo_inactive():
    promo = _promo(available_quantity=1)
    services.issue_coupon(promo)
    with pytest.raises(services.CouponUnavailable):
        services.issue_coupon(promo)
    paused = _promo(status="paused")
    with pytest.raises(services.CouponUnavailable):
        services.issue_coupon(paused)
    assert Voucher.objects.filter(promotion=paused).count() == 0


def test_coupon_never_spends_at_online_checkout():
    coupon, _ = services.issue_coupon(_promo())
    with pytest.raises(services.VoucherError):
        services.spend_voucher(coupon.code, 1000)
    coupon.refresh_from_db()
    assert coupon.used_count == 0


# --- витрина -------------------------------------------------------------------------


def test_detail_shows_coupon_button_posting_to_coupon_receiver():
    tenant = _tenant()
    promo = _promo()
    body = public_views.promotion_detail(
        _public("get", f"/p/{promo.pk}/", tenant), pk=promo.pk
    ).content.decode()
    assert "data-promo-coupon" in body
    form = re.search(r"<form[^>]*data-promo-coupon[^>]*>", body).group(0)
    assert f"/p/{promo.pk}/coupon/" in form
    assert f"/p/{promo.pk}/kaufen/" not in body


def test_post_issues_coupon_sets_cookie_and_repeat_returns_same():
    tenant = _tenant("t83-post")
    promo = _promo()
    resp = public_views.coupon_create(
        _public("post", f"/p/{promo.pk}/coupon/", tenant), pk=promo.pk
    )
    coupon = Voucher.objects.get(promotion=promo)
    assert resp.status_code == 302 and resp.url == f"/coupon/{coupon.code}/"
    cookie = resp.cookies[public_views.COUPON_COOKIE].value
    again = public_views.coupon_create(
        _public(
            "post",
            f"/p/{promo.pk}/coupon/",
            tenant,
            cookies={public_views.COUPON_COOKIE: cookie},
            ip="10.83.0.2",
        ),
        pk=promo.pk,
    )
    assert again.url == f"/coupon/{coupon.code}/"
    assert Voucher.objects.filter(promotion=promo).count() == 1


def test_receiver_refuses_when_response_is_not_coupon():
    tenant = _tenant("t83-no")
    promo = _promo(metadata={"response": "reserve"})
    resp = public_views.coupon_create(
        _public("post", f"/p/{promo.pk}/coupon/", tenant), pk=promo.pk
    )
    assert resp.url == f"/p/{promo.pk}/"
    assert not Voucher.objects.exists()


def test_coupon_page_shows_code_qr_and_state():
    tenant = _tenant("t83-page")
    coupon, _ = services.issue_coupon(_promo())
    body = public_views.coupon_page(
        _public("get", f"/coupon/{coupon.code}/", tenant), code=coupon.code
    ).content.decode()
    assert coupon.code in body and f"/coupon/{coupon.code}/qr.svg" in body
    assert 'data-coupon-state="valid"' in body
    services.redeem_voucher(coupon.code)
    body = public_views.coupon_page(
        _public("get", f"/coupon/{coupon.code}/", tenant, ip="10.83.0.9"), code=coupon.code
    ).content.decode()
    assert 'data-coupon-state="used"' in body


# --- касса ---------------------------------------------------------------------------


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="kasse", email="kasse@test.de", password="pw12345678"
    )


def _cabinet(method, path, user, tenant, data=None):
    from django.contrib.sessions.middleware import SessionMiddleware

    rf = RequestFactory()
    request = rf.post(path, data or {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def test_scanner_redeems_coupon_once(user):
    tenant = _tenant("t83-scan")
    coupon, _ = services.issue_coupon(_promo())
    body = views.redeem_detail(
        _cabinet("get", f"/promotions/redeem/{coupon.code}/", user, tenant), code=coupon.code
    ).content.decode()
    assert "data-redeem-coupon" in body and 'value="coupon"' in body
    views.redeem_action(
        _cabinet("post", "/x/", user, tenant, {"action": "coupon"}), code=coupon.code
    )
    coupon.refresh_from_db()
    assert coupon.used_count == 1
    req = _cabinet("post", "/x/", user, tenant, {"action": "coupon"})
    views.redeem_action(req, code=coupon.code)
    coupon.refresh_from_db()
    assert coupon.used_count == 1  # второй раз не гасится
    assert any("bereits" in str(m) for m in req._messages)


# --- кабинет -------------------------------------------------------------------------


def test_coupon_response_is_offered_in_form_assistant_and_flyer():
    tenant = _tenant("t83-cab")
    assert response.COUPON in dict(response.CHOICES)
    assert response.COUPON in [k for k, _l, _h in quick.response_options(tenant)]
    from apps.promotions import flyer

    assert "Coupon" in flyer.call_to_action(_promo(), tenant)


def test_list_counts_issued_and_redeemed_coupons(user):
    tenant = _tenant("t83-list")
    promo = _promo(available_quantity=5)
    first, _ = services.issue_coupon(promo)
    services.issue_coupon(promo, email="b@example.de")
    services.redeem_voucher(first.code)
    body = views.promotion_list(_cabinet("get", "/promotions/", user, tenant)).content.decode()
    assert "Coupons 2 · eingelöst 1" in body
