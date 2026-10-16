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

Дополнено 2026-10-16 (ECC коммит `76aaa77df6adc5b889e689007bf99b9a4f74af34`; прежние 17 файлов
сверены — идентичны новой версии):
- агенты: e2e-runner, doc-updater, silent-failure-hunter, seo-specialist, a11y-architect;
- скиллы: api-design, e2e-testing, database-migrations, deployment-patterns, docker-patterns,
  django-verification, seo, accessibility, error-handling.

Осознанно НЕ взято (весь каталог: 71 агент, 311 скиллов — сверено 2026-10-16): ревьюеры/
резолверы других языков и фреймворков (JS/TS/React/Vue/Go/Rust/Java/Kotlin/Swift/C#/PHP/Ruby/
Laravel/Spring/FastAPI…), refactor-cleaner и performance-optimizer (заточены под npm-инструменты),
i18n-sync (JSON-локали, у нас gettext `.po`), mcp-server-patterns (Node SDK), security-scan
(требует npx AgentShield), агентные/маркетинговые/сетевые/медицинские/научные наборы.
Дополнено 2026-10-16 (второй батч, тот же коммит ECC): агент marketing-agent; скиллы
market-research, marketing-campaign, competitive-platform-analysis → benchmark-methodology →
competitive-report-structure (цепочка конкурентного анализа), product-lens, mcp-server-patterns
(к MCP-приложению каталога T-8.10f; SDK в нём Node — у нас Python, см. project-overrides).

Имена агентов БЕЗ префикса `ecc:` (в правилах ECC упоминается `ecc:planner` — у нас `planner`).
Хуки ECC не перенесены. Обновление: склонировать ECC и заново скопировать эти файлы.

При конфликте с проектом действуют `.claude/rules/project-overrides.md` и `CLAUDE.md`.
