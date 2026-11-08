"""PH-11d1 (макет K1): баннер-слайдер главной — слайд без данных не рендерится, число ⊆ ленты."""

import re
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.aggregator import portal_home_blocks as home
from apps.aggregator import search
from apps.aggregator.models import AggregatorListing
from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Корень портала и меню кэшируются (Redis переживает прогоны и делится xdist-воркерами)."""
    cache.clear()
    yield
    cache.clear()


def _slides(html):
    return re.findall(r'data-slide="([a-z]+)"', html)


def _weekend(shift_days=0):
    """Предстоящее событие внутри окна «Wochenende»: начавшееся лента прячет (как и пул
    портала), поэтому старт — не раньше «сейчас + 10 минут»; в воскресенье поздно вечером
    будущего места в окне нет — тест пропускается."""
    start, end = search.date_window("wochenende")
    begin = max(start, timezone.now() + timedelta(minutes=10))
    if begin >= end:
        pytest.skip("окно выходных закончилось")
    shift = timedelta(days=shift_days)
    return {"starts_at": begin + shift, "ends_at": end + shift}


def test_only_business_slide_without_data_and_no_controls():
    _listing("product", "Brot", city_category="brot-backwaren")
    html = _html(_portal())
    assert _slides(html) == ["business"]
    assert "data-slider-controls" not in html
    assert "Jetzt Geschäft eintragen" in html
    assert 'href="/fuer-unternehmen/"' in html


def test_solingen_photo_has_visible_credit_and_license():
    _listing("product", "Brot", city_category="brot-backwaren")
    html = _html(_portal())
    credit = html.split("data-photo-credit", 1)[1].split("</p>", 1)[0]
    assert "InterCityImpress" in credit and "CC BY-SA 2.0" in credit
    assert 'rel="license noopener"' in credit
    assert "muengstener-bruecke.webp" in html


def test_deal_weekend_and_regional_slides_in_order_with_controls():
    _listing(
        "promotion",
        "Pizza-Deal",
        discount_percent=40,
        new_price=5,
        image={"url": "https://x.test/a.jpg"},
        city_category="restaurants",
    )
    _listing("event", "Flohmarkt", **_weekend())
    _listing("product", "Honig", city_tags=["regional"])
    html = _html(_portal())
    assert _slides(html) == ["business", "deal", "weekend", "regional"]
    assert "data-deal-of-day" in html.split('data-slide="deal"', 1)[1]
    controls = html.split("data-slider-controls", 1)[1]
    assert controls.count("data-slider-dot=") == 4 and "1 / 4" in controls
    assert 'aria-roledescription="Karussell"' in html


def test_slide_counts_are_contained_in_their_feeds():
    portal = _portal()
    _listing("event", "Flohmarkt", **_weekend())
    _listing("event", "Nächste Woche", **_weekend(7))
    _listing("product", "Honig", city_tags=["regional"])
    stats = home.home_stats(AggregatorListing.objects.all())
    assert stats["weekend"] == 1 and stats["regional"] == 1
    html = _html(portal)
    for key, title in (("weekend", "Flohmarkt"), ("regional", "Honig")):
        slide = html.split(f'data-slide="{key}"', 1)[1].split("data-slide=", 1)[0]
        url = re.search(r'<a href="(/\?[^"]+)" rel="nofollow"', slide).group(1)
        params = dict(p.split("=") for p in url.replace("&amp;", "&").split("?", 1)[1].split("&"))
        assert title in _html(portal, **params), url


def test_featured_never_lands_in_slider():
    _listing(
        "promotion",
        "Bezahlt",
        discount_percent=90,
        new_price=5,
        image={"url": "https://x.test/a.jpg"},
        featured_until=timezone.now() + timedelta(days=1),
    )
    html = _html(_portal())
    # PH-13b: заголовок теперь стоит в DOM раньше слайдера — режем слайдер по его </section>
    slider = html.split("data-portal-slider", 1)[1].split("</section>", 1)[0]
    assert "Bezahlt" not in slider


def test_home_heading_stays_below_slider_and_no_csrf():
    """PH-13b (осознанно переписан): в DOM h1 раньше слайдера (на телефоне он над баннером,
    макет M5), на десктопе слайдер визуально первым — обёртка `md:-order-1`."""
    _listing("product", "Brot", city_category="brot-backwaren")
    html = _html(_portal())
    assert html.index('id="hero-h"') < html.index("data-portal-slider")
    assert re.search(r'<div class="md:-order-1">\s*<section[^>]*data-portal-slider', html)
    assert html.count("<h1") == 1 and "csrfmiddlewaretoken" not in html


def test_page_heading_comes_first_and_slides_have_no_headings():
    """PH-12c: h1 «Was gibt's heute …» — первый заголовок страницы; у слайдов — текст."""
    _listing(
        "promotion",
        "Pizza-Deal",
        discount_percent=40,
        new_price=5,
        image={"url": "https://x.test/a.jpg"},
        city_category="restaurants",
    )
    html = _html(_portal())
    # закрытые <dialog> (мега-меню, шторка) вне дерева доступности — их заголовки не в счёт
    body = re.sub(r"<dialog\b.*?</dialog>", "", html.split("<body", 1)[1], flags=re.S)
    assert body.index("<h1") < body.index("<h2")
    slider = html.split("data-portal-slider", 1)[1].split("</section>", 1)[0]
    assert "<h2" not in slider and "<h3" not in slider
    assert 'aria-labelledby="slide-deal-h"' in slider and 'id="slide-deal-h"' in slider
