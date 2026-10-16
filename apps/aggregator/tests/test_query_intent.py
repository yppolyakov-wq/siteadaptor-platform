"""T-8.26 п.5a: разбор намерения запроса — правила без БД (план
docs/t8-26-5-query-intent-plan-2026-10-16.md). `today` передаётся явно."""

from datetime import date
from decimal import Decimal

import pytest

from apps.aggregator import query_intent as qi

WED = date(2026, 10, 14)  # среда


def _p(q, **kw):
    kw.setdefault("city", "Solingen")
    kw.setdefault("today", WED)
    return qi.parse(q, **kw)


def test_price_unter_100_euro():
    it = _p("Winterjacke unter 100 Euro")
    assert it.rest_q == "Winterjacke"
    assert it.delta == {"price_to": Decimal("100")}
    assert [c.key for c in it.chips] == ["preis_bis"]
    assert "100" in it.chips[0].label


@pytest.mark.parametrize("q", ["Brunch ab 10 Uhr", "Kurs bis 18 Uhr", "Tisch für 4"])
def test_times_and_counts_are_not_prices(q):
    assert _p(q).delta == {}


def test_ab_with_currency_is_price_from_and_range():
    assert _p("Massage ab 40 €").delta == {"price_from": Decimal("40")}
    assert _p("Jacke 50 - 120 euro").delta == {
        "price_from": Decimal("50"),
        "price_to": Decimal("120"),
    }
    assert _p("Menü bis 12,50€").delta == {"price_to": Decimal("12.50")}


def test_heute_geoeffnet_is_open_now_not_date():
    it = _p("Restaurant heute geöffnet")
    assert it.rest_q == "Restaurant" and it.delta == {"open_now": True}


def test_wochenende_and_heute_and_morgen():
    it = _p("Kinderaktivitäten am Wochenende")
    assert it.rest_q == "Kinderaktivitäten" and it.delta == {"date": "wochenende"}
    assert _p("Brunch heute").delta == {"date": "heute"}
    assert _p("Konzert morgen").delta == {"date": "2026-10-15"}


def test_weekday_next_occurrence_including_today():
    assert _p("Markt am Samstag").delta == {"date": "2026-10-17"}
    assert _p("Markt mittwoch").delta == {"date": "2026-10-14"}  # сегодня включительно


def test_district_reliable_forms_only():
    assert _p("Friseur in Solingen-Wald").delta == {"district": "wald"}
    assert _p("Friseur in Solingen-Wald").rest_q == "Friseur"
    assert _p("Ohligs Bäcker").delta == {"district": "ohligs-aufderhoehe-merscheid"}
    assert _p("Café in Gräfrath").delta == {"district": "graefrath"}
    assert _p("Wald Spaziergang").delta == {}  # голое многозначное слово — нет
    assert _p("Burgführung").delta == {}
    assert _p("Friseur in Solingen-Wald", city="").delta == {}  # без города — нет


def test_roh_ort_keeps_district_word_as_text():
    it = _p("Friseur in Solingen-Wald", roh=frozenset({"ort"}))
    assert it.delta == {} and "wald" in it.rest_q.lower()


def test_size_phrase_becomes_size_filter():
    # 5c: размер — настоящий фильтр (раньше — пилюля «noch nicht verfügbar» без delta)
    it = _p("Damenjacke Größe M")
    assert it.rest_q == "Damenjacke" and it.delta == {"size": "M"}
    assert [c.key for c in it.chips] == ["groesse"] and "M" in it.chips[0].label
    assert "noch nicht" not in it.chips[0].label
    assert _p("Schuhe Gr. 42").delta == {"size": "42"}


def test_tag_word_is_hint_not_filter():
    it = _p("Vegetarisches Mittagessen")
    assert it.delta == {} and it.rest_q == "Vegetarisches Mittagessen"
    assert it.hints == ("vegetarisch",)
    assert _p("veggie Pizza").hints == ("vegetarisch",)


def test_chip_removal_text_drops_only_its_phrase():
    it = _p("Jacke unter 100 € am Wochenende")
    by_key = {c.key: c for c in it.chips}
    assert by_key["preis_bis"].q_without == "Jacke am Wochenende"
    assert by_key["datum"].q_without == "Jacke unter 100 €"


def test_apply_respects_explicit_filters():
    from apps.aggregator.search import SearchFilters

    it = _p("Jacke unter 100 €")
    explicit = SearchFilters(price_to=Decimal("50"))
    q_eff, eff, chips = qi.apply(it, explicit)
    assert eff.price_to == Decimal("50") and q_eff == "Jacke" and chips == ()
    q_eff, eff, chips = qi.apply(it, SearchFilters())
    assert eff.price_to == Decimal("100") and [c.key for c in chips] == ["preis_bis"]
