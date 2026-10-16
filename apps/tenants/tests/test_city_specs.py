"""DCC: спеки демо-бизнесов Золингена — статические замки без БД (план §6).

Каждая спека обязана пройти валидатор (тип/категория/район/вымышленная улица/
координаты/телефон/цены/LMIV/PAngV), фото — либо свой кадр, либо тематический
плейсхолдер (никогда кадр соседа или чужих пространств `ol-`/`markt-`), один кадр —
не больше чем у одного бизнеса Золингена, переводы ≥ 95 % на четырёх локалях.
"""

import pytest

from apps.core import city_categories as cc
from apps.tenants import demo_images, demo_kits
from apps.tenants.demo_city import builder, businesses, photos, validate
from apps.tenants.demo_city.solingen import SECTIONS

BIZ = {b.key: b for b in businesses()}
SECTION_OF = {b.key: mod.SECTION for mod in SECTIONS for b in mod.BUSINESSES}


@pytest.mark.parametrize("key", sorted(BIZ))
def test_spec_is_valid(key):
    assert validate.validate(BIZ[key], section=SECTION_OF[key]) == []


def test_keys_subdomains_labels_phones_unique_across_all_kits():
    seen_sub, seen_label, seen_phone = {}, {}, {}
    for kit in demo_kits.KITS.values():
        sub = kit.subdomain or f"{kit.key}-demo"
        assert sub not in seen_sub, (sub, kit.key, seen_sub.get(sub))
        seen_sub[sub] = kit.key
        assert kit.label not in seen_label, (kit.label, kit.key)
        seen_label[kit.label] = kit.key
        if kit.phone:
            assert kit.phone not in seen_phone, (kit.phone, kit.key, seen_phone.get(kit.phone))
            seen_phone[kit.phone] = kit.key


@pytest.mark.parametrize("key", sorted(BIZ))
def test_builder_invariants(key):
    kit = demo_kits.KITS[key]
    assert kit.origin == builder.ORIGIN
    assert kit.subdomain.startswith("sg-")
    assert kit.city == "Solingen" and kit.address.endswith("Solingen")
    assert kit.opening_hours_text == builder.hours_text(kit.opening_hours)
    # меню выводит каждый наполненный модуль
    targets = {n["target"] for n in kit.menus["top"]["items"] if n["type"] == "archetype"}
    if kit.categories:
        assert "catalog" in targets
    if kit.services:
        assert "booking" in targets
    if kit.events:
        assert "events" in targets
    for cat in kit.categories:
        for p in cat[2]:
            assert p["sku"] and not p["sku"].startswith("SG_"), p["sku"]
    for spec in kit.promotions_spec:
        assert ("ends_in_days" in spec) or spec.get("no_end") or spec.get("ends_today")


def test_hours_text_format():
    assert builder.hours_text(builder.HOURS["laden"]) == "Mo–Fr 9:30–18:30 · Sa 10:00–14:00"
    assert builder.hours_text(builder.HOURS["gastro"]) == (
        "Mo–Fr 11:30–22:00 · Sa 12:00–23:00 · So 12:00–21:00"
    )


def _keywords(kit):
    from apps.tenants.management.commands.demo_photo_report import kit_keywords

    return [kw for kw, _where in kit_keywords(kit)]


@pytest.mark.parametrize("key", sorted(BIZ))
def test_photos_are_own_or_placeholder_never_borrowed(key):
    kit = demo_kits.KITS[key]
    for kw in _keywords(kit):
        status = photos.photo_status(kw)
        assert status != "borrowed", (key, kw, demo_images.photo_static_name(kw))
        assert not kw.startswith(("ol-", "markt-")), (key, kw)
        if status == "placeholder":
            assert demo_images._emoji_for(kw) not in ("✨", "🍽️"), (key, kw)


def test_no_photo_file_shared_by_two_solingen_businesses():
    """Кадр кита DCC не повторяется ни у одного другого бизнеса Золингена (две карточки с
    одним фото на портале). Рукописные киты T-8.22 между собой — вне замка (наследие)."""
    owners: dict[str, set[str]] = {}
    for kit in demo_kits.KITS.values():
        if kit.city != "Solingen":
            continue
        for kw in set(_keywords(kit)):
            name = demo_images.photo_static_name(kw)
            if name is not None:
                owners.setdefault(name, set()).add(kit.key)
    shared = {
        name: keys
        for name, keys in owners.items()
        if len(keys) > 1 and any(demo_kits.KITS[k].origin for k in keys)
    }
    assert not shared, shared


def test_addresses_and_coordinates_unique_in_city():
    """Ревью DCC: два бизнеса в одном доме / одной точке карты — дефект данных
    (на карте портала они слипаются, в адресах демо выглядят подделкой)."""
    seen_addr, seen_geo = {}, {}
    for biz in businesses():
        addr = (biz.district, biz.street, biz.house)
        geo = (biz.lat, biz.lng)
        assert addr not in seen_addr, (biz.key, seen_addr[addr], addr)
        assert geo not in seen_geo, (biz.key, seen_geo[geo], geo)
        seen_addr[addr] = biz.key
        seen_geo[geo] = biz.key


def test_predicted_categories_known():
    for biz in BIZ.values():
        for key in validate.predicted_categories(biz):
            assert cc.category(key), (biz.key, key)


def test_city_i18n_coverage():
    """Строк без пути перевода — 0; покрытие en/ru/uk/tr ≥ 95 % у каждого кита."""
    from apps.tenants.demo_i18n_measure import measure

    rows, _routed, gap, _skip = measure(keys=sorted(BIZ))
    assert not gap, sorted(gap)[:10]
    for row in rows:
        for loc in ("en", "ru", "uk", "tr"):
            assert row[loc] >= row["routed"] * 0.95, (row["kit"], loc, row[loc], row["routed"])
