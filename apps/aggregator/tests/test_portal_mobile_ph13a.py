"""PH-13a: мобильная шапка портала по макету M5 (план docs/ph13-portal-mobile-plan-2026-11-08.md).

На телефоне шапка не липкая и в одну пилюлю поиска («Was» + строка «Wo · Wann» внутри),
язык виден, «Sign in» — в нижнем меню. Десктоп не меняется: та же форма, те же поля.
"""

import re

import pytest

from apps.aggregator.tests.test_portal_discover import _html, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


def _header(html):
    return re.search(r"<header[^>]*>.*?</header>", html, re.S).group(0)


def _form(html):
    return re.search(r"<form[^>]*data-portal-header-search.*?</form>", html, re.S).group(0)


def test_header_is_sticky_only_from_md():
    tag = re.search(r"<header[^>]*>", _html(_portal())).group(0)
    assert "md:sticky" in tag
    assert not re.search(r'class="sticky\b', tag)


def test_language_menu_is_visible_on_phones():
    header = _header(_html(_portal()))
    assert "data-lang-menu" in header
    assert '<span class="hidden md:inline-flex">' not in header


def test_sign_in_moves_to_bottom_nav_on_phones():
    header = _header(_html(_portal()))
    # 2026-11-09: вход — значком (data-head-icon), на телефоне скрыт (есть «Konto» внизу)
    link = re.search(r'<a href="/konto/login/"[^>]*data-head-icon="login"[^>]*>', header)
    assert link and "hidden sm:inline-flex" in link.group(0)


def test_phone_search_is_one_pill_with_wo_wann_inside():
    form = _form(_html(_portal()))
    tag = re.search(r"<form[^>]*>", form).group(0)
    assert "max-md:rounded-[28px]" in tag and "max-md:border-2" in tag
    # подписи Wo/Wann на телефоне — только для читалок, поля остаются
    for label in ("Wo", "Wann"):
        assert re.search(rf'<span class="[^"]*max-md:sr-only[^"]*">{label}</span>', form), label
    assert form.count('name="stadtteil"') == 1 and form.count('name="datum"') == 1


# --- PH-13a (остаток): компактная шапка выдачи и подсказка раздела --------------------------


def test_search_results_header_is_compact_on_phones():
    from apps.aggregator.tests.test_portal_discover import _listing

    _listing("promotion", "Pizza Margherita")
    head = _header(_html(_portal(), q="Pizza"))
    back = re.search(r"<a[^>]*data-header-back[^>]*>", head).group(0)
    assert "md:hidden" in back and 'href="/"' in back  # ссылка, не history.back
    menu = re.search(r"<a[^>]*data-portal-menu-open[^>]*>", head).group(0)
    word = re.search(r"<a[^>]*data-portal-wordmark[^>]*>", head).group(0)
    assert "max-md:hidden" in menu
    # фидбэк 2026-11-09: бренд в компактной шапке остаётся (без подписи) — логотип не пропадает
    assert "max-md:hidden" not in word


def test_home_header_keeps_menu_and_wordmark_without_back_link():
    head = _header(_html(_portal()))
    assert "data-header-back" not in head
    menu = re.search(r"<a[^>]*data-portal-menu-open[^>]*>", head).group(0)
    assert "max-md:hidden" not in menu


def test_section_page_search_placeholder_names_the_section():
    from apps.aggregator.tests.test_portal_discover import _listing

    _listing("promotion", "Pasta-Abend", city_category="restaurants")
    form = _form(_html(_portal(), kat="essen-gastronomie"))
    ph = re.search(r'placeholder="([^"]*)"', form).group(1)
    assert ph.startswith("In ") and ph.endswith("suchen …") and "Pizza, Friseur" not in ph
    assert 'name="kat"' in form  # подсказка «в разделе» честная: раздел едет в форме


def test_section_placeholder_only_when_section_is_carried_by_the_form():
    from apps.aggregator.portal_views import _header_search
    from apps.aggregator.search import SearchFilters

    f = SearchFilters()
    assert _header_search([("kat", "essen-gastronomie")], f, "")["header_scoped"] is True
    assert _header_search([("merkmal", "vegan")], f, "")["header_scoped"] is False
    # /entdecken/ не передаёт header_hidden → подсказка обычная, не «в разделе»
    from django.template.loader import render_to_string

    out = render_to_string(
        "aggregator/_portal_header_search.html",
        {"category_chips": {"label": "Essen"}, "portal": None},
    )
    assert "In Essen suchen" not in out


def test_opening_snapshot_one_minute_old_still_counts_as_today():
    from datetime import timedelta

    from django.utils import timezone

    from apps.aggregator import portal_home_blocks as home
    from apps.tenants.openinghours import weekday_abbr

    now = timezone.localtime().replace(hour=11, minute=0, second=20, microsecond=0)
    row = {
        "holiday": None,
        "status": {"open": False, "next": (weekday_abbr(now.weekday()), "11:00")},
    }
    assert home.usable_before(row, now + timedelta(hours=1), now) is True
