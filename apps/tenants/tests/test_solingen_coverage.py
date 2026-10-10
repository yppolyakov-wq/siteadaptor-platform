"""T-8.22: демо Золингена покрывают все 15 разделов каталога города.

План — docs/t8-22-solingen-demo-coverage-plan-2026-10-10.md §2.
"""

from apps.core import city_categories as cc
from apps.core import districts
from apps.tenants import demo_kits

NEW_KITS = (
    "klingenwerk",
    "handy_doktor",
    "spielkiste",
    "pfotenglueck",
    "rad_und_tat",
    "wohnwerk",
    "feinkost_markt",
    "schuhhaus",
    "bergisch_fit",
    "lichtblick",
    "elektro_schmitz",
)


def _solingen_kits():
    return [kit for kit in demo_kits.KITS.values() if kit.city == "Solingen"]


def _sections_of(kit) -> set[str]:
    found = set()
    business = cc.normalize_category(kit.business_city_category) or cc.suggest_for_business_type(
        kit.business_type
    )
    found.add(cc.category(business).section)
    for key in kit.city_categories.values():
        found.add(cc.category(key).section)
    if kit.events:
        found.add(cc.category("events").section)
    if kit.stay_units:
        found.add(cc.category("hotels").section)
    return found


def test_every_section_has_a_solingen_business():
    covered = set().union(*(_sections_of(kit) for kit in _solingen_kits()))
    assert covered == {s.key for s in cc.SECTIONS}, {s.key for s in cc.SECTIONS} - covered


def test_new_kits_are_complete_city_businesses():
    for key in NEW_KITS:
        kit = demo_kits.KITS[key]
        assert kit.city == "Solingen", key
        assert districts.normalize("Solingen", kit.district) == kit.district, key
        assert kit.lat and kit.lng and kit.address and kit.opening_hours, key
        assert kit.profile != "aktionen", key  # товары/услуги выходят в каталог города
        assert cc.category(kit.business_city_category), key
        products = [p for cat in kit.categories for p in cat[2]]
        assert products or kit.services, key
        for cat in kit.categories:
            assert cc.category(kit.city_categories.get(cat[1], "")), (key, cat[1])
