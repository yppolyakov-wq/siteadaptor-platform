"""P6 «ценовой слой»: промо-цена/бейдж активной акции на витрине ЦЕЛЕЙ (2026-08-04).

Принцип: витрина показывает РОВНО то, что спишет чекаут (те же матчеры
price_layer), «показали дороже, списали дешевле» и наоборот — запрещено.
"""

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import price_layer
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/", tenant=None):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else TenantFactory.build(disabled_modules=[])
    return request


def _product(stock=30, price="10.00"):
    from apps.catalog.tests.factories import ProductFactory

    return ProductFactory(base_price=Decimal(price), stock_quantity=stock)


def _promo(product=None, price=None, quantity=5, **fields):
    promo = PromotionFactory(product=product, available_quantity=quantity, price_override=price)
    Promotion.objects.filter(pk=promo.pk).update(status="active", **fields)
    promo.refresh_from_db()
    return promo


# --- товар -------------------------------------------------------------------


def test_promo_for_product_picks_best_and_ignores_inactive():
    product = _product(price="10.00")
    _promo(product=product, price=Decimal("8.00"))
    best = _promo(product=product, price=Decimal("6.00"))
    cheaper_paused = _promo(product=product, price=Decimal("1.00"))
    Promotion.objects.filter(pk=cheaper_paused.pk).update(status="paused")
    found = price_layer.promo_for_product(product)
    assert found is not None and found.pk == best.pk


def test_product_promo_map_bulk_only_discounted():
    p1, p2 = _product(price="10.00"), _product(price="10.00")
    promo = _promo(product=p1, price=Decimal("5.00"))
    _promo(product=p2, price=Decimal("12.00"))  # «дороже базы» — не скидка
    found = price_layer.product_promo_map([p1.pk, p2.pk])
    assert found[p1.pk].pk == promo.pk
    assert p2.pk not in found


def test_product_detail_renders_promo_banner_linking_to_promotion():
    from apps.promotions import public_views

    product = _product(price="10.00")
    promo = _promo(product=product, price=Decimal("7.00"))
    body = public_views.product_detail(
        _req(f"/produkt/{product.pk}/"), pk=product.pk
    ).content.decode()
    assert f"/p/{promo.pk}/" in body  # чекаут по промо-цене живёт на акции
    assert "Zum Angebot" in body


def test_product_detail_without_promo_has_no_banner():
    from apps.promotions import public_views

    product = _product(price="10.00")
    body = public_views.product_detail(
        _req(f"/produkt/{product.pk}/"), pk=product.pk
    ).content.decode()
    assert "Zum Angebot" not in body


def test_product_list_marks_card_with_promo_badge():
    from apps.promotions import public_views

    product = _product(price="10.00")
    _promo(product=product, discount_percent=20)
    body = public_views.product_list(_req("/sortiment/")).content.decode()
    assert "−20 %" in body


# --- услуга (сетка слотов) ---------------------------------------------------


def _slots_setup():
    from apps.booking.models import AvailabilityRule, Resource, Service

    day = timezone.localdate() + timedelta(days=7)
    resource = Resource.objects.create(name="Stuhl P6")
    AvailabilityRule.objects.create(
        resource=resource,
        weekday=day.weekday(),
        start_time=time(10, 0),
        end_time=time(13, 0),
        slot_minutes=60,
    )
    service = Service.objects.create(name="Schnitt P6", price_cents=2500, duration_minutes=60)
    return day, resource, service


def test_service_slots_highlight_only_rule_matching_times():
    from apps.booking import public_views as booking_views

    day, _resource, service = _slots_setup()
    promo = _promo(price=Decimal("20.00"))
    Promotion.objects.filter(pk=promo.pk).update(
        service=service, target_rules={"hour_from": 10, "hour_to": 12}
    )
    body = booking_views.service_slots(
        _req(f"/termin/leistung/{service.pk}/?tag={day.isoformat()}"), pk=service.pk
    ).content.decode()
    # старты 10/11/12; окно [10,12) → ровно два помечены промо-ценой
    assert body.count('data-slot-promo="1"') == 2
    assert "gilt für die rosa markierten Zeiten" in body  # баннер акции


def test_service_slots_no_promo_no_marks():
    from apps.booking import public_views as booking_views

    day, _resource, service = _slots_setup()
    body = booking_views.service_slots(
        _req(f"/termin/leistung/{service.pk}/?tag={day.isoformat()}"), pk=service.pk
    ).content.decode()
    assert 'data-slot-promo="1"' not in body
    assert "gilt für die rosa markierten Zeiten" not in body


def test_service_slots_selected_slot_shows_promo_price_in_form():
    from datetime import datetime
    from urllib.parse import quote

    from apps.booking import public_views as booking_views

    day, _resource, service = _slots_setup()
    promo = _promo(price=Decimal("20.00"))
    Promotion.objects.filter(pk=promo.pk).update(service=service, target_rules={})
    # сетка отдаёт aware-старты — ссылка выбора несёт isoformat С офсетом
    iso = quote(timezone.make_aware(datetime.combine(day, time(10, 0))).isoformat())
    body = booking_views.service_slots(
        _req(f"/termin/leistung/{service.pk}/?tag={day.isoformat()}&slot={iso}"),
        pk=service.pk,
    ).content.decode()
    # промо-цена выбранного времени — в форме брони (зеркало service_book)
    assert "line-through text-gray-400 ml-1" in body


# --- номер -------------------------------------------------------------------


def _unit(price_cents=10000):
    import uuid

    from apps.stays.models import StayUnit

    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=price_cents)


def test_stay_detail_badge_before_dates_and_promo_quote_with_dates():
    from apps.stays import public_views as stay_views

    unit = _unit()
    promo = _promo()
    Promotion.objects.filter(pk=promo.pk).update(stay_unit=unit, discount_percent=20)
    # бейдж ДО выбора дат
    body = stay_views.unterkunft_unit(_req(f"/unterkunft/{unit.pk}/"), pk=unit.pk).content.decode()
    assert "−20 %" in body
    # с датами: quote витрины повторяет расчёт book_stay (label акции в скидке)
    von = timezone.localdate() + timedelta(days=7)
    bis = von + timedelta(days=2)
    body = stay_views.unterkunft_unit(
        _req(f"/unterkunft/{unit.pk}/?von={von.isoformat()}&bis={bis.isoformat()}"),
        pk=unit.pk,
    ).content.decode()
    assert "Aktion −20%" in body


def test_unit_listing_ab_price_includes_promo():
    from apps.stays.public_views import _unit_from_price_cents

    unit = _unit()
    promo = _promo()
    Promotion.objects.filter(pk=promo.pk).update(stay_unit=unit, discount_percent=20)
    von = timezone.localdate() + timedelta(days=7)
    cents = _unit_from_price_cents(unit, von, von + timedelta(days=2), [])
    assert cents == 16000  # 2 ночи × 100 € − 20 %
