#!/usr/bin/env bash
# Сидинг showcase-демо-тенантов по ВСЕМ китам (apps.tenants.demo_kits) на проде.
#
# Без --kit команда seed_demo_tenants проходит по всем китам из demo_kits.KITS,
# создавая по демо-сайту на субдомене <kit>-demo.<base> (apply_kit). По умолчанию —
# СОЗДАНИЕ: существующие демо НЕ трогаются (пропускаются). Запуск:
#
#   scripts/seed-demos.sh                 # создать недостающие демо по всем китам
#   scripts/seed-demos.sh --recreate      # пересоздать (дроп схемы!) — осознанно
#   scripts/seed-demos.sh --delete        # удалить демо-тенанты всех китов
#
# Логин владельца каждого демо: <kit>-demo@example.de / demo-12345678.
# Долго: миграция схемы на тенант ~1 мин на кит.
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"
ARGS="$*"  # по умолчанию пусто = СОЗДАНИЕ (существующие пропускаются, без дропа)

echo "▶ Seeding demo kits (${ARGS:-create-only}) …"
$COMPOSE exec -T web python manage.py seed_demo_tenants $ARGS
echo "✓ Done. Демо-сайты: <kit>-demo.<DOMAIN> (login <kit>-demo@example.de / demo-12345678)"
