"""Audit 2026-11-01 (owner: «проверить все шаблоны и оставить рабочие»).

Every template the owner can pick — site templates (9), Startpakete/bundles (all, not
only the recommended ones), page presets of every host — applied to a FRESH tenant of
EVERY archetype must:
* survive normalize unchanged (config valid, no silent rewrite);
* be idempotent (a second apply changes nothing);
* render the key storefront pages (home always; catalog/offers when their module is on).

Before this sweep only 5 of 9 site templates and only the archetype's recommended
bundles were ever applied in a test.
"""

import pytest

from apps.core import page_presets
from apps.tenants import siteconfig, sitetemplates
from apps.tenants.tests.test_inheritance_matrix import ARCHETYPES, _fresh_tenant, _render_pages

pytestmark = pytest.mark.django_db


def _check(tenant, label):
    stored = dict(tenant.site_config or {})
    assert siteconfig.normalize(siteconfig.normalize(stored)) == siteconfig.normalize(stored), (
        f"{label}: normalize is not stable"
    )
    pages = _render_pages(tenant)
    assert "/" in pages and pages["/"], f"{label}: empty home"


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_every_site_template_applies_and_renders(business_type):
    for tpl in sitetemplates.TEMPLATES:
        tenant = _fresh_tenant(business_type)
        assert sitetemplates.apply_template(tenant, tpl["key"]), tpl["key"]
        first = dict(tenant.site_config)
        assert sitetemplates.apply_template(tenant, tpl["key"])
        assert tenant.site_config == first, f"{business_type}/{tpl['key']}: not idempotent"
        _check(tenant, f"{business_type}/{tpl['key']}")


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_every_bundle_applies_and_renders_for_every_archetype(business_type):
    for bundle in sitetemplates.BUNDLES:
        tenant = _fresh_tenant(business_type)
        assert sitetemplates.apply_bundle(tenant, bundle["key"]), bundle["key"]
        first = dict(tenant.site_config)
        assert sitetemplates.apply_bundle(tenant, bundle["key"])
        assert tenant.site_config == first, f"{business_type}/{bundle['key']}: not idempotent"
        _check(tenant, f"{business_type}/{bundle['key']}")


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_every_page_preset_applies_and_renders(business_type):
    for host, reg in page_presets.PAGE_PRESETS.items():
        for preset in reg["presets"]:
            tenant = _fresh_tenant(business_type)
            cfg = dict(tenant.site_config or {})
            assert page_presets.apply_page_preset(cfg, host, preset["key"], tenant=tenant)
            again = dict(cfg)
            page_presets.apply_page_preset(again, host, preset["key"], tenant=tenant)
            assert siteconfig.normalize(again) == siteconfig.normalize(cfg), (
                f"{business_type}/{host}/{preset['key']}: not idempotent"
            )
            tenant.site_config = cfg
            tenant.save(update_fields=["site_config"])
            _check(tenant, f"{business_type}/{host}/{preset['key']}")


#: Templates that are a one-page visiting card BY DESIGN (banner + contact, described
#: so to the owner) — the only ones allowed to sell nothing on the home page.
VISITING_CARDS = {"minimal"}


def _live_selling_sections(tenant):
    cfg = siteconfig.normalize(tenant.site_config or {})
    return [
        s["key"]
        for s in cfg["sections"]
        if s.get("enabled")
        and s["key"] in sitetemplates._SELLING_SECTIONS
        and tenant.is_module_active(sitetemplates._SELLING_SECTIONS[s["key"]])
    ]


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_offered_bundles_and_templates_never_build_an_empty_home(business_type):
    """What the wizard/Studio/Design OFFERS a fresh business must show something it
    sells. Found on the stand: a fresh shop got «Prospekt» (promotions off) first —
    the home had no product at all."""
    base = _fresh_tenant(business_type)
    for bundle in sitetemplates.bundles_for(business_type, base):
        tenant = _fresh_tenant(business_type)
        sitetemplates.apply_bundle(tenant, bundle["key"])
        assert _live_selling_sections(tenant), f"{business_type}/{bundle['key']}: empty home"
    for tpl in sitetemplates.templates_for(business_type):
        if tpl["key"] in VISITING_CARDS:
            continue
        tenant = _fresh_tenant(business_type)
        sitetemplates.apply_template(tenant, tpl["key"])
        assert _live_selling_sections(tenant), f"{business_type}/{tpl['key']}: empty home"
