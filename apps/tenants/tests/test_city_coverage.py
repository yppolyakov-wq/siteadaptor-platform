"""DCC: покрытие каталога города Золингена демо-бизнесами (план
docs/demo-city-coverage-plan-2026-10-15.md §6).

Считаем по ВСЕМ китам Золингена (рукописные T-8.22 + спеки DCC): каждый раздел
справочника закрыт минимум шестью бизнесами, каждая категория достижима хотя бы одним
листингом, ни один район не пустует."""

from collections import Counter

from apps.core import city_categories as cc
from apps.core import districts
from apps.tenants import demo_kits
from apps.tenants.demo_city import businesses
from apps.tenants.demo_city.validate import predicted_categories

MIN_PER_SECTION = 6
MIN_DISTRICT_SHARE = 0.12


def _legacy_kits():
    return [k for k in demo_kits.KITS.values() if k.city == "Solingen" and not k.origin]


def _legacy_business_category(kit) -> str:
    return cc.normalize_category(kit.business_city_category) or cc.suggest_for_business_type(
        kit.business_type
    )


def test_every_section_has_at_least_six_businesses():
    per_section = Counter()
    for biz in businesses():
        per_section[cc.category(biz.category).section] += 1
    for kit in _legacy_kits():
        per_section[cc.category(_legacy_business_category(kit)).section] += 1
    thin = {s.key: per_section[s.key] for s in cc.SECTIONS if per_section[s.key] < MIN_PER_SECTION}
    assert not thin, thin


def test_every_city_category_is_reachable():
    covered = set()
    for biz in businesses():
        covered |= predicted_categories(biz)
    for kit in _legacy_kits():
        covered.add(_legacy_business_category(kit))
        covered |= set(kit.city_categories.values())
    missing = {c.key for c in cc.CATEGORIES} - covered
    assert not missing, sorted(missing)


def test_districts_are_evenly_populated():
    per_district = Counter(biz.district for biz in businesses())
    for kit in _legacy_kits():
        per_district[kit.district] += 1
    total = sum(per_district.values())
    for d in districts.districts_for("Solingen"):
        share = per_district[d.slug] / total
        assert share >= MIN_DISTRICT_SHARE, (d.slug, per_district[d.slug], total)


def test_dcc_specs_count():
    # 79 бизнесов плана §2: 15 разделов × 5 + Essen +3 + Freizeit +1.
    assert len(list(businesses())) == 79
