"""SEO-1: движок мета-заготовок — render/clamp/resolve + context processor."""

import pytest

from apps.core import context_processors, seo_meta
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


# --- render_template ---------------------------------------------------------------


def test_render_substitutes_placeholders():
    assert seo_meta.render_template("{a} · {b}", {"a": "X", "b": "Y"}) == "X · Y"


def test_render_drops_empty_and_cleans_separators():
    # пустой плейсхолдер в конце → без висячего разделителя
    assert seo_meta.render_template("{name} · {tenant}", {"name": "", "tenant": "Shop"}) == "Shop"
    # сдвоенный разделитель в середине схлопывается
    assert seo_meta.render_template("{a} · {x} · {b}", {"a": "A", "x": "", "b": "B"}) == "A · B"


def test_render_unknown_placeholder_removed():
    assert seo_meta.render_template("{tenant}{missing}", {"tenant": "Shop"}) == "Shop"


# --- clamp -------------------------------------------------------------------------


def test_clamp_keeps_short_and_truncates_long():
    assert seo_meta.clamp("kurz", 60) == "kurz"
    long = "wort " * 40
    out = seo_meta.clamp(long, 60)
    assert len(out) <= 61 and out.endswith("…")


# --- resolve -----------------------------------------------------------------------


def _tenant(**kw):
    kw.setdefault("name", "Bäckerei Ott")
    kw.setdefault("city", "Köln")
    return TenantFactory.build(**kw)


def test_resolve_uses_archetype_default_home():
    t = _tenant(site_config={})
    out = seo_meta.resolve(t, "home")
    assert out["title"] == "Bäckerei Ott · Köln"
    assert "Bäckerei Ott · Köln" in out["description"]


def test_resolve_home_without_city_has_no_dangling_separator():
    t = _tenant(city="", site_config={})
    out = seo_meta.resolve(t, "home")
    assert out["title"] == "Bäckerei Ott"  # без « · »


def test_resolve_listing_uses_heading():
    t = _tenant(site_config={})
    out = seo_meta.resolve(t, "listing", {"heading": "Termine"})
    assert out["title"] == "Termine · Bäckerei Ott"


def test_resolve_prefers_configured_template():
    t = _tenant(site_config={"seo": {"templates": {"home": {"title": "{tenant} — {city} Bäcker"}}}})
    assert seo_meta.resolve(t, "home")["title"] == "Bäckerei Ott — Köln Bäcker"


def test_resolve_ctx_override_wins_over_config():
    t = _tenant(site_config={"seo": {"templates": {"home": {"title": "cfg"}}}})
    out = seo_meta.resolve(t, "home", {"title_override": "{tenant}!"})
    assert out["title"] == "Bäckerei Ott!"


def test_resolve_title_falls_back_to_name_when_empty():
    t = _tenant(
        name="Solo", city="", site_config={"seo": {"templates": {"home": {"title": "{city}"}}}}
    )
    assert seo_meta.resolve(t, "home")["title"] == "Solo"


def test_resolve_clamps_title_length():
    t = _tenant(name="X" * 100, city="", site_config={})
    assert len(seo_meta.resolve(t, "home")["title"]) <= seo_meta.TITLE_MAX + 1


# --- context processor -------------------------------------------------------------


class _Match:
    def __init__(self, url_name):
        self.url_name = url_name


class _Req:
    def __init__(self, tenant, url_name):
        self.tenant = tenant
        self.resolver_match = _Match(url_name)


def test_context_processor_home_resolves():
    ctx = context_processors.seo(_Req(_tenant(site_config={}), "storefront-home"))
    assert ctx["seo_meta"]["title"] == "Bäckerei Ott · Köln"


def test_context_processor_listing_applies_heading():
    ctx = context_processors.seo(_Req(_tenant(site_config={}), "storefront-products"))
    assert "Sortiment" in ctx["seo_meta"]["title"]


def test_context_processor_unmapped_returns_empty():
    assert context_processors.seo(_Req(_tenant(site_config={}), "dashboard-home")) == {}


def test_context_processor_no_tenant_returns_empty():
    class _R:
        tenant = None
        resolver_match = _Match("storefront-home")

    assert context_processors.seo(_R()) == {}
