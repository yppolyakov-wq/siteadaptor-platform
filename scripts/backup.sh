#!/usr/bin/env bash
# SEC-G12 (аудит 2026-11-01): ночной бэкап БД и медиа.
#
#   ./scripts/backup.sh single        # Postgres в Docker на этом сервере
#   ./scripts/backup.sh               # Postgres на отдельном сервере (DB_HOST из .env.prod)
#
# Кладёт в $BACKUP_DIR (по умолчанию /var/backups/siteadaptor):
#   db-<дата>.sql.gz      — pg_dump всех схем (public + все бизнесы)
#   media-<дата>.tar.gz   — загруженные файлы (том media)
# Хранит BACKUP_KEEP_DAYS (по умолчанию 14) дней. Если в .env.prod задан
# BACKUP_S3_BUCKET — дополнительно выгружает оба файла в S3 (ключи AWS_* из .env.prod,
# Hetzner Object Storage: AWS_S3_ENDPOINT_URL).
#
# cron (root), каждую ночь в 03:17:
#   17 3 * * * cd /home/<user>/projects/siteadaptor-platform && ./scripts/backup.sh single >> /var/log/siteadaptor-backup.log 2>&1
#
# Проверка восстановления (раз в месяц, на отдельной БД):
#   gunzip -c db-<дата>.sql.gz | psql -h <host> -U <user> <тестовая_бд>

set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-}"
PROFILE_ARGS=""
if [ "$MODE" = "single" ]; then
	PROFILE_ARGS="--profile single"
fi
COMPOSE="docker compose --env-file .env.prod -f docker-compose.prod.yml $PROFILE_ARGS"

# Нужные переменные .env.prod — без `source` (значения со спецсимволами не ломают shell).
envget() {
	grep -E "^$1=" .env.prod | tail -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}
DB_NAME="$(envget DB_NAME)"
DB_USER="$(envget DB_USER)"
DB_PASSWORD="$(envget DB_PASSWORD)"
DB_HOST="$(envget DB_HOST)"
DB_PORT="$(envget DB_PORT)"
BACKUP_DIR="${BACKUP_DIR:-$(envget BACKUP_DIR)}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-$(envget BACKUP_KEEP_DAYS)}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-$(envget BACKUP_S3_BUCKET)}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/siteadaptor}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
STAMP="$(date +%Y-%m-%d_%H%M)"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
umask 077

DB_FILE="$BACKUP_DIR/db-$STAMP.sql.gz"
MEDIA_FILE="$BACKUP_DIR/media-$STAMP.tar.gz"

echo "[$(date -Is)] backup start"
if [ "$MODE" = "single" ]; then
	$COMPOSE exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner | gzip -9 >"$DB_FILE"
else
	# В образе приложения pg_dump нет — берём клиент той же major-версии (16).
	docker run --rm -e PGPASSWORD="$DB_PASSWORD" postgres:16.15-alpine \
		pg_dump -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" --no-owner \
		| gzip -9 >"$DB_FILE"
fi
# Пустой/битый дамп не должен тихо заменить хорошие: проверяем размер и gzip.
gzip -t "$DB_FILE"
if [ "$(stat -c %s "$DB_FILE")" -lt 1024 ]; then
	echo "backup: db dump suspiciously small — aborting" >&2
	exit 1
fi

$COMPOSE run --rm -T web tar -czf - -C /app media >"$MEDIA_FILE"

if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
	for f in "$DB_FILE" "$MEDIA_FILE"; do
		# SEC-G11b: файлы бэкапа — root, mode 600; приложение в образе теперь под app.
		$COMPOSE run --rm -T --user 0 -v "$BACKUP_DIR:/backup:ro" web python - "$(basename "$f")" <<'PY'
import os, sys
import boto3
name = sys.argv[1]
s3 = boto3.client(
    "s3",
    endpoint_url=os.environ.get("AWS_S3_ENDPOINT_URL") or None,
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
)
s3.upload_file(f"/backup/{name}", os.environ["BACKUP_S3_BUCKET"], f"backups/{name}")
print("uploaded", name)
PY
	done
fi

find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'db-*.sql.gz' -o -name 'media-*.tar.gz' \) \
	-mtime +"$KEEP_DAYS" -delete
echo "[$(date -Is)] backup done: $(basename "$DB_FILE"), $(basename "$MEDIA_FILE")"
