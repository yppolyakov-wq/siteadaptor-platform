"""FB-30.11: ступени веса, зоны курьера и пункты самовывоза вводятся отдельными полями
(«bis kg» и «Preis €», кнопка «weitere Zeile»), а не строками «a | b» в текстовом поле."""

import pathlib

from apps.orders import shipping_admin, shipping_views

CARRIER = {"carrier": "dhl", "pricing": "weight"}


def _tiers(**fields):
    post = {**CARRIER, "weight_tiers_present": "1", **fields}
    return shipping_admin.parse(post, "carrier")


def test_weight_tiers_come_from_separate_fields():
    p = _tiers(tier_kg_0="3", tier_fee_0="5,90", tier_kg_1="5", tier_fee_1="10", tier_kg_4="31,5",
               tier_fee_4="16,90")  # fmt: skip
    assert not p.errors
    assert p.values["weight_tiers"] == [
        {"max_g": 3000, "fee_cents": 590},
        {"max_g": 5000, "fee_cents": 1000},
        {"max_g": 31500, "fee_cents": 1690},
    ]


def test_half_filled_or_broken_row_is_an_error_not_a_free_tier():
    for fields in ({"tier_kg_0": "3"}, {"tier_fee_0": "5"}, {"tier_kg_0": "3", "tier_fee_0": "x"}):
        p = _tiers(**fields)
        assert p.errors and p.values["weight_tiers"] == [], fields


def test_old_text_field_is_still_accepted():
    p = shipping_admin.parse({**CARRIER, "weight_tiers": "2 | 4,99\n5 | 6,99"}, "carrier")
    assert not p.errors and [t["max_g"] for t in p.values["weight_tiers"]] == [2000, 5000]


def test_without_the_sentinel_the_row_fields_are_ignored():
    p = shipping_admin.parse({**CARRIER, "weight_tiers": "2 | 4,99", "tier_kg_0": "9",
                              "tier_fee_0": "1"}, "carrier")  # fmt: skip
    assert [t["max_g"] for t in p.values["weight_tiers"]] == [2000]


def test_zones_and_pickup_points_come_from_fields_too():
    post = {"zones_present": "1", "zone_plz_0": "42651, 42653", "zone_fee_0": "2,50",
            "zone_free_0": "30", "zone_plz_1": "40", "zone_min_1": "15"}  # fmt: skip
    p = shipping_admin.parse(post, "courier")
    assert not p.errors
    assert p.values["zones"] == [
        {"plz": "42651, 42653", "fee_cents": 250, "free_cents": 3000},
        {"plz": "40", "min_cents": 1500},
    ]
    p = shipping_admin.parse({"zones_present": "1", "zone_fee_0": "2,50"}, "courier")
    assert p.errors, "цена без почтового индекса — ошибка, а не молча пропущенная строка"
    p = shipping_admin.parse(
        {"locations_present": "1", "loc_name_0": "Laden | Mitte", "loc_address_0": "Markt 1"},
        "pickup",
    )
    assert p.values["locations"] == [{"name": "Laden | Mitte", "address": "Markt 1"}]


def test_form_rows_show_saved_rows_with_the_range_start_and_spare_ones():
    rows = shipping_admin.form_rows({"weight_tiers": "3 | 5,90\n5 | 10,00"}, "weight_tiers")
    assert [(r["kg"], r["fee"], r["from"]) for r in rows[:2]] == [
        ("3", "5,90", "0"),
        ("5", "10,00", "3"),
    ]
    assert len(rows) == 2 + shipping_admin.SPARE_ROWS
    assert all(not r["kg"] and not r["fee"] for r in rows[2:])
    assert [r["i"] for r in rows] == list(range(len(rows)))


def test_form_rows_keep_what_was_typed_after_an_error():
    post = {"weight_tiers_present": "1", "tier_kg_0": "3", "tier_fee_0": "x", "tier_kg_2": "5"}
    rows = shipping_admin.form_rows(post, "weight_tiers")
    assert [(r["kg"], r["fee"]) for r in rows[:2]] == [("3", "x"), ("5", "")]


def test_form_template_uses_rows_and_the_sentinels():
    src = pathlib.Path("templates/tenant/_shipping_method_form.html").read_text()
    assert "<textarea" not in src
    for name in ("weight_tiers_present", "zones_present", "locations_present"):
        assert f'name="{name}"' in src
    assert "tier_kg_{{ r.i }}" in src and "tier_fee_{{ r.i }}" in src
    assert shipping_views.form_values  # читатель значений формы на месте


# --- ревью (security-reviewer) ---


def test_rows_beyond_the_limit_are_an_error_not_silently_dropped():
    fields = {}
    for i in range(21):
        fields[f"tier_kg_{i}"] = str(i + 1)
        fields[f"tier_fee_{i}"] = "1"
    fields["tier_kg_40"], fields["tier_fee_40"] = "99", "9"
    p = _tiers(**fields)
    assert any("20" in str(e) for e in p.errors)


def test_free_tier_is_legitimate_and_duplicates_are_an_error():
    p = _tiers(tier_kg_0="2", tier_fee_0="0", tier_kg_1="5", tier_fee_1="4")
    assert not p.errors and p.values["weight_tiers"][0]["fee_cents"] == 0
    p = _tiers(tier_kg_0="2", tier_fee_0="3", tier_kg_1="2", tier_fee_1="1")
    assert p.errors


def test_unsorted_rows_are_stored_sorted_and_odd_numbers_are_errors():
    p = _tiers(tier_kg_0="10", tier_fee_0="9", tier_kg_1="2", tier_fee_1="4")
    assert [t["max_g"] for t in p.values["weight_tiers"]] == [2000, 10000]
    for bad in ("inf", "1e400", "-1", "0"):
        assert _tiers(tier_kg_0=bad, tier_fee_0="1").errors, bad
    for bad in ("-1", "5000", "abc"):
        assert _tiers(tier_kg_0="2", tier_fee_0=bad).errors, bad


def test_form_without_any_rows_keeps_stored_rows():
    """W0: форма без строк (ни полей, ни текста) не стирает сохранённые ступени, зоны, пункты."""
    assert "weight_tiers" not in shipping_admin.parse(CARRIER, "carrier").values
    assert "zones" not in shipping_admin.parse({}, "courier").values
    assert "locations" not in shipping_admin.parse({}, "pickup").values
    empty = shipping_admin.parse({**CARRIER, "pricing": "flat", "weight_tiers_present": "1"},
                                 "carrier")  # fmt: skip
    assert empty.values["weight_tiers"] == [], "сентинел без строк — список очищен"


def test_pickup_point_with_an_address_but_no_name_is_an_error():
    p = shipping_admin.parse({"locations_present": "1", "loc_address_0": "Markt 1"}, "pickup")
    assert p.errors


def test_form_rows_from_a_real_querydict():
    from django.http import QueryDict

    post = QueryDict("weight_tiers_present=1&tier_kg_0=3&tier_fee_0=5,90&tier_kg_5=7")
    rows = shipping_admin.form_rows(post, "weight_tiers")
    assert [(r["kg"], r["fee"]) for r in rows[:2]] == [("3", "5,90"), ("7", "")]
