"""Замок выбора проверок `scripts/preflight.py` (T-13.1, 2026-11-21).

Финальный гейт перед пушем жил абзацем в CLAUDE.md §5 и выполнялся по памяти — отсюда красные
CI 1116/1121/1122/1145. Теперь набор проверок выбирает чистая функция `plan(files)` по списку
изменённых путей; тест закрепляет таблицу «путь → проверки», чтобы правило нельзя было
молча потерять.
"""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _mod():
    spec = importlib.util.spec_from_file_location("preflight", ROOT / "scripts" / "preflight.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _plan(*files):
    return _mod().plan(list(files))


def test_ruff_runs_always_and_on_whole_tree():
    p = _plan("docs/build-log.md")
    assert "ruff_check" in p.steps and "ruff_format" in p.steps


def test_docs_only_change_runs_doc_locks_not_app_tests():
    p = _plan("docs/pitfalls.md")
    assert p.pytest_targets == ["apps/core/tests/test_claude_md_budget.py"]
    assert "css" not in p.steps and "i18n" not in p.steps


def test_app_python_change_tests_that_app_and_runs_i18n():
    p = _plan("apps/orders/views.py")
    assert "apps/orders" in p.pytest_targets
    assert "i18n" in p.steps
    assert not p.create_db


def test_core_change_also_tests_tenants():
    # Урок CI 1145: секции главной рендерят карточки через стабы контракта SellableEntity.
    p = _plan("apps/core/sellable.py")
    assert "apps/core" in p.pytest_targets and "apps/tenants" in p.pytest_targets


def test_template_change_runs_css_comments_and_i18n():
    p = _plan("templates/orders/cart.html")
    assert {"css", "i18n"} <= set(p.steps)
    assert "apps/core/tests/test_template_comments.py" in p.pytest_targets
    assert "apps/orders" in p.pytest_targets


def test_app_level_template_counts_as_template():
    p = _plan("apps/catalog/templates/catalog/x.html")
    assert "css" in p.steps and "apps/catalog" in p.pytest_targets


def test_shared_template_without_own_app_tests_core_and_tenants():
    p = _plan("templates/storefront/home.html")
    assert {"apps/core", "apps/tenants"} <= set(p.pytest_targets)


def test_tailwind_sources_trigger_css_check():
    for path in ("tailwind.config.js", "static/src/app.css", "package.json"):
        assert "css" in _plan(path).steps, path


def test_migration_forces_fresh_test_db():
    p = _plan("apps/stays/migrations/0050_x.py")
    assert p.create_db and "apps/stays" in p.pytest_targets


def test_claude_md_and_rules_and_skills_run_their_locks():
    assert "apps/core/tests/test_claude_md_budget.py" in _plan("CLAUDE.md").pytest_targets
    assert (
        "apps/core/tests/test_claude_rules_budget.py"
        in _plan(".claude/rules/project-overrides.md").pytest_targets
    )
    assert (
        "apps/core/tests/test_project_skills.py"
        in _plan(".claude/skills/sa-increment/SKILL.md").pytest_targets
    )


def test_preflight_change_runs_its_own_lock():
    assert "apps/core/tests/test_preflight_plan.py" in _plan("scripts/preflight.py").pytest_targets


def test_whole_app_target_swallows_single_files_of_that_app():
    p = _plan("apps/core/fsm.py", "templates/core/x.html", "CLAUDE.md")
    assert "apps/core" in p.pytest_targets
    assert not [t for t in p.pytest_targets if t.startswith("apps/core/")]


def test_pytest_command_never_uses_x_and_skips_the_hanging_module():
    mod = _mod()
    cmd = mod.pytest_command(mod.plan(["apps/billing/models.py"]))
    assert "-x" not in cmd
    assert "--ignore=apps/billing/tests/test_tasks.py" in cmd
    assert "--reuse-db" in cmd and "--create-db" not in cmd
    assert "--create-db" in mod.pytest_command(mod.plan(["apps/billing/migrations/0009_x.py"]))


def test_every_lock_file_named_by_the_plan_exists_or_is_scheduled():
    mod = _mod()
    for path in mod.LOCKS.values():
        assert (ROOT / path).exists(), f"preflight называет несуществующий замок {path}"
