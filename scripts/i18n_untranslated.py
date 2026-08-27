"""Сканер строк БЕЗ ПУТИ ПЕРЕВОДА: видимый текст, который не доедет до `.po`.

Зачем нужен ЕЩЁ один гейт. `scripts/i18n_gap.py` сверяет с каталогами то, что
ИЗВЛЁК `makemessages`, — значит по построению не видит два класса:

  1. строка вообще не обёрнута (`label="Preis"`, подпись в `choices`, немецкий
     текст прямо в шаблоне) — xgettext её не извлекает, гейт молчит, у ru/tr/uk
     навсегда остаётся немецкий;
  2. строка обёрнута, но внутри f-строки (`f"{_('Zimmer')}: {name}"`) — xgettext
     не парсит выражения в f-строках (проверено), msgid не появляется.

Что делает скрипт: собирает кандидатов по трём правилам, ОТБРАСЫВАЕТ те, у
которых путь перевода всё-таки есть (обёрнуты, либо msgid уже лежит в
`locale/de/…po` — так живут реестры с рантайм-`gettext(var)`: Finder, меню), и
сравнивает остаток с базовой линией `locale/i18n-untranslated-baseline.json`.
Падает ТОЛЬКО на новом — существующий долг зафиксирован и не мешает работать.

Режимы:
    uv run python scripts/i18n_untranslated.py              # отчёт по всему репо
    uv run python scripts/i18n_untranslated.py --check      # гейт: падает на НОВОМ
    uv run python scripts/i18n_untranslated.py --check --files a.py b.html
    uv run python scripts/i18n_untranslated.py --write-baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "locale" / "i18n-untranslated-baseline.json"
PO_DE = ROOT / "locale" / "de" / "LC_MESSAGES" / "django.po"

GETTEXT = {
    "_",
    "gettext",
    "gettext_lazy",
    "ngettext",
    "ngettext_lazy",
    "pgettext",
    "pgettext_lazy",
}
# Аргументы-подписи: их значение всегда видно человеку, независимо от языка
# (поэтому ловим и «Bot token», а не только строки с умлаутами).
LABEL_KW = {
    "label",
    "help_text",
    "verbose_name",
    "verbose_name_plural",
    "placeholder",
    "empty_label",
    "short_description",
}
# Вызовы, чьи строковые аргументы уезжают на экран. `messages.*` берём только
# по объекту (`logger.warning(...)` — то же имя метода, но это лог, не UI).
MESSAGE_ATTRS = {"success", "error", "warning", "info", "add_message"}
MESSAGE_OBJECTS = {"messages", "django_messages"}
MESSAGE_NAMES = {"ValidationError"}
# Ключи словарей-реестров, под которыми лежит подпись для интерфейса.
LABEL_KEYS = {"label", "title", "hint", "caption", "heading", "subtitle", "placeholder"}

# Маркеры немецкого: слова и умлауты. Нужны для строк ВНЕ «позиции подписи»
# (сообщения, тексты в шаблонах) — там позиция не подсказывает.
DE_MARK = re.compile(
    r"[äöüÄÖÜß]|\b("
    r"der|die|das|und|für|nicht|mit|wird|kein|keine|Ihre|Ihren|Ihr|Sie|eine|einen|einem|"
    r"oder|auf|zum|zur|beim|vom|noch|schon|bitte|Bitte|wurde|werden|sind|ist|bei|von|dem|"
    r"den|des|nur|alle|neue|neuer|ohne|mehr|pro|anzeigen|speichern|bearbeiten|löschen|"
    r"hinzufügen|Einstellungen|Anzeige|Buchung|Bestellung|Termin|Zimmer|Kunde|Kunden|"
    r"Rechnung|Angebot|Preis|Lager|Verkauf|Verkäufe|Woche|Monat|Datum|Beschreibung|"
    r"Gutschein|Zahlung|Lieferung|Bestand|Aktion|Aktionen|Betrieb|Konto"
    r")\b"
)
CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
# Технические строки: слаги, пути, шаблоны форматирования, CSS, ключи JSON.
TECHNICAL = re.compile(r"^[a-z0-9_.:/#?=&%-]+$|^https?://|^\{|^<|^%|^\.[a-z-]+$")

# Файлы-генераторы КОНТЕНТА (тексты попадают в данные тенанта и переводятся
# словарями demo_i18n_*, а не каталогами) и осознанное исключение гейта I18N-9.
SKIP_FILES = (
    "apps/tenants/demo_kits.py",
    "apps/tenants/demo.py",
    "apps/tenants/demo_i18n.py",
    "apps/tenants/archetype_pages.py",
)
SKIP_DIR_PARTS = ("/migrations/", "/tests/", "/node_modules/", "/.venv/")

TPL_ATTR = re.compile(r'\b(placeholder|title|aria-label|alt)="([^"{}]{3,160})"')
TPL_TEXT = re.compile(r">\s*([^<>{}\n]{3,160}?)\s*<")


def po_msgids() -> set[str]:
    """msgid каталога de: строка ЕСТЬ в каталоге → путь перевода существует."""
    ids: set[str] = set()
    cur: list[str] = []
    in_id = False
    for line in PO_DE.read_text(encoding="utf-8").splitlines():
        if line.startswith("msgid "):
            cur, in_id = [line[6:].strip().strip('"')], True
        elif in_id and line.startswith('"'):
            cur.append(line.strip().strip('"'))
        elif in_id:
            ids.add("".join(cur))
            in_id = False
    if in_id:
        ids.add("".join(cur))
    ids.discard("")
    return ids


def humanish(text: str) -> bool:
    """Похоже на текст для человека, а не на ключ/путь/шаблон."""
    if not isinstance(text, str):
        return False
    text = text.strip()
    if not (3 <= len(text) <= 200):
        return False
    if CYRILLIC.search(text):  # русские комментарии/докстринги — не UI
        return False
    if TECHNICAL.match(text):
        return False
    if not re.search(r"[A-Za-zÄÖÜäöüß]{3}", text):
        return False
    # Строка целиком в нижнем регистре без пунктуации — обычно ключевые слова
    # для поиска (nav_registry) или значения-токены (finder «words»).
    if text == text.lower() and not re.search(r"[.!?:€%]", text):
        return False
    return True


def _docstring_ids(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                out.add(id(body[0].value))
    return out


def _is_gettext_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in GETTEXT
    if isinstance(func, ast.Attribute):
        return func.attr in GETTEXT
    return False


def scan_python(path: Path, rel: str, known: set[str]) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    skip = _docstring_ids(tree)
    wrapped: set[int] = set()
    label_pos: dict[int, str] = {}
    fstring_risk: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if _is_gettext_call(node):
            for arg in node.args:
                if isinstance(arg, ast.Constant):
                    wrapped.add(id(arg))
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in LABEL_KW and isinstance(kw.value, ast.Constant):
                    label_pos[id(kw.value)] = kw.arg
                if kw.arg == "choices" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    for el in kw.value.elts:
                        if isinstance(el, (ast.Tuple, ast.List)) and len(el.elts) == 2:
                            if isinstance(el.elts[1], ast.Constant):
                                label_pos[id(el.elts[1])] = "choices"
            is_message = False
            if isinstance(node.func, ast.Attribute) and node.func.attr in MESSAGE_ATTRS:
                owner = node.func.value
                is_message = isinstance(owner, ast.Name) and owner.id in MESSAGE_OBJECTS
            elif isinstance(node.func, ast.Name):
                is_message = node.func.id in MESSAGE_NAMES
            if is_message:
                for arg in node.args:
                    if isinstance(arg, ast.Constant):
                        label_pos[id(arg)] = "message"
        # Пары («code», «Подпись») в реестрах-константах.
        if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) == 2:
            first, second = node.elts
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and isinstance(second, ast.Constant)
                and isinstance(second.value, str)
                and TECHNICAL.match(first.value or "x")
            ):
                label_pos.setdefault(id(second), "pair")
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in LABEL_KEYS
                    and isinstance(value, ast.Constant)
                ):
                    label_pos.setdefault(id(value), f"dict:{key.value}")
        # Обёрнуто, но внутри f-строки → xgettext не извлекает (проверено).
        if isinstance(node, ast.JoinedStr):
            for sub in ast.walk(node):
                if _is_gettext_call(sub) and sub.args and isinstance(sub.args[0], ast.Constant):
                    fstring_risk.append((sub.lineno, sub.args[0].value))

    out: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip or id(node) in wrapped:
            continue
        text = node.value.strip()
        if text in known or not humanish(text):
            continue
        rule = label_pos.get(id(node))
        if rule is None and not DE_MARK.search(text):
            continue
        out.append(
            {"file": rel, "line": node.lineno, "text": text, "rule": rule or "german-literal"}
        )
    for line, text in fstring_risk:
        if text not in known:
            out.append({"file": rel, "line": line, "text": text, "rule": "fstring"})
    return out


def scan_template(path: Path, rel: str, known: set[str]) -> list[dict]:
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    lines = src.splitlines()

    def line_of(pos: int) -> int:
        return src.count("\n", 0, pos) + 1

    out: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for match in TPL_ATTR.finditer(src):
        text = match.group(2).strip()
        if text in known or not humanish(text) or not DE_MARK.search(text):
            continue
        out.append(
            {
                "file": rel,
                "line": line_of(match.start()),
                "text": text,
                "rule": f"attr:{match.group(1)}",
            }
        )
    for match in TPL_TEXT.finditer(src):
        text = match.group(1).strip()
        if text in known or not humanish(text) or not DE_MARK.search(text):
            continue
        line = line_of(match.start())
        # Внутри <script>/<style> текста для человека нет — там JS-строки ловит
        # правило атрибутов и обычный review.
        chunk = "\n".join(lines[max(0, line - 40) : line])
        if chunk.count("<script") > chunk.count("</script"):
            continue
        key = (text, line)
        if key in seen:
            continue
        seen.add(key)
        out.append({"file": rel, "line": line, "text": text, "rule": "template-text"})
    return out


def collect(targets: list[Path] | None = None) -> list[dict]:
    known = po_msgids()
    if targets is None:
        targets = sorted(ROOT.glob("apps/**/*.py")) + sorted(ROOT.glob("templates/**/*.html"))
    findings: list[dict] = []
    for path in targets:
        if not path.exists() or not path.is_file():
            continue
        try:
            rel = str(path.resolve().relative_to(ROOT))
        except ValueError:
            continue
        if any(part in f"/{rel}" for part in SKIP_DIR_PARTS) or rel in SKIP_FILES:
            continue
        if rel.endswith(".py"):
            findings += scan_python(path, rel, known)
        elif rel.endswith(".html"):
            findings += scan_template(path, rel, known)
    return findings


def load_baseline() -> dict[str, list[str]]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="падать на строках вне базовой линии")
    ap.add_argument("--write-baseline", action="store_true", help="зафиксировать текущий долг")
    ap.add_argument("--files", nargs="*", default=None, help="проверить только эти файлы")
    args = ap.parse_args(argv[1:])

    targets = [Path(f) if Path(f).is_absolute() else ROOT / f for f in args.files or []] or None
    findings = collect(targets)

    if args.write_baseline:
        full = collect()  # базовая линия всегда пишется по всему репозиторию
        data: dict[str, list[str]] = defaultdict(list)
        for f in full:
            if f["text"] not in data[f["file"]]:
                data[f["file"]].append(f["text"])
        BASELINE.write_text(
            json.dumps(
                {k: sorted(v) for k, v in sorted(data.items())}, ensure_ascii=False, indent=1
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"базовая линия обновлена: {sum(len(v) for v in data.values())} строк → {BASELINE}")
        return 0

    baseline = load_baseline()
    fresh = [f for f in findings if f["text"] not in baseline.get(f["file"], [])]

    if args.check:
        if not fresh:
            print(
                f"i18n-untranslated: ок (новых строк без перевода нет, в долге {sum(len(v) for v in baseline.values())})"
            )
            return 0
        print("i18n: НОВЫЕ строки без пути перевода", file=sys.stderr)
        for f in fresh:
            print(f"  {f['file']}:{f['line']} [{f['rule']}] «{f['text'][:110]}»", file=sys.stderr)
        print(
            "\nЧто делать:\n"
            "  • интерфейс → обернуть в gettext_lazy/{% trans %} И добавить msgid во ВСЕ "
            "locale/*/LC_MESSAGES/django.po;\n"
            '  • gettext внутри f-строки → вынести наружу (title = _("…"); f"{title}: …");\n'
            "  • контент/демо/правовой текст → внести в базовую линию: "
            "uv run python scripts/i18n_untranslated.py --write-baseline",
            file=sys.stderr,
        )
        return 1

    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_file[f["file"]].append(f)
    print(f"строк без пути перевода: {len(findings)} в {len(by_file)} файлах")
    print(f"из них новых (вне базовой линии): {len(fresh)}\n")
    for file, items in sorted(by_file.items(), key=lambda kv: -len(kv[1])):
        known_cnt = len(items) - len([i for i in items if i["text"] not in baseline.get(file, [])])
        print(f"  {len(items):4d}  {file}  (в долге: {known_cnt})")
        for item in items[:6]:
            mark = " " if item["text"] in baseline.get(file, []) else "+"
            print(f"        {mark} {item['line']:5d} [{item['rule']}] «{item['text'][:90]}»")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
