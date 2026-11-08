"""PH-11a: шапка портала — поиск «Was / Wo / Wann» одной GET-формой на всех страницах."""

import re

import pytest

from apps.aggregator import portal_views
from apps.aggregator import search as search_engine
from apps.aggregator.tests.test_portal_discover import _get, _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


def _header_form(html: str) -> str:
    return html.split("data-portal-header-search", 1)[1].split("</form>", 1)[0]


def test_header_form_on_home_and_feed_has_three_labelled_fields():
    _listing("promotion", "Herbstrabatt")
    portal = _portal()
    for params in ({}, {"q": "Herbst"}, {"kind": "alle"}):
        form = _header_form(_html(portal, **params))
        assert 'name="q"' in form and 'name="stadtteil"' in form and 'name="datum"' in form
        for label in ("Was", "Wo", "Wann"):
            assert f">{label}</span>" in form


def test_header_wo_lists_city_districts_and_preselects_filter():
    _listing("promotion", "Herbstrabatt")
    form = _header_form(_html(_portal(), q="Herbst", stadtteil="wald"))
    assert '<option value="wald" selected>' in form
    assert 'value="graefrath"' in form  # все районы города из реестра


def test_header_hidden_does_not_duplicate_visible_fields():
    """Дубль имени перетёр бы выбор в форме (QueryDict.get берёт последнее)."""
    _listing("promotion", "Herbstrabatt")
    html = _html(_portal(), q="Herbst", stadtteil=["wald", "mitte"], offen="1", kind="angebote")
    form = _header_form(html)
    hidden = re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form)
    names = [n for n, _ in hidden]
    assert ("stadtteil", "mitte") in hidden  # второй район едет скрытым
    assert ("stadtteil", "wald") not in hidden and "offen" not in names and "datum" not in names
    assert ("kind", "angebote") in hidden
    assert '<option value="jetzt" selected>' in form


def test_datum_jetzt_means_open_now():
    req = _get(_portal(), datum="jetzt")
    f = search_engine.parse_filters(req, city="Solingen")
    assert f.open_now is True and f.date == ""
    assert ("offen", "1") in search_engine.carry("", f)


def test_empty_header_submit_stays_on_home():
    _listing("promotion", "Herbstrabatt")
    assert "data-portal-home" in _html(_portal(), q="", stadtteil="", datum="")


def test_header_search_without_csrf_and_menu_button_keeps_anchor():
    _listing("promotion", "Herbstrabatt")
    html = _html(_portal())
    assert "csrfmiddlewaretoken" not in html
    assert 'href="/#kategorien" data-portal-menu-open' in html
    assert html.count("data-portal-search") == 1  # одна форма поиска на странице


def test_header_on_district_page_preselects_path_district():
    _listing("promotion", "Herbstrabatt", district="wald")
    resp = portal_views.portal_home(_get(_portal(), path="/stadtteil/wald/"), district="wald")
    form = _header_form(resp.content.decode())
    assert '<option value="wald" selected>' in form
