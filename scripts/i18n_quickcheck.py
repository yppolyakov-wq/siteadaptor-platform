"""Быстрая ЛОКАЛЬНАЯ сверка msgid шаблонов с .po (замена i18n_gap без gettext).

`scripts/i18n_gap.py` гоняет `makemessages`, которому нужен xgettext — в дев-
контейнере его нет, поэтому недостающие msgid ловил только CI (дважды за волну
«Кабинет-X»). Этот скрипт разбирает `{% trans "…" %}` / `{% blocktrans %}…`
регулярками: он НЕ заменяет гейт CI (не видит Python-строки и plural-формы),
но ловит самый частый случай — новую строку в шаблоне без записи в каталогах.

Запуск: `uv run python scripts/i18n_quickcheck.py [файлы…]` (по умолчанию —
изменённые в рабочем дереве шаблоны).
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


def po_msgids(locale: str) -> set[str]:
    text = (ROOT / f"locale/{locale}/LC_MESSAGES/django.po").read_text(encoding="utf-8")
    ids, cur, in_id = set(), [], False
    for line in text.splitlines():
        if line.startswith("msgid "):
            cur, in_id = [line[6:].strip().strip('"')], True
        elif in_id and line.startswith('"'):
            cur.append(line.strip().strip('"'))
        elif in_id:
            ids.add("".join(cur))
            in_id = False
    if in_id:
        ids.add("".join(cur))
    return ids


def changed_templates() -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "templates"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout.split()
    return [ROOT / p for p in out if p.endswith(".html")]


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv[1:]] or changed_templates()
    if not files:
        print("i18n-quickcheck: изменённых шаблонов нет")
        return 0
    wanted: set[str] = set()
    for f in files:
        if not f.exists():
            continue
        src = f.read_text(encoding="utf-8")
        wanted |= {m.group(2) for m in TRANS.finditer(src)}
        # blocktrans с плейсхолдерами {{ x }} — сверяем только форму без них
        for m in BLOCKTRANS.finditer(src):
            # Django (templatize) экранирует одиночный «%» в теле как «%%»,
            # а {{ x }} превращает в «%(x)s» — повторяем ту же нормализацию.
            body = m.group(1).replace("%", "%%")
            body = re.sub(r"\{\{\s*(\w+)\s*\}\}", r"%(\1)s", body).strip()
            if body:
                wanted.add(body)
    missing = {}
    for loc in LOCALES:
        gap = sorted(s for s in wanted if s not in po_msgids(loc))
        if gap:
            missing[loc] = gap
    if not missing:
        print(f"i18n-quickcheck: ок ({len(wanted)} msgid из {len(files)} шаблонов)")
        return 0
    for loc, gap in missing.items():
        print(f"{loc}: нет в .po — {len(gap)}")
        for s in gap[:20]:
            print(f"    {s}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
