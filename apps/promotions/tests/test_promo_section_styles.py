"""DL-3: стили секции акций на главной — spotlight / rows / "" (легаси-грид).

Характеризационные замки: дефолт БЕЗ стиля рендерится прежней сеткой (никаких
маркеров новых веток), spotlight несёт featured-карточку + полосу «Endet bald»
(только при ends_at ≤ 3 дня), rows — компактные строки с бейджем-процентом.
План: deal-looks-wave-plan-2026-09-01 §3.
"""

from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import public_views
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _home(sections=None):
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    config = {"sections": sections} if sections is not None else {}
    request.tenant = TenantFactory.build(site_config=config)
    return public_views.storefront_home(request).content.decode()


def test_default_grid_has_no_new_style_markers():
    PromotionFactory(status="active", title={"de": "Sommeraktion"})
    html = _home()
    assert 'id="promo-grid"' in html and "Sommeraktion" in html
    for marker in ("data-promo-spotlight", "data-promo-rows", "data-promo-ending"):
        assert marker not in html, marker


def test_spotlight_features_first_promo_and_ending_strip():
    PromotionFactory(
        status="active",
        title={"de": "Endet gleich"},
        ends_at=timezone.now() + timedelta(days=1),
    )
    PromotionFactory(status="active", title={"de": "Zweite Aktion"})
    html = _home([{"key": "promotions", "enabled": True, "style": "spotlight"}])
    assert "data-promo-spotlight" in html
    assert "data-promo-ending" in html  # полоса «Endet bald» — есть срок ≤ 3 дня
    assert "data-countdown=" in html
    assert "Endet gleich" in html and "Zweite Aktion" in html


def test_spotlight_without_soon_deadlines_hides_strip():
    PromotionFactory(status="active")  # без ends_at
    PromotionFactory(status="active", ends_at=timezone.now() + timedelta(days=30))
    html = _home([{"key": "promotions", "enabled": True, "style": "spotlight"}])
    assert "data-promo-spotlight" in html
    assert "data-promo-ending" not in html


def test_banner_style_features_first_promo_wide():
    """DL-7d: banner — первая акция широкой горизонтальной картой, остальные
    обычной сеткой; полоса «Endet bald» общая со spotlight."""
    PromotionFactory(
        status="active",
        title={"de": "Wochen-Kracher"},
        ends_at=timezone.now() + timedelta(days=1),
    )
    PromotionFactory(status="active", title={"de": "Zweite Aktion"})
    html = _home([{"key": "promotions", "enabled": True, "style": "banner"}])
    assert "data-promo-hero" in html
    assert "data-promo-spotlight" not in html
    assert 'id="promo-grid"' in html  # остальные — сеткой
    assert "data-promo-ending" in html
    # Единственная акция → баннер без пустой сетки под ним.
    from apps.promotions.models import Promotion

    Promotion.objects.filter(title__de="Zweite Aktion").delete()
    html = _home([{"key": "promotions", "enabled": True, "style": "banner"}])
    assert "data-promo-hero" in html and 'id="promo-grid"' not in html


def test_rows_style_renders_compact_rows():
    PromotionFactory(status="active", title={"de": "Prozent-Deal"}, discount_percent=30)
    html = _home([{"key": "promotions", "enabled": True, "style": "rows"}])
    assert "data-promo-rows" in html
    assert "data-promo-spotlight" not in html
    assert "Prozent-Deal" in html
    assert "−30 %" in html  # бейдж процента — герой строки (V5 Marktplatz)
