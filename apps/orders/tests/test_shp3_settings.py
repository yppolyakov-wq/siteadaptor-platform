"""SHP-3: экран способов доставки и единственный писатель `orders.shipping_admin`.

Замки: первое действие переносит прежние настройки в строки без потерь (зоны, пункты,
сборы); последний включённый способ при открытых заказах выключить нельзя; суммы —
строгий разбор (мусор — ошибка, не 0 €), потолки; порядок двигается; зеркало
`Tenant.delivery_enabled` следует за списком; вкладка показывает список ВНЕ большой формы,
а прежние поля доставки исчезают (иначе два писателя)."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.orders import shipping, shipping_admin, shipping_views
from apps.orders.models import ShippingMethod
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    kw.setdefault("schema_name", f"shp3_{uuid.uuid4().hex[:6]}")
    kw.setdefault("slug", kw["schema_name"])
    return TenantFactory(**kw)


def _req(method="get", data=None, tenant=None, path="/dashboard/settings/versand/neu/"):
    rf = RequestFactory()
    request = getattr(rf, method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    user = get_user_model().objects.create_user(
        username=f"o{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@t.de",
        password="pw12345678",
    )
    Membership.objects.get_or_create(user=user, defaults={"role": Membership.ROLE_OWNER})
    request.user = user
    request.tenant = tenant or _tenant()
    return request


ZONES = [{"plz": "40", "fee_cents": 200, "free_cents": 3000, "min_cents": 0}]


def test_first_change_moves_legacy_settings_into_rows_without_loss():
    tenant = _tenant(
        delivery_enabled=True,
        delivery_fee_cents=390,
        delivery_free_cents=5000,
        delivery_zones=ZONES,
        delivery_restrict_to_zones=True,
        pickup_locations=[{"name": "Markt", "address": "Platz 1"}],
        pickup_min_cents=500,
    )
    before = [shipping.quote(m, 1000, "40210") for m in shipping.methods(tenant)]
    shipping_admin.create(tenant, "carrier", {"carrier": "dhl", "fee_cents": 499})
    shipping.forget(tenant)
    rows = shipping.methods(tenant)
    assert [m.kind for m in rows] == ["pickup", "courier", "carrier"]
    assert rows[0].locations == [{"name": "Markt", "address": "Platz 1"}]
    assert [shipping.quote(m, 1000, "40210") for m in rows[:2]] == before  # те же цены


def test_last_active_method_cannot_be_switched_off():
    tenant = _tenant()
    shipping_admin.materialize(tenant)
    pickup = ShippingMethod.objects.get()
    with pytest.raises(shipping_admin.LastMethod):
        shipping_admin.set_active(tenant, pickup, False)
    shipping_admin.create(tenant, "courier", {"fee_cents": 300})
    shipping_admin.set_active(tenant, pickup, False)  # теперь можно: курьер остаётся
    pickup.refresh_from_db()
    assert not pickup.active


def test_mirror_follows_the_list():
    tenant = _tenant(delivery_enabled=False)
    courier = shipping_admin.create(tenant, "courier", {"fee_cents": 300})
    tenant.refresh_from_db()
    assert tenant.delivery_enabled
    shipping_admin.set_active(tenant, courier, False)
    tenant.refresh_from_db()
    assert not tenant.delivery_enabled


def test_parse_is_strict_and_capped():
    post = {
        "fee": "abc",
        "free_from": "1.234,50",
        "carrier": "nope",
        "service": "pickup_point",
        "pricing": "weight",
        "weight_tiers": "2 | 4,99\n5 | 6,99\nkaputt",
        "max_weight_kg": "31,5",
    }
    parsed = shipping_admin.parse(post, "carrier")
    assert parsed.errors  # мусорная цена, неизвестный перевозчик, кривая ступень
    assert parsed.values["free_from_cents"] == 0  # 1234,50 € > потолка 1000 € — не пишется
    assert parsed.values["weight_tiers"] == [
        {"max_g": 2000, "fee_cents": 499},
        {"max_g": 5000, "fee_cents": 699},
    ]
    assert parsed.values["max_weight_g"] == 31500
    ok = shipping_admin.parse(
        {"carrier": "hermes", "service": "pickup_point", "fee": "3,99"}, "carrier"
    )
    assert not ok.errors and ok.values["fee_cents"] == 399
    zones = shipping_admin.parse({"zones": "42651, 42653 | 2,50 | 30 |\n40 | 4,90"}, "courier")
    assert zones.values["zones"][0] == {"plz": "42651, 42653", "fee_cents": 250, "free_cents": 3000}


def test_move_changes_cart_order():
    tenant = _tenant()
    shipping_admin.materialize(tenant)
    carrier = shipping_admin.create(tenant, "carrier", {"carrier": "dhl"})
    shipping_admin.move(tenant, carrier, -1)
    assert [m.kind for m in shipping.methods(tenant)] == ["carrier", "pickup"]


def test_new_method_form_and_post_create_rows():
    request = _req("get", {"art": "carrier"})
    html = shipping_views.shipping_method_new(request).content.decode()
    assert 'name="carrier"' in html and 'value="4,99"' in html
    post = _req(
        "post", {"kind": "carrier", "carrier": "dpd", "fee": "5,49", "delivery_time": "1–3 Tage"}
    )
    response = shipping_views.shipping_method_new(post)
    assert response.status_code == 302
    dpd = ShippingMethod.objects.get(carrier="dpd")
    assert (dpd.fee_cents, dpd.delivery_time) == (549, "1–3 Tage")


def test_delivery_tab_shows_list_outside_the_form_and_no_legacy_fields():
    from apps.core.views import payment_settings

    tenant = _tenant()
    tenant.disabled_modules = []
    request = _req("get", {"tab": "lieferung"}, tenant=tenant, path="/dashboard/settings/payments/")
    html = payment_settings(request).content.decode()
    assert "data-shipping-methods" in html
    form_start = html.index("data-payment-grid")
    assert html.index("data-shipping-methods") < form_start  # список — до большой формы
    assert 'name="delivery_enabled"' not in html  # прежнего писателя на вкладке нет
