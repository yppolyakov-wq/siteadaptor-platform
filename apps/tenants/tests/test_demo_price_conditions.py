"""В2/В4-3: акция «на вторую штуку / n für m / ab n Stück» в демо обязана нести условие
цены — иначе витрина и каталог города покажут цену ШТУКИ × (1−%), а это неправда (PAngV)."""

import re

import pytest

from apps.core import price_conditions
from apps.tenants import demo_kits
from apps.tenants.demo_city import builder, businesses

CONDITIONAL = re.compile(
    r"zweite[snr]?\b(?! Leben)|jede[snr]? zweite|\b\d+ für \d+\b|\bab \d+ (Stück|Teile)",
    re.IGNORECASE,
)


def _kit_promos():
    for kit in demo_kits.KITS.values():
        for spec in kit.promotions_spec or ():
            yield kit.key, spec


@pytest.mark.parametrize("key, spec", list(_kit_promos()), ids=lambda v: str(v)[:40])
def test_conditional_wording_requires_condition(key, spec):
    text = f"{spec.get('title', '')} {spec.get('desc', '')}"
    if CONDITIONAL.search(text):
        cond = price_conditions.normalize(spec.get("price_condition"))
        assert cond, f"{key}: «{spec['title']}» — нужен price_condition"
        if cond["kind"] in price_conditions.PERCENT_KINDS and cond["kind"] == "nth":
            assert spec.get("percent") or cond["note"], key
        assert not spec.get("new_price"), f"{key}: условие + фикс-цена несовместимы"
        assert not spec.get("compare_at"), f"{key}: «statt» у цены штуки было бы неправдой"


def test_city_specs_conditions_are_valid():
    for biz in businesses():
        for offer in biz.offers:
            if offer.cond:
                assert price_conditions.normalize(offer.cond), (biz.key, offer.title)
                assert builder._offer_spec(offer)["price_condition"] == offer.cond


def test_demo_carries_the_four_examples():
    titles = {spec["title"] for _k, spec in _kit_promos() if spec.get("price_condition")}
    for expected in (
        "Pizza-Abend: zweite Pizza −50 %",
        "Kabel-Dienstag: 2 für 1",
        "Zweitbrille −50 %",
        "Schleifwoche: zweites Messer gratis",
    ):
        assert expected in titles
