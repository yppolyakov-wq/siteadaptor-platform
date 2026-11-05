"""AIS-M M-1a: слои модулей, один источник «Wie verkaufen Sie?», резерв ключа directions."""

from types import SimpleNamespace

import pytest

from apps.core import directions, modules, offer_batch
from apps.core.module_presets import LEGACY_DISABLED
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

TYPES = [k for k, _ in Tenant.BUSINESS_TYPES]


def test_every_module_has_exactly_one_layer():
    for spec in modules.REGISTRY:
        assert spec.layer in ("core", "base", "direction", "addon"), spec.key
        assert (spec.layer == "core") is spec.core, spec.key


def test_addons_point_to_real_directions():
    keys = {d.key for d in directions.REGISTRY} | {modules.ANY, modules.SELLING}
    for spec in modules.REGISTRY:
        if spec.layer == "addon":
            assert spec.addon_for and set(spec.addon_for) <= keys, spec.key
        else:
            assert not spec.addon_for, spec.key


def test_direction_layer_equals_direction_modules():
    in_layer = {s.key for s in modules.REGISTRY if s.layer == "direction"}
    in_directions = {m for d in directions.REGISTRY for m in d.modules}
    assert in_layer == in_directions


def test_base_modules_are_not_core():
    """Базовые модули под потолком пакета: core обходил бы его (§5.1 п.3)."""
    for spec in modules.REGISTRY:
        if spec.layer == "base":
            assert not spec.core, spec.key


@pytest.mark.parametrize("btype", TYPES)
def test_choices_for_is_the_wizard_source(btype):
    tenant = SimpleNamespace(business_type=btype)
    assert directions.choices_for(tenant) == offer_batch.direction_choices(tenant)
    keys = [d.key for d in directions.choices_for(tenant)]
    assert not ("tisch" in keys and "termine" in keys)


def test_normalize_keeps_directions_presence_minimal():
    got = siteconfig.normalize({"directions": {"termine": {"mode": "zeigen"}}})
    assert got["directions"] == {"termine": {"mode": "zeigen"}}
    dirty = siteconfig.normalize(
        {"directions": {"termine": {"mode": "x"}, "nope": {"mode": "zeigen"}, "waren": "s"}}
    )
    assert "directions" not in dirty
    assert "directions" not in siteconfig.normalize({})


@pytest.mark.parametrize("btype", TYPES)
def test_legacy_presets_cover_every_type(btype):
    """Снимок до смены пресетов — у каждого типа, только известные модули."""
    known = {s.key for s in modules.REGISTRY if not s.core}
    assert btype in LEGACY_DISABLED
    assert set(LEGACY_DISABLED[btype]) <= known
    assert list(LEGACY_DISABLED[btype]) == sorted(LEGACY_DISABLED[btype])
