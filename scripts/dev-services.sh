#!/usr/bin/env bash
# Идемпотентно поднимает локальные Postgres 16 + Redis 7 для прогона тестов в
# песочнице Claude Code on the web. Контейнер может ронять службы между шагами,
# поэтому скрипт безопасно вызывать сколько угодно раз.
#
# Локальный прогон тестов — это ФОЛБЭК. Основная проверка идёт на git
# (GitHub Actions); локально гоняем, только если CI на git показал красный.
#
# Использование: bash scripts/dev-services.sh
set -uo pipefail

# --- Postgres 16 (кластер main на :5432) ---
if ! pg_lsclusters 2>/dev/null | awk '$1=="16" && $2=="main"{print $4}' | grep -q online; then
  pg_ctlcluster 16 main start >/dev/null 2>&1 || true
fi

# --- Redis на :6379 ---
if ! redis-cli ping >/dev/null 2>&1; then
  redis-server --daemonize yes --port 6379 >/dev/null 2>&1 || true
fi

# --- Роль и БД как в CI (idempotent) ---
su postgres -c \
  "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='platform'\" | grep -q 1 \
   || psql -c \"CREATE ROLE platform LOGIN PASSWORD 'platform' SUPERUSER\"" \
  >/dev/null 2>&1 || true
su postgres -c \
  "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='platform'\" | grep -q 1 \
   || psql -c \"CREATE DATABASE platform OWNER platform\"" \
  >/dev/null 2>&1 || true

# --- Статус ---
pg_ok=$(PGPASSWORD=platform psql -h localhost -U platform -d platform -tAc "select 'up'" 2>/dev/null)
redis_ok=$(redis-cli ping 2>/dev/null)
echo "postgres: ${pg_ok:-DOWN}  redis: ${redis_ok:-DOWN}"
