"""SH-23a (фидбэк владельца 2026-09-03): «для каждого типа заказа всех архетипов
по желанию нужна оплата онлайн, при получении или на месте или выставить счёт
как юрлицо; видимо нужен выбор — юрлицо покупает или физлицо».

Слайс a: общий реестр способов (`apps.core.payment_methods`), счёт юрлицу у
заказа, тип покупателя на чекауте, настройки бизнеса (срок оплаты, удержание).
Решения владельца: Р-1 счёт автоматически, Р-2 срок 14 дней, Р-3 счёт только
фирмам, Р-4 удержание — до срока счёта / 3 дня для Vorkasse.

План — `docs/order-feedback-plan-2026-09-03.md` §6.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import payment_methods as pm
from apps.orders import payments as order_payments
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    kw.setdefault("disabled_modules", [])
    return TenantFactory(**kw)


# ─────────────────────────── реестр ───────────────────────────


def test_on_site_is_always_available_and_last():
    methods = pm.available(_tenant(), "order")
    assert methods[-1] == pm.ON_SITE


def test_vorkasse_needs_the_iban():
    tenant = _tenant(vorkasse_enabled=True, bank_iban="")
    assert pm.VORKASSE not in pm.available(tenant, "order")
    tenant.bank_iban = "DE89370400440532013000"
    assert pm.VORKASSE in pm.available(tenant, "order")


def test_invoice_is_offered_to_companies_only():
    """Р-3: частному лицу счёт не предлагается никогда."""
    tenant = _tenant(invoice_b2b_enabled=True)
    assert pm.INVOICE not in pm.available(tenant, "order", customer_type=pm.PRIVATE)
    assert pm.INVOICE in pm.available(tenant, "order", customer_type=pm.COMPANY)
    off = _tenant(schema_name="sh23b", slug="sh23b", invoice_b2b_enabled=False)
    assert pm.INVOICE not in pm.available(off, "order", customer_type=pm.COMPANY)


def test_normalize_falls_back_to_the_first_available():
    tenant = _tenant(invoice_b2b_enabled=True)
    # подмена формы: частное лицо выбирает счёт → откат к доступному способу
    assert pm.normalize(pm.INVOICE, tenant, "order", customer_type=pm.PRIVATE) == pm.ON_SITE
    assert pm.normalize("erfunden", tenant, "order") == pm.ON_SITE
    assert pm.normalize(pm.INVOICE, tenant, "order", customer_type=pm.COMPANY) == pm.INVOICE


def test_customer_type_is_fail_closed():
    assert pm.customer_type_of("company") == pm.COMPANY
    assert pm.customer_type_of("Firma") == pm.PRIVATE
    assert pm.customer_type_of(None) == pm.PRIVATE


def test_hold_days_follow_the_owner_decisions():
    """Р-4: счёт — до срока счёта, Vorkasse — 3 дня, прочее — без удержания."""
    tenant = _tenant(invoice_terms_days=21, vorkasse_hold_days=5)
    assert pm.hold_days(tenant, pm.INVOICE) == 21
    assert pm.hold_days(tenant, pm.VORKASSE) == 5
    assert pm.hold_days(tenant, pm.ON_SITE) == 0
    assert pm.hold_days(tenant, pm.STRIPE) == 0
    default = _tenant(schema_name="sh23c", slug="sh23c")
    assert pm.hold_days(default, pm.INVOICE) == 14 and pm.hold_days(default, pm.VORKASSE) == 3


def test_orders_helper_delegates_to_the_registry():
    """Прежний вызов чекаута не изменился по смыслу (E7-2 паритет)."""
    tenant = _tenant(vorkasse_enabled=True, bank_iban="DE89370400440532013000")
    assert order_payments.available_methods(tenant) == [pm.VORKASSE, pm.ON_SITE]


# ─────────────────────────── чекаут заказа ───────────────────────────


def _req(method="get", data=None, tenant=None, path="/warenkorb/"):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    request.user = get_user_model()(is_active=True)
    return request


def test_checkout_stores_the_buyer_type_and_company():
    from decimal import Decimal

    from apps.catalog.models import Product
    from apps.orders import public_views
    from apps.orders.models import Order

    tenant = _tenant(schema_name="sh23d", slug="sh23d", invoice_b2b_enabled=True)
    product = Product.objects.create(
        name={"de": "Saft"}, base_price=Decimal("2.49"), stock_quantity=10
    )
    request = _req(
        "post",
        {
            "name": "Firma Muster",
            "email": "buchhaltung@muster.de",
            "customer_type": "company",
            "billing_company": "Muster GmbH",
            "billing_vat_id": "DE123456789",
            "payment": "invoice",
        },
        tenant,
        path="/warenkorb/checkout/",
    )
    request.session["cart"] = {str(product.pk): 2}
    public_views.checkout(request)
    order = Order.objects.get()
    assert order.customer_type == "company"
    assert order.billing_company == "Muster GmbH" and order.billing_vat_id == "DE123456789"
    assert order.payment_method == Order.METHOD_INVOICE
    assert order.payment_due_at is not None  # Р-2/Р-4: срок оплаты проставлен


def test_private_buyer_cannot_pick_the_invoice():
    from decimal import Decimal

    from apps.catalog.models import Product
    from apps.orders import public_views
    from apps.orders.models import Order

    tenant = _tenant(schema_name="sh23e", slug="sh23e", invoice_b2b_enabled=True)
    product = Product.objects.create(
        name={"de": "Saft"}, base_price=Decimal("2.49"), stock_quantity=10
    )
    request = _req(
        "post",
        {"name": "Privat", "customer_type": "private", "payment": "invoice"},
        tenant,
        path="/warenkorb/checkout/",
    )
    request.session["cart"] = {str(product.pk): 1}
    public_views.checkout(request)
    order = Order.objects.get()
    assert order.payment_method == Order.METHOD_ON_SITE  # счёт недоступен
    assert order.payment_due_at is None


# ─────────────────────────── настройки бизнеса ───────────────────────────


def test_settings_section_saves_and_is_sentinel_guarded():
    from apps.core import views as core_views

    tenant = _tenant(schema_name="sh23f", slug="sh23f")
    user = get_user_model().objects.create_user("sh23f", "sh23f@test.de", "pw12345678")

    def _post(data):
        request = RequestFactory().post("/dashboard/settings/payments/", data)
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.user = user
        request.tenant = tenant
        return request

    core_views.payment_settings(
        _post(
            {
                "sec_invoice": "1",
                "invoice_b2b_enabled": "on",
                "invoice_terms_days": "30",
                "vorkasse_hold_days": "7",
            }
        )
    )
    tenant.refresh_from_db()
    assert tenant.invoice_b2b_enabled and tenant.invoice_terms_days == 30
    assert tenant.vorkasse_hold_days == 7

    # POST без сентинеля секцию НЕ трогает (guard потери, механика W4-3).
    core_views.payment_settings(_post({"sec_vorkasse": "1"}))
    tenant.refresh_from_db()
    assert tenant.invoice_b2b_enabled and tenant.invoice_terms_days == 30
