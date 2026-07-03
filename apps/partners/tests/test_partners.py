"""D3: партнёрка — атрибуция реф-кода, кабинет, шов скидки в Checkout."""

import uuid

import pytest
import stripe
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.billing import services as billing_services
from apps.partners.models import Partner
from apps.partners.views import dashboard
from apps.tenants.services import _new_tenant
from apps.tenants.tests.factories import TenantFactory
from apps.tenants.views import BusinessSignupView

pytestmark = pytest.mark.django_db


def _user(**kw):
    uname = f"p-{uuid.uuid4().hex[:8]}"
    return get_user_model().objects.create_user(
        username=uname, email=f"{uname}@t.de", password="pw12345678", **kw
    )


def _partner(**kw):
    kw.setdefault("user", _user())
    kw.setdefault("name", "Studio X")
    kw.setdefault("code", f"studio-{uuid.uuid4().hex[:6]}")
    return Partner.objects.create(**kw)


def _req(method="get", path="/partner/", data=None, user=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user or _user()
    return request


# --- атрибуция --------------------------------------------------------------


def test_signup_get_captures_ref_into_session():
    partner = _partner()
    request = _req(path=f"/?ref={partner.code}")
    request.GET = {"ref": partner.code}
    BusinessSignupView().get(request)
    assert request.session["partner_ref"] == partner.code


def test_new_tenant_attributes_partner():
    # _new_tenant — общая точка обоих создателей (sync + async), без схемы.
    partner = _partner()
    tenant = _new_tenant(
        business_name="Bäckerei",
        slug=f"b-{uuid.uuid4().hex[:6]}",
        business_type="bakery",
        city="Hilden",
        email="o@test.de",
        partner_code=partner.code,
    )
    assert tenant.partner_id == partner.pk


def test_unknown_or_inactive_code_is_silently_ignored():
    inactive = _partner(is_active=False)
    for code in ("nope-unknown", inactive.code, ""):
        tenant = _new_tenant(
            business_name="Cafe",
            slug=f"c-{uuid.uuid4().hex[:6]}",
            business_type="cafe",
            city="Hilden",
            email="o@test.de",
            partner_code=code,
        )
        assert tenant.partner_id is None


# --- кабинет ----------------------------------------------------------------


def test_dashboard_lists_only_own_tenants():
    partner = _partner()
    mine = TenantFactory(partner=partner, name="Meine Bäckerei")
    TenantFactory(name="Fremdes Cafe")  # чужой — не виден
    body = dashboard(_req(user=partner.user)).content.decode()
    assert mine.name in body and "Fremdes Cafe" not in body
    assert f"?ref={partner.code}" in body


def test_dashboard_without_profile_is_403():
    resp = dashboard(_req())
    assert resp.status_code == 403


def test_dashboard_revshare_summary():
    partner = _partner(reward_kind=Partner.REWARD_REVSHARE, revshare_percent=20)
    TenantFactory(partner=partner, subscription_status="active")
    TenantFactory(partner=partner, subscription_status="active")
    TenantFactory(partner=partner, subscription_status="trial")  # не считается
    body = dashboard(_req(user=partner.user)).content.decode()
    # 2 актива × 39 € × 20 % = 15.60 €/мес
    assert "15,60" in body or "15.60" in body


# --- шов скидки в подписочном Checkout ---------------------------------------


def _capture_checkout(monkeypatch):
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return {"url": "https://checkout/sub"}

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    return captured


def test_checkout_carries_partner_coupon(monkeypatch):
    captured = _capture_checkout(monkeypatch)
    partner = _partner(reward_kind=Partner.REWARD_CLIENT_DISCOUNT, stripe_coupon_id="coup_10off")
    tenant = TenantFactory(partner=partner, stripe_customer_id="cus_1")
    billing_services.create_checkout_session(
        tenant, success_url="https://s", cancel_url="https://c"
    )
    assert captured["discounts"] == [{"coupon": "coup_10off"}]


def test_checkout_unchanged_without_partner_or_coupon(monkeypatch):
    captured = _capture_checkout(monkeypatch)
    tenant = TenantFactory(stripe_customer_id="cus_1")
    billing_services.create_checkout_session(
        tenant, success_url="https://s", cancel_url="https://c"
    )
    assert "discounts" not in captured  # паритет: без партнёра запрос прежний

    # партнёр с ревшарой (не скидкой) тоже не трогает Checkout
    captured.clear()
    partner = _partner(reward_kind=Partner.REWARD_REVSHARE, revshare_percent=10)
    tenant2 = TenantFactory(partner=partner, stripe_customer_id="cus_2")
    billing_services.create_checkout_session(
        tenant2, success_url="https://s", cancel_url="https://c"
    )
    assert "discounts" not in captured


def test_signup_post_pops_ref_and_passes_code(monkeypatch, settings):
    # pop: код одноразовый на браузер-сессию (ревью D3) — и уходит в сервис.
    settings.ROOT_URLCONF = "config.urls_public"
    from apps.tenants import views as tenant_views

    partner = _partner()
    captured = {}

    def _fake(**kw):
        captured.update(kw)

        class _T:
            slug = "fake"

        return _T()

    monkeypatch.setattr(tenant_views, "start_business_provisioning", _fake)
    request = _req(
        "post",
        path="/",
        data={
            "business_name": "Bäckerei",
            "slug": f"b{uuid.uuid4().hex[:8]}",
            "business_type": "bakery",
            "city": "Hilden",
            "email": "o@test.de",
            "password1": "pw12345678",
            "password2": "pw12345678",
        },
    )
    request.session["partner_ref"] = partner.code
    tenant_views.BusinessSignupView().post(request)
    assert captured["partner_code"] == partner.code
    assert "partner_ref" not in request.session


def test_checkout_falls_back_when_coupon_invalid(monkeypatch):
    # Ревью D3: протухший coupon-id не роняет оплату — ретрай без скидки.
    calls = []

    def _create(**kw):
        calls.append(kw)
        if "discounts" in kw:
            raise stripe.error.InvalidRequestError("No such coupon", param="discounts")
        return {"url": "https://checkout/sub"}

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    partner = _partner(reward_kind=Partner.REWARD_CLIENT_DISCOUNT, stripe_coupon_id="coup_dead")
    tenant = TenantFactory(partner=partner, stripe_customer_id="cus_1")
    url = billing_services.create_checkout_session(
        tenant, success_url="https://s", cancel_url="https://c"
    )
    assert url == "https://checkout/sub"
    assert len(calls) == 2 and "discounts" not in calls[1]
