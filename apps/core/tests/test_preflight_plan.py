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


def _plan(
    *files,
    importers=lambda module: set(),
    tests_of=lambda script: set(),
    goldens=lambda: set(),
):
    return _mod().plan(list(files), importers=importers, tests_of=tests_of, goldens=goldens)


def test_ruff_runs_always_and_on_whole_tree():
    p = _plan("docs/build-log.md")
    assert "ruff_check" in p.steps and "ruff_format" in p.steps


def test_docs_only_change_runs_doc_locks_not_app_tests():
    p = _plan("docs/pitfalls.md")
    # T-14.1: правка документа проверяет и карту работ — порядок и статус стопок живут в docs/.
    assert p.pytest_targets == [
        "apps/core/tests/test_claude_md_budget.py",
        "apps/core/tests/test_work_map.py",
    ]
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
    assert "apps/orders" in p.pytest_targets
    wide = _plan("templates/zzz/cart.html").pytest_targets  # ядро и главная целиком
    assert {"apps/core", "apps/tenants"} <= set(wide)
    for lock in ("test_template_comments", "test_template_tag_balance", "test_a11y_templates"):
        assert f"apps/core/tests/{lock}.py" in p.pytest_targets, lock
    assert "apps/tenants/tests/test_template_sweep.py" in p.pytest_targets


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


def test_script_change_runs_the_tests_that_mention_it():
    # Тесты скриптов лежат в приложениях — настоящий поиск по имени файла.
    mod = _mod()
    assert (
        "apps/core/tests/test_preflight_plan.py"
        in mod.plan(["scripts/preflight.py"]).pytest_targets
    )
    p = _plan("scripts/x.py", tests_of=lambda script: {"apps/booking/tests/test_x.py"})
    assert "apps/booking/tests/test_x.py" in p.pytest_targets


def test_core_module_change_tests_the_apps_that_import_it():
    # Ревью плана: правка ядра роняла третью группу CI при зелёном местном прогоне.
    p = _plan("apps/core/form_spec.py", importers=lambda module: {f"apps/uses_{module}"})
    assert "apps/uses_form_spec" in p.pytest_targets
    real = _mod().plan(["apps/core/form_spec.py"]).pytest_targets
    assert "apps/orders" in real, real


def test_core_test_or_template_change_does_not_fan_out():
    p = _plan("apps/core/tests/test_x.py", importers=lambda module: {"apps/everything"})
    assert "apps/everything" not in p.pytest_targets


def test_dependency_files_check_the_lock():
    assert "lock" in _plan("pyproject.toml").steps and "lock" in _plan("uv.lock").steps
    assert "lock" not in _plan("apps/orders/views.py").steps


def test_translation_catalog_change_runs_i18n():
    assert "i18n" in _plan("locale/ru/LC_MESSAGES/django.po").steps


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


# --- T-13.9 (2026-11-23): находки «правило было, не сработало» стопок 8–10 → механизм ----------


def test_template_change_runs_every_golden_suite_of_every_app():
    # Журнал находок, трижды за стопки 8–10 (M3-9c ×2, M5b-2) и красный CI 4445: правка шаблона
    # задевала наборы эталонов вне списка плана, срез гонял их выборочно. Текст в скилле не помог.
    extra = {"apps/promotions/tests/test_fb31p3_golden.py", "apps/orders/tests/test_x_golden.py"}
    p = _plan("templates/storefront/_card.html", goldens=lambda: extra)
    assert extra <= set(p.pytest_targets)
    assert not (extra & set(_plan("apps/orders/views.py", goldens=lambda: extra).pytest_targets))


def test_real_golden_suites_are_found_across_apps():
    found = _mod().golden_tests()
    apps = {path.split("/")[1] for path in found}
    assert {"core", "tenants", "promotions"} <= apps, apps
    assert all(path.endswith(".py") and "/tests/" in path for path in found)


def test_storefront_layout_change_reminds_about_the_owner_walk():
    # Находка «после мержа» стопки 8: мелкие цели нашёл обход владельца, который до мержа не гоняли.
    notes = " ".join(_plan("templates/storefront/home.html").notes)
    assert "fb33_m3_9_owner_stand.py" in notes
    assert "owner_stand" not in " ".join(_plan("apps/orders/views.py").notes)


def test_parallel_pytest_guard_looks_only_at_the_same_test_database():
    # Находка стопки 9: гейт отказывал при ЛЮБОМ чужом pytest, даже на другой `DB_NAME` —
    # параллельные срезы в worktree гоняли pytest вручную, мимо гейта.
    mod = _mod()
    procs = [("101", "platform", "pytest apps/core"), ("102", "platform_m5c", "pytest apps/orders")]
    assert mod.same_db_pytest(procs, "platform") == "pytest apps/core"
    assert mod.same_db_pytest(procs, "platform_m5d") == ""
    assert (
        mod.same_db_pytest([("7", "", "pytest x")], "platform") == "pytest x"
    )  # без DB_NAME — общая
