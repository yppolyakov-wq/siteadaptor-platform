"""PH-11e (макет K1): тёмный подвал портала — пять колонок, ссылки только на непустые ленты,
кэш на портал и язык, на всех страницах; районы и отрасли — только здесь (сняты с главной)."""

import pytest
from django.core.cache import cache

from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _foot(html):
    return html.split("data-portal-footer", 1)[1].split("</footer>", 1)[0]


def test_footer_has_five_columns_and_only_non_empty_links():
    _listing("promotion", "Pizza", business_type="bakery", district="wald")
    foot = _foot(_html(_portal()))
    for heading in ("Entdecken", "Stadtteile", "Für Unternehmen", "Rechtliches"):
        assert heading in foot
    assert "?kind=angebote" in foot and "?kind=event" not in foot  # событий нет — ссылки нет
    assert "/stadtteil/wald/" in foot and "/stadtteil/mitte/" not in foot
    assert "/bakery/" in foot.split("data-footer-facets", 1)[1]
    assert "Impressum" in foot and "Datenschutz" in foot


def test_footer_is_on_feed_pages_and_never_links_other_portals():
    p = _portal()
    _portal(host="koeln.siteadaptor.de", city="Köln", title={"de": "Angebote Köln"})
    _listing("promotion", "Pizza", district="wald")
    for params in ({}, {"kind": "alle"}, {"q": "Pizza"}):
        foot = _foot(_html(p, **params))
        assert "/stadtteil/wald/" in foot, params
        assert "koeln.siteadaptor.de" not in foot


def test_footer_data_is_cached(django_assert_num_queries):
    from apps.aggregator.templatetags.portal_brand import portal_footer

    p = _portal()
    _listing("promotion", "Pizza", district="wald", business_type="bakery")
    first = portal_footer(p)
    assert first["districts"] and first["facets"] and first["kinds"]
    with django_assert_num_queries(0):
        assert portal_footer(p) == first


def test_home_has_no_district_tiles_or_branche_any_more():
    _listing("promotion", "Pizza", business_type="bakery", district="wald")
    html = _html(_portal())
    body = html.split("data-portal-footer", 1)[0]
    assert "data-district-tile" not in body and "/stadtteil/wald/" not in body.split("<main", 1)[1]


def test_footer_failure_does_not_break_the_page(monkeypatch):
    from apps.aggregator import portal_views

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(portal_views, "_district_choices", boom)
    _listing("promotion", "Pizza")
    html = _html(_portal(), kind="alle")
    assert "data-portal-footer" in html and "Pizza" in html


def test_feed_links_in_footer_are_nofollow():
    _listing("promotion", "Pizza")
    foot = _foot(_html(_portal()))
    assert 'href="/?kind=angebote" rel="nofollow"' in foot


def test_visible_prices_use_euro_sign_not_iso_code():
    """Прод-разбор PH-10: «5,00 EUR» на карточках → «5,00 €»."""
    from apps.aggregator.templatetags.portal_brand import currency_sign

    assert currency_sign("EUR") == "€" and currency_sign("CHF") == "CHF" and currency_sign("") == ""
    _listing("promotion", "Pizza", new_price=5, currency="EUR")
    html = _html(_portal(), kind="alle")
    cards = html.split("data-card-title", 1)[1].split("data-portal-footer", 1)[0]
    assert "€" in cards and " EUR<" not in cards
