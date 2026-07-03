"""B1.1 — витрина Geschenkgutscheine для всех архетипов: гейт (модуль gift +
онлайн-оплата), покупка любым business_type, паритет отельной ссылки."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.loyalty import public_views
from apps.loyalty.models import GiftVoucher
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def _connect_ok(monkeypatch):
    monkeypatch.setattr("apps.billing.connect.is_connect_configured", lambda: True)
    monkeypatch.setattr(
        "apps.billing.connect.connected_checkout_session",
        lambda **kw: "https://stripe.test/session",
    )


def _req(method="get", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/gutschein/", data or {})
    request.META["REMOTE_ADDR"] = f"10.77.{hash(str(data)) % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build(
        payments_enabled=True, business_type="other", stripe_connect_id="acct_1"
    )
    return request


def test_gift_page_open_for_any_archetype(_connect_ok):
    """Не-stays бизнес (friseur/other) видит страницу покупки — гейт больше не stays."""
    body = public_views.gutschein_index(_req()).content.decode()
    assert "50" in body  # пресеты номиналов


def test_gift_gates_module_payments_connect(monkeypatch, _connect_ok):
    # выключен модуль gift → 404
    off = TenantFactory.build(payments_enabled=True, disabled_modules=["gift"])
    with pytest.raises(Http404):
        public_views.gutschein_index(_req(tenant=off))
    # нет онлайн-оплаты → 404
    no_pay = TenantFactory.build(payments_enabled=False)
    with pytest.raises(Http404):
        public_views.gutschein_index(_req(tenant=no_pay))
    # нет Connect-конфига → 404
    monkeypatch.setattr("apps.billing.connect.is_connect_configured", lambda: False)
    with pytest.raises(Http404):
        public_views.gutschein_index(_req())


def test_gift_buy_creates_record_and_redirects_to_stripe(_connect_ok):
    resp = public_views.gutschein_buy(
        _req(
            "post",
            {"name": "Kim", "email": "kim@test.de", "amount_eur": "75", "recipient": "Ana"},
        )
    )
    assert resp.status_code == 302 and resp.url == "https://stripe.test/session"
    gv = GiftVoucher.objects.get()
    assert gv.amount_cents == 7500 and gv.payment_state == "pending"


def test_stay_index_gift_flag_uses_unified_gate(_connect_ok):
    """Паритет отельной витрины: ссылка «в подарок» живёт при активном gift."""
    from apps.loyalty.public_views import gift_purchase_active

    on = TenantFactory.build(payments_enabled=True)
    assert gift_purchase_active(on) is True
    assert (
        gift_purchase_active(TenantFactory.build(payments_enabled=True, disabled_modules=["gift"]))
        is False
    )
