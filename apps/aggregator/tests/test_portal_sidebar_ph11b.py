"""PH-11b: колонка фильтров выдачи — та же форма шторки, сворачивается кнопкой."""

import pytest

from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


def _feed(**params):
    _listing("promotion", "Herbstrabatt")
    return _html(_portal(), **params)


def test_one_filter_form_serves_as_sidebar_before_results():
    html = _feed(q="Herbst")
    layout = html.split("data-flt-layout", 1)[1]
    assert html.count('id="flt-drawer"') == 1  # поля не дублируются
    assert layout.index('id="flt-drawer"') < layout.index("data-card-title")
    assert "lg:block" in html.split('id="flt-drawer"', 1)[1].split(">", 1)[0]


def test_toggle_controls_the_sidebar_and_labels_both_states():
    html = _feed(q="Herbst")
    bar = html.split("data-flt-bar", 1)[1].split("data-hit-count", 1)[0]
    assert 'aria-controls="flt-drawer"' in bar and "data-flt-open" in bar
    assert (
        'data-label-hide="Filter ausblenden"' in bar
        and 'data-label-show="Filter einblenden"' in bar
    )


def test_cards_grid_widens_when_sidebar_collapsed():
    html = _feed(kind="alle")
    grid = html.split("data-flt-grid", 1)[0].rsplit("<div", 1)[1]
    assert "xl:grid-cols-4" in grid and "xl:group-data-[flt-collapsed]/flt:grid-cols-5" in grid


def test_breadcrumbs_on_search_results():
    html = _feed(q="Herbst")
    crumbs = html.split("data-breadcrumbs", 1)[1].split("</nav>", 1)[0]
    assert "Startseite" in crumbs and "Suchergebnisse" in crumbs


def test_non_city_portal_keeps_old_layout():
    _listing("promotion", "Herbstrabatt")
    html = _html(_portal(kind="vertical", business_type="bakery"), kind="alle")
    assert "data-flt-layout" not in html


def test_search_heading_names_the_query():
    html = _feed(q="Herbst")
    assert "Suchergebnisse für „Herbst“" in html.split("<h1", 1)[1].split("</h1>", 1)[0]


def test_search_heading_escapes_the_query():
    html = _feed(q='<script>x</script>"')
    h1 = html.split("<h1", 1)[1].split("</h1>", 1)[0]
    assert "<script>x" not in h1 and "&lt;script&gt;" in h1


def test_collapsed_state_applied_before_paint():
    """Свёрнутая колонка не мигает: атрибут ставится до отрисовки, из того же localStorage."""
    html = _feed(q="Herbst")
    layout = html.split("data-flt-layout", 1)[1].split('id="flt-drawer"', 1)[0]
    assert (
        'localStorage.getItem("portal:fltCollapsed")' in layout and "data-flt-collapsed" in layout
    )
    assert (
        "lg:group-data-[flt-collapsed]/flt:hidden"
        in html.split('id="flt-drawer"', 1)[1].split(">", 1)[0]
    )
