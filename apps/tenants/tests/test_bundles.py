"""DS-3c (Fokus): сборки (Startpakete) — Look + виды вывода одним кликом.
Адверсариальный цикл по образцу test_looks: каждая сборка × каждый архетип
применяется идемпотентно, оси материализованы, чужие ключи целы."""

import pytest

from apps.tenants import siteconfig, sitetemplates
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ARCHETYPES = [k for k, _ in Tenant.BUSINESS_TYPES if k != "other"]


def test_registry_valid():
    for b in sitetemplates.BUNDLES:
        assert sitetemplates.get_look_family(b["look"]) is not None, b["key"]
        styles = b["config"].get("section_styles", {})
        for sec, st in styles.items():
            assert st in siteconfig.SECTION_STYLES.get(sec, ()), (b["key"], sec, st)
        preset = (b["config"].get("catalog_layout") or {}).get("preset")
        if preset:
            assert (
                preset in siteconfig.LAYOUT_PRESETS
                or preset in siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"]
            )


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_every_bundle_applies_and_is_idempotent(business_type):
    for b in sitetemplates.BUNDLES:
        tenant = TenantFactory(
            business_type=business_type,
            site_config={"notify": {"customer": {"email": True}}, "board": {"order": ["done"]}},
        )
        assert sitetemplates.apply_bundle(tenant, b["key"]) is True
        cfg = tenant.site_config
        assert siteconfig.normalize(cfg) == cfg  # normalize идемпотентен
        if b["config"].get("hero_style"):
            assert cfg["hero_style"] == b["config"]["hero_style"]
        if b["config"].get("nav_cta"):
            assert cfg["nav"]["cta"] is True
        for sec, st in b["config"].get("section_styles", {}).items():
            row = next(r for r in cfg["sections"] if r["key"] == sec)
            assert row["style"] == st
        for sec in b["config"].get("sections_on", ()):
            assert next(r for r in cfg["sections"] if r["key"] == sec)["enabled"] is True
        # чужие ключи целы (W6-инвариант через apply_look-базу)
        assert cfg["notify"] == {"customer": {"email": True}}
        assert cfg["board"]["order"] == ["done"]
        # повторное применение — идемпотентно
        before = dict(cfg)
        sitetemplates.apply_bundle(tenant, b["key"])
        assert tenant.site_config == before


def test_unknown_bundle_false():
    tenant = TenantFactory(business_type="catering")
    assert sitetemplates.apply_bundle(tenant, "junk") is False


def test_bundles_for_recommended_first():
    keys = [b["key"] for b in sitetemplates.bundles_for("catering")]
    assert "fokus" in keys
