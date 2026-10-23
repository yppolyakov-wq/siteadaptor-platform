"""KA-H9 (аудит KA-5f/g): касса сертификатов, чужой купон, купон закончившейся акции,
«Geschäft» только владельцу."""

import uuid
from datetime import timedelta
from importlib import import_module
from unittest import mock

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

from apps.loyalty.models import Voucher
from apps.promotions import public_views, services, views
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_rate_limits(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    cache.clear()
    yield
    cache.clear()


def _gift(balance=5000):
    return Voucher.objects.create(
        code=f"GS-{uuid.uuid4().hex[:6].upper()}",
        label="Geschenkgutschein",
        balance_cents=balance,
        discount_cents=balance,
        max_uses=0,
    )


def _promo(**kw):
    kw.setdefault("status", "active")
    kw.setdefault("available_quantity", 3)
    kw.setdefault("metadata", {"response": "coupon"})
    kw.setdefault("promo_type", Promotion.DISCOUNT)
    kw.setdefault("ends_at", timezone.now() + timedelta(days=2))
    return PromotionFactory(**kw)


def _cab(data=None, method="post", query=""):
    rf = RequestFactory()
    path = "/promotions/vouchers/einloesen/" + query
    request = rf.post(path, data or {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"k-{owner}", email=f"k-{owner}@test.de", password="pw12345678"
    )
    return request


# --- L1: сертификат с остатком --------------------------------------------------------


def test_redeem_voucher_refuses_balance_voucher():
    gift = _gift()
    with pytest.raises(services.VoucherError) as exc:
        services.redeem_voucher(gift.code)
    assert exc.value.reason == "needs_amount"
    gift.refresh_from_db()
    assert (gift.used_count, gift.balance_cents) == (0, 5000)


def test_redeem_balance_decrements_and_returns_rest():
    gift = _gift()
    voucher = services.redeem_balance(gift.code, 1250)
    assert voucher.balance_cents == 3750 and voucher.used_count == 1


def test_redeem_balance_insufficient_keeps_balance():
    gift = _gift()
    with pytest.raises(services.VoucherError) as exc:
        services.redeem_balance(gift.code, 6000)
    assert exc.value.reason == "insufficient"
    gift.refresh_from_db()
    assert gift.balance_cents == 5000


def test_redeem_balance_double_tap_spends_once():
    gift = _gift()
    services.redeem_balance(gift.code, 1000, expect_used=0)
    with pytest.raises(services.VoucherError) as exc:
        services.redeem_balance(gift.code, 1000, expect_used=0)
    assert exc.value.reason == "stale"
    gift.refresh_from_db()
    assert gift.balance_cents == 4000


def test_redeem_balance_rejects_zero_and_non_balance():
    gift = _gift()
    with pytest.raises(services.VoucherError) as exc:
        services.redeem_balance(gift.code, 0)
    assert exc.value.reason == "invalid_amount"
    plain = Voucher.objects.create(code="V-PLAIN1", label="Rabatt", max_uses=1)
    with pytest.raises(services.VoucherError) as exc:
        services.redeem_balance(plain.code, 100)
    assert exc.value.reason == "not_found"


def test_counter_view_spends_amount_from_balance():
    gift = _gift()
    req = _cab({"code": gift.code, "amount": "12,50", "expect": "0"})
    views.voucher_redeem(req)
    gift.refresh_from_db()
    assert gift.balance_cents == 3750
    assert any("37.50" in str(m) for m in get_messages(req))


def test_counter_view_without_amount_goes_back_to_card():
    gift = _gift()
    resp = views.voucher_redeem(_cab({"code": gift.code}))
    assert resp.status_code == 302 and f"code={gift.code}" in resp.url
    gift.refresh_from_db()
    assert gift.balance_cents == 5000


def test_counter_card_shows_amount_field_and_rest():
    gift = _gift()
    resp = views.voucher_redeem(_cab(method="get", query=f"?code={gift.code}"))
    body = resp.content.decode()
    assert 'name="amount"' in body and "Restguthaben" in body


def test_scan_never_redeems_balance_voucher():
    gift = _gift()
    views._redeem_voucher_scan(_cab(), gift.code)
    gift.refresh_from_db()
    assert (gift.used_count, gift.balance_cents) == (0, 5000)


def test_plain_voucher_still_redeems_without_amount():
    plain = Voucher.objects.create(code="V-PLAIN2", label="Rabatt", max_uses=1)
    views.voucher_redeem(_cab({"code": plain.code}))
    plain.refresh_from_db()
    assert plain.used_count == 1


# --- L2: чужой купон по контакту -------------------------------------------------------


def _public(path, tenant, data, ip):
    request = RequestFactory().post(path, data)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    request.META["REMOTE_ADDR"] = ip
    return request


def _tenant(slug):
    return TenantFactory(
        schema_name=slug.replace("-", "_"), slug=slug, name=slug, disabled_modules=["orders"]
    )


def test_other_browser_with_known_email_gets_no_code():
    tenant = _tenant("h9-mail")
    promo = _promo()
    path = f"/p/{promo.pk}/coupon/"
    first = public_views.coupon_create(
        _public(path, tenant, {"email": "a@example.de"}, "10.9.0.1"), pk=promo.pk
    )
    coupon = Voucher.objects.get(promotion=promo)
    assert first.url == f"/coupon/{coupon.code}/"
    with mock.patch("apps.notifications.services.notify") as notify:
        req = _public(path, tenant, {"email": "A@example.de"}, "10.9.0.2")
        resp = public_views.coupon_create(req, pk=promo.pk)
    assert resp.url == f"/p/{promo.pk}/"
    assert coupon.code not in resp.url
    assert all(coupon.code not in str(m) for m in get_messages(req))
    assert public_views.COUPON_COOKIE not in resp.cookies
    assert Voucher.objects.filter(promotion=promo).count() == 1
    notify.assert_called_once()
    assert notify.call_args.kwargs["recipient"] == "a@example.de"


def test_phone_only_match_sends_nothing():
    tenant = _tenant("h9-phone")
    promo = _promo()
    path = f"/p/{promo.pk}/coupon/"
    public_views.coupon_create(_public(path, tenant, {"phone": "0171 1"}, "10.9.1.1"), pk=promo.pk)
    coupon = Voucher.objects.get(promotion=promo)
    with mock.patch("apps.notifications.services.notify") as notify:
        resp = public_views.coupon_create(
            _public(path, tenant, {"phone": "0171 1"}, "10.9.1.2"), pk=promo.pk
        )
    assert resp.url == f"/p/{promo.pk}/" and coupon.code not in resp.url
    notify.assert_not_called()


def test_service_default_still_reveals_for_proven_owner():
    """MCP-путь (владение почтой доказано кликом) — прежнее поведение."""
    promo = _promo()
    first, _ = services.issue_coupon(promo, email="b@example.de")
    again, created = services.issue_coupon(promo, email="b@example.de")
    assert again.pk == first.pk and created is False


# --- L3: купон закончившейся акции -------------------------------------------------------


def _coupon(promo):
    voucher, _ = services.issue_coupon(promo, email=f"{uuid.uuid4().hex[:6]}@example.de")
    return voucher


def test_coupon_of_paused_promo_not_redeemable():
    promo = _promo()
    coupon = _coupon(promo)
    Promotion.objects.filter(pk=promo.pk).update(status="paused")
    with pytest.raises(services.VoucherError) as exc:
        services.redeem_voucher(coupon.code)
    assert exc.value.reason == "promotion_ended"
    coupon.refresh_from_db()
    assert coupon.used_count == 0


def test_coupon_of_promo_past_end_not_redeemable_despite_snapshot():
    promo = _promo()
    coupon = _coupon(promo)
    Voucher.objects.filter(pk=coupon.pk).update(expires_at=timezone.now() + timedelta(days=9))
    Promotion.objects.filter(pk=promo.pk).update(ends_at=timezone.now() - timedelta(hours=1))
    with pytest.raises(services.VoucherError) as exc:
        services.redeem_voucher(coupon.code)
    assert exc.value.reason == "promotion_ended"


def test_coupon_redeemable_when_promo_sold_out():
    promo = _promo(available_quantity=1)
    coupon = _coupon(promo)
    promo.refresh_from_db()
    assert promo.available_quantity == 0
    assert services.redeem_voucher(coupon.code).used_count == 1


def test_coupon_page_of_ended_promo_shows_expired():
    promo = _promo()
    coupon = _coupon(promo)
    Promotion.objects.filter(pk=promo.pk).update(status="ended")
    request = RequestFactory().get(f"/coupon/{coupon.code}/")
    request.META["REMOTE_ADDR"] = "10.9.2.1"
    with mock.patch.object(public_views, "render") as render:
        public_views.coupon_page(request, coupon.code)
    assert render.call_args.args[2]["state"] == "expired"


# --- L4: «Geschäft» только владельцу -----------------------------------------------------


def test_lite_business_is_owner_only_prefix():
    from apps.core.middleware import CabinetOwnerAccessMiddleware

    assert "/dashboard/geschaeft/" in CabinetOwnerAccessMiddleware._OWNER_ONLY


def test_lite_nav_hides_business_for_staff(monkeypatch):
    from apps.core import lite_cabinet, roles

    staff = get_user_model().objects.create_user(
        username=f"s-{uuid.uuid4().hex[:6]}", password="pw12345678"
    )
    monkeypatch.setattr(roles, "is_owner", lambda user: False)
    names = [i["url_name"] for i in lite_cabinet.sidebar_items(None, staff)]
    assert "lite-business" not in names
    assert "lite-business" in [i["url_name"] for i in lite_cabinet.sidebar_items(None)]
