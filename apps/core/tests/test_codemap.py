"""Замок справки по коду `scripts/codemap.py` (T-15, 2026-11-24).

258 тысяч строк, 221 модуль ядра, 310 связей между приложениями: в начале каждого среза сессия собирала
связи файла десятком поисков и часть пропускала (журнал находок: «предпосылка без проверки по коду»,
«второй писатель»). Справка считает связи из кода в момент запроса. Замок проверяет, что она не
молчит о том, что есть, и что оглавление ядра и базовая линия взаимных зависимостей не устарели.
"""

import functools
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _mod():
    spec = importlib.util.spec_from_file_location("codemap", ROOT / "scripts" / "codemap.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.lru_cache(maxsize=1)
def _real():
    """Индекс настоящего репозитория — один на весь файл (разбор 2000+ файлов не быстрый)."""
    mod = _mod()
    return mod, mod.build_index(ROOT)


def _tree(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


FILES = {
    "apps/__init__.py": "",
    "apps/core/__init__.py": "",
    "apps/core/fsm.py": '"""Машина состояний."""\n\ndef apply():\n    pass\n',
    "apps/core/money.py": '"""Разбор сумм."""\nfrom apps.core import fsm\n',
    "apps/orders/__init__.py": "",
    "apps/orders/views.py": "from apps.core.fsm import apply\nfrom . import models\n",
    "apps/orders/models.py": "",
    "apps/orders/tasks.py": "def run():\n    from apps.core import fsm, money\n    return fsm\n",
    "apps/orders/tests/test_views.py": "from apps.core.fsm import apply\n",
    "apps/booking/__init__.py": "",
    "apps/booking/views.py": "import apps.core.fsm\nfrom apps.orders import views\n",
}


def test_importers_see_plain_from_package_lazy_and_dotted_imports(tmp_path):
    index = _mod().build_index(_tree(tmp_path, FILES))
    who = _mod().importers(index, "apps/core/fsm.py")
    assert who == [
        "apps/booking/views.py",
        "apps/core/money.py",
        "apps/orders/tasks.py",
        "apps/orders/views.py",
    ], "тесты — отдельно; ленивый импорт внутри функции и `from apps.core import fsm` считаются"


def test_relative_import_resolves_to_the_sibling_module(tmp_path):
    index = _mod().build_index(_tree(tmp_path, FILES))
    assert _mod().importers(index, "apps/orders/models.py") == ["apps/orders/views.py"]
    assert "apps/orders/models.py" in _mod().imports_of(index, "apps/orders/views.py")


def test_imports_of_lists_what_the_file_depends_on(tmp_path):
    index = _mod().build_index(_tree(tmp_path, FILES))
    assert _mod().imports_of(index, "apps/orders/tasks.py") == [
        "apps/core/fsm.py",
        "apps/core/money.py",
    ]


def test_app_pairs_and_mutual_dependencies(tmp_path):
    files = dict(FILES)
    files["apps/orders/extra.py"] = "from apps.booking import views\n"
    index = _mod().build_index(_tree(tmp_path, files))
    assert _mod().mutual_pairs(index) == [("booking", "orders")]


def test_resolve_accepts_path_dotted_module_and_name(tmp_path):
    root = _tree(tmp_path, FILES)
    mod = _mod()
    assert mod.resolve(root, "apps/core/fsm.py") == ("apps/core/fsm.py", "")
    assert mod.resolve(root, "apps.core.fsm") == ("apps/core/fsm.py", "")
    assert mod.resolve(root, "apps/core/fsm.py::apply") == ("apps/core/fsm.py", "apply")
    assert mod.resolve(root, "fsm") == ("apps/core/fsm.py", ""), "голое имя — модуль ядра"
    assert mod.resolve(root, "apps/core/nope.py") is None


def test_core_index_lines_carry_module_and_purpose(tmp_path):
    index = _mod().build_index(_tree(tmp_path, FILES))
    text = _mod().core_index(_tree(tmp_path, FILES), index)
    assert "| `fsm.py` | Машина состояний. |" in text.replace("  ", " ")
    assert "`money.py`" in text


# --- на настоящем коде ---------------------------------------------------------------------------


def test_real_repo_known_links_are_found():
    mod, index = _real()
    apps = {path.split("/")[1] for path in mod.importers(index, "apps/core/form_spec.py")}
    assert {"orders", "jobs"} <= apps, apps
    assert len(mod.importers(index, "apps/core/fsm.py")) >= 10


def test_report_is_not_silent_about_a_core_module():
    mod, index = _real()
    text = mod.report(ROOT, "apps/core/form_spec.py", index)
    for part in ("Кто импортирует", "Тесты", "Скилл", "Память проекта"):
        assert part in text, part
    assert "sa-block-editor" in text, "скилл редактора блоков называет form_spec"


def test_unknown_target_says_so_instead_of_an_empty_report():
    assert "не найден" in _mod().report(ROOT, "apps/core/no_such_module_zz.py")


def test_core_index_lists_every_core_module():
    listed = (ROOT / "docs" / "codemap-core.md").read_text(encoding="utf-8")
    missing = [
        p.name
        for p in sorted((ROOT / "apps" / "core").glob("*.py"))
        if p.name != "__init__.py" and f"`{p.name}`" not in listed
    ]
    assert not missing, (
        f"в docs/codemap-core.md нет модулей ядра {missing} — "
        "uv run python scripts/codemap.py --core-index (и строка в docs/project-memory.md §3)"
    )


def test_no_new_mutual_dependencies_between_apps():
    mod, index = _real()
    baseline = {
        tuple(line.split())
        for line in (ROOT / "docs" / "codemap-mutual-baseline.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.startswith("#")
    }
    new = [pair for pair in mod.mutual_pairs(index) if pair not in baseline]
    assert not new, (
        f"новые взаимные зависимости приложений: {new}. Два приложения стали импортировать друг друга — "
        "вынести общее в apps/core или развязать сигналом; осознанно — строка в docs/codemap-mutual-baseline.txt"
    )


# --- ревью silent-failure-hunter (2026-11-24): где справка молча давала неполный ответ -----------


def test_string_references_are_reported_not_hidden(tmp_path):
    # Таблицы «модуль строкой» (transactions, finder, setup_steps) и settings — связь без import.
    files = dict(FILES)
    files["apps/core/registry.py"] = (
        'TABLE = (("apps.orders.views", "OrderView"),)\nX = "apps.core.fsm.apply"\n'
    )
    root = _tree(tmp_path, files)
    index = _mod().build_index(root)
    assert _mod().string_refs(index, "apps/orders/views.py") == ["apps/core/registry.py"]
    assert _mod().string_refs(index, "apps/core/fsm.py") == ["apps/core/registry.py"]
    assert "apps/core/registry.py" not in _mod().importers(index, "apps/orders/views.py")


def test_config_and_scripts_are_indexed_too(tmp_path):
    files = dict(FILES)
    files["config/urls.py"] = "from apps.orders import views\n"
    files["scripts/tool.py"] = "import apps.core.fsm\n"
    index = _mod().build_index(_tree(tmp_path, files))
    assert "config/urls.py" in _mod().importers(index, "apps/orders/views.py")
    assert "scripts/tool.py" in _mod().importers(index, "apps/core/fsm.py")
    assert _mod().mutual_pairs(index) == [], "config и scripts в пары приложений не входят"


def test_ambiguous_bare_name_lists_candidates_instead_of_guessing(tmp_path):
    root = _tree(tmp_path, {**FILES, "apps/booking/models.py": "", "apps/core/models.py": ""})
    assert _mod().resolve(root, "models") is None
    text = _mod().report(root, "models")
    assert "apps/orders/models.py" in text and "apps/booking/models.py" in text


def test_missing_name_in_file_is_said_plainly(tmp_path):
    root = _tree(tmp_path, FILES)
    text = _mod().report(root, "apps/core/fsm.py::no_such_name")
    assert "нет в файле" in text


def test_broken_file_is_reported_in_every_mode(tmp_path):
    root = _tree(tmp_path, {**FILES, "apps/core/bad.py": "def broken(:\n"})
    mod = _mod()
    index = mod.build_index(root)
    assert mod.broken_note(index) and "apps/core/bad.py" in mod.broken_note(index)
    text = mod.core_index(root, index)
    assert "`bad.py`" in text and "не разобран" in text, (
        "битый модуль виден в оглавлении, а не потерян"
    )


def test_generic_module_name_does_not_drag_every_test_in():
    mod, index = _real()
    text = mod.report(ROOT, "apps/orders/models.py", index)
    line = next(ln for ln in text.splitlines() if ln.startswith("## Тесты"))
    count = int(line.split("—")[1].split()[0])
    assert count < 300, f"по слову «models» попали тесты всех приложений: {line}"


def test_real_repo_string_table_and_template_tags_are_visible():
    mod, index = _real()
    assert "apps/core/transactions.py" in mod.string_refs(index, "apps/orders/state_machine.py")
    text = mod.report(ROOT, "apps/tenants/templatetags/siteui.py", index)
    assert "{% load" in text and "siteui" in text


def test_real_fsm_importers_are_complete():
    mod, index = _real()
    who = mod.importers(index, "apps/core/fsm.py")
    assert len(who) >= 30 and "apps/orders/state_machine.py" in who, len(who)


def test_core_index_covers_subpackages():
    listed = (ROOT / "docs" / "codemap-core.md").read_text(encoding="utf-8")
    assert "templatetags/" in listed and "management/commands/" in listed


def test_template_is_searched_by_its_full_file_name():
    """Стопка 14 (журнал находок): у шаблона справка резала три знака как у `.py` и искала `_cb_row.h` —
    «тестов 0», хотя `_cb_row.html` называют семь тестов."""
    mod, index = _real()
    word, skill_needle, _ = mod._names("templates/tenant/_cb_row.html")
    assert word == "_cb_row.html" and skill_needle == "_cb_row.html"
    tests, _how = mod._tests_of(ROOT, index, "templates/tenant/_cb_row.html")
    assert len(tests) >= 5, sorted(tests)
