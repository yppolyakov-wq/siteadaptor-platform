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
    # опубликованный конфиг не тронут (правки только под `_draft`)
    tenant.refresh_from_db()
    assert tenant.site_config.get(
        "archetypes", {}
    ) == {} or "catalog" not in tenant.site_config.get("archetypes", {})


def test_draft_endpoint_persists_to_db_under_draft_key():
    """SE-5b-2: автосейв черновика — `_draft` в БД переживает потерю сессии; опубликованные
    ключи не затронуты (правки живут под `_draft`, normalize() дропает их из выдачи)."""
    tenant = TenantFactory(
        schema_name="public", slug="dpd", name="DPD", site_config={"hero_title": "Saved"}
    )
    body = json.dumps({"sections": [{"key": "hero", "enabled": True}], "font": "serif"})
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.site_preview_draft(req).status_code == 204
    tenant.refresh_from_db()
    assert tenant.site_config["hero_title"] == "Saved"  # опубликованное не тронуто
    assert tenant.site_config["_draft"]["font"] == "serif"  # черновик сохранён в БД
    assert "_draft_ts" in tenant.site_config
    # normalize() (выдача/история) не показывает служебные ключи
    assert "_draft" not in siteconfig.normalize(tenant.site_config)


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


def test_storefront_preview_applies_layout_columns():
    """Баг D (диагностика): выбранная раскладка должна отражаться в РЕНДЕРЕ витрины —
    черновик products cols4 → грид рендерит lg:grid-cols-4 (десктоп). Если зелёный —
    бэкенд применяет раскладку, и «не применяется» = узкое превью (lg не срабатывает)."""
    from apps.catalog.tests.factories import ProductFactory

    tenant = TenantFactory(schema_name="public", slug="laycol", name="LAYCOL")
    ProductFactory(name={"de": "Brot", "en": ""}, is_active=True)
    draft = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "layout": {"preset": "cols4"}}]}
    )
    req = _session(RequestFactory().get("/?preview=1"))
    req.session["site_preview_draft"] = draft
    req.session.save()
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = public_views.storefront_home(req)
    assert resp.status_code == 200
    assert "lg:grid-cols-4" in resp.content.decode()


def test_storefront_preview_explicit_cols_overrides_preset():
    """Баг D корень: явный пер-девайс `cols` ПЕРЕБИВАЕТ пресет раскладки.
    {preset:cols2} → lg:grid-cols-2 (пресет применяется); {preset:cols2, cols:3} →
    lg:grid-cols-3 (старый cols перебивает «2 в ряд» → показывало 3). Фронт-фикс
    сбрасывает cols/mobile/tablet при выборе пресета-миниатюры."""
    from apps.catalog.tests.factories import ProductFactory

    tenant = TenantFactory(schema_name="public", slug="layovr", name="LAYOVR")
    ProductFactory(name={"de": "P", "en": ""}, is_active=True)

    def render(layout):
        draft = siteconfig.normalize(
            {"sections": [{"key": "products", "enabled": True, "layout": layout}]}
        )
        req = _session(RequestFactory().get("/?preview=1"))
        req.session["site_preview_draft"] = draft
        req.session.save()
        req.user = SimpleNamespace(is_authenticated=True)
        req.tenant = tenant
        return public_views.storefront_home(req).content.decode()

    assert "lg:grid-cols-2" in render({"preset": "cols2"})  # пресет применяется
    assert "lg:grid-cols-3" in render({"preset": "cols2", "cols": 3})  # явный cols перебивает


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


def test_draft_endpoint_includes_landing_layouts():
    """SE-2d-5: пер-страничные раскладки лендингов попадают в черновик (live-preview
    раскладки каталога/событий/номеров до Save)."""
    tenant = TenantFactory(schema_name="public", slug="dll", name="DLL")
    body = json.dumps(
        {
            "sections": [{"key": "hero", "enabled": True}],
            "catalog_layout": {"preset": "gallery"},
            "events_index_layout": {"preset": "cols3"},
            "stay_index_layout": {"preset": "cols4"},
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
    assert draft["catalog_layout"]["preset"] == "gallery"
    assert draft["events_index_layout"]["preset"] == "cols3"
    assert draft["stay_index_layout"]["preset"] == "cols4"


def test_draft_endpoint_includes_service_index_layout():
    """UB1-1: раскладка листинга услуг попадает в черновик (live-preview /termin/ до Save)."""
    tenant = TenantFactory(schema_name="public", slug="dsv", name="DSV")
    body = json.dumps(
        {
            "sections": [{"key": "hero", "enabled": True}],
            "service_index_layout": {"preset": "cols3"},
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
    assert req.session["site_preview_draft"]["service_index_layout"]["preset"] == "cols3"


def test_draft_endpoint_includes_site_defaults():
    """SE-2d-3: глобальный стиль карточек попадает в черновик превью (normalize клампит)."""
    tenant = TenantFactory(schema_name="public", slug="dsd", name="DSD")
    body = json.dumps(
        {
            "sections": [{"key": "hero", "enabled": True}],
            "site_defaults": {"card_radius": 18, "card_shadow": True},
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
    sd = req.session["site_preview_draft"]["site_defaults"]
    assert sd["card_radius"] == 18 and sd["card_shadow"] is True


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


def test_storefront_base_emits_global_bg_padding():
    """SE-3d: <body> несёт --sf-bg/--sf-pad при заданных site_defaults; без них — нет."""
    tenant = TenantFactory.build()
    tenant.site_config = {"site_defaults": {"card_bg": "#abcdef", "card_padding": 20}}
    req = _session(RequestFactory().get("/"))
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert "--sf-bg:#abcdef" in body and "--sf-pad:20px" in body
    # CSS-селекторы карточек присутствуют
    assert '[style*="--sf-bg"] .sf-card' in body and '[style*="--sf-pad"] .sf-card' in body

    tenant.site_config = {}
    req2 = _session(RequestFactory().get("/"))
    req2.tenant = tenant
    body2 = public_views.storefront_home(req2).content.decode()
    assert "--sf-bg:" not in body2 and "--sf-pad:" not in body2  # legacy без регрессии


def test_draft_endpoint_includes_section_visual():
    """SE-3d: пер-секционный visual (incl. bg/padding) попадает в черновик для live-preview."""
    tenant = TenantFactory(schema_name="public", slug="dsv", name="DSV")
    body = json.dumps(
        {
            "sections": [
                {
                    "key": "products",
                    "enabled": True,
                    "visual": {
                        "radius": 0,
                        "shadow": False,
                        "background": "#101010",
                        "padding": 10,
                    },
                }
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
    v = siteconfig.section_visual(draft, "products")
    assert v["background"] == "#101010" and v["padding"] == 10


def test_storefront_base_emits_typography():
    """SE-3b: <:root> несёт --fw-head/--lh-body при заданной типографике; без неё — нет."""
    tenant = TenantFactory.build()
    tenant.site_config = {"typography": {"weight_head": 700, "line_height": 1.6}}
    req = _session(RequestFactory().get("/"))
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert "--fw-head: 700" in body and "--lh-body: 1.6" in body

    tenant.site_config = {}
    req2 = _session(RequestFactory().get("/"))
    req2.tenant = tenant
    body2 = public_views.storefront_home(req2).content.decode()
    assert "--fw-head:" not in body2 and "--lh-body:" not in body2  # legacy без регрессии


def test_draft_endpoint_includes_typography():
    """SE-3b: типографика попадает в черновик превью (normalize клампит)."""
    tenant = TenantFactory(schema_name="public", slug="dty", name="DTY")
    body = json.dumps(
        {
            "sections": [{"key": "hero", "enabled": True}],
            "typography": {"weight_head": 800, "line_height": 2.0},
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
    assert req.session["site_preview_draft"]["typography"] == {
        "weight_head": 800,
        "line_height": 2.0,
    }


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


def test_draft_applies_nav_style_and_hero_for_live_preview():
    """SE-8b: Меню (nav_style/sticky) и Баннер (hero_title/text) попадают в черновик →
    видны в превью вживую (раньше collect их не слал)."""
    tenant = TenantFactory(
        schema_name="public", slug="se8b", name="SE8B", site_config={"hero_title": "Alt"}
    )
    body = json.dumps(
        {"nav_style": "centered", "nav_sticky": True, "hero_title": "Neu", "hero_text": "Hallo"}
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
    assert draft["nav"]["style"] == "centered" and draft["nav"]["sticky"] is True
    assert draft["hero_title"] == "Neu" and draft["hero_text"] == "Hallo"


def test_draft_endpoint_includes_cblocks():
    """D.2b: C-блок из collect() (key=тип, id, data) попадает в черновик. Раньше
    site_preview_draft фильтровал только ФИКС-секции → cblocks выпадали и добавленный
    блок «не появлялся» в live-preview (корень бага «Templates: кнопки неактивны»)."""
    tenant = TenantFactory(schema_name="public", slug="dcb", name="DCB")
    body = json.dumps(
        {
            "sections": [
                {"key": "hero", "enabled": True},
                {
                    "key": "text",
                    "id": "abc123def456",
                    "enabled": True,
                    "data": {"title": "T", "body": "B"},
                },
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
    cb = next((s for s in draft["sections"] if s.get("id") == "abc123def456"), None)
    assert cb is not None and cb["key"] == "text"
    assert cb["data"]["title"] == "T" and cb["data"]["body"] == "B"


def test_draft_endpoint_keeps_multiple_cblocks_of_same_type():
    """C-блоки одного ТИПА различаются по id (не дедупятся по ключу, как фикс-секции)."""
    tenant = TenantFactory(schema_name="public", slug="dcb2", name="DCB2")
    body = json.dumps(
        {
            "sections": [
                {"key": "text", "id": "id1aaaaaaaaa", "enabled": True, "data": {"body": "one"}},
                {"key": "text", "id": "id2bbbbbbbbb", "enabled": True, "data": {"body": "two"}},
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
    ids = {
        s.get("id") for s in req.session["site_preview_draft"]["sections"] if s.get("key") == "text"
    }
    assert ids == {"id1aaaaaaaaa", "id2bbbbbbbbb"}


def test_empty_cblock_shows_placeholder_only_in_preview():
    """Пустой C-блок: в редакторе (is_preview) — кликабельный плейсхолдер (виден на канве),
    на публичной витрине — ничего (чисто). Непустой — рендерит контент, не плейсхолдер."""
    from django.template.loader import render_to_string

    empty_preview = render_to_string(
        "storefront/sections/_block_text.html", {"block": {}, "is_preview": True}
    )
    assert "klicken zum Bearbeiten" in empty_preview
    empty_public = render_to_string(
        "storefront/sections/_block_text.html", {"block": {}, "is_preview": False}
    )
    assert "klicken zum Bearbeiten" not in empty_public
    filled = render_to_string(
        "storefront/sections/_block_text.html",
        {"block": {"title": "Hi", "body": "X"}, "is_preview": True},
    )
    assert "Hi" in filled and "klicken zum Bearbeiten" not in filled


def test_empty_image_block_placeholder_in_preview():
    from django.template.loader import render_to_string

    out = render_to_string(
        "storefront/sections/_block_image.html", {"block": {}, "is_preview": True}
    )
    assert "klicken zum Hinzuf" in out  # «klicken zum Hinzufügen»
