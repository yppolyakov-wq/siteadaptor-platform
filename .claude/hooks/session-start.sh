#!/bin/bash
# SessionStart hook (Claude Code on the web): поднимает локальные службы и
# зависимости, чтобы фолбэк-прогон тестов работал. Основная проверка — на git
# (GitHub Actions); локально гоняем, только если CI на git показал красный.
set -uo pipefail

# Только в удалённой среде (Claude Code on the web).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# 1) Postgres 16 + Redis 7 + роль/БД (идемпотентно).
bash scripts/dev-services.sh || echo "warn: dev-services failed"

# 2) venv + зависимости (файлы кешируются в состоянии контейнера после хука).
if [ ! -d .venv ]; then
  uv venv --python 3.12 || echo "warn: uv venv failed"
fi
uv pip install -e ".[dev]" >/dev/null 2>&1 || echo "warn: dep install failed"

# 3) Dev-переменные окружения для тестов (НЕ секреты — те же значения, что в
#    .github/workflows/ci.yml). Пишем в CLAUDE_ENV_FILE, если он задан.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  cat >>"$CLAUDE_ENV_FILE" <<'ENV'
export SECRET_KEY=ci-test-secret-key-not-for-production
export DEBUG=True
export ALLOWED_HOSTS='*'
export DB_NAME=platform
export DB_USER=platform
export DB_PASSWORD=platform
export DB_HOST=localhost
export DB_PORT=5432
export REDIS_URL=redis://localhost:6379/0
export REDIS_CACHE_URL=redis://localhost:6379/1
export REDIS_RESULT_URL=redis://localhost:6379/2
ENV
fi

echo "session-start: services + deps ready"
