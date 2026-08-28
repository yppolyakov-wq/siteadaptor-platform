"""Быстрая ЛОКАЛЬНАЯ сверка msgid шаблонов с .po (замена i18n_gap без gettext).

`scripts/i18n_gap.py` гоняет `makemessages`, которому нужен xgettext — в дев-
контейнере его нет, поэтому недостающие msgid ловил только CI (дважды за волну
«Кабинет-X»). Этот скрипт разбирает `{% trans "…" %}` / `{% blocktrans %}…`
регулярками, плюс литералы `_("…")` / `gettext…("…")` в Python. Он НЕ заменяет
гейт CI (не знает plural-форм и контекстов), но ловит самый частый случай —
новую строку без записи в каталогах.

X4: сканирование .py добавлено после того, как six новых меток реестра
навигации прошли мимо шаблонной проверки (скрипт смотрел только templates/).

Запуск: `uv run python scripts/i18n_quickcheck.py [файлы…]` (по умолчанию —
изменённые в рабочем дереве шаблоны и Python-модули).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ("de", "en", "tr", "ru", "uk")
TRANS = re.compile(r"{%\s*trans\s+([\"'])(.+?)\1")
BLOCKTRANS = re.compile(r"{%\s*blocktrans[^%]*%}(.*?){%\s*endblocktrans\s*%}", re.S)
# Python: _("…") / gettext("…") / gettext_lazy("…") — ТОЛЬКО строковый литерал
# в одинарных кавычках без конкатенации (f-строки xgettext и так не берёт).
PY_TRANS = re.compile(r"\b(?:_|gettext|gettext_lazy|pgettext|ngettext)\(\s*([\"'])(.+?)\1\s*[,)]")
# Волна SH: длинная подсказка была РАЗБИТА на соседние литералы («…» «…»), и
# проверка её не видела — msgid поймал только CI. Ловим склейку явно.
PY_TRANS_JOINED = re.compile(
    # Литерал = две альтернативы по типу кавычки: тело исключает СВОЮ кавычку,
    # поэтому апостроф внутри двойных кавычек («we'll») склейку не рвёт, а
    # выражение не «перепрыгивает» через код между соседними строками.
    r"\b(?:_|gettext|gettext_lazy|pgettext|ngettext)\(\s*"
    r"((?:(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')\s*){2,})\)?",
    re.S,
)
LITERAL = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")


def _unescape(text: str) -> str:
    """`.po` хранит msgid экранированным: `Show \\"View all\\" link`. Без снятия
    экранирования сверка врёт на любой строке с кавычками (ложная тревога
    pre-commit-хука, 2026-08-27)."""
    return text.replace('\\"', '"').replace("\\\\", "\\")


def po_msgids(locale: str) -> set[str]:
    text = (ROOT / f"locale/{locale}/LC_MESSAGES/django.po").read_text(encoding="utf-8")
    ids, cur, in_id = set(), [], False
    for line in text.splitlines():
        if line.startswith("msgid "):
            cur, in_id = [line[6:].strip().strip('"')], True
        elif in_id and line.startswith('"'):
            cur.append(line.strip().strip('"'))
        elif in_id:
            ids.add(_unescape("".join(cur)))
            in_id = False
    if in_id:
        ids.add(_unescape("".join(cur)))
    return ids


def changed_sources() -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "templates", "apps", "config"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout.split()
    return [
        ROOT / p
        for p in out
        if (p.endswith(".html") or p.endswith(".py"))
        and "/migrations/" not in p
        and "/tests/" not in p
    ]


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv[1:]] or changed_sources()
    if not files:
        print("i18n-quickcheck: изменённых исходников нет")
        return 0
    wanted: set[str] = set()
    for f in files:
        if not f.exists():
            continue
        src = f.read_text(encoding="utf-8")
        if f.suffix == ".py":
            for m in PY_TRANS_JOINED.finditer(src):
                lit = "".join(x.group(0)[1:-1] for x in LITERAL.finditer(m.group(1)))
                if "\\" in lit:
                    continue
                if "%" in lit and "%(" not in lit:
                    lit = lit.replace("%", "%%")
                wanted.add(lit)
            for m in PY_TRANS.finditer(src):
                lit = m.group(2)
                if "\\" in lit:
                    continue  # экранирование внутри литерала — пропускаем (шум)
                # Одиночный «%» в Python-строке попадает в .po как «%%» (так его
                # пишет makemessages); строки с настоящими плейсхолдерами
                # %(name)s остаются как есть.
                if "%" in lit and "%(" not in lit:
                    lit = lit.replace("%", "%%")
                wanted.add(lit)
            continue
        # X6: `{% trans %}` тоже проходит через templatize — одиночный «%»
        # попадает в .po как «%%» (нашлось на units.html: «Preisänderung (%…)»).
        for m in TRANS.finditer(src):
            lit = m.group(2)
            if "%" in lit and "%(" not in lit:
                lit = lit.replace("%", "%%")
            wanted.add(lit)
        # blocktrans с плейсхолдерами {{ x }} — сверяем только форму без них
        for m in BLOCKTRANS.finditer(src):
            if "{% plural %}" in m.group(1):
                continue  # plural-формы разбирает только gettext (CI-гейт)
            # Django (templatize) экранирует одиночный «%» в теле как «%%»,
            # а {{ x }} превращает в «%(x)s» — повторяем ту же нормализацию.
            body = m.group(1).replace("%", "%%")
            body = re.sub(r"\{\{\s*(\w+)\s*\}\}", r"%(\1)s", body).strip()
            if body:
                wanted.add(body)
    missing = {}
    for loc in LOCALES:
        ids = po_msgids(loc)
        # «%» в .po хранится то как «%», то как «%%» — xgettext помечает строку
        # python-format только при настоящем плейсхолдере. Считаем найденной
        # ЛЮБУЮ из двух форм, иначе проверка врёт на подсказках вида «95 % Baumwolle».
        gap = sorted(s for s in wanted if s not in ids and s.replace("%%", "%") not in ids)
        if gap:
            missing[loc] = gap
    if not missing:
        print(f"i18n-quickcheck: ок ({len(wanted)} msgid из {len(files)} файлов)")
        return 0
    for loc, gap in missing.items():
        print(f"{loc}: нет в .po — {len(gap)}")
        for s in gap[:20]:
            print(f"    {s}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
