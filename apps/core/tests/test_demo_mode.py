"""В1 (решение владельца 2026-10-16): на витрине демо-бизнеса — только плашка «это
демо-магазин»; оплата, письма и прочий функционал не меняются."""

from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _detail_html(tenant):
    from apps.promotions import public_views
    from apps.promotions.models import Promotion

    promo = Promotion.objects.create(
        title={"de": "Brot"}, status="active", price_override=Decimal("2.00")
    )
    req = RequestFactory().get(f"/p/{promo.pk}/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.promotion_detail(req, pk=promo.pk).content.decode()


# --- (a) плашка ------------------------------------------------------------------


def test_demo_storefront_shows_banner():
    html = _detail_html(TenantFactory.build(business_type="bakery", is_demo=True))
    assert "data-demo-banner" in html
    assert "Beispiel-Shop" in html


def test_real_storefront_has_no_banner():
    html = _detail_html(TenantFactory.build(business_type="bakery", is_demo=False))
    assert "data-demo-banner" not in html


def test_embed_base_includes_banner():
    src = (Path(settings.BASE_DIR) / "templates/storefront/_embed_base.html").read_text()
    assert "_demo_banner.html" in src
