"""FB-33 M4b: замки ДО кода — из старой панели Студии сняты группы, дублирующие окно блока.

Решение владельца (2026-11-21, «по рекомендации»): что показывает блок, как он расставлен,
форма карточки и место (Was · Wie anordnen · Karte · Platz) правятся только в окне блока
«Seitenaufbau». В панели Студии остаются содержимое (тексты, фото, карточки «Unser
Angebot») и «Feinschliff» — тонкие настройки вида, которых в окне нет.

Главный риск — грабля W0: поле, которого нет в форме, стирается при «Speichern». Поэтому
сервер сначала учится брать снятое из сохранённого (`site_schema.merge_structure`), потом
шаблон теряет поля.

CH характеристика: Студия по-прежнему пишет тексты и «Feinschliff» · L1 у каждого снятого
поля есть место в окне, и окно его пишет · L2 «Speichern» без снятых полей их не стирает ·
L3 устаревшая или подделанная форма (и живой черновик) их не меняет · L4 разметка строки ·
L5 плашка: «Raster ▾ / Stil ▾» ведут в окно, «Breite ▾» снята.
"""

import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import list_blocks, list_panel, site_schema, views
from apps.core.modules import default_disabled_for
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
STUDIO_TPL = ROOT / "templates" / "tenant" / "site_home.html"

#: Поля «ЧТО» встроенных списков, которые строка Студии рисовала до среза (снимок GET
#: Студии у онлайн-магазина со всеми модулями, 2026-11-21, без сентинела `present`).
STUDIO_WHAT_BEFORE = {
    "promotions": ("card", "endet", "rabatt", "sort", "type", "ziel"),
    "products": ("card", "category", "collection", "only", "sort"),
    "categories": ("category",),
    "services": ("card", "collection", "only", "sort"),
    "stay_rooms": ("card", "collection", "sort"),
    "events": ("card", "event_category", "only", "sort"),
    "tours": ("card", "country"),
    "blog": (),
}

PRODUCTS = {
    "key": "products",
    "enabled": True,
    "layout": {"preset": "cols4", "cols": 4, "rows": 2, "scroll": True, "mobile": 1},
    "limit": 6,
    "style": "preisliste",
    "data": {"sort": "price_asc"},
}
LISTE = {
    "key": "list",
    "id": "l1",
    "enabled": True,
    "data": {
        "source": "events",
        "sort": "price_desc",
        "out": "slider",
        "cols": 2,
        "card": "compact",
        "title": "Alt",
        "speed": 5,
    },
}
CFG = {
    "sections": [
        PRODUCTS,
        {"key": "faq", "enabled": True, "style": "cards"},
        {"key": "usp_bar", "enabled": True, "style": "pillars"},
        {"key": "team", "enabled": True, "style": "circles", "layout": {"preset": "cols3"}},
        LISTE,
    ]
}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(cfg=None):
    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    tenant.site_config = copy.deepcopy(CFG if cfg is None else cfg)
    tenant.save()
    return tenant


def _req(method, path, tenant, data=None, **kw):
    req = getattr(RequestFactory(), method)(path, data or {}, **kw)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    tenant.refresh_from_db()
    req.tenant = tenant
    return req


def _studio(tenant) -> str:
    return views.home_builder_view(_req("get", "/dashboard/site/home/", tenant)).content.decode()


#: Форма строк, которые Студия шлёт после среза: порядок, видимость, тексты и «Feinschliff».
BASE = {
    "order_products": "1",
    "enabled_products": "on",
    "order_faq": "2",
    "enabled_faq": "on",
    "order_usp_bar": "3",
    "enabled_usp_bar": "on",
    "order_team": "4",
    "enabled_team": "on",
    "cb_id": "l1",
    "cb_type_l1": "list",
    "order_cb_l1": "5",
    "enabled_cb_l1": "on",
}


def _save(tenant, data) -> dict:
    resp = views.home_builder_view(_req("post", "/dashboard/site/home/", tenant, {**BASE, **data}))
    assert resp.status_code == 302, resp.status_code
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def _row(cfg, key, ident="key"):
    return next(
        s for s in cfg["sections"] if s.get(ident) == key and (ident == "id" or "id" not in s)
    )


# ───────────── CH: характеристика — Студия по-прежнему пишет своё ─────────────


def test_studio_still_writes_texts_and_fine_tuning():
    tenant = _tenant()
    font = list(siteconfig.FONTS)[1]
    cfg = _save(
        tenant,
        {
            "hero_title": "Frisch gebacken",
            "tail_products": "show",
            "balance_products": "on",
            "mobile_products": "2",
            "tablet_products": "3",
            "font_products": font,
            "visual_radius_px_products": "8",
            "visual_shadow_products": "on",
            "hide_mobile_products": "on",
            "rows_products": "4",
            "cb_l1_title": "Neu",
            "cb_l1_intro": "Hallo",
            "cb_l1_speed": "7",
        },
    )
    assert cfg["hero_title"] == "Frisch gebacken"
    row = _row(cfg, "products")
    lay = row["layout"]
    assert lay.get("tail") == "show" and lay.get("balance") is True
    assert lay["mobile"] == 2 and lay["tablet"] == 3
    assert row["font"] == font and row["visual"]["radius"] == 8 and row["visual"]["shadow"]
    assert row["hidden_on"] == ["mobile"] and row["rows"] == 4
    liste = _row(cfg, "l1", "id")["data"]
    assert (liste["title"], liste["intro"], liste["speed"]) == ("Neu", "Hallo", 7)


# ───────────── L1: у каждого снятого поля есть место в окне ─────────────


@pytest.mark.parametrize("key", sorted(STUDIO_WHAT_BEFORE))
def test_every_removed_what_field_is_written_by_the_window(key):
    source = siteconfig.BUILTIN_LIST_SOURCES[key]
    spec = siteconfig.LIST_SOURCES[source]
    reachable = set(spec["filters"]) | {"card"}
    if siteconfig.LIST_ONLY.get(source):
        reachable.add("only")
    if siteconfig.list_sort_keys(source):
        reachable.add("sort")
    for field in STUDIO_WHAT_BEFORE[key]:
        assert field in list_blocks.BUILTIN_WHAT_FIELDS, f"{key}.{field}: окно его не пишет"
        assert field in reachable, f"{key}.{field}: в окне нет поля"


@pytest.mark.parametrize("key", sorted(siteconfig.BUILTIN_LIST_SOURCES))
def test_removed_view_fields_of_a_builtin_list_are_in_the_window(key, rf):
    """`layout_preset_`/🖥 `cols_` → «Spalten», `grid_rows_` → «Reihen», `scroll_` →
    «Ausgabe», `limit_` → «Höchstens», `style_` → «Darstellung»."""
    tenant = _tenant()
    req = rf.get("/")
    req.tenant = tenant
    cfg = siteconfig.normalize(tenant.site_config)
    row = next(s for s in cfg["sections"] if s["key"] == key and "id" not in s)
    names = {
        f["name"]
        for g in list_panel.builtin_groups(req, cfg, key, site_schema.builtin_panel_data(row))
        for f in g["fields"]
    }
    want = {"cols", "rows", "out"}
    if key in siteconfig.GRID_SECTION_LIMITS:
        want.add("limit")
    if siteconfig.SECTION_STYLES.get(key):
        want.add("style")
    assert want <= names, want - names
    assert want <= set(site_schema.BUILTIN_VIEW_FIELDS) | {"out"}


def test_window_writes_what_view_and_limit_of_a_builtin_list():
    tenant = _tenant()
    fields = {"sort": "newest", "cols": "3", "rows": "1", "out": "grid", "limit": "8"}
    site_schema.apply(tenant, "home", "update", ref="products", fields={**fields, "style": ""})
    row = _row(siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config), "products")
    assert row["layout"]["cols"] == 3 and row["layout"]["rows"] == 1
    assert not row["layout"].get("scroll") and row["limit"] == 8 and "style" not in row
    assert list_blocks.section_data(row)["sort"] == "newest"


@pytest.mark.parametrize("key", site_schema.STYLE_SECTIONS)
def test_section_style_has_its_field_in_the_window(key):
    assert [f["name"] for f in site_schema.section_style_fields({"key": key})] == ["style"]


def test_removed_liste_fields_are_window_fields():
    removed = set(views._LIST_BLOCK_FIELDS) - {"title", "intro", "speed", "pick", "scope"}
    assert removed <= set(list_panel.NAMES), removed - set(list_panel.NAMES)


# ───────────── L2: W0 — «Speichern» без снятых полей их не стирает ─────────────


def test_save_without_the_removed_fields_keeps_the_window_values():
    tenant = _tenant()
    cfg = _save(tenant, {"tail_products": "show", "mobile_products": "2", "cb_l1_title": "Neu"})
    row = _row(cfg, "products")
    lay = row["layout"]
    assert (lay["preset"], lay["cols"], lay["rows"], lay.get("scroll")) == ("cols4", 4, 2, True)
    assert lay["mobile"] == 2 and lay.get("tail") == "show"  # оставшееся — из формы
    assert row["limit"] == 6 and row["style"] == "preisliste"
    assert list_blocks.section_data(row)["sort"] == "price_asc"
    assert _row(cfg, "faq")["style"] == "cards" and _row(cfg, "usp_bar")["style"] == "pillars"
    assert _row(cfg, "team")["style"] == "circles"
    data = _row(cfg, "l1", "id")["data"]
    assert data["title"] == "Neu"
    for field in ("source", "sort", "out", "cols", "card"):
        assert data[field] == LISTE["data"][field], field


# ───────────── L3: устаревшая или подделанная форма их не меняет ─────────────

FORGED = {
    "layout_preset_products": "cols2",
    "cols_products": "2",
    "grid_rows_products": "5",
    "limit_products": "3",
    "style_products": "preisliste_karte",
    "sl_products_present": "1",
    "sl_products_sort": "newest",
    "style_faq": "numbered",
    "style_usp_bar": "plain",
    "style_team": "list",
    "cb_l1_source": "products",
    "cb_l1_cols": "1",
    "cb_l1_out": "grid",
    "cb_l1_scope": "type",
}


def test_forged_studio_form_does_not_change_window_values():
    tenant = _tenant()
    cfg = _save(tenant, FORGED)
    row = _row(cfg, "products")
    assert (row["layout"]["preset"], row["layout"]["cols"], row["layout"]["rows"]) == (
        "cols4",
        4,
        2,
    )
    assert row["layout"].get("scroll") is True  # `scroll_` не прислан — лента цела
    assert row["limit"] == 6 and row["style"] == "preisliste"
    assert list_blocks.section_data(row)["sort"] == "price_asc"
    assert _row(cfg, "faq")["style"] == "cards" and _row(cfg, "usp_bar")["style"] == "pillars"
    assert _row(cfg, "team")["style"] == "circles"
    data = _row(cfg, "l1", "id")["data"]
    assert (data["source"], data["cols"], data["out"]) == ("events", 2, "slider")
    assert "scope" not in data


def test_forged_live_draft_does_not_change_window_values():
    tenant = _tenant()
    payload = {
        "sections": [
            {
                "key": "products",
                "enabled": True,
                "layout": {"preset": "cols2", "cols": 2, "mobile": 2},
                "limit": 3,
                "style": "preisliste_karte",
                "data": {"sort": "newest"},
            },
            {"key": "faq", "enabled": True, "style": "numbered"},
        ]
    }
    req = _req(
        "post",
        "/dashboard/site/preview/draft/",
        tenant,
        json.dumps(payload),
        content_type="application/json",
    )
    assert views.site_preview_draft(req).status_code == 204
    cfg = siteconfig.normalize(req.session["site_preview_draft"])
    row = _row(cfg, "products")
    assert (row["layout"]["preset"], row["layout"]["cols"], row["layout"]["rows"]) == (
        "cols4",
        4,
        2,
    )
    assert row["layout"]["mobile"] == 2  # «Feinschliff» черновика действует
    assert row["limit"] == 6 and row["style"] == "preisliste"
    assert list_blocks.section_data(row)["sort"] == "price_asc"
    assert _row(cfg, "faq")["style"] == "cards"


def test_merge_keeps_window_keys_and_takes_the_rest_of_the_layout():
    """Ядро C1 на уровне функции: остальная раскладка (хвост, 📱/▭) — из формы."""
    saved = [copy.deepcopy(PRODUCTS)]
    posted = [{"key": "products", "layout": {"preset": "list", "mobile": 2, "tail": "show"}}]
    merged = site_schema.merge_structure(saved, posted, fixed=True)[0]
    assert merged["layout"] == {
        "preset": "cols4",
        "cols": 4,
        "rows": 2,
        "scroll": True,
        "mobile": 2,
        "tail": "show",
    }


# ───────────── L4: разметка строки ─────────────

REMOVED_PRODUCTS = (
    "layout_preset_products",
    "cols_products",
    "grid_rows_products",
    "scroll_products",
    "limit_products",
    "style_products",
    "width_products",
    "sl_products_",
)
KEPT_PRODUCTS = (
    "tail_products",
    "balance_products",
    "mobile_products",
    "tablet_products",
    "hide_mobile_products",
    "font_products",
    "visual_radius_px_products",
    "rows_products",
    "show_all_products",
)
REMOVED_LISTE = ("source", "type", "sort", "limit", "style", "out", "cols", "rows", "card")


def _names(html: str) -> set[str]:
    return set(re.findall(r'name="([^"]+)"', html))


def test_studio_rows_have_no_removed_fields():
    names = _names(_studio(_tenant()))
    for name in REMOVED_PRODUCTS:
        assert not any(n.startswith(name) for n in names), name
    for key in ("faq", "usp_bar", "team"):
        assert f"style_{key}" not in names, key
    for field in REMOVED_LISTE:
        assert f"cb_l1_{field}" not in names, field
    assert "cb_l1_scope" not in names and "cb_l1_pick" not in names


def test_studio_rows_keep_content_and_fine_tuning():
    html = _studio(_tenant())
    names = _names(html)
    for name in KEPT_PRODUCTS:
        assert name in names, name
    assert {"layout_preset_team", "grid_rows_team", "mobile_team"} <= names  # окна нет
    assert {"cb_l1_title", "cb_l1_intro", "cb_l1_speed"} <= names
    assert "copy_builtin:products" in html  # «Als eigenen Block kopieren» — не в окне


def test_row_links_into_the_window_without_js():
    html = _studio(_tenant())
    for key in ("products", "faq", "usp_bar"):
        assert f"?page=%2F&amp;block={key}&amp;tab=wie" in html, key
    assert "data-stu-window-hint" in html
    assert "Feinschliff" in html


# ───────────── L5: плашка ─────────────


def _segment(body, start, end):
    i = body.index(start)
    return body[i : body.index(end, i)]


@pytest.mark.xfail(strict=True, reason="C4: «Raster ▾ / Stil ▾» ведут в окно, «Breite ▾» снята")
def test_action_bar_enters_the_window_for_removed_controls():
    tpl = STUDIO_TPL.read_text()
    bar = _segment(tpl, 'id="bld-action-bar"', "</div>")
    assert 'data-quick="width"' not in bar
    assert 'data-quick="layout"' in bar and 'data-quick="style"' in bar
    href = _segment(tpl, "function windowHref(", "\n  }")
    assert "&tab=" in href
    assert 'openWindowFor(abKey, "wie")' in tpl
    assert "data-quick-window" in tpl and "data-win-quick" in tpl
