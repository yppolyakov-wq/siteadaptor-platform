"""LS-4 v2: «Verkauft N diese Woche» — честный social-proof.

Замки: порог SOLD_BADGE_MIN (меньше → None), окно 7 дней, отменённые заказы
исключены, неизвестный kind/ошибка → None (fail-safe), бейдж-партиал рендерит
пусто без n и текст при n.
"""

from datetime import timedelta

import pytest
from django.template.loader import render_to_string
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.core import social_proof
from apps.orders import services as order_services
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


def _sell(product, qty=1):
    return order_services.create_order(
        items=[(product, qty)], name="K", email=f"k{qty}-{timezone.now().timestamp()}@t.de"
    )


def test_threshold_and_counting():
    p = ProductFactory(name={"de": "Brot"})
    _sell(p, 4)
    assert social_proof.sold_last_week("product", p.pk) is None  # 4 < порога
    _sell(p, 3)
    assert social_proof.sold_last_week("product", p.pk) == 7  # Σ qty


def test_cancelled_orders_excluded():
    p = ProductFactory(name={"de": "Brot"})
    order = _sell(p, 6)
    Order.objects.filter(pk=order.pk).update(status=Order.STATUS_CANCELLED)
    assert social_proof.sold_last_week("product", p.pk) is None


def test_window_excludes_old_sales():
    p = ProductFactory(name={"de": "Brot"})
    order = _sell(p, 6)
    Order.objects.filter(pk=order.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )
    assert social_proof.sold_last_week("product", p.pk) is None


def test_unknown_kind_and_failures_are_none():
    assert social_proof.sold_last_week("promotion", "x") is None
    assert social_proof.sold_last_week("product", "not-a-uuid") is None  # fail-safe


def test_badge_partial_renders_only_with_n():
    empty = render_to_string("storefront/_sold_badge.html", {"n": None, "kind": "product"})
    assert "verkauft" not in empty
    html = render_to_string("storefront/_sold_badge.html", {"n": 7, "kind": "product"})
    assert "7" in html and "verkauft diese Woche" in html
    stay = render_to_string("storefront/_sold_badge.html", {"n": 6, "kind": "stay"})
    assert "gebucht" in stay
