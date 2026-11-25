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

# FB-33 M3-9b (ревью): всё тело — в функции main, вызов — последней строкой. Шаг [1/8]
# делает `git pull` и меняет ЭТОТ файл под работающим bash; построчно читаемый скрипт
# продолжил бы со сдвигом. Функцию bash читает целиком до исполнения, а после pull скрипт
# один раз запускает себя заново (DEPLOY_REEXEC) — деплой идёт сценарием своего коммита.
# Тело намеренно без отступа: правки шагов читаются в diff как прежде.
main() {
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
# E8c ревью 1: шаги, отработавшие с WARN (деплой их не останавливает), — сводкой в конце,
# чтобы предупреждение не утонуло в выводе сборки
DEPLOY_WARNS=()
warn_step() { DEPLOY_WARNS+=("$1"); }

# FB-33 M3-9b: два деплоя сразу на одном сервере — второй выходит, не начав (раньше оба
# собирали образ и мигрировали вперемешку). Блокировка — файл на этом сервере; снимается
# сама, когда скрипт завершается (в том числе аварийно).
# Файл — в каталоге репозитория (.git не чистится и в рабочее дерево не попадает).
DEPLOY_LOCK_FILE="${DEPLOY_LOCK_FILE:-$REPO_DIR/.git/siteadaptor-deploy.lock}"
if [ "${DEPLOY_REEXEC:-0}" = "1" ]; then
	: # перезапуск после pull: блокировка уже наша — дескриптор 9 унаследован
elif command -v flock >/dev/null 2>&1; then
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

if [ "${DEPLOY_REEXEC:-0}" != "1" ]; then
	step "[1/8] Pull $BRANCH from git"
	git fetch origin "$BRANCH"
	git checkout "$BRANCH"
	git pull --ff-only origin "$BRANCH"
	# дальше — сценарий только что полученного коммита (второго pull там нет)
	export DEPLOY_REEXEC=1
	SELF="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
	exec "$SELF" "$@"
fi
echo "==> [1/8] Pull: сделан, деплой идёт сценарием коммита $(git rev-parse --short HEAD)"

step "[2/8] Build images"
# Один образ (web) на web/worker/beat + caddy; слой зависимостей берётся из кэша,
# пока не менялся uv.lock (T-10).
$COMPOSE build
# Тег образа по коммиту — для отката: `docker tag siteadaptor-app:<sha> siteadaptor-app:latest`
# и `$COMPOSE up -d` (latest перезаписывается каждой сборкой).
docker tag siteadaptor-app:latest "siteadaptor-app:$(git rev-parse --short HEAD)" || true

# FB-33 M3-9b: чистка диска. Каждый деплой оставлял образ `siteadaptor-app:<sha>` и кэш
# сборки навсегда. Остаются latest, образ текущего коммита и ещё IMAGE_KEEP−1 предыдущих
# (откат), остальным снимаем тег; кэш сборки старше 72 ч — прочь. Без силы (`rmi` без -f): образ
# запущенного контейнера Docker удалить не даст. Контейнеры и тома не трогаем. Любая
# ошибка чистки деплой не останавливает.
IMAGE_KEEP="${IMAGE_KEEP:-5}"
cleanup_images() {
	local current tags old tag
	current="$(git rev-parse --short HEAD)"
	# теги-коммиты, новые первыми (по дате создания образа), без текущего коммита
	tags="$(docker image ls siteadaptor-app --format '{{.CreatedAt}}|{{.Tag}}' \
		| sort -r -s -t '|' -k1,1 | cut -d '|' -f2 \
		| grep -E '^[0-9a-f]{7,40}$' | grep -vx "$current")" || tags=""
	# текущий коммит оставляем всегда, к нему — IMAGE_KEEP-1 предыдущих
	old="$(printf '%s\n' "$tags" | tail -n +"$IMAGE_KEEP")"
	for tag in $old; do
		docker rmi "siteadaptor-app:$tag" >/dev/null && echo "    образ siteadaptor-app:$tag снят"
	done
	docker builder prune -f --filter until=72h >/dev/null
}
cleanup_images || echo "    чистка образов не удалась — деплой продолжается"

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
# Под той же блокировкой: пересев демо создаёт схемы копией шаблона.
rc=0
# shellcheck disable=SC2086
$COMPOSE run --rm $LOCK_ENV web python manage.py run_locked ensure_template_schema || rc=$?
if [ "$rc" = "$LOCK_BUSY" ]; then lock_busy_stop; fi
if [ "$rc" != "0" ]; then
	echo "    шаблон не готов — новые схемы будут создаваться миграциями"
fi

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
		{ $COMPOSE run --rm $LOCK_ENV web python manage.py run_locked migrate_schemas --tenant; } || rc=$?
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
	warn_step "detach_quick_links"
	echo "!!! WARN: detach_quick_links FAILED or skipped some sites (see lines above)."
	echo "!!! On those sites tiles are NOT shown until detach_quick_links runs; do not save settings on these sites."
	echo "!!! Re-run: python manage.py detach_quick_links"
fi
if ! $COMPOSE run --rm web python manage.py detach_quick_links --residue; then
	warn_step "detach_quick_links --residue"
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
	warn_step "import_banners"
	echo "!!! WARN: import_banners FAILED for some schemas (see lines above)."
	echo "!!! The site keeps the old slides there. Re-run: python manage.py import_banners"
fi
# FB-31.7 (решение владельца): старые коды шаблонов страниц -> строки схемы «Seitenaufbau».
# Для каждого сайта вид «до/после» сверяется; расхождение — сайт не трогается (строки
# «ПРОПУЩЕНО»). Снимок настроек — в базе; откат: python manage.py materialize_page_axes --undo
if ! $COMPOSE exec -T web python manage.py materialize_page_axes; then
	warn_step "materialize_page_axes"
	echo "!!! WARN: materialize_page_axes FAILED for some sites (see lines above)."
	echo "!!! Those sites keep the old template codes. Re-run: python manage.py materialize_page_axes"
fi
# FB-31.7 B3a: остаток перед снятием чтения старых кодов (B3b ждёт «residue: 0»)
if ! $COMPOSE exec -T web python manage.py materialize_page_axes --residue; then
	warn_step "materialize_page_axes --residue"
	echo "!!! WARN: materialize_page_axes --residue could not check some sites (see lines above)."
fi
# FB-33 M2i-5b: переводы вариантов «Art der Veranstaltung» — из позиционного оверлея
# `i18n.*.anfrage` ключом по тексту (`form_fields.anfrage.event_types_i18n`), оверлей — прочь.
# ПОСЛЕ подъёма нового web — наоборот, чем detach_quick_links: старый web ключа
# `event_types_i18n` не знает, и любой Save на нём стёр бы перенесённое безвозвратно; новый
# web до переноса показывает старый оверлей запасным позиционным чтением (окно покрыто).
# Повтор — no-op; откат — form_i18n_realign --undo (вместе с откатом кода).
if ! $COMPOSE exec -T web python manage.py form_i18n_realign; then
	warn_step "form_i18n_realign"
	echo "!!! WARN: form_i18n_realign FAILED or skipped busy sites (see lines above)."
	echo "!!! Those sites still show old positional translations of event types; re-run:"
	echo "!!! python manage.py form_i18n_realign"
fi
# FB-33 стопка 15 E8c: блок «Suche» (site_search) живёт только на странице 404; старые конфиги
# с ним на других страницах снимают его при чтении (лог на каждый запрос). Разовая чистка
# хранимых списков (переводы едут за своими блоками, страница, где он был один, — «ПУСТО»).
# Вид сайта не меняется; повтор — no-op; сбой деплой не останавливает.
if ! $COMPOSE exec -T web python manage.py drop_stray_site_search; then
	warn_step "drop_stray_site_search"
	echo "!!! WARN: drop_stray_site_search FAILED or skipped busy sites (see lines above)."
	echo "!!! Those sites still drop the search block at read time; re-run:"
	echo "!!! python manage.py drop_stray_site_search"
fi
if [ "${#DEPLOY_WARNS[@]}" -gt 0 ]; then
	echo "!!! WARN summary: ${#DEPLOY_WARNS[@]} step(s) finished with warnings:"
	for w in "${DEPLOY_WARNS[@]}"; do echo "!!!   - $w"; done
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
}

main "$@"
exit
