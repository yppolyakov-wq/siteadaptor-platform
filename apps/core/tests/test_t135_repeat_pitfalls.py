"""T-13.5: замки на грабли из `docs/pitfalls.md`, которые повторялись.

Правило проекта: «грабля повторилась — превратить её в замок». Здесь те из
повторившихся, что ловятся статически — чтением исходников, без БД и без запуска
кода. У каждого замка рядом тест «замок видит нарушение»: проверяющая функция
получает заведомо плохой текст и обязана его поймать (иначе замок холостой).
"""

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
APPS = REPO / "apps"
PERM_GRANTS = APPS / "core" / "perm_grants.py"


def _test_files():
    for path in sorted(APPS.rglob("*.py")):
        if "tests" in path.parts and "migrations" not in path.parts:
            yield path


# --- 1. Холостые ассерты `… or True` (pitfalls.md:1025) -----------------------


def _vacuous_asserts(source: str) -> list[int]:
    """Строки `assert`, условие которых истинно всегда: в `or` стоит истинная
    константа (`assert x or True`) либо всё условие — истинная константа."""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        parts = (
            test.values if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or) else [test]
        )
        if any(isinstance(p, ast.Constant) and bool(p.value) for p in parts):
            bad.append(node.lineno)
    return bad


def test_no_vacuous_asserts_in_tests():
    """2026-09-10 (P0), pitfalls.md:1025 — четыре раунда ревью безопасности
    подряд находили HIGH в коде предыдущего, в тестах встречались ассерты вида
    `… or True`: тест зелёный, а не проверяет ничего. Тот же приём позже нашли
    в `test_storefront_cache.py` («заведомо ложная под `or True`»)."""
    offenders = []
    for path in _test_files():
        offenders += [
            f"{path.relative_to(REPO)}:{line}"
            for line in _vacuous_asserts(path.read_text(encoding="utf-8"))
        ]
    assert not offenders, "холостые ассерты (условие истинно всегда):\n" + "\n".join(offenders)


def test_vacuous_assert_lock_sees_violation():
    bad = "def test_x():\n    assert 'a' in html or True\n    assert 1\n    assert x or 'msg'\n"
    assert _vacuous_asserts(bad) == [2, 3, 4]
    good = "def test_x():\n    assert a or b\n    assert a == 1, 'msg'\n    assert f(x or True)\n"
    assert _vacuous_asserts(good) == []


# --- 2. Декоратор `_audited` достался не той функции (pitfalls.md:834-838) ----

AUDITED_ARGS = ("actor_user", "member_pk")


def _audited_mismatches(source: str) -> list[str]:
    """`_audited` обязан стоять ровно на публичных писателях с подписью
    `(actor_user, member_pk, …)` — обёртка читает именно эти два аргумента.
    Возвращает и «декоратор на чужой функции», и «писатель без декоратора»."""
    bad = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        decorated = any(isinstance(d, ast.Name) and d.id == "_audited" for d in node.decorator_list)
        writer = (
            not node.name.startswith("_")
            and tuple(a.arg for a in node.args.args[:2]) == AUDITED_ARGS
        )
        if decorated and not writer:
            bad.append(f"{node.name}:{node.lineno} — @_audited на чужой функции")
        if writer and not decorated:
            bad.append(f"{node.name}:{node.lineno} — писатель без @_audited")
    return bad


def test_audited_decorator_sits_on_permission_writers():
    """2026-10-25 (E6.7c-2), pitfalls.md:834-838 — новая функция, вставленная
    ПОД `@_audited`, забрала декоратор себе, а настоящий писатель прав остался
    без журнала отказов. Повтор грабли «хелпер съел декоратор» (≥3 раз);
    `test_orphan_decorators` знает только декораторы вьюх и `atomic`."""
    source = PERM_GRANTS.read_text(encoding="utf-8")
    assert "def _audited(" in source, "обёртка _audited переехала — обновить замок"
    assert "@_audited" in source, "ни одного писателя под @_audited — замок холостой"
    assert not _audited_mismatches(source)


def test_audited_lock_sees_violation():
    source = PERM_GRANTS.read_text(encoding="utf-8")
    marker = "@_audited\ndef revoke_member("
    assert marker in source
    eaten = source.replace(
        marker, "@_audited\ndef _helper(x):\n    return x\n\n\ndef revoke_member("
    )
    found = _audited_mismatches(eaten)
    assert any(f.startswith("_helper:") for f in found), found
    assert any(f.startswith("revoke_member:") for f in found), found


# --- 3. Снимок сверяют целым dict (pitfalls.md:1014) --------------------------


def _leaf_name(node) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return str(node.slice.value)
    return ""


def _whole_snapshot_compares(source: str) -> list[int]:
    """Строки `assert`, где `<…>snapshot == {непустой литерал dict}`. Пустой
    литерал (`== {}`) разрешён: «снимка нет» новое поле не ломает."""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assert):
            continue
        for cmp_ in ast.walk(node.test):
            if not (
                isinstance(cmp_, ast.Compare)
                and len(cmp_.ops) == 1
                and isinstance(cmp_.ops[0], ast.Eq)
            ):
                continue
            left, right = cmp_.left, cmp_.comparators[0]
            for value, literal in ((left, right), (right, left)):
                if (
                    isinstance(literal, ast.Dict)
                    and literal.keys
                    and _leaf_name(value).lower().endswith("snapshot")
                ):
                    bad.append(node.lineno)
    return bad


def test_snapshots_are_not_compared_as_whole_dicts():
    """pitfalls.md:1014 (MX, VAT; повтор дважды) — замок, сверяющий снимок
    сделки целым dict, падает в чужом инкременте от любого нового поля снимка.
    Сверять по полям: `snap["rate"] == …`."""
    offenders = []
    for path in _test_files():
        offenders += [
            f"{path.relative_to(REPO)}:{line}"
            for line in _whole_snapshot_compares(path.read_text(encoding="utf-8"))
        ]
    assert not offenders, "снимок сверяется целым dict — сверять по полям:\n" + "\n".join(offenders)


def test_snapshot_lock_sees_violation(tmp_path):
    bad = tmp_path / "test_bad.py"
    bad.write_text(
        "def test_x(b):\n"
        "    assert b.rate_snapshot == {'rate': 7, 'nights': 2}\n"
        "    assert {'vat': 19} == row['vat_snapshot']\n",
        encoding="utf-8",
    )
    assert _whole_snapshot_compares(bad.read_text(encoding="utf-8")) == [2, 3]
    good = (
        "def test_x(b):\n"
        "    assert b.rate_snapshot == {}\n"
        "    assert b.rate_snapshot['rate'] == 7\n"
        "    assert b.other == {'rate': 7}\n"
    )
    assert _whole_snapshot_compares(good) == []
