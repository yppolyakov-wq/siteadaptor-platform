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
RED = pytest.mark.xfail(strict=True, reason="FB-33 стопка 14 E8: до реализации")


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


@RED
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


def _calls(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if called == name:
                yield node


def _sources():
    for base in ("apps", "scripts"):
        for path in (ROOT / base).rglob("*.py"):
            if "migrations" in path.parts:
                continue
            yield path


@RED
@pytest.mark.parametrize("name", ["blocks_for", "main_list_name"])
def test_main_list_name_everywhere_calls(name):
    """№3 / №13: каждый вызов (код, стенды, тесты) передаёт тенанта — `blocks_for`
    именем `tenant=`, `main_list_name` вторым аргументом; обхода `name_main_rows` нет."""
    missing = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        if f"{name}(" not in text:
            continue
        for call in _calls(ast.parse(text), name):
            if name == "blocks_for":
                ok = any(k.arg == "tenant" for k in call.keywords) or any(
                    k.arg is None for k in call.keywords
                )
            else:
                ok = len(call.args) >= 2 or any(k.arg == "tenant" for k in call.keywords)
            if not ok and not path.name.startswith("test_fb33_e8_"):
                missing.append(f"{path.relative_to(ROOT)}:{call.lineno}")
    assert missing == []
    assert not hasattr(site_schema, "name_main_rows")
    views = (ROOT / "apps/core/site_schema_views.py").read_text(encoding="utf-8")
    assert "name_main_rows" not in views


@RED
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
