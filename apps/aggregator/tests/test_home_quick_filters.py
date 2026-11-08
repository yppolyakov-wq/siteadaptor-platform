"""PH-5 → PH-11d2/e: быстрые фильтры сняты с главной (замок отсутствия), код удалён в PH-11e."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


def _seed():
    _listing(
        "promotion",
        "Pizza-Deal",
        city_category="restaurants",
        discount_percent=30,
        new_price=5,
        ends_at=timezone.now() + timedelta(hours=3),
    )
    _listing("product", "Brot", city_category="brot-backwaren", new_price=3, district="mitte")


def test_home_has_no_quick_filters_or_hero_chips():
    """PH-11d2 (макет K1): быстрые фильтры и чипы первого экрана сняты — их работу делают поиск
    шапки («Was/Wo/Wann»), баннер и quad-карточки. Фильтры живут в ленте."""
    portal = _portal()
    _seed()
    body = _html(portal)
    assert "data-home-quick-filters" not in body and "data-hero-chip" not in body
    assert "data-hero-stats" not in body and "data-section-tiles" not in body
    assert "data-portal-header-search" in body and "csrfmiddlewaretoken" not in body
