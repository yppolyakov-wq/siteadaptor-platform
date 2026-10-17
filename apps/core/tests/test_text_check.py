"""D2a-1 (T-8.10e): замки движка «Text-Check» — детерминированные правила без ИИ.

План — docs/d2-ai-text-check-plan-2026-10-17.md §3, §7. Движок ничего не пишет и не
блокирует: он возвращает подсказки. Каждое правило обязано иметь пример «срабатывает»
и пример «молчит» (замок полноты реестра)."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.core import text_check as tc

TODAY = date(2026, 10, 17)
BERLIN = ZoneInfo("Europe/Berlin")


def _end(days: int) -> datetime:
    return datetime(2026, 10, 17, 18, 0, tzinfo=BERLIN) + timedelta(days=days)


def inp(title="", description="", **kw) -> tc.CheckInput:
    texts = {}
    if title:
        texts["title"] = {"de": title}
    if description:
        texts["description"] = {"de": description}
    kw.setdefault("today", TODAY)
    return tc.CheckInput(texts=texts, **kw)


def codes(findings) -> set[str]:
    return {f.code for f in findings}


# (code, срабатывает, молчит) — по паре на КАЖДОЕ правило реестра.
EXAMPLES = {
    "statt_ohne_referenz": (
        inp("Kaffee statt 4,99 € jetzt 2,99 €", new_price=Decimal("2.99")),
        inp(
            "Kaffee statt 4,99 € jetzt 2,99 €",
            new_price=Decimal("2.99"),
            old_price=Decimal("4.99"),
            ends_at=_end(3),
        ),
    ),
    "preis_widerspruch": (
        inp("Brot für 2,49 €", new_price=Decimal("3.49")),
        inp("Brot für 3,49 €", new_price=Decimal("3.49")),
    ),
    "rabatt_unplausibel": (
        inp(
            "Jacke",
            new_price=Decimal("10"),
            old_price=Decimal("100"),
            ends_at=_end(3),
        ),
        inp(
            "Jacke",
            new_price=Decimal("70"),
            old_price=Decimal("100"),
            ends_at=_end(3),
        ),
    ),
    "streich_ohne_ende": (
        inp("Jacke", new_price=Decimal("70"), old_price=Decimal("100")),
        inp("Jacke", new_price=Decimal("70"), old_price=Decimal("100"), ends_at=_end(3)),
    ),
    "gratis_mit_preis": (
        inp("Gratis Kaffee", new_price=Decimal("2.50")),
        inp("Kaffee mit kostenloser Lieferung", new_price=Decimal("2.50")),
    ),
    "dringlichkeit_heute": (
        inp("Nur heute: Brezeln", ends_at=_end(6)),
        inp("Nur heute: Brezeln", ends_at=_end(0)),
    ),
    "dringlichkeit_menge": (
        inp("Nur noch 5 Stück!", quantity=20),
        inp("Nur noch 5 Stück!", quantity=5),
    ),
    "alleinstellung": (
        inp("Der beste Kaffee der Stadt"),
        inp("Guter Kaffee aus der Stadt"),
    ),
    "gesundheit": (
        inp("Ingwershot stärkt das Immunsystem", is_food=True),
        inp("Ingwershot mit Zitrone", is_food=True),
    ),
    "bio_claim": (
        inp("Bio-Äpfel aus dem Umland"),
        inp("Äpfel aus dem Umland"),
    ),
    "diaet_widerspruch": (
        inp("Veganer Kuchen", has_product=True, allergens=frozenset({"milch"})),
        inp("Veganer Kuchen", has_product=True, allergens=frozenset({"gluten"})),
    ),
    "allergene_fehlen": (
        inp("Kuchen", is_food=True, has_product=True),
        inp("Kuchen", is_food=True, has_product=True, allergens=frozenset({"gluten"})),
    ),
    "grundpreis_fehlt": (
        inp("Kaffee 500 g", new_price=Decimal("5.99")),
        inp("Kaffee 500 g", new_price=Decimal("5.99"), grundpreis_ok=True),
    ),
    "raeumung": (
        inp("Räumungsverkauf: alles muss raus"),
        inp("Herbstverkauf im Laden"),
    ),
    "mystery_verraten": (
        inp("Überraschung für 3 €", mystery=True),
        inp("Überraschungstüte", mystery=True),
    ),
    "kontakt_im_text": (
        inp("Bestellen unter www.example.de"),
        inp("Bestellen im Laden"),
    ),
    "grossbuchstaben": (
        inp("SUPER ANGEBOT FÜR ALLE KUNDEN"),
        inp("Super Angebot für alle Kunden"),
    ),
    "garantie": (
        inp("Garantiert frisch"),
        inp("Täglich frisch"),
    ),
}


def test_every_rule_has_an_example():
    owner_rules = {r.code for r in tc.RULES if "owner" in r.scopes}
    assert owner_rules == set(EXAMPLES), "у каждого правила — пара примеров"


@pytest.mark.parametrize("code", sorted(EXAMPLES))
def test_each_rule_fires_on_its_example_and_not_on_clean_text(code):
    fires, silent = EXAMPLES[code]
    assert code in codes(tc.run(fires)), code
    assert code not in codes(tc.run(silent)), code


def test_statt_without_old_price_is_high():
    (f,) = [
        x for x in tc.run(inp("statt 4,99 €", new_price=Decimal("2"))) if x.code.startswith("statt")
    ]
    assert f.severity == "high"
    assert "statt" in f.quote.lower()


@pytest.mark.parametrize(
    "text,new,old,percent,fires",
    [
        ("Brot für 1.299,00 €", Decimal("1299"), None, None, False),
        ("Brot für 1.299,00 €", Decimal("1199"), None, None, True),
        ("Jetzt 3,49 € statt 4,99 €", Decimal("3.49"), Decimal("4.99"), None, False),
        ("−30 % auf alles", Decimal("7"), Decimal("10"), None, False),
        ("−50 % auf alles", Decimal("7"), Decimal("10"), None, True),
        ("−20 % auf alles", None, None, 20, False),
        ("Grundpreis 1,20 €/kg", Decimal("2.40"), None, None, False),
        ("Kaffee 2,99 €", None, None, None, False),  # нет полей — сравнивать не с чем
    ],
)
def test_price_in_text_must_match_fields(text, new, old, percent, fires):
    found = tc.run(inp(text, new_price=new, old_price=old, percent=percent, ends_at=_end(3)))
    assert ("preis_widerspruch" in codes(found)) is fires


def test_price_condition_x_for_y_silences_price_and_gratis_rules():
    cond = {"kind": "x_for_y", "n": 2, "pay": 1, "note": {}}
    found = tc.run(inp("2 für 1 – das zweite gratis", new_price=Decimal("3"), price_condition=cond))
    assert not codes(found) & {"preis_widerspruch", "gratis_mit_preis"}


def test_nur_heute_without_end_fires():
    assert "dringlichkeit_heute" in codes(tc.run(inp("Nur heute!")))


def test_nur_heute_suggestion_uses_date_from_field_only():
    (f,) = [
        x
        for x in tc.run(inp("Nur heute Brezeln", ends_at=_end(6)))
        if x.code == "dringlichkeit_heute"
    ]
    assert f.suggestion is not None and "23.10." in f.suggestion


def test_nur_heute_respects_local_day_boundary():
    late = datetime(2026, 10, 17, 23, 30, tzinfo=BERLIN)  # 21:30 UTC — всё ещё сегодня
    assert "dringlichkeit_heute" not in codes(tc.run(inp("Nur heute", ends_at=late)))


def test_glutenfrei_vs_gluten():
    found = tc.run(inp("Glutenfreies Brot", has_product=True, allergens=frozenset({"gluten"})))
    assert "diaet_widerspruch" in codes(found)


def test_gesundheit_is_high_only_for_food():
    food = [f for f in tc.run(inp("Detox-Tee", is_food=True)) if f.code == "gesundheit"]
    other = [f for f in tc.run(inp("Detox-Tee", is_food=False)) if f.code == "gesundheit"]
    assert food[0].severity == "high" and other[0].severity == "medium"


def test_grundpreis_missing_when_product_has_unit():
    found = tc.run(
        inp(
            "Kaffee",
            new_price=Decimal("5"),
            has_product=True,
            product_unit="g",
            grundpreis_ok=False,
        )
    )
    assert "grundpreis_fehlt" in codes(found)


def test_bio_claim_silent_when_owner_declared_bio_diet():
    found = tc.run(inp("Bio-Äpfel", has_product=True, diets=frozenset({"bio"})))
    assert "bio_claim" not in codes(found)


def test_non_german_locale_runs_only_language_agnostic_rules():
    data = tc.CheckInput(
        texts={"title": {"en": "Best coffee, only today!!! www.example.com"}},
        today=TODAY,
        ends_at=_end(6),
    )
    found = tc.run(data)
    assert "kontakt_im_text" in codes(found)
    assert not codes(found) & {"alleinstellung", "dringlichkeit_heute"}


def test_german_rules_do_not_fire_on_other_locale_with_german_words():
    data = tc.CheckInput(texts={"title": {"ru": "beste"}}, today=TODAY)
    assert "alleinstellung" not in codes(tc.run(data))


def test_catalog_scope_skips_owner_only_rules():
    found = tc.run(inp("Der beste Kaffee, garantiert"), scope="catalog")
    assert not codes(found) & {"alleinstellung", "garantie"}


def test_broken_rule_is_skipped_not_raised(monkeypatch):
    def boom(*a, **k):
        raise ValueError("boom")

    broken = tc.Rule("kaputt", "low", boom, message="x", norm="x")
    monkeypatch.setattr(tc, "RULES", (broken, *tc.RULES))
    found = tc.run(inp("Der beste Kaffee"))
    assert "alleinstellung" in codes(found) and "kaputt" not in codes(found)


def test_findings_deduplicated_and_sorted_by_severity():
    found = tc.run(
        inp(
            "Der beste Kaffee – der beste! Garantiert. Gratis Keks",
            description="Der beste Kaffee",
            new_price=Decimal("2"),
        )
    )
    order = [tc.SEVERITY_ORDER[f.severity] for f in found]
    assert order == sorted(order)
    keys = [(f.code, f.field, f.locale, f.quote.casefold()) for f in found]
    assert len(keys) == len(set(keys))


def test_suggestions_of_rules_contain_no_number_not_in_fields():
    data = inp(
        "Nur heute: der beste Kaffee, gratis Keks, nur noch 3 Stück",
        new_price=Decimal("2"),
        ends_at=_end(6),
        quantity=10,
    )
    for f in tc.run(data):
        if f.suggestion:
            for num in tc.NUMBER_RE.findall(f.suggestion):
                assert num in "23.10.", (f.code, f.suggestion)


def test_messages_are_lazy_translatable():
    for rule in tc.RULES:
        assert str(rule.message), rule.code
        assert rule.norm, rule.code


def test_ai_draft_regex_reexports_unchanged():
    from apps.promotions import ai_draft

    assert ai_draft._PRICE_RE is tc.PRICE_RE
    assert ai_draft._DISCOUNT_RE is tc.DISCOUNT_RE
    assert ai_draft._CONTACT_RE is tc.CONTACT_RE
    assert ai_draft._CLAIM_RE is tc.CLAIM_RE
    assert ai_draft.CLAIM_STEMS is tc.CLAIM_STEMS
    assert ai_draft.DISCOUNT_STEMS is tc.DISCOUNT_STEMS


def test_regex_linear_on_long_input():
    hostile = ("1 " * 5000) + ("a" * 5000) + ("!" * 5000) + ("statt " * 1000)
    started = time.perf_counter()
    tc.run(inp(hostile, description=hostile, new_price=Decimal("1")))
    assert time.perf_counter() - started < 1.0


def test_garbage_input_does_not_raise():
    data = tc.CheckInput(texts={"title": {"de": None}, "x": "nope"}, today=TODAY)  # type: ignore[dict-item]
    assert tc.run(data) == []


# --- регрессии ревью D2a-1: обычные фразы объявлений не должны давать подсказок ---------


@pytest.mark.parametrize(
    "text,code",
    [
        ("Jetzt nur noch 1,99 €", "dringlichkeit_menge"),
        ("Nur noch 5 € für das Brot", "dringlichkeit_menge"),
        ("Nur noch 2 Tage!", "dringlichkeit_menge"),
        ("Lieferung kostenlos", "gratis_mit_preis"),
        ("Parken kostenlos, Versand gratis", "gratis_mit_preis"),
        ("Kostenlose Stornierung und kostenlose Abholung", "gratis_mit_preis"),
        ("Kostenlose Lieferung ab 20 €", "preis_widerspruch"),
        ("Dazu ein 10 € Gutschein", "preis_widerspruch"),
        ("Milch 3,5 % Fett", "preis_widerspruch"),
        ("Preise inkl. 7 % MwSt", "preis_widerspruch"),
        ("Pfand 0,25 €", "preis_widerspruch"),
        ("Vorher anrufen, 10 € Gutschein", "statt_ohne_referenz"),
        ("Wochenmarkt statt Supermarkt: Brot 3 €", "statt_ohne_referenz"),
        ("Brotdose mit abnehmbarem Deckel", "gesundheit"),
        ("Kontrolle durch das Gesundheitsamt", "gesundheit"),
        ("Geöffnet Mo-Fr 9-12 / 14-18 Uhr", "kontakt_im_text"),
    ],
)
def test_common_offer_phrases_do_not_fire(text, code):
    data = inp(
        text, new_price=Decimal("2.99"), percent=30, quantity=10, ends_at=_end(3), is_food=True
    )
    assert code not in codes(tc.run(data)), text


def test_stock_rule_still_fires_with_stock_noun():
    assert "dringlichkeit_menge" in codes(tc.run(inp("Nur noch 3 Stück", quantity=12)))


def test_statt_still_fires_on_direct_amount_forms():
    for text in ("statt bisher 4,99 €", "UVP: 49 €", "Regulär 5 €"):
        assert "statt_ohne_referenz" in codes(tc.run(inp(text, new_price=Decimal("2")))), text


def test_lactose_free_milk_is_not_a_diet_conflict():
    data = inp("Laktosefreie Milch", has_product=True, allergens=frozenset({"milch"}))
    assert "diaet_widerspruch" not in codes(tc.run(data))


def test_health_still_fires_on_real_claims():
    for text in ("Hilft beim Abnehmen", "Stärkt die Immunabwehr", "Gesunde Snacks"):
        assert "gesundheit" in codes(tc.run(inp(text, is_food=True))), text


def test_midnight_end_counts_as_previous_day():
    midnight = datetime(2026, 10, 18, 0, 0, tzinfo=BERLIN)
    assert "dringlichkeit_heute" not in codes(tc.run(inp("Nur heute", ends_at=midnight)))


def test_real_phone_number_still_fires():
    assert "kontakt_im_text" in codes(tc.run(inp("Bestellen: 0212 1234567")))


def test_input_shape_is_capped():
    texts = {f"f{i}": {f"de{j}": "Nur heute! " * 50 for j in range(50)} for i in range(50)}
    data = tc.CheckInput(texts=texts, today=TODAY, ends_at=_end(6))
    started = time.perf_counter()
    found = tc.run(data)
    assert time.perf_counter() - started < 1.0
    assert len(found) <= tc.MAX_FINDINGS


def test_hits_per_rule_and_text_are_capped():
    data = inp("1 % " * 400, mystery=True)
    mystery = [f for f in tc.run(data) if f.code == "mystery_verraten"]
    assert len(mystery) <= tc.MAX_HITS


def test_odd_keys_are_ignored():
    data = tc.CheckInput(
        texts={"<b>x</b>" * 10: {"de": "Nur heute"}, "title": {"x" * 50: "Nur heute"}}, today=TODAY
    )
    assert tc.run(data) == []


def test_quote_is_truncated():
    data = inp("Bestellen unter https://example.de/" + "a" * 500)
    (f,) = [x for x in tc.run(data) if x.code == "kontakt_im_text"]
    assert len(f.quote) <= tc.QUOTE_MAX


def test_findings_are_json_serialisable_via_str():
    import json

    found = tc.run(inp("Gratis Kaffee nur heute", new_price=Decimal("2"), ends_at=_end(5)))
    json.dumps([f.as_dict() for f in found])
