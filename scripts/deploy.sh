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

# T-10: длительность каждого шага — чтобы видеть, что именно тормозит деплой.
DEPLOY_START=$SECONDS
STEP_START=$SECONDS
STEP_NAME=""
step() {
	if [ -n "$STEP_NAME" ]; then
		echo "    ⏱ $STEP_NAME: $((SECONDS - STEP_START)) с"
	fi
	STEP_NAME="$1"
	STEP_START=$SECONDS
	echo "==> $1"
}

step "[1/8] Pull $BRANCH from git"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

step "[2/8] Build images"
# Один образ (web) на web/worker/beat + caddy; слой зависимостей берётся из кэша,
# пока не менялся uv.lock (T-10).
$COMPOSE build
# Тег образа по коммиту — для отката: `docker tag siteadaptor-app:<sha> siteadaptor-app:latest`
# и `$COMPOSE up -d` (latest перезаписывается каждой сборкой).
docker tag siteadaptor-app:latest "siteadaptor-app:$(git rev-parse --short HEAD)" || true

if [ "$MODE" = "single" ]; then
	step "[3/8] Start local Postgres and wait for healthy"
	$COMPOSE up -d db
	for i in $(seq 1 30); do
		if $COMPOSE exec -T db pg_isready -U "${DB_USER:-platform}" >/dev/null 2>&1; then
			echo "    db is ready"
			break
		fi
		sleep 2
	done
else
	step "[3/8] External Postgres (DB_HOST in .env.prod) — skip local db"
fi

step "[4/8] Preflight: deploy checks (fail-closed)"
# P0-3 (аудит 2026-09-03): раньше стоял последним шагом под `|| true` — Error
# secrets.E001 (нет отдельного SECRETS_ENCRYPTION_KEY, ключ выводится из
# SECRET_KEY) деплой не останавливал. Теперь ДО миграций и рестарта: упал —
# контейнеры и схемы не тронуты, владелец правит .env.prod и запускает снова.
# Ключ задать безопасно: crypto читает старые шифротексты производным ключом
# (MultiFernet), довести до конца — `manage.py rotate_secrets --apply`.
$COMPOSE run --rm web python manage.py check --deploy

step "[5/8] Migrate shared (public) schema"
$COMPOSE run --rm web python manage.py migrate_schemas --shared

step "[6/8] Migrate tenant schemas"
# T-10: если по всем схемам применять нечего — шаг пропускается (раньше сотня схем
# проходилась по одной на каждом деплое). Иначе — параллельно
# (TENANT_MIGRATION_PROCESSES, по умолчанию 3). FORCE_MIGRATE=1 — прогнать всегда.
if [ "${FORCE_MIGRATE:-0}" != "1" ] \
	&& $COMPOSE run --rm web python manage.py migration_state --check; then
	echo "    все схемы на последней миграции — пропуск"
else
	# Сбой параллельного прогона (взаимная блокировка на public-таблицах и т. п.) —
	# повтор по одной схеме: миграции атомарны, применённое не повторяется.
	$COMPOSE run --rm web python manage.py migrate_schemas --tenant --executor=multiprocessing \
		|| { echo "    параллельно не вышло — повтор по одной схеме"; \
			$COMPOSE run --rm web python manage.py migrate_schemas --tenant; }
fi
# collectstatic делает сам web при старте (compose). Отдельный шаг `run --rm
# collectstatic` писал во временный контейнер и только тратил время (T-10).
# L4/T1-b: .mo компилируются при СБОРКЕ ОБРАЗА (Dockerfile, msgfmt).

step "[7/8] Restart services"
$COMPOSE up -d

step "[8/8] Deploy checks"
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

step "done"
echo "==> Deploy complete (mode: $MODE) за $((SECONDS - DEPLOY_START)) с."
