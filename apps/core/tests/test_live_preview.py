"""V1: live-preview конструктора главной — draft-эндпоинт + рендер ?preview=1."""

import json
from types import SimpleNamespace

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _session(req):
    SessionMiddleware(lambda r: None).process_request(req)
    return req


def test_draft_endpoint_merges_into_session():
    tenant = TenantFactory(
        schema_name="public", slug="d", name="D", site_config={"hero_title": "Saved"}
    )
    body = json.dumps(
        {
            "sections": [{"key": "hero", "enabled": True}, {"key": "products", "enabled": False}],
            "archetypes": {"catalog": {"hidden": True, "label": "X"}},
        }
    )
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = views.site_preview_draft(req)
    assert resp.status_code == 204
    draft = req.session["site_preview_draft"]
    en = {s["key"] for s in draft["sections"] if s["enabled"]}
    assert "hero" in en and "products" not in en
    assert draft["hero_title"] == "Saved"  # прочий конфиг не затёрт
    assert draft["archetypes"]["catalog"]["hidden"] is True
    assert draft["archetypes"]["catalog"]["label"] == "X"
    # в БД ничего не записано
    tenant.refresh_from_db()
    assert tenant.site_config.get(
        "archetypes", {}
    ) == {} or "catalog" not in tenant.site_config.get("archetypes", {})


def test_draft_endpoint_includes_layout_preset():
    """M20U-7: пресет раскладки секции-сетки отражается в черновике превью."""
    tenant = TenantFactory(schema_name="public", slug="dl", name="DL")
    body = json.dumps(
        {
            "sections": [
                {"key": "products", "enabled": True, "layout": {"preset": "gallery"}},
                # hero — не сетка: layout игнорируется
                {"key": "hero", "enabled": True, "layout": {"preset": "gallery"}},
            ]
        }
    )
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.site_preview_draft(req).status_code == 204
    draft = req.session["site_preview_draft"]
    products = next(s for s in draft["sections"] if s["key"] == "products")
    assert products["layout"]["preset"] == "gallery"
    hero = next(s for s in draft["sections"] if s["key"] == "hero")
    assert "layout" not in hero  # не секция-сетка


def test_draft_endpoint_includes_product_source():
    """M20U-7: источник товаров попадает в черновик превью."""
    tenant = TenantFactory(schema_name="public", slug="ds", name="DS")
    body = json.dumps(
        {"sections": [{"key": "products", "enabled": True, "source": "featured_only"}]}
    )
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.site_preview_draft(req).status_code == 204
    assert siteconfig.product_source(req.session["site_preview_draft"]) == "featured_only"


def test_draft_endpoint_includes_show_all():
    """M20U-7: видимость «View all» попадает в черновик превью."""
    tenant = TenantFactory(schema_name="public", slug="dsa", name="DSA")
    body = json.dumps({"sections": [{"key": "products", "enabled": True, "show_all": False}]})
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.site_preview_draft(req).status_code == 204
    assert siteconfig.section_show_all(req.session["site_preview_draft"], "products") is False


def test_draft_endpoint_includes_section_titles():
    """M20U-7: кастомные заголовки секций попадают в черновик (чистятся normalize)."""
    tenant = TenantFactory(schema_name="public", slug="dt", name="DT")
    body = json.dumps(
        {
            "sections": [{"key": "events", "enabled": True}],
            "section_titles": {"events": "Retreats", "hero": "x"},
        }
    )
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.site_preview_draft(req).status_code == 204
    draft = req.session["site_preview_draft"]
    assert draft["section_titles"] == {"events": "Retreats"}  # hero отброшен


def test_draft_endpoint_includes_design():
    """M20f: шрифт/стиль hero/акцент попадают в черновик (акцент — как `_accent`)."""
    tenant = TenantFactory(schema_name="public", slug="dd", name="DD")
    body = json.dumps(
        {
            "sections": [{"key": "hero", "enabled": True}],
            "font": "rounded",
            "hero_style": "accent",
            "accent": "#123456",
        }
    )
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.site_preview_draft(req).status_code == 204
    draft = req.session["site_preview_draft"]
    assert draft["font"] == "rounded" and draft["hero_style"] == "accent"
    assert draft["_accent"] == "#123456"


def test_draft_endpoint_rejects_bad_design():
    """Неизвестный шрифт и кривой акцент игнорируются (дефолты, без _accent)."""
    tenant = TenantFactory(schema_name="public", slug="dd2", name="DD2")
    body = json.dumps(
        {"sections": [{"key": "hero", "enabled": True}], "font": "comic", "accent": "red"}
    )
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    views.site_preview_draft(req)
    draft = req.session["site_preview_draft"]
    assert draft["font"] == "system" and "_accent" not in draft


def test_draft_endpoint_includes_content_sections():
    """M20d: CTA/FAQ из билдера отражаются в черновике (живое превью)."""
    tenant = TenantFactory(schema_name="public", slug="dc", name="DC")
    body = json.dumps(
        {
            "sections": [{"key": "cta", "enabled": True}],
            "cta_title": "Jetzt buchen",
            "cta_button_url": "/termin/",
            "faq_text": "Parkplatz? | Ja.",
        }
    )
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.site_preview_draft(req).status_code == 204
    draft = req.session["site_preview_draft"]
    assert draft["cta"]["title"] == "Jetzt buchen" and draft["cta"]["button_url"] == "/termin/"
    assert draft["faq"] == [{"q": "Parkplatz?", "a": "Ja."}]


def test_draft_without_content_keys_preserves_existing():
    """Черновик без контент-полей не затирает сохранённые CTA/FAQ (presence-guard)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="dc2",
        name="DC2",
        site_config={
            "cta": {"title": "Saved CTA", "text": "", "button_label": "", "button_url": ""}
        },
    )
    body = json.dumps({"sections": [{"key": "cta", "enabled": True}]})
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    views.site_preview_draft(req)
    assert req.session["site_preview_draft"]["cta"]["title"] == "Saved CTA"


def test_draft_endpoint_includes_event_detail():
    """SE-2b-2: порядок/видимость секций детальной события попадают в черновик
    превью (normalize_event_detail оставляет лишь известные ключи)."""
    tenant = TenantFactory(schema_name="public", slug="ded", name="DED")
    body = json.dumps(
        {
            "sections": [{"key": "hero", "enabled": True}],
            "event_detail": {"order": ["faq", "bogus"], "hidden": ["idea"]},
        }
    )
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.site_preview_draft(req).status_code == 204
    draft = req.session["site_preview_draft"]
    order = siteconfig.event_detail_order(draft)
    assert order[0] == "faq" and "idea" not in order  # faq поднят, idea скрыта
    assert "bogus" not in order  # неизвестный ключ отброшен normalize


def test_modules_nav_exposes_global_card_style():
    """SE-2d: глобальный стиль карточек (site_defaults) отдаётся в контекст витрины."""
    from apps.core.context import modules_nav

    tenant = TenantFactory(
        schema_name="t", slug="gcs", name="GCS", site_config={"site_defaults": {"card_radius": 14}}
    )
    req = _session(RequestFactory().get("/"))
    req.tenant = tenant
    ctx = modules_nav(req)
    assert ctx["storefront_card_radius"] == 14 and ctx["storefront_card_shadow"] is False


def test_modules_nav_previews_draft_card_style():
    """SE-2d: под ?preview=1 глобальный стиль карточек берётся из черновика."""
    from apps.core.context import modules_nav

    tenant = TenantFactory(schema_name="t", slug="gcsp", name="GCSP")
    draft = siteconfig.normalize({"site_defaults": {"card_radius": 20, "card_shadow": True}})
    req = _session(RequestFactory().get("/?preview=1"))
    req.session["site_preview_draft"] = draft
    req.tenant = tenant
    ctx = modules_nav(req)
    assert ctx["storefront_card_radius"] == 20 and ctx["storefront_card_shadow"] is True


def test_storefront_base_emits_global_card_vars():
    """SE-2d: <body> несёт --sf-r/--sf-sh при заданном site_defaults; без него — нет."""
    tenant = TenantFactory.build()
    tenant.site_config = {"site_defaults": {"card_radius": 16, "card_shadow": True}}
    req = _session(RequestFactory().get("/"))
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert "--sf-r:16px" in body and "--sf-sh:" in body

    tenant.site_config = {}  # legacy → без inline-переменных (без регрессии)
    req2 = _session(RequestFactory().get("/"))
    req2.tenant = tenant
    body2 = public_views.storefront_home(req2).content.decode()
    assert "--sf-r:" not in body2


def test_modules_nav_previews_draft_design():
    """Context-процессор под ?preview=1 отдаёт шрифт/акцент из черновика."""
    from apps.core.context import modules_nav

    tenant = TenantFactory(schema_name="t", slug="mn", name="MN", primary_color="#000000")
    draft = siteconfig.normalize({"font": "serif"})
    draft["_accent"] = "#abcdef"
    req = _session(RequestFactory().get("/?preview=1"))
    req.session["site_preview_draft"] = draft
    req.tenant = tenant
    ctx = modules_nav(req)
    assert ctx["storefront_accent"] == "#abcdef"
    assert "Georgia" in ctx["storefront_font_head"]  # serif-стек заголовков


def _home(req, tenant):
    req = _session(req)
    req.tenant = tenant
    return public_views.storefront_home(req)


def test_storefront_home_renders_draft_under_preview():
    tenant = TenantFactory.build()
    draft = siteconfig.normalize(
        {
            "sections": [{"key": "hero", "enabled": True}, {"key": "contact", "enabled": True}],
            "hero_title": "DRAFTONLY",
        }
    )
    req = RequestFactory().get("/?preview=1")
    req = _session(req)
    req.session["site_preview_draft"] = draft
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert "DRAFTONLY" in body  # черновик отрендерен

    # без ?preview=1 — сохранённое (черновик игнорируется)
    req2 = RequestFactory().get("/")
    req2 = _session(req2)
    req2.session["site_preview_draft"] = draft
    req2.tenant = tenant
    assert "DRAFTONLY" not in public_views.storefront_home(req2).content.decode()


def test_preview_skips_standalone_redirect():
    tenant = TenantFactory.build()
    draft = siteconfig.normalize(
        {"storefront_root": "catalog", "sections": [{"key": "hero", "enabled": True}]}
    )
    req = RequestFactory().get("/?preview=1")
    req = _session(req)
    req.session["site_preview_draft"] = draft
    req.tenant = tenant
    assert public_views.storefront_home(req).status_code == 200  # без редиректа


def test_storefront_home_allows_same_origin_framing():
    """Кабинет (тот же origin) показывает витрину в iframe — прод-DENY бы блокировал
    live-preview. Витрина отдаёт X-Frame-Options: SAMEORIGIN."""
    tenant = TenantFactory.build()
    req = _session(RequestFactory().get("/"))
    req.tenant = tenant
    resp = public_views.storefront_home(req)
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
