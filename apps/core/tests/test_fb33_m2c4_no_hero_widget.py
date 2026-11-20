"""FB-33 M2c-4: ключ `site_defaults.hero_widget` больше нигде не читается.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2c-4». Быстрые ссылки — только блок
«Schnellzugriff» (`quick_links`), форма дат — секция «Suche», топ услуг — секция «Leistungen»
или список. Писатели (шаблоны, сборки, Look, демо-киты) ставят блок сами
(`quick_links_migration.place`) и ключа не пишут; нормализатор ключ роняет; баннер плиток не
рисует ни в одном виде.

* L1 — normalize ключ не держит;
* L2 — баннер всех видов с сырым ключом: плиток нет, кнопка на месте;
* L3 — в шаблонах нет чтения ключа, у `siteui` нет `banner_tiles`;
* L4 — какой набор плиток и где ставит каждый демо-кит (таблица снята ДО правки писателей);
* L5 — выход писателей: ключа нет, блок/секция сразу после баннера;
* L6 — каждый набор рисуется блоком.
"""

import pathlib
import re

import pytest
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.core import hero_tiles
from apps.tenants import siteconfig, sitetemplates
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _squash(html):
    return re.sub(r"\s+", " ", html).strip()


# --- L1: нормализатор ключ не держит -----------------------------------------------------


_C3 = pytest.mark.xfail(strict=True, reason="M2c-4 C3: нормализатор/баннер ещё читают hero_widget")


@pytest.mark.parametrize(
    "widget",
    (
        pytest.param("shop", marks=_C3),
        pytest.param("stays", marks=_C3),
        pytest.param("services", marks=_C3),
        pytest.param("gastro", marks=_C3),
        "nonsense",
        7,
    ),
)
def test_l1_normalize_drops_the_key(widget):
    cfg = siteconfig.normalize({"site_defaults": {"hero_widget": widget, "radius": 8}})
    assert "hero_widget" not in cfg["site_defaults"]


# --- L2: баннер с сырым ключом плиток не рисует -------------------------------------------

#: вид баннера → есть ли у него своя кнопка (у plain кнопки нет вовсе)
STYLES = {
    "plain": False,
    "accent": True,
    "split": True,
    "fullscreen": True,  # без фото рисуется как accent
    "fullscreen-photo": True,
    "bento": True,
    "own_image": True,
    "slider": True,
}


def _raw_hero_site(style):
    raw = {}
    if style == "fullscreen-photo":
        raw = {"hero_style": "fullscreen", "hero_image": "https://x/bg.jpg"}
    elif style == "own_image":
        raw = {"hero_image": "https://x/bg.jpg"}
    elif style == "slider":
        raw = {
            "heroes": [
                {"image": "https://x/1.jpg", "title": "Eins"},
                {"image": "https://x/2.jpg", "title": "Zwei"},
            ]
        }
    elif style != "plain":
        raw = {"hero_style": style}
    cfg = siteconfig.normalize(raw)
    # сырой ключ — ПОСЛЕ нормализации: так его увидел бы шаблон, если бы читал
    cfg["site_defaults"] = {**cfg["site_defaults"], "hero_widget": "shop"}
    return cfg


def _hero_ctx(cfg):
    request = RequestFactory().get("/")
    request.tenant = TenantFactory(business_type="online_shop", disabled_modules=[])
    primary = {"landing": "storefront-products", "label": "Sortiment", "module": "catalog"}
    return {"site": cfg, "request": request, "primary_item": primary, "modules": {}}


@pytest.mark.parametrize(
    "style",
    # bento плиток не рисовал и до M2c-4 — замок держит его рядом с остальными
    [pytest.param(s, marks=_C3) if s != "bento" else s for s in STYLES],
)
def test_l2_banner_draws_no_tiles_from_the_raw_key(style):
    ctx = _hero_ctx(_raw_hero_site(style))
    html = render_to_string("storefront/sections/_hero.html", ctx)
    tiles = _squash(
        render_to_string("storefront/sections/_hero_widget.html", {**ctx, "hero_widget": "shop"})
    )
    assert tiles and tiles not in _squash(html)
    assert "data-hero-tiles" not in html
    if style == "slider":
        assert "data-hero-slider" in html
    if STYLES[style] and style != "slider":
        assert "data-hero-cta" in html


# --- L3: чтения ключа в шаблонах и фильтра больше нет -------------------------------------


@pytest.mark.xfail(strict=True, reason="M2c-4 C3: шаблоны ещё читают hero_widget")
def test_l3_templates_do_not_read_the_key():
    found = sorted(
        str(p.relative_to(ROOT))
        for p in (ROOT / "templates").rglob("*.html")
        if re.search(r"site_defaults\.hero_widget|banner_tiles", p.read_text(encoding="utf-8"))
    )
    assert found == []


@pytest.mark.xfail(strict=True, reason="M2c-4 C3: фильтр banner_tiles ещё есть")
def test_l3_no_banner_tiles_filter():
    from apps.tenants.templatetags import siteui

    assert not hasattr(siteui, "banner_tiles")
    assert not hasattr(siteconfig, "HERO_WIDGETS")


# --- L5: выход писателей -------------------------------------------------------------------


def _rows(cfg):
    return [r for r in cfg.get("sections") or [] if isinstance(r, dict)]


def _after_hero(cfg):
    rows = _rows(cfg)
    keys = [r.get("key") for r in rows]
    at = keys.index("hero") + 1 if "hero" in keys else 0
    return rows[at] if at < len(rows) else {}


def _no_key(cfg):
    assert "hero_widget" not in (cfg.get("site_defaults") or {})


def _check_placed(cfg, widget):
    """Набор плиток писателя стоит сразу после баннера тем, во что он превращается."""
    nxt = _after_hero(cfg)
    if widget in hero_tiles.QUICK_LINK_SETS:
        assert nxt.get("key") == "quick_links" and nxt.get("data") == {"set": widget}
    elif widget == "stays":
        assert nxt.get("key") == "stay_search" and nxt.get("enabled") is True
    elif widget == "services":
        assert nxt.get("key") in ("services", "list")
        if nxt.get("key") == "list":
            assert (nxt.get("data") or {}).get("source") == "services"
    else:
        auto = {"quicklinks", "services3"}
        assert not any(r.get("id") in auto for r in _rows(cfg))


def _same_block(row, block):
    return all(row.get(k) == block[k] for k in ("key", "id", "enabled", "data"))


def _template_widget(tpl):
    return tpl.get("quick_links") or (tpl.get("site_defaults") or {}).get("hero_widget") or ""


@pytest.mark.parametrize("key", [t["key"] for t in sitetemplates.TEMPLATES])
def test_l5_template_places_its_tiles_and_writes_no_key(key):
    tenant = TenantFactory(business_type="hotel", disabled_modules=[])
    assert sitetemplates.apply_template(tenant, key)
    cfg = tenant.site_config
    _no_key(cfg)
    _check_placed(cfg, _template_widget(sitetemplates.get_template(key)))


def _bundle_widget(bundle):
    widget = bundle["config"].get("hero_widget") or ""
    return "" if widget == "none" else widget


@pytest.mark.parametrize("rebuild", (True, False))
@pytest.mark.parametrize("key", [b["key"] for b in sitetemplates.BUNDLES])
def test_l5_bundle_places_its_tiles_and_writes_no_key(key, rebuild):
    bundle = sitetemplates.get_bundle(key)
    btype = (bundle["recommended_for"] or ("retail",))[0]
    tenant = TenantFactory(business_type=btype, disabled_modules=[])
    owner = {"key": "quick_links", "id": "own", "enabled": True, "data": {"set": "shop"}}
    tenant.site_config = {"sections": [{"key": "hero", "enabled": True}, owner]}
    tenant.save()
    assert sitetemplates.apply_bundle(tenant, key, rebuild_home=rebuild)
    cfg = tenant.site_config
    _no_key(cfg)
    if rebuild:
        widget = _bundle_widget(bundle)
        if widget in hero_tiles.QUICK_LINK_SETS:
            assert _after_hero(cfg)["data"] == {"set": widget}
        elif widget:
            _check_placed(cfg, widget)
    else:
        # без перестройки главной — только вид: блок владельца на месте и с его набором
        assert _same_block(_after_hero(cfg), owner)
    preview = sitetemplates.apply_preview_bundle(siteconfig.normalize({}), key)
    _no_key(preview)


@pytest.mark.parametrize("family", [f["key"] for f in sitetemplates.LOOK_FAMILIES])
def test_l5_look_writes_no_key_and_keeps_the_block(family):
    tenant = TenantFactory(business_type="cafe", disabled_modules=[])
    owner = {"key": "quick_links", "id": "own", "enabled": True, "data": {"set": "gastro"}}
    tenant.site_config = {"sections": [{"key": "hero", "enabled": True}, owner]}
    tenant.save()
    assert sitetemplates.apply_look(tenant, family)
    _no_key(tenant.site_config)
    assert _same_block(_after_hero(tenant.site_config), owner)


# --- L6: каждый набор рисуется блоком ------------------------------------------------------


@pytest.mark.parametrize("link_set", hero_tiles.QUICK_LINK_SETS)
def test_l6_every_link_set_is_drawn_by_the_block(link_set):
    request = RequestFactory().get("/")
    request.tenant = TenantFactory(business_type="online_shop", disabled_modules=[])
    tpl = Template("{% load siteui %}{% render_block b %}")
    block = {"key": "quick_links", "id": "q1", "data": {"set": link_set}}
    ctx = {"request": request, "site": siteconfig.normalize({}), "modules": {}, "b": block}
    html = tpl.render(Context(ctx))
    assert "data-block-quick-links" in html
    assert re.search(r'href="/', html), f"{link_set}: блок без ссылок"


# --- L4: что ставит каждый демо-кит (снято на коде ДО M2c-4, 2026-11-20) ------------------

#: кит → набор плиток первого экрана; остальные киты плиток не ставят. Снято полным
#: `apply_kit` всех китов: блок/секция сразу после баннера итогового `site_config`.
KIT_TILES = {
    "aktionsmarkt": "aktionsmarkt",  # патч кита побеждает «none» сборки (DL-4)
    "pranasy": "gastro",
    "friseur": "services",  # ось сборки побеждает набор кита
    "werkstatt": "services",
    "hotel": "stays",
}
#: кит → что стоит сразу после баннера (ключ, id, включён, данные блока)
KIT_AFTER_HERO = {
    "aktionsmarkt": ("quick_links", "quicklinks", True, {"set": "aktionsmarkt"}),
    "pranasy": ("quick_links", "quicklinks", True, {"set": "gastro"}),
    "friseur": ("services", None, True, None),
    "werkstatt": ("services", None, True, None),
    "hotel": ("stay_search", None, True, None),
    "butcher": ("categories", None, True, None),  # сборка «none» снимает набор кита
    "cafe": ("categories", None, False, None),  # патч "" снимает набор кита
}


def _kit_widget(kit):
    """Набор кита: патч кита > ось сборки > `kit.hero_widget` (до M2c-4 — тем же порядком
    через ключ-переносчик)."""
    patch = ((kit.config_patch or {}).get("site_defaults") or {}) if kit.config_patch else {}
    if "hero_widget" in patch:
        return patch["hero_widget"] or ""
    bundle = sitetemplates.get_bundle(kit.bundle) if kit.bundle else None
    if bundle is not None and bundle["config"].get("hero_widget"):
        widget = bundle["config"]["hero_widget"]
        return "" if widget == "none" else widget
    return kit.hero_widget if kit.hero_widget in siteconfig.HERO_WIDGETS else ""


def test_l4_every_kit_places_the_same_tiles():
    from apps.tenants.demo_kits import KITS

    got = {key: _kit_widget(kit) for key, kit in KITS.items() if _kit_widget(kit)}
    assert got == KIT_TILES


@pytest.mark.parametrize("key", sorted(KIT_AFTER_HERO))
def test_l4_applied_kit_has_the_frozen_row_after_the_banner(key):
    from apps.tenants import demo_kits

    kit = demo_kits.KITS[key]
    tenant = TenantFactory(
        schema_name="public", slug="k4", name="K4", business_type=kit.business_type
    )
    assert demo_kits.apply_kit(tenant, key)
    cfg = tenant.site_config
    nxt = _after_hero(cfg)
    data = nxt.get("data") if nxt.get("key") in ("quick_links", "list") else None
    assert (nxt.get("key"), nxt.get("id"), nxt.get("enabled"), data) == KIT_AFTER_HERO[key]
    assert not (cfg.get("site_defaults") or {}).get("hero_widget")
