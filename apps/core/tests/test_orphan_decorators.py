"""Замок против «осиротевшего декоратора».

Дважды в проекте хелпер, вставленный МЕЖДУ декоратором и функцией, забирал
декоратор себе, и функция молча теряла обвязку:

* 2026-08-01 — вьюха кабинета осталась без `@login_required` (аноним видел
  чужие данные);
* 2026-08-28 — `orders.editing.add_item` осталась без `@transaction.atomic`,
  и добавление товара в заказ падало 500-й (`select_for_update` вне
  транзакции). Обычные тесты этого не видят: pytest-django оборачивает каждый
  тест в транзакцию.

Оба случая ловятся статически, без запуска кода.
"""

import ast
import pathlib

VIEW_DECORATORS = {
    "login_required",
    "require_POST",
    "require_GET",
    "require_http_methods",
    "staff_member_required",
}
ROOT = pathlib.Path(__file__).resolve().parents[3] / "apps"


def _decorator_name(node):
    while isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _functions():
    for path in sorted(ROOT.rglob("*.py")):
        if "/migrations/" in str(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — синтаксис ловит ruff
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = {_decorator_name(d) for d in node.decorator_list}
                yield path, node, names


def test_view_decorators_sit_on_views():
    """`@login_required`/`@require_POST` на функции без `request` — значит его
    перехватил хелпер, а настоящая вьюха осталась голой."""
    orphans = [
        f"{path.relative_to(ROOT.parent)}:{node.lineno} {node.name}() ← {sorted(names & VIEW_DECORATORS)}"
        for path, node, names in _functions()
        if names & VIEW_DECORATORS
        and (not node.args.args or node.args.args[0].arg not in ("request", "self", "cls"))
    ]
    assert not orphans, "декоратор вьюхи достался не вьюхе:\n" + "\n".join(orphans)


def test_atomic_does_not_sit_on_a_pure_helper():
    """`@transaction.atomic` на приватном хелпере без обращений к БД — тот же
    симптом: транзакция ушла хелперу, а сервис остался без неё."""
    marks = ("objects.", ".save(", ".delete(", "select_for_update", "bulk_", "record_movement")
    orphans = []
    for path, node, names in _functions():
        if "atomic" not in names or not node.name.startswith("_"):
            continue
        body = "\n".join(
            path.read_text(encoding="utf-8").splitlines()[node.lineno - 1 : node.end_lineno]
        )
        if not any(m in body for m in marks):
            orphans.append(f"{path.relative_to(ROOT.parent)}:{node.lineno} {node.name}()")
    assert not orphans, "transaction.atomic достался хелперу без работы с БД:\n" + "\n".join(
        orphans
    )
