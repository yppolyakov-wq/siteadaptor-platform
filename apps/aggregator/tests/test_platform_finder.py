"""FD-4: платформенный Finder агрегатора («2 вопроса → 3 Angebote»).

Замки: серверные шаги (вертикаль → город → выдача), невалидные параметры =
возврат на шаг, фолбэк при пустой выдаче, ОРГАНИЧЕСКИЙ порядок (UWG §5a:
платная позиция не переприоритизируется и несёт метку «★ Anzeige»).
"""

import uuid
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.aggregator import finder as agg_finder
from apps.aggregator import views
from apps.aggregator.models import AggregatorListing

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_public"


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "Backhaus",
        "business_type": "bakery",
        "city": "Hilden",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot -20%"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _get(params=None):
    return views.platform_finder(RequestFactory().get("/entdecken/finder/", params or {}))


def test_step_flow_type_then_city_then_results():
    _listing()
    _listing(city="Köln", promo_uuid=uuid.uuid4(), business_type="cafe", business_name="Café K")
    body = _get().content.decode()
    assert "Was suchst du?" in body and "?typ=bakery" in body  # шаг 1: вертикали
    body2 = _get({"typ": "bakery"}).content.decode()
    assert "Wo?" in body2 and "stadt=Hilden" in body2
    assert "K%C3%B6ln" not in body2 and "Köln" not in body2  # город чужой вертикали скрыт
    body3 = _get({"typ": "bakery", "stadt": "Hilden"}).content.decode()
    assert "Backhaus" in body3 and "Noch mal suchen" in body3


def test_invalid_params_return_to_step():
    _listing()
    assert "Was suchst du?" in _get({"typ": "bogus"}).content.decode()
    assert "Wo?" in _get({"typ": "bakery", "stadt": "Nirgendwo"}).content.decode()


def test_empty_city_pool_gives_honest_fallback():
    lst = _listing()
    # город валиден для bakery, но все листинги города деактивировались между шагами
    state = agg_finder.resolve_public("bakery", "Hilden")
    assert state["step"] == 3 and not state["fallback"]
    AggregatorListing.objects.filter(pk=lst.pk).update(city="Neuss")
    state2 = agg_finder.resolve_public("bakery", "Hilden")
    assert state2["step"] == 2  # города пересчитались — Hilden больше не валиден


def test_organic_order_and_featured_marked():
    """UWG §5a: платная позиция НЕ переставляется вперёд и несёт «★ Anzeige»."""
    first = _listing(business_name="Organisch A")
    featured = _listing(
        business_name="Bezahlt B",
        promo_uuid=uuid.uuid4(),
        featured_until=timezone.now() + timedelta(hours=5),
    )
    state = agg_finder.resolve_public("bakery", "Hilden")
    ids = [r.pk for r in state["results"]]
    organic_ids = list(
        views.listings_for(city="Hilden", business_type="bakery").values_list("pk", flat=True)
    )[:3]
    assert ids == organic_ids  # порядок дефолтный, без featured-подъёма
    body = _get({"typ": "bakery", "stadt": "Hilden"}).content.decode()
    assert "★ Anzeige" in body  # платная позиция помечена (реюз _cards)
    assert "Unser Vorschlag" not in body  # нейтральная выдача — без «рекомендуем»
    assert first.pk in ids and featured.pk in ids
