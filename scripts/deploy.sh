#!/usr/bin/env bash
# Деплой из git. Запускать НА сервере (из любой папки — путь к репо
# определяется автоматически по расположению скрипта):
#   ./scripts/deploy.sh            # прод: Postgres на отдельном db-сервере
#   ./scripts/deploy.sh single     # один сервер: Postgres в Docker здесь же
#
# Или одной командой с локальной машины:
#   ssh hetzner-app '~/projects/siteadaptor-platform/scripts/deploy.sh single'
#
# Идемпотентно: тянет main, пересобирает образы, прогоняет миграции по всем
# схемам, собирает статику, перезапускает сервисы, проверяет health.
set -euo pipefail

# Корень репозитория = на уровень выше папки со скриптом (scripts/).
# Можно переопределить через REPO_DIR=... ./scripts/deploy.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-https://siteadaptor.de/health/ready/}"

# Режим single → активируем профиль с локальным Postgres.
MODE="${1:-prod}"
PROFILE_ARGS=""
if [ "$MODE" = "single" ]; then
	PROFILE_ARGS="--profile single"
fi
# --env-file гарантирует, что ${...} в compose (напр. POSTGRES_PASSWORD:
# ${DB_PASSWORD}) интерполируются из .env.prod, а не из дефолтного .env/shell.
COMPOSE="docker compose --env-file .env.prod -f docker-compose.prod.yml $PROFILE_ARGS"

cd "$REPO_DIR"

echo "==> [1/9] Pull $BRANCH from git"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "==> [2/9] Build images"
$COMPOSE build

if [ "$MODE" = "single" ]; then
	echo "==> [3/9] Start local Postgres and wait for healthy"
	$COMPOSE up -d db
	for i in $(seq 1 30); do
		if $COMPOSE exec -T db pg_isready -U "${DB_USER:-platform}" >/dev/null 2>&1; then
			echo "    db is ready"
			break
		fi
		sleep 2
	done
else
	echo "==> [3/9] External Postgres (DB_HOST in .env.prod) — skip local db"
fi

echo "==> [4/9] Preflight: deploy checks (fail-closed)"
# P0-3 (аудит 2026-09-03): раньше стоял последним шагом под `|| true` — Error
# secrets.E001 (нет отдельного SECRETS_ENCRYPTION_KEY, ключ выводится из
# SECRET_KEY) деплой не останавливал. Теперь ДО миграций и рестарта: упал —
# контейнеры и схемы не тронуты, владелец правит .env.prod и запускает снова.
# Ключ задать безопасно: crypto читает старые шифротексты производным ключом
# (MultiFernet), довести до конца — `manage.py rotate_secrets --apply`.
$COMPOSE run --rm web python manage.py check --deploy

echo "==> [5/9] Migrate shared (public) schema"
$COMPOSE run --rm web python manage.py migrate_schemas --shared

echo "==> [6/9] Migrate tenant schemas"
$COMPOSE run --rm web python manage.py migrate_schemas

echo "==> [7/9] Collect static"
$COMPOSE run --rm web python manage.py collectstatic --noinput
# L4/T1-b: .mo компилируются при СБОРКЕ ОБРАЗА (Dockerfile, msgfmt). Шаг
# `compose run --rm … compilemessages` убран: он писал .mo в эфемерный
# контейнер — рабочий web их не видел (в проде переводы не работали).

echo "==> [8/9] Restart services"
$COMPOSE up -d

echo "==> [9/9] Deploy checks"
# Сверка миграций ПО ВСЕМ СХЕМАМ: обычный showmigrations видит только public, из-за
# чего очередь миграций в памяти проекта разъезжалась с реальностью (аудит 01.08).
# Печатает только отставание — «Всё применено» и есть ожидаемый вывод.
$COMPOSE exec -T web python manage.py migration_state || true
sleep 5
if curl -fsS "$HEALTH_URL" >/dev/null; then
	echo "OK: readiness passed"
else
	echo "WARN: readiness check failed — смотри логи: $COMPOSE logs --tail=50 web"
	exit 1
fi

echo "==> Deploy complete (mode: $MODE)."
