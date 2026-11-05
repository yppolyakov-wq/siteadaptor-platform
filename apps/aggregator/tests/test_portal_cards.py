"""PH-3: карточка портала — «Endet in …», часы работы, пилюля действия, маркеры."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.aggregator import portal_cards
from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(minutes=20), "Endet in 20 Min."),
        (timedelta(hours=3, minutes=5), "Endet in 3 Std."),
        (timedelta(days=2, hours=1), "Endet in 2 Tagen"),
        (timedelta(days=1, hours=1), "Endet in 1 Tag"),
        (timedelta(days=9), ""),
        (timedelta(minutes=-5), ""),
    ],
)
def test_ends_label(delta, expected):
    now = timezone.now()
    text, iso = portal_cards.ends_label(SimpleNamespace(ends_at=now + delta), now)
    assert text == expected
    assert bool(iso) is bool(expected)
    assert portal_cards.ends_label(SimpleNamespace(ends_at=None)) == ("", "")


def test_prepare_cards_one_query():
    cards = [SimpleNamespace(tenant_schema=f"s{i}", ends_at=None) for i in range(5)]
    with CaptureQueriesContext(connection) as ctx:
        portal_cards.prepare_cards(cards)
    assert len(ctx.captured_queries) == 1


def test_card_shows_countdown_action_and_keeps_markers():
    portal = _portal()
    soon = timezone.now() + timedelta(hours=2, minutes=30)
    _listing(
        "promotion", "Pizza-Deal", city_category="restaurants", ends_at=soon, discount_percent=30
    )
    _listing(
        "product", "Messer", city_category="handgemachtes", is_new=True, availability="sold_out"
    )
    body = _html(portal, kind="alle")
    assert "data-ends-at=" in body and "Endet in 2 Std." in body
    assert "data-card-action>Zum Angebot<" in body and "data-card-action>Ansehen<" in body
    for marker in (
        "data-pstat=",
        "data-card-title",
        "data-new-badge",
        'data-availability="sold_out"',
        "−30 %",
    ):
        assert marker in body, marker
    assert body.count("<a ") >= 2
    # пилюля — не вложенная ссылка
    assert "<a" not in body.split("data-card-action", 1)[1].split("</span>", 1)[0]
