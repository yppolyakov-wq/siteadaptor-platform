"""Сводный отчёт по переводам: одна команда — вся картина.

    uv run python scripts/i18n_status.py

Отвечает на вопрос «все ли поля и параметры кабинета доехали до файлов перевода»:

1. каталоги по локалям (msgid, пустые переводы, identity);
2. расхождение наборов msgid между локалями (обязано быть нулевым);
3. АНГЛИЙСКИЙ msgid без немецкого перевода — на немецкой витрине/в кабинете
   такая строка выводится по-английски (класс, который чинила волна I18N-12);
4. строки БЕЗ пути перевода (`scripts/i18n_untranslated.py`) + сколько из них
   новых относительно базовой линии;
5. `gettext` внутри f-строк — xgettext их не извлекает (латентная ловушка);
6. при наличии gettext — полная сверка «код ⇄ .po» (что не покрыто и что в
   каталогах лежит мёртвым грузом).

Никаких зависимостей сверх стандартной библиотеки: `.po` разбираются вручную
(polib в проекте не объявлен), makemessages вызывается только если есть xgettext.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
LOCALES = ("de", "en", "tr", "ru", "uk")
# Названия брендов/форматов совпадают во всех языках — «перевода» у них нет.
# Английские служебные слова: без них короткая строка («Warm», «Link (URL)»)
# неотличима от немецкой — там пустой de-перевод норма, а не дефект.
EN_MARK = re.compile(
    r"\b(the|a|an|and|or|of|for|to|in|on|with|your|you|we|is|are|be|per|by|from|"
    r"this|that|it|all|new|show|hide|save|delete|please|no|yes|not|can|will|use|"
    r"add|edit|open|close|only|more|less|next|back|here)\b",
    re.I,
)
BRANDS = {
    "WhatsApp",
    "Instagram",
    "Facebook",
    "Telegram",
    "TikTok",
    "LinkedIn",
    "YouTube",
    "Stripe",
    "PayPal",
    "Klarna",
    "SEPA",
    "Google",
    "DATEV",
    "PDF",
    "CSV",
    "QR",
    "API",
}
DE_MARK = re.compile(
    r"[äöüÄÖÜß]|\b(der|die|das|und|für|nicht|mit|wird|Sie|Ihre|eine|einen|oder|auf|zum|zur|"
    r"beim|noch|bitte|werden|sind|ist|von|dem|den|des|nur|alle|neue|ohne|mehr|Gast|Termin|"
    r"Produkt|frei|Anreise|Nachricht|Veranstaltung|Vorgang|Mitglied|Zusatzleistung)\b"
)


class Entry:
    __slots__ = ("msgid", "plural", "strs")

    def __init__(self, msgid: str, plural: str | None, strs: list[str]):
        self.msgid, self.plural, self.strs = msgid, plural, strs

    @property
    def translated(self) -> bool:
        return all(self.strs) if self.plural else bool(self.strs and self.strs[0])


def parse_po(path: Path) -> dict[str, Entry]:
    """{msgid: Entry} — свой разбор (контекстов msgctxt в проекте нет)."""
    out: dict[str, Entry] = {}
    msgid: str | None = None
    plural: str | None = None
    strs: list[str] = []
    mode: str | None = None

    def flush() -> None:
        nonlocal msgid, plural, strs
        if msgid:
            out[msgid] = Entry(msgid, plural, list(strs))
        msgid, plural, strs = None, None, []

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.startswith("#"):
            continue
        head = re.match(r'^(msgid|msgid_plural|msgstr(?:\[\d+\])?)\s+"(.*)"$', line)
        if head:
            key, val = head.group(1), head.group(2)
            if key == "msgid":
                flush()
                msgid, mode = val, "id"
            elif key == "msgid_plural":
                plural, mode = val, "plural"
            else:
                strs.append(val)
                mode = "str"
            continue
        cont = re.match(r'^"(.*)"$', line.strip())
        if cont and mode:
            if mode == "id" and msgid is not None:
                msgid += cont.group(1)
            elif mode == "plural" and plural is not None:
                plural += cont.group(1)
            elif mode == "str" and strs:
                strs[-1] += cont.group(1)
    flush()
    out.pop("", None)
    return out


def english_msgid_without_german(cats: dict[str, dict[str, Entry]]) -> list[str]:
    """msgid на английском, у которого немецкого перевода нет.

    Базовый язык проекта — немецкий, поэтому пустой `msgstr` в de.po обычно
    означает «msgid и есть перевод». Но если msgid написан по-английски (так
    иногда заводили строки), немецкий пользователь видит английский текст.
    Признак «msgid английский»: нет немецких маркеров И en.po переводит его
    сам в себя (identity).
    """
    de, en = cats["de"], cats["en"]
    bad = []
    for msgid, entry in de.items():
        if entry.translated or DE_MARK.search(msgid) or msgid in BRANDS:
            continue
        if not EN_MARK.search(msgid):
            continue  # ни немецких, ни английских маркеров → судить не о чем
        if entry.plural and DE_MARK.search(entry.plural):
            continue
        ref = en.get(msgid)
        if ref is None or not ref.translated or ref.strs[0] == msgid:
            bad.append(msgid)
    return bad


def main() -> int:
    cats = {loc: parse_po(ROOT / f"locale/{loc}/LC_MESSAGES/django.po") for loc in LOCALES}

    print("=== 1. Каталоги ===")
    for loc, entries in cats.items():
        empty = [e for e in entries.values() if not e.translated]
        ident = [
            e for e in entries.values() if e.translated and not e.plural and e.strs[0] == e.msgid
        ]
        print(
            f"  {loc}: msgid {len(entries):5d} | без перевода {len(empty):4d} "
            f"(для de/en это норма: msgid уже на этом языке) | identity {len(ident):5d}"
        )

    print("\n=== 2. Расхождение наборов msgid между локалями ===")
    union: set[str] = set().union(*(set(e) for e in cats.values()))
    drift = {loc: union - set(entries) for loc, entries in cats.items()}
    if any(drift.values()):
        for loc, miss in drift.items():
            if miss:
                print(f"  {loc}: нет {len(miss)} msgid")
                for m in sorted(miss)[:10]:
                    print(f"      {m[:90]}")
    else:
        print(f"  ок: у всех локалей одинаковые {len(union)} msgid")

    print("\n=== 3. Английский msgid без немецкого перевода ===")
    bad = english_msgid_without_german(cats)
    if bad:
        for m in bad:
            print(f"  «{m[:90]}»")
        print("  → добавить немецкий msgstr в locale/de/LC_MESSAGES/django.po")
    else:
        print("  ок: таких строк нет")

    print("\n=== 4. Строки без пути перевода (не обёрнуты и не в .po) ===")
    import i18n_untranslated as scanner

    findings = scanner.collect()
    baseline = scanner.load_baseline()
    fresh = [f for f in findings if f["text"] not in baseline.get(f["file"], [])]
    print(f"  всего {len(findings)} в {len({f['file'] for f in findings})} файлах")
    print(f"  из них НОВЫХ (вне базовой линии) — {len(fresh)}")
    for f in fresh[:10]:
        print(f"      {f['file']}:{f['line']} [{f['rule']}] «{f['text'][:80]}»")

    print("\n=== 5. gettext внутри f-строк (xgettext их не извлекает) ===")
    risks = [f for f in findings if f["rule"] == "fstring"]
    known = scanner.po_msgids()
    hidden = []
    for path in sorted(ROOT.glob("apps/**/*.py")):
        rel = str(path.relative_to(ROOT))
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        src = path.read_text(encoding="utf-8", errors="ignore")
        if 'f"' not in src and "f'" not in src:
            continue
        import ast

        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for sub in ast.walk(node):
                    if scanner._is_gettext_call(sub) and sub.args:
                        arg = sub.args[0]
                        if isinstance(arg, ast.Constant):
                            hidden.append((rel, sub.lineno, arg.value, arg.value in known))
    if hidden:
        for rel, line, text, in_po in hidden:
            mark = "msgid есть (совпадение с другим местом)" if in_po else "МСГИД ПОТЕРЯН"
            print(f"  {rel}:{line} «{text[:60]}» — {mark}")
    else:
        print("  ок: таких мест нет")
    if risks:
        print(f"  из них без записи в .po: {len(risks)}")

    print("\n=== 6. Сверка «код ⇄ .po» ===")
    if shutil.which("xgettext"):
        rc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "i18n_gap.py")], cwd=ROOT
        ).returncode
        print(f"  i18n_gap.py: {'ок' if rc == 0 else 'НЕ ПОЛНОЕ (см. вывод выше)'}")
    else:
        print("  xgettext не установлен — полная сверка только в CI")
        print("  (локально: apt-get install -y gettext, затем uv run python scripts/i18n_gap.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
