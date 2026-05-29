#!/usr/bin/env bash
# Деплой из git. Запускать НА сервере из корня репозитория:
#   ./scripts/deploy.sh            # прод: Postgres на отдельном db-сервере
#   ./scripts/deploy.sh single     # один сервер: Postgres в Docker здесь же
#
# Или одной командой с локальной машины:
#   ssh hetzner-app 'cd /opt/siteadaptor-platform && ./scripts/deploy.sh single'
#
# Идемпотентно: тянет main, пересобирает образы, прогоняет миграции по всем
# схемам, собирает статику, перезапускает сервисы, проверяет health.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/siteadaptor-platform}"
BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-https://siteadaptor.de/health/ready/}"

# Режим single → активируем профиль с локальным Postgres.
MODE="${1:-prod}"
PROFILE_ARGS=""
if [ "$MODE" = "single" ]; then
	PROFILE_ARGS="--profile single"
fi
COMPOSE="docker compose -f docker-compose.prod.yml $PROFILE_ARGS"

cd "$REPO_DIR"

echo "==> [1/8] Pull $BRANCH from git"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "==> [2/8] Build images"
$COMPOSE build

if [ "$MODE" = "single" ]; then
	echo "==> [3/8] Start local Postgres and wait for healthy"
	$COMPOSE up -d db
	for i in $(seq 1 30); do
		if $COMPOSE exec -T db pg_isready -U "${DB_USER:-platform}" >/dev/null 2>&1; then
			echo "    db is ready"
			break
		fi
		sleep 2
	done
else
	echo "==> [3/8] External Postgres (DB_HOST in .env.prod) — skip local db"
fi

echo "==> [4/8] Migrate shared (public) schema"
$COMPOSE run --rm web python manage.py migrate_schemas --shared

echo "==> [5/8] Migrate tenant schemas"
$COMPOSE run --rm web python manage.py migrate_schemas

echo "==> [6/8] Collect static"
$COMPOSE run --rm web python manage.py collectstatic --noinput

echo "==> [7/8] Restart services"
$COMPOSE up -d

echo "==> [8/8] Deploy checks"
$COMPOSE exec -T web python manage.py check --deploy || true
sleep 5
if curl -fsS "$HEALTH_URL" >/dev/null; then
	echo "OK: readiness passed"
else
	echo "WARN: readiness check failed — смотри логи: $COMPOSE logs --tail=50 web"
	exit 1
fi

echo "==> Deploy complete (mode: $MODE)."
