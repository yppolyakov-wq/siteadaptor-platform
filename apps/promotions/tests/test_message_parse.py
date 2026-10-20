"""T-8.10b B-1b: разбор сообщения владельца — таблица плана §3 + негативные случаи."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.promotions import message_parse as mp

# Среда, 21.10.2026, 10:00 — «сегодня» ещё не закончилось.
NOW = timezone.make_aware(datetime(2026, 10, 21, 10, 0))
TODAY = NOW.date()


def P(text):
    return mp.parse(text, now=NOW)


@pytest.mark.parametrize(
    "text, title, new, old, pct, qty, term, until, tm",
    [
        (
            "Brötchen −30 % bis 18 Uhr, 20 Stück",
            "Brötchen",
            None,
            None,
            30,
            20,
            "today",
            None,
            time(18),
        ),
        (
            "Erdbeerkuchen 2,50 € statt 3,90 € heute",
            "Erdbeerkuchen",
            "2.50",
            "3.90",
            None,
            None,
            "today",
            None,
            None,
        ),
        (
            "Herbstjacken 20% bis Sonntag",
            "Herbstjacken",
            None,
            None,
            20,
            None,
            "date",
            date(2026, 10, 25),
            None,
        ),
        (
            "Haarschnitt nur 19 € am Wochenende",
            "Haarschnitt",
            "19.00",
            None,
            None,
            None,
            "weekend",
            None,
            None,
        ),
        ("Tomaten 1 kg 1,99", "Tomaten 1 kg", "1.99", None, None, None, "", None, None),
        (
            "Pizza 4 Käse 8,50 € statt 10 €",
            "Pizza 4 Käse",
            "8.50",
            "10.00",
            None,
            None,
            "",
            None,
            None,
        ),
        ("Sale -50% bis 31.10.", "Sale", None, None, 50, None, "date", date(2026, 10, 31), None),
        (
            "Croissants 30% off until 6pm, 15 pcs",
            "Croissants",
            None,
            None,
            30,
            15,
            "today",
            None,
            time(18),
        ),
        ("Пирожки −20% до 19:00, 10 шт", "Пирожки", None, None, 20, 10, "today", None, time(19)),
        ("Simit %25 indirim bugün", "Simit", None, None, 25, None, "today", None, None),
        ("Kuchen 3,90 → 2,50", "Kuchen", "2.50", "3.90", None, None, "", None, None),
        (
            "Äpfel 2 kg 3,00 € morgen",
            "Äpfel 2 kg",
            "3.00",
            None,
            None,
            None,
            "date",
            TODAY + timedelta(days=1),
            None,
        ),
        (
            "Salat −10 % 3 Tage",
            "Salat",
            None,
            None,
            10,
            None,
            "date",
            TODAY + timedelta(days=3),
            None,
        ),
    ],
)
def test_table(text, title, new, old, pct, qty, term, until, tm):
    r = P(text)
    assert r.title == title
    assert r.new_price == (Decimal(new) if new else None)
    assert r.old_price == (Decimal(old) if old else None)
    assert r.percent == pct
    assert r.quantity == qty
    assert r.term == term
    assert r.until == until
    assert r.until_time == tm


def test_price_condition_is_only_a_warning():
    r = P("Kaffee 2 für 1")
    assert r.title == "Kaffee" and "price_condition" in r.warnings
    assert r.new_price is None and r.percent is None


def test_phone_is_not_a_signal():
    r = P("Ruf an: 0212 123456")
    assert not r.signals


def test_price_and_percent_keeps_price():
    r = P("Kuchen 3,50 € −20 %")
    assert r.new_price == Decimal("3.50") and r.percent is None
    assert "price_and_percent" in r.warnings


def test_old_not_higher_dropped():
    r = P("Brot 4 € statt 3 €")
    assert r.new_price == Decimal("4.00") and r.old_price is None
    assert "old_not_higher" in r.warnings


def test_time_in_the_past_is_dropped():
    r = P("Brötchen −30 % bis 8 Uhr")
    assert r.until_time is None and "time_past" in r.warnings


def test_invalid_date_and_percent():
    r = P("Sale -150% bis 31.02.")
    assert r.until is None and r.percent is None
    assert "date_invalid" in r.warnings and "percent_invalid" in r.warnings


def test_past_date_without_year_rolls_over():
    r = P("Sale -10% bis 01.01.")
    assert r.until == date(2027, 1, 1) and "date_rolled" in r.warnings


def test_bare_number_after_bis_is_not_time():
    r = P("Gurken bis 18")
    assert r.until_time is None and r.term == ""


def test_description_from_following_lines():
    r = P("Brötchen −30 %\nFrisch aus dem Ofen.\nNur solange der Vorrat reicht.")
    assert r.title == "Brötchen"
    assert r.description == "Frisch aus dem Ofen. Nur solange der Vorrat reicht."


def test_long_text_is_capped_and_never_raises():
    r = P("A" * 5000)
    assert len(r.title) <= mp.TITLE_MAX
    for junk in ("", "   ", "€€€", "%%%", "bis bis bis", "0,00 €", "99999999 €"):
        mp.parse(junk, now=NOW)


@pytest.mark.parametrize(
    "text, term, until, tm",
    [
        ("Brötchen morgen bis 18 Uhr 2,50 €", "date", date(2026, 10, 22), time(18)),
        ("Herbstjacken 20% bis Sonntag 18 Uhr", "date", date(2026, 10, 25), time(18)),
        ("Salat −10 % 3 Tage bis 12:30", "date", date(2026, 10, 24), time(12, 30)),
        ("Brötchen heute bis 18 Uhr −30 %", "today", None, time(18)),
    ],
)
def test_relative_term_with_time_applies_time_to_that_day(text, term, until, tm):
    r = P(text)
    assert (r.term, r.until, r.until_time) == (term, until, tm)
    assert "morgen" not in r.title and "Uhr" not in r.title


def test_time_with_weekend_is_ignored_with_warning():
    r = P("Kuchen −20 % Wochenende bis 20 Uhr")
    assert r.term == "weekend" and r.until_time is None and "time_ignored" in r.warnings


@pytest.mark.parametrize(
    "text, title, price, qty",
    [
        ("Wein 0,75 l nur heute", "Wein 0,75 l", None, None),
        ("Brot 3 Euro 50", "Brot", Decimal("3.50"), None),
        ("Shirt 5 x-large 20 €", "Shirt 5 x-large", Decimal("20.00"), None),
        ("Käse 500g 1,99 statt 2,49", "Käse 500g", Decimal("1.99"), None),
    ],
)
def test_units_are_not_prices(text, title, price, qty):
    r = P(text)
    assert (r.title, r.new_price, r.quantity) == (title, price, qty)


@pytest.mark.parametrize(
    "text",
    ["Brötchen −30 % diese Woche", "Brötchen −30 % this week", "Brötchen −30 % bu hafta"],
)
def test_this_week_is_a_term_not_part_of_title(text):
    parsed = mp.parse(text)
    assert parsed.term == "week"
    assert parsed.title == "Brötchen"
