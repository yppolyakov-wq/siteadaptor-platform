# ECC (Everything Claude Code) — копия в репозитории

Источник: https://github.com/affaan-m/ECC, коммит `b92f181b3b748d1abbc2afd94af6aa7d8c8fca29`
(2026-10-11), лицензия MIT — `LICENSE` рядом.

**Почему копия, а не плагин:** облачные сессии (claude.ai/code) плагины не загружают,
даже включённые в `.claude/settings.json` репозитория. Подхватываются только файлы,
лежащие в репозитории: `.claude/rules/`, `.claude/agents/`, `.claude/skills/`.

Что взято (набор под Django):
- правила — `.claude/rules/ecc/common/`, `.claude/rules/ecc/python/` (целыми папками,
  внутри относительные ссылки `../common/...`);
- агенты — `.claude/agents/`: planner, architect, code-reviewer, security-reviewer,
  python-reviewer, django-reviewer, database-reviewer, django-build-resolver, tdd-guide;
- скиллы — `.claude/skills/`: django-patterns, django-security, django-tdd, django-celery,
  python-patterns, python-testing, postgres-patterns, redis-patterns.

Имена агентов БЕЗ префикса `ecc:` (в правилах ECC упоминается `ecc:planner` — у нас `planner`).
Хуки ECC не перенесены. Обновление: склонировать ECC и заново скопировать эти файлы.

При конфликте с проектом действуют `.claude/rules/project-overrides.md` и `CLAUDE.md`.
