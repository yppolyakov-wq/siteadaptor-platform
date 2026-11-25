"""FB-33 стопка 15 M5e-3: своя схема категории даёт те же окна, что общая страница категории,
и S14-E2-ghost (ссылки Студии в окно — только у живых страниц).

План — `docs/fb33-stack15-plan-2026-11-25.md` §0.1 №4, §0.2 «M5eKategorie», §1 «Своя
категория» и «Ghost», §2 и §4 «M5e-3», §14.1 A8 (первая ось своей схемы не роняет прочие —
унаследованные оси записываются `catalog_parts.write_rows`), A13 (живая ли страница — через
`site_schema.host_for(code, known_slugs=)`, второго списка нет). Плюс публичный
`site_schema.main_list_source(host)` (TODO M5e-2a).
"""

import ast
import copy
from decimal import Decimal
from pathlib import Path

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog import catalog_parts
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.core import site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import _capture
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
OWN = "catalog:brot"
OWN_CODE = f"category@{OWN}"


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    from apps.core import page_settings

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(page_settings, "_storefront_shows", lambda tenant, code: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(page_blocks=None, slugs=("brot",)):
    tenant = TenantFactory(business_type="online_shop", disabled_modules=[])
    tenant.site_config = {**(tenant.site_config or {}), "page_blocks": page_blocks or {}}
    tenant.save()
    connection.tenant = tenant
    for slug in slugs:
        ProductFactory(category=CategoryFactory(slug=slug, name={"de": slug.title()}))
    return tenant


def _text_block(ref="t1abc"):
    return {"key": "text", "id": ref, "enabled": True, "data": {"title": "X", "body": "Y"}}


def _refs(tenant, code):
    return [b["ref"] for b in site_schema.blocks_for(tenant.site_config, code, tenant=tenant)]


def _window(tenant, code, ref):
    _html, _view, selected = _capture(Browser(tenant), f"?seite={code}&block={ref}")
    return selected or {}


# --- №2/№3: один предикат ------------------------------------------------------------------------


def _literals(path: Path, funcs: set[str]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in funcs:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Tuple) and {getattr(e, "value", None) for e in sub.elts} == {
                    "catalog",
                    "category",
                }:
                    found.append(f"{node.name}:{sub.lineno}")
    return found


def test_one_catalog_predicate():
    """№2/№3: «страница каталога» — один предикат `siteconfig.is_catalog_host`; в местах плана
    литерала («catalog», «category») больше нет."""
    assert siteconfig.is_catalog_host("catalog") and siteconfig.is_catalog_host("category")
    assert siteconfig.is_catalog_host(OWN) and siteconfig.is_catalog_host("catalog:brot-2")
    for no in ("catalogx", "catalog:", "promos", "", None, "category:x", 3):
        assert not siteconfig.is_catalog_host(no), no
    left = _literals(
        ROOT / "apps/tenants/siteconfig.py",
        {"page_builtin_keys", "part_styles", "main_list_sequence"},
    ) + _literals(ROOT / "apps/core/site_schema.py", {"blocks_for"})
    assert not left, left


# --- №5, №6: те же окна -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    [
        OWN,
        "catalog:brot-2",
        "category",  # охранный: общая страница — как была
    ],
)
def test_own_host_exact(host):
    """№5: строки каталога («Banner · Fotos der Seite», «Kategorien», ★) — у общей страницы
    категорий и у своей схемы КАЖДОЙ категории; правка одной своей схемы не видна у другой."""
    tenant = _tenant({OWN: [_text_block()]}, slugs=("brot", "brot-2"))
    code = "category" if host == "category" else f"category@{host}"
    refs = _refs(tenant, code)
    for ref in (siteconfig.CATALOG_HEAD_KEY, "categories", "main"):
        assert ref in refs, (host, refs)
    assert ("t1abc" in refs) == (host == OWN), refs


@pytest.mark.parametrize("ref", ["page_head", "combos", "categories", "main"])
def test_own_category_windows_equal_shared(ref):
    """№6: окно строки своей схемы — то же, что у общей страницы категорий (имя, вид, плитки)."""
    from apps.catalog.models import Combo

    tenant = _tenant({OWN: [_text_block()]})
    Combo.objects.create(name="Menü 1", price=Decimal("9.90"))
    shared, own = _window(tenant, "category", ref), _window(tenant, OWN_CODE, ref)
    assert shared, ref
    for key in ("label", "pinned", "catview", "mainview"):
        assert own.get(key) == shared.get(key), (ref, key, own.get(key), shared.get(key))


def _set_rows(tenant, host, rows):
    cfg = copy.deepcopy(tenant.site_config)
    cfg.setdefault("page_blocks", {})[host] = rows
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save()


def test_own_without_parts_follows_storefront():
    """№6: своя схема без осей — витрина берёт оси «Alle Kategorien» (`category_host`); окно
    показывает их же. С осями — свои."""
    tenant = _tenant({OWN: [_text_block()]})
    _set_rows(tenant, "category", [{"key": "categories", "style": "tabs", "enabled": True}])
    from apps.catalog.models import Category

    category = Category.objects.get(slug="brot")
    want = catalog_parts.category_parts(tenant.site_config, category).categories
    assert want == "tabs"
    assert _window(tenant, OWN_CODE, "categories")["catview"]["value"] == "tabs"
    _set_rows(
        tenant, OWN, [{"key": "categories", "style": "index", "enabled": True}, _text_block()]
    )
    assert catalog_parts.category_parts(tenant.site_config, category).categories == "index"
    assert _window(tenant, OWN_CODE, "categories")["catview"]["value"] == "index"


def test_sets_row_only_with_combos():
    """§0.1 №4: «Sets & Menüs» своей схемы — только если у бизнеса есть наборы."""
    from apps.catalog.models import Combo

    tenant = _tenant({OWN: [_text_block()]})
    assert siteconfig.CATALOG_SETS_KEY not in _refs(tenant, OWN_CODE)
    Combo.objects.create(name="Menü 1", price=Decimal("9.90"))
    assert siteconfig.CATALOG_SETS_KEY in _refs(tenant, OWN_CODE)


# --- A8: первая ось своей схемы ------------------------------------------------------------------


@pytest.mark.parametrize(
    "op,ref,value", [("catview", "categories", "index"), ("mainview", "main", "magazin")]
)
def test_first_axis_on_own_category_keeps_other_parts(op, ref, value):
    """A8: первая правка оси своей схемы переключает витрину на свой хост — прочие оси, что
    посетитель видел из «Alle Kategorien», остаются (записываются явно)."""
    from apps.catalog.models import Category

    tenant = _tenant({OWN: [_text_block()]})
    _set_rows(
        tenant,
        "category",
        [
            {"key": siteconfig.CATALOG_HEAD_KEY, "style": "titelbild"},
            {"key": "categories", "style": "tabs", "enabled": True},
            {"key": "main", "style": "schaufenster"},
        ],
    )
    category = Category.objects.get(slug="brot")
    before = catalog_parts.category_parts(tenant.site_config, category)
    assert before.head == "titelbild" and before.categories == "tabs"
    site_schema.apply(tenant, OWN_CODE, op, ref, value=value)
    tenant.refresh_from_db()
    after = catalog_parts.category_parts(tenant.site_config, category)
    assert catalog_parts.category_host(tenant.site_config, category) == OWN
    changed = {"catview": "categories", "mainview": "products"}[op]
    assert getattr(after, changed) == value
    for axis in ("head", "categories", "products", "sets"):
        if axis != changed:
            assert getattr(after, axis) == getattr(before, axis), axis
    refs = [r.get("id") or r.get("key") for r in siteconfig.page_rows(tenant.site_config, OWN)]
    assert "t1abc" in refs  # свой блок остался


# --- №31: один запрос категории ------------------------------------------------------------------


def test_one_category_query():
    """№31: строки своей схемы ищут категорию один раз на `blocks_for`."""
    tenant = _tenant({OWN: [_text_block()]})
    with CaptureQueriesContext(connection) as q:
        # хост экран уже знает (`resolve`) — как у вьюхи схемы
        site_schema.blocks_for(
            tenant.site_config, OWN_CODE, host=OWN, tenant=tenant, has_combos=False
        )
    hits = [x["sql"] for x in q.captured_queries if "catalog_category" in x["sql"]]
    assert len(hits) == 1, hits


# --- Ghost (S14-E2-ghost), A13 ----------------------------------------------------------------------


def _liste(ref):
    return {"key": "list", "id": ref, "enabled": True, "data": {"source": "events", "title": ""}}


def test_deleted_category_no_window_url():
    """Ghost: у блоков удалённой категории (хост остался в конфиге) ссылки в окно нет; у живой
    — есть."""
    from apps.core.tests.test_fb33_e2_studio_links import _anchors, _page_part, _studio

    tenant = _tenant({OWN: [_liste("l2")], "catalog:weg": [_liste("l3")]})
    html = _studio(tenant)
    assert _anchors(_page_part(html, OWN), "Fenster öffnen")
    assert not _anchors(_page_part(html, "catalog:weg"), "Fenster öffnen")


def test_window_url_opens_that_block():
    """Ghost, сквозной: адрес «Fenster öffnen» открывает окно ЭТОГО блока."""
    from urllib.parse import urlsplit

    from apps.core.tests.test_fb33_e2_studio_links import _anchors, _href, _page_part, _studio

    tenant = _tenant({OWN: [_liste("l2")], "catalog:weg": [_liste("l3")]})
    (fenster,) = _anchors(_page_part(_studio(tenant), OWN), "Fenster öffnen")
    url = urlsplit(_href(fenster[0]))
    _html, _view, selected = _capture(Browser(tenant), f"?{url.query}")
    assert selected and selected["ref"] == "l2"


def test_ghost_check_constant_queries(monkeypatch):
    """№31, A13: проверка «страница жива» — слаги загружаются один раз на тип подстраниц (не на
    каждый хост), `host_for` получает их готовыми. (Строка ★ каждого хоста Студии стоит свой
    запрос и раньше — `_main_list_row` → `page_row_ref`; это не проверка призраков.)"""
    from apps.core.tests.test_fb33_e2_studio_links import _studio

    tenant = _tenant()
    blocks = {f"catalog:g{i}": [_liste(f"l{i}")] for i in range(4)}
    _set_rows(tenant, OWN, [_liste("l0x")])
    cfg = copy.deepcopy(tenant.site_config)
    cfg["page_blocks"] = {OWN: [_liste("l0x")], "seite:x": [_liste("l9")], **blocks}
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save()
    loads, checks = [], []
    real_known, real_host_for = site_schema.known_slugs_for, site_schema.host_for

    def known(code):
        loads.append(code.split("@", 1)[0])
        return real_known(code)

    def host_for(code, known_slugs=None, live_groups=None):
        checks.append(known_slugs is not None or live_groups is not None)
        return real_host_for(code, known_slugs=known_slugs, live_groups=live_groups)

    monkeypatch.setattr(site_schema, "known_slugs_for", known)
    monkeypatch.setattr(site_schema, "host_for", host_for)
    with CaptureQueriesContext(connection) as q:
        _studio(tenant)
    assert sorted(loads) == ["category", "text"], loads
    assert checks.count(True) == 6  # каждый хост подстраницы — с готовыми слагами
    slug_reads = [x for x in q.captured_queries if 'SELECT "catalog_category"."slug"' in x["sql"]]
    assert len(slug_reads) == 1


# --- TODO M5e-2a: публичный источник основного списка --------------------------------------------


def test_main_list_source_public():
    """`site_schema.main_list_source(host)` — источник «Liste» основного списка; `main_list_name`
    и `window_parts.main_list_screen` берут его (частных имён `site_schema` снаружи нет)."""
    want = {
        "catalog": "products",
        "category": "products",
        OWN: "products",
        "promos": "promotions",
        "services": "services",
        "stay_rooms": "stays",
        "combos": "combos",
        "reviews": "reviews",
        "team": "",
        "gallery": "",
        "cart": "",
        "": "",
    }
    for host, source in want.items():
        assert site_schema.main_list_source(host) == source, host
    src = (ROOT / "apps/core/window_parts.py").read_text(encoding="utf-8")
    assert "site_schema._" not in src
