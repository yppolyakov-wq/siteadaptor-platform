"""PH-12d: честность первого экрана (ошибки прода §1 п. 1, 2, 4, 8 разбора 2026-11-07)."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.aggregator import portal_home_blocks as home
from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]

IMG = {"url": "https://x.test/a.jpg"}


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _biz(i, *, photo=True, offer=True):
    from apps.aggregator.models import AggregatorListing

    schema = f"nb{i}"
    _listing("business", f"Laden {i}", schema=schema, image=IMG if photo else {})
    if offer:
        _listing("promotion", f"Angebot {i}", schema=schema)
    # блок печатает business_name (у хелпера он от глобального счётчика) — задаём явно
    AggregatorListing.objects.filter(tenant_schema=schema).update(business_name=f"Laden {i}")


def _ends_today():
    now = timezone.localtime()
    eod = now.replace(hour=23, minute=59, second=0, microsecond=0)
    return min(now + timedelta(minutes=30), max(eod, now + timedelta(seconds=30)))


def _hours(open_now: bool, *, opens_later_today: bool = False):
    """Часы на сегодня: открыто сейчас / откроется позже сегодня / закрыто до завтра."""
    now = timezone.localtime()
    if open_now:
        return {str(d): ["00:00", "23:59"] for d in range(7)}
    if opens_later_today:
        later = (now + timedelta(minutes=5)).strftime("%H:%M")
        return {str(now.weekday()): [later, "23:59"]}
    return {str((now.weekday() + 1) % 7): ["08:00", "18:00"]}  # только завтра


# --- d1 «Neu in <город>» -------------------------------------------------------------------


def test_new_business_needs_photo_and_an_offer():
    for i in range(3):
        _biz(i)
    _biz(7, photo=False)
    _biz(8, offer=False)
    html = _html(_portal())
    block = html.split("data-home-new-businesses", 1)[1].split("</section>", 1)[0]
    assert "Laden 0" in block and "Laden 7" not in block and "Laden 8" not in block


def test_new_businesses_block_hidden_when_only_empty_businesses():
    for i in range(3):
        _biz(i, offer=False)
    assert "data-home-new-businesses" not in _html(_portal())


# --- d2 «Endet heute» — только то, чем можно воспользоваться --------------------------------


def _endet_card(html):
    if 'data-quad="endet"' not in html:
        return ""
    return html.split('data-quad="endet"', 1)[1].split("Alle anzeigen", 1)[0]


def test_ending_today_skips_business_closed_until_tomorrow():
    TenantFactory(schema_name="zu", slug="zu", opening_hours_structured=_hours(False))
    TenantFactory(schema_name="auf", slug="auf", opening_hours_structured=_hours(True))
    _listing("promotion", "Zu-Deal", schema="zu", ends_at=_ends_today())
    _listing("promotion", "Auf-Deal", schema="auf", ends_at=_ends_today())
    _listing("promotion", "Ohne-Uhr", schema="ohne", ends_at=_ends_today())
    _listing(
        "event",
        "Wochenend-Film",
        city_category="kino",
        starts_at=timezone.now() + timedelta(days=1),
    )
    card = _endet_card(_html(_portal()))
    assert "Auf-Deal" in card and "Ohne-Uhr" in card  # без часов — не утверждаем «закрыто»
    assert "Zu-Deal" not in card


def test_ending_today_keeps_business_that_opens_later_today():
    now = timezone.localtime()
    if now.hour >= 23:
        pytest.skip("до полуночи нет окна «откроется позже сегодня»")
    TenantFactory(
        schema_name="bald",
        slug="bald",
        opening_hours_structured=_hours(False, opens_later_today=True),
    )
    _listing("promotion", "Bald-Deal", schema="bald", ends_at=_ends_today())
    _listing("promotion", "Zweiter", schema="x2", ends_at=_ends_today())
    # вторая карточка — ряд рисуется от двух
    _listing("event", "Film", city_category="kino", starts_at=timezone.now() + timedelta(days=1))
    assert "Bald-Deal" in _endet_card(_html(_portal()))


def test_usable_today_helper_rules():
    now = timezone.localtime().replace(hour=10, minute=0)
    ends = now.replace(hour=12)
    closed_all_day = {
        "holiday": None,
        "status": {"open": False, "until": None, "next": ("Mo", "08:00")},
    }
    assert home.usable_before(None, ends, now) is True  # часов нет
    assert home.usable_before({"holiday": None, "status": None}, ends, now) is True
    assert home.usable_before({"holiday": None, "status": {"open": True}}, ends, now) is True
    assert home.usable_before({"holiday": "x", "status": None}, ends, now) is False
    assert home.usable_before(closed_all_day, ends, now) is False


# --- d3 «Melden» ------------------------------------------------------------------------------


def test_report_link_only_on_offer_page_not_on_cards():
    _listing("promotion", "Pizza")
    html = _html(_portal(), kind="alle")
    assert "data-report-link" not in html and "Melden" not in html.split("<main", 1)[1]


# --- d4 подпись заглушки ---------------------------------------------------------------------


def test_placeholder_without_caption_for_technical_keys():
    from apps.tenants.demo_images import svg_for

    assert "Sg-biergarten" not in svg_for("sg-biergarten")
    assert "Ol-w-blazer" not in svg_for("ol-w-blazer")
    assert "Croissant" in svg_for("croissant")  # человеческий ключ — подпись остаётся
    assert "Biergarten am Fluss" in svg_for("sg-biergarten", cap="Biergarten am Fluss")
