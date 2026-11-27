"""FB-33 M5d-0: замок скрипта инвентаризации окон блоков `scripts/fb33_m5d_inventory.py`.

План стопки 10 §4 «C. M5d-0», §8.1 A-H4: ответ «окно есть / нет» берётся из разметки вьюхи
экрана (то, что видит владелец), а не из `blocks_for + block_window.tabs` — вкладки зависят от
декораторов вьюхи (`site_schema_views`), без них окна «Kaufen» (🔒, `legal_buttons`) и
«Ähnliche Produkte» (строка раздела со своими настройками) пропали бы.

(а) ответ скрипта = разметка окна вьюхи на фикстуре: главная `about` («Platz») — окно есть;
    товар `description` — есть (часть «Inhalt», M5d-4a), раздел без источника — нет; товар
    `kauf` и `related` — есть, хотя «наивный» счёт без вьюхи
    говорит «нет» (фикстура различает подмену);
(б) скрипт не держит своего списка видов блоков (ast: ни одной строки-ключа блока);
    страницы и строки — те же, что у стенда владельца (`DUMP` `fb33_m3_9_owner_stand.py`);
(в) непостроенная страница или окно — строкой «пропущено: причина», не молча.
"""

import ast
import contextlib
import dataclasses
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.core import block_window, detail_sections, site_schema
from apps.core.modules import default_disabled_for
from apps.core.site_schema_views import site_schema_view
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "fb33_m5d_inventory.py"
OWNER_STAND = ROOT / "scripts" / "fb33_m3_9_owner_stand.py"
CODES = {"home", "product"}


def _script():
    spec = importlib.util.spec_from_file_location("fb33_m5d_inventory", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core import view_perms

    # владелец (у заглушки пользователя членства нет), как `test_fb27_r2_draft.Browser`
    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant():
    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    connection.tenant = tenant
    Product.objects.create(name={"de": "Darjeeling", "en": ""}, base_price="9.90")
    return tenant


def view_fetch(tenant):
    """fetch(code, ref) — ответ самой вьюхи экрана (RequestFactory, как `Browser`)."""

    def fetch(code, ref=""):
        query = {"seite": code, **({"block": ref} if ref else {})}
        req = RequestFactory().get("/dashboard/site/aufbau/", query)
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = SimpleNamespace(is_authenticated=True)
        tenant.refresh_from_db()
        req.tenant = tenant
        resp = site_schema_view(req)
        return resp.status_code, resp.content.decode()

    return fetch


def _lines(tenant, fetch=None, codes=CODES):
    return _script().inventory(tenant, fetch or view_fetch(tenant), codes=codes)


def _by(lines, code, key):
    found = [ln for ln in lines if ln["code"] == code and ln["key"] == key]
    assert found, f"нет строки {code} {key}: {[(ln['code'], ln['key']) for ln in lines]}"
    return found[0]


def _block(tenant, code, key) -> dict:
    saved = siteconfig.normalize(tenant.site_config)
    return next(b for b in site_schema.blocks_for(saved, code, tenant=None) if b["key"] == key)


def _naive(tenant, code, key) -> bool:
    """Подмена, от которой замок защищает: `blocks_for + tabs` без декораторов вьюхи."""
    block = _block(tenant, code, key)
    return bool(block_window.tabs(block, {"settings": [], "design_rows": []}, ""))


# --- (а) ответ скрипта = разметка вьюхи ------------------------------------------------------


def _bare_section(monkeypatch, key="recent"):
    """Раздел товара без источника — строка «без окна» (план стопки 12 §10 A8: после M5d-4a у
    разделов товара окно «Inhalt» есть, негативный пример задаёт фикстура)."""
    monkeypatch.setitem(
        detail_sections.DETAIL_SECTIONS,
        "catalog",
        tuple(
            dataclasses.replace(s, source=None, content_nav="") if s.key == key else s
            for s in detail_sections.DETAIL_SECTIONS["catalog"]
        ),
    )
    return key


def test_window_answer_follows_the_view_markup(monkeypatch):
    tenant = _tenant()
    bare = _bare_section(monkeypatch)
    lines = _lines(tenant)
    assert not [ln for ln in lines if ln.get("skipped")]
    about = _by(lines, "home", "about")
    assert about["window"] is True and "wie" in about["tabs"]  # «Platz» главной
    desc = _by(lines, "product", "description")
    assert desc["window"] is True and desc["tabs"] == ["was"]  # M5d-4a: часть «Inhalt»
    none = _by(lines, "product", bare)
    assert none["window"] is False and none["tabs"] == []
    for key in ("kauf", "related"):
        line = _by(lines, "product", key)
        assert line["window"] is True and line["tabs"], line


def test_fixture_tells_the_view_from_the_naive_count():
    """Окна «Kaufen» и «Ähnliche» есть только у вьюхи: подмена на `blocks_for + tabs` даст «нет»
    — тогда `test_window_answer_follows_the_view_markup` падает."""
    tenant = _tenant()
    assert _naive(tenant, "product", "kauf") is False
    assert _naive(tenant, "product", "related") is False
    assert _naive(tenant, "product", "description") is False


def test_window_tabs_reads_the_panel_of_the_view(monkeypatch):
    tenant = _tenant()
    bare = _bare_section(monkeypatch)
    fetch = view_fetch(tenant)
    window_tabs = _script().window_tabs
    _status, html = fetch("product", _block(tenant, "product", "kauf")["ref"])
    assert window_tabs(html) == ["texte"]
    _status, html = fetch("product", _block(tenant, "product", "description")["ref"])
    assert window_tabs(html) == ["was"] and 'value="window_done"' in html
    _status, html = fetch("product", _block(tenant, "product", bare)["ref"])
    assert window_tabs(html) is None
    assert 'value="window_done"' not in html  # тот же признак, что `aufbauWindowWanted`


# --- (б) свой список видов не держит; страницы — как у стенда владельца -----------------------


def _block_keys() -> set[str]:
    keys = {s.key for sections in detail_sections.DETAIL_SECTIONS.values() for s in sections}
    keys |= {item[0] for item in siteconfig.SECTIONS}
    keys |= set(siteconfig.REPEATABLE_BLOCKS)
    return keys


def _string_constants(tree) -> set[str]:
    docs = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
    }


def test_script_keeps_no_list_of_block_kinds():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    keys = _block_keys()
    assert {"description", "about", "faq"} <= keys  # реестр собран
    leaked = sorted(_string_constants(tree) & keys)
    assert not leaked, f"скрипт держит ключи блоков: {leaked}"
    # ответ — из разметки вьюхи (A-H4): `block_window` скрипт не импортирует и не зовёт
    names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert "block_window" not in names and "apps.core.block_window" not in names
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "tabs"]
    # признак окна — как у aufbau.js и стенда владельца
    assert 'value="window_done"' in _string_constants(tree)


def test_pages_and_rows_match_the_owner_stand():
    """`schema_pages` + `page_blocks` скрипта = страницы и строки `DUMP` стенда владельца."""
    tenant = _tenant()
    mod = _script()
    saved = siteconfig.normalize(tenant.site_config)
    mine = {
        r.code: [b["ref"] for b in mod.page_blocks(tenant, saved, r)]
        for r in mod.schema_pages(tenant, saved)
    }
    tree = ast.parse(OWNER_STAND.read_text(encoding="utf-8"))
    dump = next(
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DUMP"
    )
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(f"SLUGS = {[tenant.slug]!r}\n" + dump, {})  # noqa: S102 — код стенда из репозитория
    connection.tenant = tenant
    theirs = json.loads(out.getvalue().rsplit("@@JSON@@", 1)[1])[tenant.slug]["pages"]
    assert {p["code"]: p["refs"] for p in theirs} == mine
    assert any(site_schema.is_object_code(c) for c in mine)  # строка «Nur diese Seite» есть


# --- (в) непостроенное — строкой «пропущено» --------------------------------------------------


def test_unbuilt_page_is_a_skipped_line():
    tenant = _tenant()
    real = view_fetch(tenant)

    def fetch(code, ref=""):
        if code == "home":
            return 500, ""
        if ref == "description":
            return 200, "<main>без панели</main>"
        return real(code, ref)

    lines = _lines(tenant, fetch)
    home = [ln for ln in lines if ln["code"] == "home"]
    assert len(home) == 1 and "500" in home[0]["skipped"] and home[0]["ref"] == ""
    desc = _by(lines, "product", "description")
    assert "панели" in desc["skipped"] and "window" not in desc
    summary = _script().summarize(lines)
    assert summary["total"]["skipped"] == 2
    md = _script().markdown(summary)
    assert "пропущено: экран страницы: ответ 500" in md


def test_schema_error_and_view_crash_are_skipped_lines(monkeypatch):
    tenant = _tenant()
    mod = _script()

    def boom(code, ref=""):
        if ref:
            raise RuntimeError("вьюха упала")
        raise site_schema.SchemaError("нет страницы")

    lines = mod.inventory(tenant, boom, codes={"product"})
    assert [ln["skipped"] for ln in lines] == ["нет страницы"]
    monkeypatch.setattr(mod, "page_blocks", lambda *a: [{"ref": "x", "key": "x", "label": ""}])
    lines = mod.inventory(tenant, lambda c, r="": (200, "") if not r else boom(c, r), codes=CODES)
    assert lines and all("RuntimeError: вьюха упала" in ln["skipped"] for ln in lines)


def test_missing_business_is_a_skipped_line():
    lines = _script().run(["nicht-da"])
    assert lines == [{"kit": "nicht-da", "code": "", "ref": "", "skipped": "нет бизнеса"}]


# --- (г) S15-catering-302: потерянная сессия — не «пропущено: ответ 302» -----------------------
# Причина 302 кейтеринга (стопка 16, K1): хук сессии экспортирует `REDIS_CACHE_URL=…/1` — ту же
# базу, что у pytest без xdist (`cache.clear()` = FLUSHDB), — и запасная база стенда `/2`
# (`config/settings/stand.py`) не включается. Сессия владельца стиралась посреди прогона.


def test_inventory_refuses_shared_redis_db():
    mod = _script()
    for shared in ("redis://localhost:6379/1", "redis://127.0.0.1:6379/1/"):
        with pytest.raises(SystemExit, match="REDIS_CACHE_URL"):
            mod.refuse_shared_cache(shared)
    for own in (
        "redis://localhost:6379/9",
        "redis://localhost:6379/2",
        "redis://localhost:6379/11",
    ):
        mod.refuse_shared_cache(own)  # своя база — без отказа


class _Resp:
    def __init__(self, status, location=""):
        self.status_code = status
        self.content = b""
        self._headers = {"Location": location} if location else {}

    def get(self, name, default=None):
        return self._headers.get(name, default)


class _Client:
    def __init__(self, resp):
        self.resp = resp

    def get(self, path, query):
        return self.resp


def test_redirect_to_login_is_a_lost_session():
    mod = _script()
    fetch = mod.client_fetch(_Client(_Resp(302, "/accounts/login/?next=/dashboard/site/aufbau/")))
    with pytest.raises(mod.SessionLostError, match="сессия потеряна"):
        fetch("home")
    # 302 не на вход — по-прежнему ответ вьюхи (строка «пропущено: ответ 302»)
    assert mod.client_fetch(_Client(_Resp(302, "/dashboard/")))("home")[0] == 302


def test_lost_session_stops_the_kit_with_its_own_line(monkeypatch):
    tenant = _tenant()
    mod = _script()

    def lost(code, ref=""):
        raise mod.SessionLostError("сессия потеряна: 302 → вход")

    with pytest.raises(mod.SessionLostError):  # не строка «пропущено» на каждую страницу
        mod.inventory(tenant, lost, codes=CODES)
    monkeypatch.setattr(
        mod,
        "owner_client",
        lambda *a: SimpleNamespace(session=SimpleNamespace(delete=lambda: None)),
    )
    monkeypatch.setattr(mod, "client_fetch", lambda client: lost)
    lines = mod.run([tenant.slug])
    assert lines[-1]["skipped"].startswith("сессия потеряна"), lines[-1]
    assert mod.main_exit_code(lines) == 1
