"""FB-33 стопка 14 E8: имя главного списка — в самом `blocks_for`, тенант обязателен.

План — `docs/fb33-stack14-plan-2026-11-24.md` §2 E8, §4 E8, §10 (architect H6). Раньше
`blocks_for` тенанта не знал, и «Menü-Pakete» у гастро ставил только экран «Seitenaufbau»
отдельным обходом `name_main_rows`; прочие вызовы показывали общее имя. Теперь `tenant` —
обязательный именованный параметр (`None` — явно), `main_list_name(host, tenant)` —
обязательный позиционный, обхода нет.
"""

import ast
import copy
import inspect
import pathlib

import pytest
from django.db import connection
from django.utils import translation

from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parents[3]
MAIN = siteconfig.MAIN_LIST_KEY


@pytest.fixture(autouse=True)
def _restore_connection_tenant():
    before = getattr(connection, "tenant", None)
    yield
    connection.tenant = before


def _tenant(bt="restaurant", config=None):
    tenant = TenantFactory(
        business_type=bt,
        disabled_modules=list(default_disabled_for(bt)),
        site_config=copy.deepcopy(config) if config is not None else {},
    )
    connection.tenant = tenant
    return tenant


def _main_label(blocks):
    return next(b["label"] for b in blocks if b.get("main") and not b.get("cblock"))


def test_blocks_for_requires_tenant():
    """H6: без `tenant` — `TypeError`; параметр именованный и без умолчания."""
    param = inspect.signature(site_schema.blocks_for).parameters["tenant"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        site_schema.blocks_for({}, "combos")
    with pytest.raises(TypeError):
        site_schema.main_list_name("combos")
    assert site_schema.blocks_for({}, "combos", tenant=None) is not None


#: L3 (ревью E8): места, где `tenant=None` передаётся осознанно — счёт строк, вид, умолчания
#: типа, места баннера (имя главного списка там не нужно). Новый `None` вне списка — красный.
TENANT_NONE_OK = {
    ("apps/core/site_schema.py", "page_rows"),
    ("apps/core/site_schema.py", "_row"),
    ("apps/core/site_schema.py", "check_view_available"),
    ("apps/core/site_schema.py", "_default_rows"),
    ("apps/core/window_banner.py", "_chosen"),
}


def _calls(tree, name):
    """Вызовы `name(...)` с именем объемлющей функции (`""` — уровень модуля)."""

    def walk(node, func):
        for child in ast.iter_child_nodes(node):
            inner = func
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                inner = child.name
            if isinstance(child, ast.Call):
                f = child.func
                called = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if called == name:
                    yield child, inner
            yield from walk(child, inner)

    yield from walk(tree, "")


def _sources():
    for base in ("apps", "scripts"):
        for path in (ROOT / base).rglob("*.py"):
            if "migrations" in path.parts:
                continue
            yield path


def _is_none(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _tenant_arg(call, name):
    """Узел тенанта в вызове, `...` — передан через `**kwargs`, `None` — не передан."""
    for k in call.keywords:
        if k.arg == "tenant":
            return k.value
    if name == "main_list_name" and len(call.args) >= 2:
        return call.args[1]
    if any(k.arg is None for k in call.keywords):
        return ...
    return None


@pytest.mark.parametrize("name", ["blocks_for", "main_list_name"])
def test_main_list_name_everywhere_calls(name):
    """№3 / №13: каждый вызов (код, стенды, тесты) передаёт тенанта — `blocks_for`
    именем `tenant=`, `main_list_name` вторым аргументом; обхода `name_main_rows` нет.
    L3: явный `tenant=None` вне тестов — только в местах `TENANT_NONE_OK`."""
    missing, unlisted, used = [], [], set()
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        if f"{name}(" not in text:
            continue
        rel = str(path.relative_to(ROOT))
        in_tests = "tests" in path.parts
        for call, func in _calls(ast.parse(text), name):
            arg = _tenant_arg(call, name)
            if arg is None:
                if not path.name.startswith("test_fb33_e8_"):
                    missing.append(f"{rel}:{call.lineno}")
                continue
            if arg is ... or in_tests or not _is_none(arg):
                continue
            if (rel, func) in TENANT_NONE_OK:
                used.add((rel, func))
            else:
                unlisted.append(f"{rel}:{call.lineno} ({func})")
    assert missing == []
    assert unlisted == []
    if name == "blocks_for":
        assert used == TENANT_NONE_OK  # список не устаревает: каждое место ещё живо
    assert not hasattr(site_schema, "name_main_rows")
    views = (ROOT / "apps/core/site_schema_views.py").read_text(encoding="utf-8")
    assert "name_main_rows" not in views


def test_tenant_none_lock_catches_new_place():
    """L3: замок ловит новый `tenant=None` вне списка (проверка самого разбора)."""
    tree = ast.parse("def fresh(c):\n    return site_schema.blocks_for(c, 'x', tenant=None)\n")
    [(call, func)] = list(_calls(tree, "blocks_for"))
    assert func == "fresh" and _is_none(_tenant_arg(call, "blocks_for"))
    assert ("apps/core/site_schema.py", func) not in TENANT_NONE_OK


@pytest.mark.parametrize(
    ("bt", "name"), [("restaurant", "Menü-Pakete"), ("online_shop", "Sets & Pakete")]
)
def test_main_list_name_everywhere(bt, name):
    """№3: имя главного списка с типом бизнеса — прямо из `blocks_for` (любой вызов), без
    тенанта — общее имя."""
    tenant = _tenant(bt)
    config = siteconfig.normalize({})
    with translation.override("de"):
        assert _main_label(site_schema.blocks_for(config, "combos", tenant=tenant)) == name
        assert _main_label(site_schema.blocks_for(config, "combos", tenant=None)) == "Sets & Pakete"
        assert site_schema.main_list_name("combos", tenant) == name


def test_main_list_name_in_screen_gastro():
    """Экран «Seitenaufbau» берёт имя из `blocks_for` (обход снят) — «Menü-Pakete»."""
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.core.tests.test_fb33_m5b2_names import _row

    html = Browser(_tenant("restaurant")).get("?seite=combos")
    _tag, inner = _row(html, MAIN)
    assert ">Menü-Pakete</span>" in inner
