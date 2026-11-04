"""W4-3: единый экран «Zahlung & Versand» — свод оплаты/доставки.

Ключевые инварианты: (1) секции гейтятся по модулю (orders) / Stripe-Connect;
(2) save-хелперы те же, что у старых экранов (нормализация IBAN, eur→cents, зоны);
(3) секция сохраняется ТОЛЬКО при своём сентинеле — POST без него НЕ затирает поля.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(method, user, tenant, data=None):
    request = getattr(RequestFactory(), method)("/dashboard/settings/payments/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def _user(n):
    # KA-H2: банковские реквизиты меняет только владелец — экран открывает владелец.
    from apps.core.models import Membership

    user = get_user_model().objects.create_user(n, f"{n}@test.de", "pw12345678")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return user


def test_renders_orders_sections(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(disabled_modules=[])  # orders активен
    html = core_views.payment_settings(_req("get", _user("ps1"), tenant)).content.decode()
    for name in ("vorkasse_enabled", "bank_iban", "orders_prepay"):
        assert f'name="{name}"' in html
    assert 'name="sec_vorkasse"' in html
    # UX-D D9: доставка — на своей вкладке
    html = core_views.payment_settings(
        _req("get", _user("ps1b"), tenant, {"tab": "lieferung"})
    ).content.decode()
    assert 'name="delivery_enabled"' in html and 'name="sec_delivery"' in html


def test_saves_all_orders_sections(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(disabled_modules=[], vorkasse_enabled=False)
    data = {
        "sec_prepay": "1",
        "sec_vorkasse": "1",
        "sec_delivery": "1",
        "orders_prepay": "on",
        "vorkasse_enabled": "on",
        "bank_holder": "Max Mustermann",
        "bank_iban": "de89 3704 0044 0532 0130 00",  # нормализуется upper/без пробелов
        "delivery_enabled": "on",
        "delivery_fee_eur": "3,90",
        "zone_plz_0": "40",
        "zone_fee_0": "4,90",
    }
    resp = core_views.payment_settings(_req("post", _user("ps2"), tenant, data))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.orders_prepay is True
    assert tenant.vorkasse_enabled is True
    assert tenant.bank_iban == "DE89370400440532013000"  # save_vorkasse нормализовал
    assert tenant.delivery_enabled is True
    assert tenant.delivery_fee_cents == 390  # save_delivery eur→cents
    assert tenant.delivery_zones and tenant.delivery_zones[0]["plz"] == "40"


def test_missing_sentinel_does_not_wipe_section(settings):
    """Guard потери данных: POST без sec_delivery НЕ трогает delivery-поля (даже в
    единой форме) — секция сохраняется только по своему сентинелу."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(disabled_modules=[], delivery_enabled=True, delivery_fee_cents=500)
    # POST только vorkasse-секции (sec_delivery ОТСУТСТВУЕТ).
    data = {"sec_vorkasse": "1", "vorkasse_enabled": "on", "bank_iban": "DE89370400440532013000"}
    core_views.payment_settings(_req("post", _user("ps3"), tenant, data))
    tenant.refresh_from_db()
    assert tenant.delivery_enabled is True  # НЕ затёрто
    assert tenant.delivery_fee_cents == 500  # НЕ затёрто
    assert tenant.vorkasse_enabled is True  # vorkasse сохранён


def test_stripe_section_gated_on_connect(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.billing import connect

    tenant = TenantFactory(disabled_modules=[])
    monkeypatch.setattr(connect, "is_connect_configured", lambda: False)
    html = core_views.payment_settings(_req("get", _user("ps4"), tenant)).content.decode()
    assert 'name="sec_stripe"' not in html

    monkeypatch.setattr(connect, "is_connect_configured", lambda: True)
    html2 = core_views.payment_settings(_req("get", _user("ps5"), tenant)).content.decode()
    assert 'name="sec_stripe"' in html2 and 'name="methods"' in html2


def test_orders_sections_hidden_when_orders_off(settings):
    """SH-24: блок доставки живёт при ЛЮБОМ из двух модулей — заказы или заявки
    (кейтеринг продаёт через /anfrage/, и вопрос «привезём или заберёте» — его).
    Без обоих — прежнее поведение: блока нет."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(disabled_modules=["orders", "jobs"])
    html = core_views.payment_settings(_req("get", _user("ps6"), tenant)).content.decode()
    assert 'name="sec_delivery"' not in html
    assert 'name="delivery_enabled"' not in html

    jobs_only = TenantFactory(schema_name="ps6b", slug="ps6b", disabled_modules=["orders"])
    html2 = core_views.payment_settings(
        _req("get", _user("ps6b"), jobs_only, {"tab": "lieferung"})
    ).content.decode()
    assert 'name="sec_delivery"' in html2 and 'name="delivery_enabled"' in html2
    html3 = core_views.payment_settings(_req("get", _user("ps6c"), jobs_only)).content.decode()
    assert 'name="sec_prepay"' not in html3  # блок «Abholung & Vorkasse» остаётся за orders


# --- UX-D D9: вкладки «Zahlung» и «Lieferung & Abholung» ---------------------------


def test_tabs_split_payment_and_delivery(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="ps9a", slug="ps9a", disabled_modules=[])
    pay = core_views.payment_settings(_req("get", _user("ps9a"), tenant)).content.decode()
    assert "data-pay-tabs" in pay and 'aria-current="page">Zahlung' in pay
    assert 'name="vorkasse_enabled"' in pay and 'name="invoice_b2b_enabled"' in pay
    assert 'name="delivery_enabled"' not in pay and 'name="pickup_slots_on"' not in pay
    deliv = core_views.payment_settings(
        _req("get", _user("ps9b"), tenant, {"tab": "lieferung"})
    ).content.decode()
    assert "data-pay-delivery" in deliv and "data-pay-pickup" in deliv
    assert 'name="pickup_slots_on"' in deliv and 'name="pickup_locations"' in deliv
    assert 'name="vorkasse_enabled"' not in deliv and 'name="sec_invoice"' not in deliv
    assert 'name="tab" value="lieferung"' in deliv


def test_saving_one_tab_keeps_the_other(settings):
    """Сентинелы sec_*: «Speichern» вкладки Zahlung не трогает доставку и наоборот."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        schema_name="ps9c",
        slug="ps9c",
        disabled_modules=[],
        delivery_enabled=True,
        delivery_fee_cents=390,
    )
    resp = core_views.payment_settings(
        _req("post", _user("ps9c"), tenant, {"tab": "zahlung", "sec_invoice": "1"})
    )
    assert resp.status_code == 302 and resp.url == "/dashboard/settings/payments/"
    tenant.refresh_from_db()
    assert tenant.delivery_enabled is True and tenant.delivery_fee_cents == 390
    resp = core_views.payment_settings(
        _req(
            "post",
            _user("ps9d"),
            tenant,
            {"tab": "lieferung", "sec_delivery": "1", "delivery_fee_eur": "4,50"},
        )
    )
    assert resp.url == "/dashboard/settings/payments/?tab=lieferung"
    tenant.refresh_from_db()
    assert tenant.delivery_fee_cents == 450


def test_no_tabs_without_delivery_and_bad_tab_falls_back(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="ps9e", slug="ps9e", disabled_modules=["orders", "jobs"])
    html = core_views.payment_settings(
        _req("get", _user("ps9e"), tenant, {"tab": "lieferung"})
    ).content.decode()
    assert "data-pay-tabs" not in html  # одна вкладка — полосы нет
    assert 'name="sec_invoice"' in html  # открылась Zahlung, а не пустая страница
    assert 'type="submit"' in html  # счёт фирме можно сохранить и без заказов
