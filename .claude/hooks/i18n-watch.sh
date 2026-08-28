#!/bin/bash
# I18N-13, уровень 1: PostToolUse-хук. После правки .py/.html сразу проверяет
# ТОЛЬКО этот файл на строки без пути перевода (сканер) и на новые msgid без
# записи в .po (quickcheck). Молчит, когда всё чисто; при находке пишет в stderr
# и выходит с кодом 2 — Claude Code показывает текст модели в том же ходу.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

FILE=$(python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit
inp = data.get("tool_input") or {}
print(inp.get("file_path") or inp.get("notebook_path") or "")
' 2>/dev/null)

case "$FILE" in
  *.py|*.html) ;;
  *) exit 0 ;;
esac
case "$FILE" in
  */migrations/*|*/tests/*|*/locale/*) exit 0 ;;
esac
# Только живой код приложения и шаблоны (в scripts/ и docs/ литералы _("…") —
# примеры в подсказках, они дали бы ложную тревогу).
case "${FILE#"${CLAUDE_PROJECT_DIR:-.}/"}" in
  apps/*|templates/*|config/*) ;;
  *) exit 0 ;;
esac
[ -f "$FILE" ] || exit 0

RUN="uv run --no-sync python"
command -v uv >/dev/null 2>&1 || RUN="python3"

OUT=$( { $RUN scripts/i18n_untranslated.py --check --files "$FILE"; } 2>&1 )
RC=$?
OUT2=$( { $RUN scripts/i18n_quickcheck.py "$FILE"; } 2>&1 )
RC2=$?

if [ $RC -ne 0 ] || [ $RC2 -ne 0 ]; then
  {
    echo "i18n: в $FILE есть строки, которые не доедут до перевода."
    [ $RC -ne 0 ] && echo "$OUT"
    [ $RC2 -ne 0 ] && echo "$OUT2"
    echo "Обернуть в gettext_lazy/{% trans %} + добавить msgid во все locale/*/django.po,"
    echo "либо (контент/демо) внести в базовую линию: scripts/i18n_untranslated.py --write-baseline"
  } >&2
  exit 2
fi
exit 0
