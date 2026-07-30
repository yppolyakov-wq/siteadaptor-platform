"""M1 Boutique (§11 PAngV): журнал цен + 30-дневный минимум + Textilkennzeichnung
на витрине (план mode-boutique-plan-2026-07-30)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.models import PriceLog, Product
from apps.catalog.price_history import lowest_price_30d
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_price_log_written_on_change_only():
    p = Product.objects.create(name={"de": "Kleid"}, base_price=Decimal("45.00"))
    assert PriceLog.objects.filter(product=p).count() == 1  # первая запись при создании
    p.save()  # цена не менялась → без дубля
    assert PriceLog.objects.filter(product=p).count() == 1
    p.base_price = Decimal("39.00")
    p.save()
    assert PriceLog.objects.filter(product=p).count() == 2


def test_lowest_price_30d_includes_price_at_window_start():
    p = Product.objects.create(name={"de": "Rock"}, base_price=Decimal("50.00"))
    # старая запись ДО окна (цена действовала на его начало) должна учитываться
    old = PriceLog.objects.get(product=p)
    PriceLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=45))
    p.base_price = Decimal("60.00")
    p.save()
    assert lowest_price_30d(p) == Decimal("50.00")


def test_lowest_price_none_without_logs():
    p = Product.objects.create(name={"de": "X"}, base_price=Decimal("10.00"))
    PriceLog.objects.filter(product=p).delete()
    assert lowest_price_30d(p) is None


def _detail(promo):
    from apps.promotions import public_views

    request = RequestFactory().get(f"/p/{promo.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="clothing")
    return public_views.promotion_detail(request, pk=promo.pk).content.decode()


def test_promotion_detail_shows_30d_reference_price():
    from apps.promotions.models import Promotion

    p = Product.objects.create(name={"de": "Bluse"}, base_price=Decimal("39.90"))
    promo = Promotion.objects.create(
        title={"de": "Bluse −20 %"},
        status="active",
        product=p,
        discount_percent=20,
        compare_at_price=Decimal("39.90"),
    )
    body = _detail(promo)
    assert "letzten 30 Tage" in body and "39,90" in body or "39.90" in body


def test_product_detail_shows_material_and_care():
    from apps.promotions import public_views

    p = Product.objects.create(
        name={"de": "Kleid"},
        base_price=Decimal("45.00"),
        material="100 % Leinen",
        care="30 °C Schonwäsche",
    )
    request = RequestFactory().get(f"/produkt/{p.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="clothing")
    body = public_views.product_detail(request, pk=p.pk).content.decode()
    assert "100 % Leinen" in body and "30 °C Schonwäsche" in body
