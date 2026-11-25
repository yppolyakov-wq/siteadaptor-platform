"""FB-33 стопка 15 M5e-3: своя схема категории даёт те же окна, что общая страница категории,
и S14-E2-ghost (ссылки Студии в окно — только у живых страниц).

План — `docs/fb33-stack15-plan-2026-11-25.md` §0.1 №4, §0.2 «M5eKategorie», §1 «Своя
категория» и «Ghost», §2 и §4 «M5e-3», §14.1 A8 (первая ось своей схемы не роняет прочие —
унаследованные оси записываются `catalog_parts.write_rows`), A13 (живая ли страница — через
`site_schema.host_for(code, known_slugs=)`, второго списка нет). Плюс публичный
`site_schema.main_list_source(host)` (из M5e-2a).
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


# --- M5e-2a: публичный источник основного списка --------------------------------------------------


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


# --- ревью 1 -----------------------------------------------------------------------------------


def _all_literals(path: Path) -> list[str]:
    """Все места литерала («catalog», «category») в модуле: функция:строка."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Tuple) and {getattr(e, "value", None) for e in sub.elts} == {
                    "catalog",
                    "category",
                }:
                    found.append(node.name)
    return found


def test_catalog_literal_only_in_predicates():
    """Ревью 1 №4: литерал («catalog», «category») — только в предикате «общая страница
    каталога» (не своя схема категории); «страница каталога» строится на нём."""
    left = _all_literals(ROOT / "apps/tenants/siteconfig.py") + _all_literals(
        ROOT / "apps/core/site_schema.py"
    )
    assert left == ["is_shared_catalog_host"], left  # `is_catalog_host` зовёт его
    assert siteconfig.is_shared_catalog_host("catalog")
    assert siteconfig.is_shared_catalog_host("category")
    assert not siteconfig.is_shared_catalog_host(OWN)


def test_no_connection_tenant_in_site_schema():
    """Ревью 1 №1 (b): схема не берёт бизнес из соединения — конфиг передаётся явно."""
    src = (ROOT / "apps/core/site_schema.py").read_text(encoding="utf-8")
    assert "connection.tenant" not in src and 'getattr(connection, "tenant"' not in src


def test_a8_uses_passed_config_not_connection(monkeypatch):
    """Ревью 1 №1 (a): правка через черновик (`Browser`) при чужом `connection.tenant` —
    унаследованные оси из конфига бизнеса запроса."""
    from apps.catalog.models import Category

    other = TenantFactory(business_type="online_shop", disabled_modules=[])
    tenant = _tenant({OWN: [_text_block()]})
    _set_rows(
        tenant,
        "category",
        [{"key": siteconfig.CATALOG_HEAD_KEY, "style": "titelbild"}, {"key": "main"}],
    )
    for foreign in (other, None):
        connection.tenant = foreign
        b = Browser(tenant)
        b.post(seite=OWN_CODE, op="catview", ref="categories", value="index")
        b.post(seite=OWN_CODE, op="save")
        tenant.refresh_from_db()
        parts = catalog_parts.category_parts(tenant.site_config, Category.objects.get(slug="brot"))
        assert parts.head == "titelbild" and parts.categories == "index", foreign
        _set_rows(tenant, OWN, [_text_block()])


def test_a8_without_config_refuses():
    """Ревью 1 №1: без конфига ось своей схемы не пишется — отказ, а не тихая потеря осей."""
    tenant = _tenant({OWN: [_text_block()]})
    items = site_schema.load_items(tenant.site_config, False, OWN)
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, OWN_CODE, "catview", "categories", value="index")


def test_a8_freezes_saved_shared_not_saved_own():
    """Ревью 1 №1 (c): своя схема со своими осями в базе, в черновике их сняли — первая ось
    берёт видимое СЕЙЧАС на общей странице категорий (сохранённое), не старые свои оси."""
    tenant = _tenant()
    _set_rows(tenant, "category", [{"key": siteconfig.CATALOG_HEAD_KEY, "style": "titelbild"}])
    _set_rows(
        tenant,
        OWN,
        [{"key": siteconfig.CATALOG_HEAD_KEY, "style": "aus"}, _text_block()],
    )
    items = [{"key": "main"}, {"key": "categories"}, _text_block()]  # черновик без осей
    site_schema.mutate(
        items, OWN_CODE, "catview", "categories", value="index", config=tenant.site_config
    )
    parts = catalog_parts.from_rows(items)
    assert parts.head == "titelbild" and parts.categories == "index", items


def test_inherit_returns_row_or_raises():
    """Ревью 1 №1: после записи осей строка `ref` находится — иначе отказ."""
    tenant = _tenant()
    items = [{"key": "main"}, _text_block()]
    row = site_schema._inherit_catalog_axes(items, OWN, "categories", tenant.site_config)
    assert row is not None and row in items and row["key"] == "categories"
    items = [{"key": "main"}, _text_block()]
    with pytest.raises(site_schema.SchemaError):
        site_schema._inherit_catalog_axes(items, OWN, "nope", tenant.site_config)


def test_known_slugs_for_db_error_logs_and_falls_back(monkeypatch, caplog):
    """Ревью 1 №2: сбой загрузки слагов — предупреждение в журнал и None (вызывающий проверяет
    страницу по одной), ссылка живой категории остаётся."""
    import logging

    from django.db import DatabaseError

    from apps.catalog.models import Category
    from apps.core.tests.test_fb33_e2_studio_links import _anchors, _page_part, _studio

    tenant = _tenant({OWN: [_liste("l2")]})

    def boom(*a, **kw):
        raise DatabaseError("boom")

    monkeypatch.setattr(Category.objects, "values_list", boom)
    with caplog.at_level(logging.WARNING, logger="apps.core.site_schema"):
        assert site_schema.known_slugs_for(OWN_CODE) is None
        html = _studio(tenant)
    assert any(r.exc_info for r in caplog.records if r.levelno == logging.WARNING)
    assert _anchors(_page_part(html, OWN), "Fenster öffnen")


def test_live_groups_db_error_falls_back(monkeypatch, caplog):
    """Ревью 1 №2: сбой загрузки групп акций — None и предупреждение, не «все группы мертвы»."""
    import logging

    from django.db import DatabaseError

    def boom():
        raise DatabaseError("boom")

    monkeypatch.setattr(site_schema, "_live_promo_groups", boom)
    with caplog.at_level(logging.WARNING, logger="apps.core.site_schema"):
        code = f"{site_schema.PROMO_GROUP}@{siteconfig.promo_group_host('Sale')}"
        assert site_schema.known_slugs_for(code) is None
    assert caplog.records


def test_deleted_category_parts_warn(caplog):
    """Ревью 1 №3: категории своей схемы нет — свои строки и предупреждение в журнал."""
    import logging

    tenant = _tenant()
    with caplog.at_level(logging.WARNING, logger="apps.core.site_schema"):
        site_schema.catalog_seen_parts(tenant.site_config, "catalog:weg")
    assert any("catalog:weg" in r.getMessage() for r in caplog.records)


def test_has_combos_db_error_shows_row(monkeypatch):
    """Ревью 1 №3: сбой проверки наборов — строка «Sets & Menüs» видна (не прячется молча)."""
    from django.db import DatabaseError

    from apps.catalog.models import Combo

    def boom():
        raise DatabaseError("boom")

    monkeypatch.setattr(Combo.objects, "exists", boom)
    assert site_schema._has_combos() is True


def test_every_main_list_host_has_source_or_own_name():
    """Ревью 1 №3: у каждого хоста основного списка — источник «Liste» или своё имя."""
    for host in siteconfig.MAIN_LIST_HOSTS:
        assert site_schema.main_list_source(host) or host in site_schema._MAIN_LIST_OWN_NAMES, host


def test_catalog_code_only_shared_hosts(monkeypatch):
    """Ревью 1 №4: `_catalog_code` (код шаблона общей страницы) своей схеме не нужен."""
    seen = []
    real = site_schema._catalog_code

    def spy(config, host):
        seen.append(host)
        return real(config, host)

    monkeypatch.setattr(site_schema, "_catalog_code", spy)
    tenant = _tenant({OWN: [_text_block()]})
    for code in ("catalog", "category", OWN_CODE):
        site_schema.blocks_for(tenant.site_config, code, tenant=tenant, has_combos=True)
    assert seen and set(seen) <= {"catalog", "category"}, seen


def test_slug_case_kept():
    """Ревью 1 №4: регистр слага не меняется — хост и категория находят друг друга."""
    tenant = _tenant({"catalog:Sommer_2026": [_text_block()]}, slugs=("Sommer_2026",))
    code = "category@catalog:Sommer_2026"
    assert site_schema.host_for(code) == "catalog:Sommer_2026"
    assert site_schema.host_for(code, known_slugs=site_schema.known_slugs_for(code))
    assert "categories" in _refs(tenant, code)
