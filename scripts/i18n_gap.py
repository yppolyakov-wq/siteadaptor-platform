"""I18N-9: гейт покрытия переводов — какие msgid есть в КОДЕ, но нет в `.po`.

Зачем: `.po` в этом проекте велись руками, а `makemessages` долго падал на
конфликте msgid (одна и та же строка как единственное и как множественное
число) — из-за этого сотни `{% trans %}` жили без переводов и молча выводились
по-немецки в ru/tr/uk/en. Гейт делает разрыв видимым сразу.

Как работает: гоняет `makemessages` во ВРЕМЕННУЮ локаль `xx` (реальные `.po`
не трогаются), сравнивает извлечённые msgid с содержимым `locale/<loc>/…po`
и падает, если появилось непокрытое.

Осознанное исключение — `apps/tenants/archetype_pages.py`: маркетинговая копия
Branchen-лендингов (SEO-текст под DACH). Её перевод — отдельное решение
владельца, а не техдолг; см. `docs/i18n-full-coverage-plan-2026-07-30.md`.

Запуск: `uv run python scripts/i18n_gap.py` (нужен gettext/xgettext).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ("de", "en", "tr", "ru", "uk")
# Локали, где перевод обязателен (в de/en часть msgid совпадает с текстом — там
# пустой msgstr означает «строка уже на этом языке», это норма).
REQUIRE_NONEMPTY = ("tr", "ru", "uk")
ALLOWED_SOURCES = ("apps/tenants/archetype_pages.py",)
TMP_LOCALE = "xx"


def parse_po(path: Path) -> dict[str, list[str]]:
    """{msgid: [msgstr, …]} — плоский разбор (без учёта контекстов, их в проекте нет)."""
    entries: dict[str, list[str]] = {}
    msgid: str | None = None
    strs: list[str] = []
    mode: str | None = None

    def flush() -> None:
        nonlocal msgid, strs
        if msgid:
            entries[msgid] = list(strs)
        msgid, strs = None, []

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.startswith("#"):
            continue
        m = re.match(r'^(msgid|msgid_plural|msgstr(?:\[\d+\])?)\s+"(.*)"$', line)
        if m:
            key, val = m.group(1), m.group(2)
            if key == "msgid":
                flush()
                msgid, mode = val, "id"
            elif key == "msgid_plural":
                mode = "plural"
            else:
                strs.append(val)
                mode = "str"
            continue
        cont = re.match(r'^"(.*)"$', line.strip())
        if cont and mode:
            if mode == "id" and msgid is not None:
                msgid += cont.group(1)
            elif mode == "str" and strs:
                strs[-1] += cont.group(1)
    flush()
    return entries


def sources_by_msgid(path: Path) -> dict[str, list[str]]:
    """{msgid: [файл, …]} из `#:`-комментариев свежей экстракции."""
    out: dict[str, list[str]] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    locs: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#: "):
            locs += re.findall(r"(\S+?):\d+", line[3:])
        elif line.startswith("msgid "):
            msgid = re.match(r'^msgid "(.*)"$', line).group(1)
            j = i + 1
            while j < len(lines) and lines[j].startswith('"'):
                msgid += lines[j].strip()[1:-1]
                j += 1
            if msgid:
                out[msgid] = locs
            locs, i = [], j
            continue
        elif not line.strip():
            locs = []
        i += 1
    return out


def extract() -> Path:
    """Свежая экстракция во временную локаль; возвращает путь к .po."""
    tmp_dir = ROOT / "locale" / TMP_LOCALE
    shutil.rmtree(tmp_dir, ignore_errors=True)
    env = dict(os.environ)
    env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    env.setdefault("SECRET_KEY", "i18n-gap-check")
    subprocess.run(
        [
            sys.executable,
            "manage.py",
            "makemessages",
            "-l",
            TMP_LOCALE,
            "-i",
            ".venv",
            "-i",
            "node_modules",
            "-i",
            "staticfiles",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    return tmp_dir / "LC_MESSAGES" / "django.po"


def main() -> int:
    po = extract()
    extracted = parse_po(po)
    srcs = sources_by_msgid(po)
    shutil.rmtree(ROOT / "locale" / TMP_LOCALE, ignore_errors=True)

    def allowed(msgid: str) -> bool:
        files = srcs.get(msgid) or []
        return bool(files) and all(f.startswith(ALLOWED_SOURCES) for f in files)

    failures: list[str] = []
    for loc in LOCALES:
        have = parse_po(ROOT / "locale" / loc / "LC_MESSAGES" / "django.po")
        missing = [k for k in extracted if k not in have and not allowed(k)]
        if missing:
            failures.append(f"{loc}: {len(missing)} msgid без записи в .po")
            for k in missing[:15]:
                failures.append(f"    {k[:100]}")
        if loc in REQUIRE_NONEMPTY:
            empty = [k for k, v in have.items() if k in extracted and not allowed(k) and not any(v)]
            if empty:
                failures.append(f"{loc}: {len(empty)} msgid с пустым переводом")
                for k in empty[:15]:
                    failures.append(f"    {k[:100]}")

    if failures:
        print("i18n-покрытие: НЕ полное", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        print(
            "\nДобавьте msgid с переводами во ВСЕ locale/*/LC_MESSAGES/django.po "
            "(конвенция проекта — правим .po вручную, makemessages не перезаписывает их).",
            file=sys.stderr,
        )
        return 1
    print(f"i18n-покрытие: ок ({len(extracted)} msgid, исключения: {', '.join(ALLOWED_SOURCES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
