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


# --- SEO-2: normalize_seo (survives normalize) + cabinet view ----------------------

from django.contrib.messages.middleware import MessageMiddleware  # noqa: E402
from django.contrib.sessions.middleware import SessionMiddleware  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from apps.core import views  # noqa: E402
from apps.tenants import siteconfig  # noqa: E402
from apps.tenants.tests.factories import TenantFactory as _TF  # noqa: E402


def test_normalize_seo_keeps_valid_and_drops_unknown():
    raw = {
        "templates": {
            "home": {"title": "{tenant}"},
            "bogus": {"title": "x"},  # неизвестный page_type → отброшен
            "listing": {"description": "d"},
        }
    }
    out = siteconfig.normalize_seo(raw)
    assert out == {"templates": {"home": {"title": "{tenant}"}, "listing": {"description": "d"}}}


def test_normalize_seo_empty_returns_empty():
    assert siteconfig.normalize_seo({}) == {}
    assert siteconfig.normalize_seo(None) == {}
    assert siteconfig.normalize_seo({"templates": {"home": {"title": "   "}}}) == {}


def test_normalize_preserves_seo_and_omits_when_absent():
    out = siteconfig.normalize({"seo": {"templates": {"home": {"title": "{tenant} SEO"}}}})
    assert out["seo"]["templates"]["home"]["title"] == "{tenant} SEO"
    assert "seo" not in siteconfig.normalize({})  # golden-паритет: пусто → нет ключа


class _CabUser:
    is_authenticated = True
    is_active = True
    username = "owner"


def _cab_req(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _CabUser()
    req.tenant = tenant
    return req


def test_seo_view_get_renders_editor(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _TF(schema_name="public", slug="seocab1", name="Bäcker", city="Köln")
    body = views.seo_settings_view(
        _cab_req("get", "/dashboard/site/seo/", tenant=tenant)
    ).content.decode()
    assert 'name="title_home"' in body  # редактор home
    assert 'name="desc_listing"' in body  # редактор listing
    assert "data-seo-ph" in body  # плейсхолдер-чипы
    assert "data-seo-prev-title" in body  # live-превью сниппета


def test_seo_view_saves_and_survives_home_builder_save(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _TF(schema_name="public", slug="seocab2", name="Bäcker Ott", city="Köln")
    resp = views.seo_settings_view(
        _cab_req("post", "/dashboard/site/seo/", {"title_home": "{tenant} — {city}"}, tenant=tenant)
    )
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["seo"]["templates"]["home"]["title"] == "{tenant} — {city}"
    # Ключевое: сохранение конструктора главной НЕ должно стереть SEO-шаблоны.
    views.home_builder_view(
        _cab_req(
            "post",
            "/dashboard/site/home/",
            {"order_hero": "1", "enabled_hero": "on"},
            tenant=tenant,
        )
    )
    tenant.refresh_from_db()
    assert tenant.site_config["seo"]["templates"]["home"]["title"] == "{tenant} — {city}"


def test_seo_view_empty_post_clears_templates(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _TF(schema_name="public", slug="seocab3", name="X", city="")
    views.seo_settings_view(
        _cab_req(
            "post",
            "/dashboard/site/seo/",
            {"title_home": "{tenant}!", "allow_ai": "on"},
            tenant=tenant,
        )
    )
    # форма отправлена: все шаблоны пусты, ИИ разрешён (allow_ai=on) → seo не материализуется.
    views.seo_settings_view(
        _cab_req("post", "/dashboard/site/seo/", {"allow_ai": "on"}, tenant=tenant)
    )
    tenant.refresh_from_db()
    assert "seo" not in tenant.site_config  # шаблоны сняты + ИИ разрешён → ключ не материализован


# --- SEO-3: FAQPage JSON-LD + AI-краулеры (allow_ai) + robots/llms -----------------

from apps.core.seo import faqpage_ld  # noqa: E402
from apps.promotions import public_views  # noqa: E402


def test_faqpage_ld_builds_and_skips_incomplete():
    out = faqpage_ld(
        [{"q": "Öffnungszeiten?", "a": "Mo-Fr 8-18"}, {"q": "Q", "a": ""}, {"q": "", "a": "x"}]
    )
    assert '"@type":"FAQPage"' in out
    assert "Öffnungszeiten?" in out
    assert out.count('"Question"') == 1  # только полная пара


def test_faqpage_ld_empty_returns_blank():
    assert faqpage_ld([]) == ""
    assert faqpage_ld([{"q": "only q"}]) == ""


def test_normalize_seo_allow_ai_only_when_false():
    assert siteconfig.normalize_seo({"allow_ai": False}) == {"allow_ai": False}
    assert siteconfig.normalize_seo({"allow_ai": True}) == {}  # дефолт → не материализуем
    out = siteconfig.normalize_seo({"templates": {"home": {"title": "x"}}, "allow_ai": False})
    assert out == {"templates": {"home": {"title": "x"}}, "allow_ai": False}


def test_robots_blocks_ai_when_disabled(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _TF(
        schema_name="public", slug="rob1", name="X", site_config={"seo": {"allow_ai": False}}
    )
    req = RequestFactory().get("/robots.txt")
    req.tenant = tenant
    body = public_views.robots_txt(req).content.decode()
    assert "GPTBot" in body and "ClaudeBot" in body and "Disallow: /" in body


def test_robots_allows_ai_by_default(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _TF(schema_name="public", slug="rob2", name="X", site_config={})
    req = RequestFactory().get("/robots.txt")
    req.tenant = tenant
    body = public_views.robots_txt(req).content.decode()
    assert "User-agent: *" in body
    assert "GPTBot" not in body  # дефолт: ИИ разрешён


def test_llms_txt_renders_business(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _TF(
        schema_name="public",
        slug="llm1",
        name="Bäcker Ott",
        city="Köln",
        site_config={"about_text": "Frische Backwaren."},
    )
    req = RequestFactory().get("/llms.txt")
    req.tenant = tenant
    body = public_views.llms_txt(req).content.decode()
    assert "# Bäcker Ott" in body
    assert "Standort: Köln" in body
    assert "Frische Backwaren." in body


def test_seo_view_ai_toggle_off_survives_home_save(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _TF(schema_name="public", slug="seocab4", name="X")
    views.seo_settings_view(  # чекбокс allow_ai НЕ прислан → выключено
        _cab_req("post", "/dashboard/site/seo/", {"title_home": "{tenant}"}, tenant=tenant)
    )
    tenant.refresh_from_db()
    assert tenant.site_config["seo"]["allow_ai"] is False
    views.home_builder_view(
        _cab_req("post", "/dashboard/site/home/", {"order_hero": "1"}, tenant=tenant)
    )
    tenant.refresh_from_db()
    assert tenant.site_config["seo"]["allow_ai"] is False  # переживает сохранение главной


def test_seo_view_ai_toggle_on_clears_key(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _TF(schema_name="public", slug="seocab5", name="X")
    views.seo_settings_view(
        _cab_req("post", "/dashboard/site/seo/", {"allow_ai": "on"}, tenant=tenant)
    )
    tenant.refresh_from_db()
    assert "allow_ai" not in (tenant.site_config.get("seo") or {})  # разрешено → ключ не пишем
