"""AIS-W W4-2 срез 1: разбор строк «Name — Preis» шага «Angebot prüfen» (без БД)."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from apps.core import offer_lines
from apps.core.offer_lines import parse_lines, validate_row

TODAY = date(2026, 11, 5)


def one(text, kind="waren"):
    lines = parse_lines(text, kind, today=TODAY).lines
    assert len(lines) == 1, lines
    return lines[0]


@pytest.mark.parametrize(
    ("raw", "price"),
    [
        ("Brot — 3,50 €", "3.50"),
        ("Brot — 3,50", "3.50"),
        ("Brot — 3.50 EUR", "3.50"),
        ("Brot — € 3,50", "3.50"),
        ("Brot — 3,50€", "3.50"),
        ("Brot — 12,-", "12.00"),
        ("Brot — 12,–", "12.00"),
        ("Torte — 1.234,50 €", "1234.50"),
        ("Brot 3,50 €", "3.50"),
        ("Brot — 3,50 €", "3.50"),
        ("Brot ........ 3,50", "3.50"),
        ("Brot: 3,50", "3.50"),
        ("Brot\t3,50", "3.50"),
        ("Brot; 3,50", "3.50"),
        ("Brot | 3,50", "3.50"),
        ("Brot - 3,50", "3.50"),
        ("Brot – 3,50", "3.50"),
    ],
)
def test_prices_and_separators(raw, price):
    line = one(raw)
    assert line.name == "Brot" or line.name == "Torte"
    assert line.price == Decimal(price) and not line.errors


def test_number_in_name_stays_in_name():
    line = one("Pizza 4 Käse — 9,50")
    assert line.name == "Pizza 4 Käse" and line.price == Decimal("9.50")
    line = one("1 kg Kartoffeln — 2,99")
    assert line.name == "1 kg Kartoffeln"
    line = one("Roggenbrot 750 g 3,50 €")
    assert line.name == "Roggenbrot 750 g" and line.price == Decimal("3.50")


def test_bullets_and_numbering_are_stripped():
    text = "• Brot — 3,50\n- Brötchen — 0,60\n* Kuchen — 2\n1. Torte — 30\n2) Strudel — 3"
    names = [x.name for x in parse_lines(text, "waren", today=TODAY).lines]
    assert names == ["Brot", "Brötchen", "Kuchen", "Torte", "Strudel"]


def test_ab_and_ranges_and_second_price_and_unit():
    line = one("Haarschnitt — ab 9 — 30 Min", "termine")
    assert line.price == Decimal("9") and line.price_from and not line.errors
    line = one("Färben — 9–12 € — 60 Min", "termine")
    assert line.price == Decimal("9") and line.price_from and line.warnings
    line = one("Färben — 9 bis 12 — 60 Min", "termine")
    assert line.price == Decimal("9") and line.warnings
    line = one("Bauernbrot — 3,90 € / 5,90 €")
    assert line.price == Decimal("3.90") and line.warnings
    line = one("Käse — 3,50 €/kg")
    assert line.price == Decimal("3.50") and line.warnings
    line = one("Käse — 2,10 € pro 100 g")
    assert line.price == Decimal("2.10") and line.warnings
    line = one("Käse — CHF 12")
    assert line.price == Decimal("12") and line.warnings


@pytest.mark.parametrize("raw", ["Brot — 1,234", "Brot — 1.500", "Brot — -3", "Brot — 2000000"])
def test_bad_prices_are_errors(raw):
    line = one(raw)
    assert line.errors


def test_missing_and_free_prices_depend_on_kind():
    assert one("Brot").errors
    assert one("Brot — auf Anfrage").errors
    assert one("Brot — gratis").errors  # товар за 0 € — ошибка
    assert one("Brot — 0,00").errors
    assert not one("Dachreparatur", "anfragen").errors
    assert one("Dachreparatur — auf Anfrage", "anfragen").price is None
    line = one("Lesung — gratis — 20.12.2026 19:00", "tickets")
    assert line.price == Decimal("0") and not line.errors


@pytest.mark.parametrize(
    ("raw", "minutes"),
    [
        ("Schnitt — 30 Min — 25", 30),
        ("Schnitt — 30 min. — 25", 30),
        ("Schnitt — 45' — 25", 45),
        ("Schnitt — 1 Std — 25", 60),
        ("Schnitt — 1,5 h — 25", 90),
        ("Schnitt — 1:30 h — 25", 90),
        ("Schnitt — 90 Minuten — 25", 90),
        ("Schnitt 30 Min 25 €", 30),
    ],
)
def test_duration(raw, minutes):
    line = one(raw, "termine")
    assert line.duration_min == minutes and line.price == Decimal("25"), line
    assert line.name == "Schnitt" and not line.errors


def test_termine_without_duration_is_error():
    assert one("Schnitt — 25 €", "termine").errors


def test_guests():
    assert one("Doppelzimmer — 2 Pers. — 89", "zimmer").guests == 2
    assert one("Suite — für 4 — 189", "zimmer").guests == 4
    line = one("DZ Garten — 89", "zimmer")
    assert line.guests == 2 and not line.warnings
    assert one("EZ — 69", "zimmer").guests == 1
    line = one("Zimmer Nord — 79", "zimmer")
    assert line.guests == 2 and line.warnings and not line.errors


def test_dates():
    line = one("Konzert — 20.07.2027 19:30 — 25", "tickets")
    assert line.starts_at.replace(tzinfo=None) == datetime(2027, 7, 20, 19, 30)
    line = one("Konzert — 20.07. 19 Uhr — 25", "tickets")
    assert line.starts_at.year == 2027 and line.starts_at.hour == 19
    line = one("Konzert — 12.12. — 25", "tickets")
    assert line.starts_at.year == 2026 and line.starts_at.hour == 19 and line.warnings
    assert one("Konzert — 20.7.26 — 25", "tickets").errors  # в прошлом
    assert one("Konzert — 25", "tickets").errors  # нет даты


def test_names_limits_and_duplicates():
    long = "X" * 130
    line = one(f"{long} — 3")
    assert len(line.name) == 120 and line.warnings
    assert one("— 3,50").errors
    lines = parse_lines("Brot — 3\nbrot — 4\n\n\nKuchen — 2", "waren", today=TODAY).lines
    assert [bool(x.errors) for x in lines] == [False, True, False]


def test_too_many_lines_are_cut_with_note():
    text = "\n".join(f"Artikel {i} — 1" for i in range(60))
    result = parse_lines(text, "waren", today=TODAY)
    assert len(result.lines) == offer_lines.MAX_LINES and result.notes


def test_too_long_text_is_refused():
    with pytest.raises(offer_lines.OfferTextTooLong):
        parse_lines("x" * (offer_lines.MAX_TEXT + 1), "waren", today=TODAY)


def test_examples_are_marked():
    lines = parse_lines(
        "Brot — 3,50\nKuchen — 2", "waren", examples=frozenset({"Brot — 3,50"}), today=TODAY
    ).lines
    assert [x.example for x in lines] == [True, False]


def test_validate_row_is_the_same_parser():
    parsed = one("Schnitt — 45 Min — ab 25 €", "termine")
    row = validate_row({"name": "Schnitt", "duration": "45 Min", "price": "ab 25 €"}, "termine")
    assert (row.name, row.price, row.price_from, row.duration_min) == (
        parsed.name,
        parsed.price,
        parsed.price_from,
        parsed.duration_min,
    )
    assert validate_row({"name": "Brot", "price": "-3"}, "waren").errors
    # Имя из таблицы берётся как есть: разделители в нём — часть имени.
    assert validate_row({"name": "Brot — Spezial", "price": "3"}, "waren").name == (
        "Brot — Spezial"
    )


def test_unknown_kind_is_refused():
    with pytest.raises(ValueError):
        parse_lines("Brot — 3", "tisch", today=TODAY)


def test_no_homemade_money_parsing():
    src = Path(offer_lines.__file__).read_text(encoding="utf-8")
    assert "float(" not in src and 'replace(",", ".")' not in src


def test_unmarked_extra_numbers_never_become_the_price():
    line = one("Cappuccino — 0,2 l — 3,40 €")
    assert line.price == Decimal("3.40") and not line.errors
    assert one("Pizza — 12 Zoll — 9,50").errors  # два числа без «€» — спросить
    assert one("Suite — 45 m² — 120 €", "zimmer").price == Decimal("120")
    line = one("Haarschnitt — 30–45 Min — 26 €", "termine")
    assert line.errors and line.duration_min is None


def test_date_without_year_rolling_over_warns():
    line = one("Konzert — 20.07. 19 Uhr — 25", "tickets")
    assert any("2027" in w for w in line.warnings)


def test_validate_row_ignores_fields_of_other_kinds():
    line = validate_row({"name": "Brot", "price": "3", "duration": "999"}, "waren")
    assert line.price == Decimal("3") and not line.errors
    line = validate_row(
        {"name": "S", "price": "25", "duration": "30", "starts_at": "20.07.2026 19:00"},
        "termine",
    )
    assert line.price == Decimal("25") and not line.errors


def test_long_lines_are_not_regex_parsed():
    import time

    start = time.monotonic()
    text = "a " + "1" * 7990
    line = one(text)
    spaces = parse_lines("a" + " " * 7990 + "x", "waren", today=TODAY).lines[0]
    assert line.errors and spaces.errors
    assert time.monotonic() - start < 0.5
