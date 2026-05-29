#!/usr/bin/env bash
# Деплой из git на app-сервер. Запускать НА сервере из корня репозитория:
#   ./scripts/deploy.sh
# Или одной командой с локальной машины:
#   ssh hetzner-app 'cd /opt/siteadaptor-platform && ./scripts/deploy.sh'
#
# Идемпотентно: тянет main, пересобирает образы, прогоняет миграции по всем
# схемам, собирает статику, перезапускает сервисы, проверяет health.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/siteadaptor-platform}"
BRANCH="${DEPLOY_BRANCH:-main}"
COMPOSE="docker compose -f docker-compose.prod.yml"

cd "$REPO_DIR"

echo "==> [1/7] Pull $BRANCH from git"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "==> [2/7] Build images"
$COMPOSE build

echo "==> [3/7] Migrate shared (public) schema"
$COMPOSE run --rm web python manage.py migrate_schemas --shared

echo "==> [4/7] Migrate tenant schemas"
$COMPOSE run --rm web python manage.py migrate_schemas

echo "==> [5/7] Collect static"
$COMPOSE run --rm web python manage.py collectstatic --noinput

echo "==> [6/7] Restart services"
$COMPOSE up -d

echo "==> [7/7] Deploy checks"
$COMPOSE exec -T web python manage.py check --deploy || true
sleep 5
if curl -fsS https://siteadaptor.de/health/ready/ >/dev/null; then
	echo "OK: readiness passed"
else
	echo "WARN: readiness check failed — смотри логи: $COMPOSE logs --tail=50 web"
	exit 1
fi

echo "==> Deploy complete."
