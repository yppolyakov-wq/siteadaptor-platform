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

# FB-33 M3-9b: два деплоя сразу на одном сервере — второй выходит, не начав (раньше оба
# собирали образ и мигрировали вперемешку). Блокировка — файл на этом сервере; снимается
# сама, когда скрипт завершается (в том числе аварийно).
DEPLOY_LOCK_FILE="${DEPLOY_LOCK_FILE:-${TMPDIR:-/tmp}/siteadaptor-deploy.lock}"
if command -v flock >/dev/null 2>&1; then
	exec 9>"$DEPLOY_LOCK_FILE"
	if ! flock -n 9; then
		echo "!!! Другой деплой уже идёт на этом сервере ($DEPLOY_LOCK_FILE занят)." >&2
		echo "!!! Дождитесь его конца и запустите снова." >&2
		exit 1
	fi
else
	echo "    WARN: flock не найден — защита от двух деплоев сразу выключена"
fi

# FB-33 M3-9b: миграции идут под общей блокировкой операций над схемами
# (apps/core/ops_lock.py) — её же берёт пересев демо (seed_demo_tenants): пересев удалял
# схему, которую мигрировал деплой (MigrationSchemaMissing). Занята — ждём OPS_LOCK_TIMEOUT
# секунд (по умолчанию 900) и останавливаем деплой с понятным сообщением, а не висим.
# LOCK_BUSY — код выхода run_locked «не дождались» (ops_lock.EXIT_BUSY).
LOCK_BUSY=75
LOCK_ENV="-e OPS_LOCK_TIMEOUT=${OPS_LOCK_TIMEOUT:-900}"
lock_busy_stop() {
	echo "!!! Блокировка операций над схемами занята дольше ${OPS_LOCK_TIMEOUT:-900} с:" >&2
	echo "!!! идёт пересев демо (seed_demo_tenants) или миграции другого деплоя." >&2
	echo "!!! Схемы этим шагом НЕ тронуты, сервисы работают на прежней версии." >&2
	echo "!!! Дождитесь конца той операции и запустите деплой снова" >&2
	echo "!!! (дольше ждать: OPS_LOCK_TIMEOUT=3600 ./scripts/deploy.sh ...)." >&2
	exit 1
}

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

step "[2b/8] Media volume owner (non-root app)"
# SEC-G11b: приложение работает под uid 10001, а том media создавался, когда оно было
# root, — без выравнивания загрузка фото упала бы «Permission denied». Меняем владельца
# ТОЛЬКО у несовпадающих файлов: первый деплой выравнивает том, следующие находят ноль
# файлов за секунды. Ошибка здесь останавливает деплой (set -e) — лучше, чем молча
# запустить приложение, которое не сможет писать загрузки.
# `set -e` внутри: иначе код возврата sh -c — это последний echo, и ошибка chown
# проглатывалась бы. `chown -h` меняет сам симлинк, не уходя по нему за пределы тома.
# Пересчёт после chown ловит ФС, где chown «успешен», но ничего не меняет (NFS
# root_squash); проба записи от имени app доказывает главное — загрузки будут писаться.
MEDIA_ALIGN='set -eu; test -d /app/media; \
	 n=$(find /app/media \( ! -uid 10001 -o ! -gid 10001 \) -exec chown -h 10001:10001 {} + -print | wc -l); \
	 left=$(find /app/media \( ! -uid 10001 -o ! -gid 10001 \) -print | wc -l); \
	 [ "$left" -eq 0 ] || { echo "media: $left файлов всё ещё не 10001" >&2; exit 1; }; \
	 echo "    media: владелец выровнен у $n файлов"'
$COMPOSE run --rm --no-deps --user 0 web sh -c "$MEDIA_ALIGN"
$COMPOSE run --rm --no-deps web sh -ec 'f=/app/media/.deploy-write-test; : > "$f"; rm -f "$f"'

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
rc=0
# shellcheck disable=SC2086
$COMPOSE run --rm $LOCK_ENV web python manage.py run_locked migrate_schemas --shared || rc=$?
if [ "$rc" = "$LOCK_BUSY" ]; then lock_busy_stop; fi
if [ "$rc" != "0" ]; then exit "$rc"; fi

step "[6a/8] Schema template (fast schema creation)"
# T-10 D-1: шаблон, копией которого создаются новые схемы (регистрация, пересев демо).
# Идемпотентно; свежий шаблон — секунды. Сбой не валит деплой: без шаблона схемы
# создаются прежним путём миграциями.
$COMPOSE run --rm web python manage.py ensure_template_schema \
	|| echo "    шаблон не готов — новые схемы будут создаваться миграциями"

step "[6b/8] Migrate tenant schemas"
# T-10: если по всем схемам применять нечего — шаг пропускается (раньше сотня схем
# проходилась по одной на каждом деплое). Иначе — параллельно
# (TENANT_MIGRATION_PROCESSES, по умолчанию 3). FORCE_MIGRATE=1 — прогнать всегда.
if [ "${FORCE_MIGRATE:-0}" != "1" ] \
	&& $COMPOSE run --rm web python manage.py migration_state --check; then
	echo "    все схемы на последней миграции — пропуск"
else
	# Сбой параллельного прогона (взаимная блокировка на public-таблицах и т. п.) —
	# повтор по одной схеме: миграции атомарны, применённое не повторяется.
	# Занятая блокировка (код LOCK_BUSY) — не сбой миграций: повтор ждал бы её ещё раз.
	rc=0
	# shellcheck disable=SC2086
	$COMPOSE run --rm $LOCK_ENV web python manage.py run_locked migrate_schemas --tenant --executor=multiprocessing || rc=$?
	if [ "$rc" = "$LOCK_BUSY" ]; then lock_busy_stop; fi
	if [ "$rc" != "0" ]; then
		echo "    параллельно не вышло — повтор по одной схеме"
		rc=0
		# shellcheck disable=SC2086
		$COMPOSE run --rm $LOCK_ENV web python manage.py run_locked migrate_schemas --tenant || rc=$?
		if [ "$rc" = "$LOCK_BUSY" ]; then lock_busy_stop; fi
		if [ "$rc" != "0" ]; then exit "$rc"; fi
	fi
fi
# collectstatic делает сам web при старте (compose). Отдельный шаг `run --rm
# collectstatic` писал во временный контейнер и только тратил время (T-10).
# L4/T1-b: .mo компилируются при СБОРКЕ ОБРАЗА (Dockerfile, msgfmt).

# FB-33 M2c (решение владельца): плитки «Schnellzugriff» из баннера главной -> отдельный блок
# сразу после баннера (у «Bento» — скрытым), форма дат -> секция «Suche», топ услуг -> список.
# M2c-4 (ревью): ДО подъёма нового web — новый код ключ `hero_widget` не читает, и любое
# сохранение настроек неперенесённого сайта молча уронило бы ключ (плитки пропали бы без
# снимка). Пока идёт шаг, работает старый web — он читает и ключ, и блок. На чистых данных
# шаг no-op. Порядок теперь «перенос плиток → (после подъёма) materialize_page_axes»;
# откаты — в обратном порядке: сначала materialize_page_axes --undo, затем
# detach_quick_links --undo --force (только вместе с откатом кода M2c-4).
step "[6c/8] Quick links: banner tiles -> block (before the new web starts)"
if ! $COMPOSE run --rm web python manage.py detach_quick_links; then
	echo "!!! WARN: detach_quick_links FAILED or skipped some sites (see lines above)."
	echo "!!! On those sites tiles are NOT shown until detach_quick_links runs; do not save settings on these sites."
	echo "!!! Re-run: python manage.py detach_quick_links"
fi
if ! $COMPOSE run --rm web python manage.py detach_quick_links --residue; then
	echo "!!! WARN: detach_quick_links --residue: sites with the old key left or unchecked (see above)."
	echo "!!! On those sites tiles are NOT shown until detach_quick_links runs; do not save settings on these sites."
fi

step "[7/8] Restart services"
$COMPOSE up -d
# SEC-G11b: старые контейнеры (на первом деплое — ещё под root) работали всё время
# миграций и могли создать в томе root-папки (например, media/products/2026/11/).
# Новые уже под app — выравниваем ещё раз, теперь гонки нет.
$COMPOSE exec -T --user 0 web sh -c "$MEDIA_ALIGN"

step "[8/8] Deploy checks"
# Сверка миграций ПО ВСЕМ СХЕМАМ: обычный showmigrations видит только public, из-за
# чего очередь миграций в памяти проекта разъезжалась с реальностью (аудит 01.08).
# Печатает только отставание — «Всё применено» и есть ожидаемый вывод.
$COMPOSE exec -T web python manage.py migration_state || true
# FB-29.2 S7: все баннеры — в библиотеке «Website › Banner». Прежние слайды главной и
# собственные слайды блоков переносятся один раз (повтор ничего не создаёт); сбой
# переноса деплой не останавливает — сайт показывает прежние слайды.
if ! $COMPOSE exec -T web python manage.py import_banners; then
	echo "!!! WARN: import_banners FAILED for some schemas (see lines above)."
	echo "!!! The site keeps the old slides there. Re-run: python manage.py import_banners"
fi
# FB-31.7 (решение владельца): старые коды шаблонов страниц -> строки схемы «Seitenaufbau».
# Для каждого сайта вид «до/после» сверяется; расхождение — сайт не трогается (строки
# «ПРОПУЩЕНО»). Снимок настроек — в базе; откат: python manage.py materialize_page_axes --undo
if ! $COMPOSE exec -T web python manage.py materialize_page_axes; then
	echo "!!! WARN: materialize_page_axes FAILED for some sites (see lines above)."
	echo "!!! Those sites keep the old template codes. Re-run: python manage.py materialize_page_axes"
fi
# FB-31.7 B3a: остаток перед снятием чтения старых кодов (B3b ждёт «residue: 0»)
if ! $COMPOSE exec -T web python manage.py materialize_page_axes --residue; then
	echo "!!! WARN: materialize_page_axes --residue could not check some sites (see lines above)."
fi
# FB-33 M2i-5b: переводы вариантов «Art der Veranstaltung» — из позиционного оверлея
# `i18n.*.anfrage` ключом по тексту (`form_fields.anfrage.event_types_i18n`), оверлей — прочь.
# ПОСЛЕ подъёма нового web — наоборот, чем detach_quick_links: старый web ключа
# `event_types_i18n` не знает, и любой Save на нём стёр бы перенесённое безвозвратно; новый
# web до переноса показывает старый оверлей запасным позиционным чтением (окно покрыто).
# Повтор — no-op; откат — form_i18n_realign --undo (вместе с откатом кода).
if ! $COMPOSE exec -T web python manage.py form_i18n_realign; then
	echo "!!! WARN: form_i18n_realign FAILED or skipped busy sites (see lines above)."
	echo "!!! Those sites still show old positional translations of event types; re-run:"
	echo "!!! python manage.py form_i18n_realign"
fi
sleep 5
if curl -fsS "$HEALTH_URL" >/dev/null; then
	echo "OK: readiness passed"
else
	echo "WARN: readiness check failed — смотри логи: $COMPOSE logs --tail=50 web"
	exit 1
fi

step "done"
echo "==> Deploy complete (mode: $MODE) за $((SECONDS - DEPLOY_START)) с."
