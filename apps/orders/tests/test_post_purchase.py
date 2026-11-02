"""CM-6.4 — post-purchase просьба об отзыве: окно/дедуп, ссылки на товары,
письмо только для выданных/отправленных заказов."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.notifications.models import Notification
from apps.orders import services, tasks
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


def _picked_up_order(days_ago=3):
    order = services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}), 1)], name="Kim", email="kim@test.de"
    )
    Order.objects.filter(pk=order.pk).update(
        status=Order.STATUS_PICKED_UP,
        updated_at=timezone.now() - timedelta(days=days_ago),
    )
    order.refresh_from_db()
    return order


def test_post_purchase_sent_once_with_review_links():
    from apps.tenants.models import Domain
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug="pp-t")
    Domain.objects.create(domain="shop.test", tenant=tenant, is_primary=True)
    order = _picked_up_order()
    assert tasks.send_due_post_purchases() == 1
    n = Notification.objects.get(type="order_post_purchase")
    assert n.recipient == "kim@test.de"
    assert "Wie war Ihr Einkauf?" in n.subject
    assert "https://shop.test/sortiment/" in n.payload["body"]  # ссылка «оценить»
    # SEC-E-M5: ссылка — на форму отзыва с подписанным токеном (право на «проверенный»
    # отзыв); GET по ней ведёт на деталь#bewertungen. E-mail в ссылке не читается.
    assert "/bewerten/?t=" in n.payload["body"]
    assert "kim@test.de" not in n.payload["body"].split("Keine E-Mails")[0]
    # дедуп: второй прогон ничего не шлёт
    assert tasks.send_due_post_purchases() == 0
    order.refresh_from_db()
    assert order.post_purchase_sent_at is not None


def test_post_purchase_ignores_new_and_too_fresh():
    services.create_order(items=[(ProductFactory(), 1)], name="K", email="a@t.de")  # new
    _picked_up_order(days_ago=0)  # выдан только что — окно ещё не наступило
    assert tasks.send_due_post_purchases() == 0
