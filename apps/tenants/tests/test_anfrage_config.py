"""AF-1: normalize_anfrage — presence-minimal конфиг событийных полей /anfrage/.

Замки класса golden: ключ «anfrage» НЕ материализуется на пустом/легаси конфиге
(иначе byte-parity golden-эталонов сломается — антипример jobs_vehicle)."""

from apps.tenants import siteconfig


def test_anfrage_absent_on_empty_config():
    assert "anfrage" not in siteconfig.normalize({})


def test_anfrage_junk_dropped():
    assert "anfrage" not in siteconfig.normalize({"anfrage": "kaputt"})
    assert "anfrage" not in siteconfig.normalize({"anfrage": {"fields": ["bogus"]}})
    assert "anfrage" not in siteconfig.normalize({"anfrage": {"event_types": ["Hochzeit"]}})


def test_anfrage_fields_canonical_order_and_whitelist():
    raw = {"anfrage": {"fields": ["event_type", "date", "junk", 7]}}
    assert siteconfig.normalize(raw)["anfrage"] == {"fields": ["date", "event_type"]}


def test_anfrage_event_types_cap_strip_and_len():
    types = [f"  Typ {i}  " for i in range(20)] + ["", 42, "x" * 200]
    out = siteconfig.normalize({"anfrage": {"fields": ["date"], "event_types": types}})
    got = out["anfrage"]["event_types"]
    assert len(got) == 12  # кап
    assert got[0] == "Typ 0"  # strip
    assert all(len(t) <= 60 for t in got)


def test_anfrage_idempotent():
    raw = {"anfrage": {"fields": ["guests", "date"], "event_types": ["Hochzeit"]}}
    once = siteconfig.normalize(raw)
    assert siteconfig.normalize(once)["anfrage"] == once["anfrage"]


def test_demo_kits_anfrage_presets_survive_normalize():
    """AF-1e: пресеты китов с Catering/Partyservice переживают normalize
    (dead-config prevention: опечатка в ките не должна молча гаснуть)."""
    from apps.tenants.demo_kits import KITS

    with_form = {key for key, kit in KITS.items() if kit.anfrage_form}
    assert {"restaurant", "pranasy", "bakery", "butcher"} <= with_form
    for key in with_form:
        out = siteconfig.normalize({"anfrage": KITS[key].anfrage_form})
        assert out["anfrage"]["fields"], key
        assert out["anfrage"]["event_types"], key
