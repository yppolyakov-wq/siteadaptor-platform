# ECC rules (vendored)

Источник: https://github.com/affaan-m/ECC, `rules/common` + `rules/python`,
коммит `b92f181b3b748d1abbc2afd94af6aa7d8c8fca29` (2026-10-11), лицензия — LICENSE.
Копируются ЦЕЛЫМИ папками (внутри относительные ссылки `../common/...`).
Обновление: склонировать ECC и заново скопировать обе папки.

Сам плагин (агенты/скиллы/хуки) подключён в `.claude/settings.json`
(`enabledPlugins: ecc@ecc`, хуки в профиле `ECC_HOOK_PROFILE=minimal`).

При конфликте с проектом действует `.claude/rules/project-overrides.md` и `CLAUDE.md`.
