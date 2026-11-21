# ECC (Everything Claude Code) — копия в репозитории

Источник: https://github.com/affaan-m/ECC, коммит `b92f181b3b748d1abbc2afd94af6aa7d8c8fca29`
(2026-10-11), лицензия MIT — `LICENSE` рядом (относится к агентам и скиллам в `.claude/`).

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

## Общие правила ECC сняты (T-13.0, 2026-11-21)

Каталог `.claude/rules/ecc/` (common + python, 16 файлов, 24 КБ) удалён, этот README и LICENSE
перенесены сюда: всё, что лежит в `.claude/rules/`, грузится каждой сессии и каждому субагенту,
а большая часть правил была отменена в `project-overrides.md`. При обновлении копии ECC
правила обратно НЕ копировать (замок `apps/core/tests/test_claude_rules_budget.py`).

| Файл | Почему снят |
|---|---|
| `common/testing.md`, `python/testing.md` | порог 80 %, обязательные E2E, TS-примеры, `--cov=src` — не требования проекта |
| `common/git-workflow.md` | conventional commits; у нас `<ID задачи>: …` |
| `common/patterns.md`, `python/patterns.md` | Repository-паттерн, API-конверты — не переписываем под них |
| `common/performance.md` | выбор модели и эффорта — не меняем без просьбы владельца |
| `common/hooks.md`, `python/hooks.md` | TodoWrite, black/mypy-хуки — у нас ruff и свои хуки |
| `common/development-workflow.md` | `gh search`, PRD-доки, conventional commits — цикл задаёт `CLAUDE.md` §5 |
| `python/fastapi.md` | проект на Django |
| `python/coding-style.md`, `python/security.md` | black/isort, dotenv, bandit — у нас ruff и django-environ |
| `common/agents.md`, `code-review.md`, `security.md`, `coding-style.md` | полезное сжато в `.claude/rules/review-and-agents.md` |

Сохранённое из снятых файлов: контракт завершения делегирования, уровни серьёзности ревью и
условие мержа, триггеры `security-reviewer`, чеклист безопасности перед коммитом, «чинить
реализацию, а не тест», запрет `dangerously-skip-permissions`.
