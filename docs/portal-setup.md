# Настройка мульти-доменных порталов (Phase 2 P2.1)

Портал — брендированный хост (`muenchen.siteadaptor.de`, `baeckerei.siteadaptor.de`
или custom-домен) поверх общего пула `AggregatorListing`, суженного по городу
и/или типу бизнеса. Код: `apps/aggregator` (модель `AggregatorPortal`, резолвер
`AggregatorPortalMiddleware`, страницы `portal_views`, urlconf `config/urls_portal.py`).

## Типы порталов

| kind       | Фильтр                  | Уточнение `/<facet>/`   | Пример хоста                       |
|------------|-------------------------|--------------------------|------------------------------------|
| `city`     | город                   | тип бизнеса (`/bakery/`) | `muenchen.siteadaptor.de`          |
| `vertical` | тип бизнеса             | город (`/Hilden/`)       | `baeckerei.siteadaptor.de`         |
| `combo`    | город + тип             | нет                      | `baeckerei-muenchen.siteadaptor.de`|

## Быстрый старт

```bash
# Городской портал
python manage.py create_portal \
    --host muenchen.siteadaptor.de --kind city --city "München" \
    --title-de "Angebote München" --tagline-de "Lokale Deals täglich"

# Вертикальный портал
python manage.py create_portal \
    --host baeckerei.siteadaptor.de --kind vertical --business-type bakery \
    --title-de "Bäckerei-Angebote"

# Комбо
python manage.py create_portal \
    --host baeckerei-muenchen.siteadaptor.de --kind combo \
    --city "München" --business-type bakery --title-de "Bäckereien München"
```

Команда атомарно создаёт **две** записи:

1. `AggregatorPortal` — фильтры + брендинг (`--title-de/-en`, `--tagline-…`,
   `--intro-…`, `--logo-url`, `--primary-color`).
2. `Domain(host → public tenant)` — без неё `TenantMainMiddleware` отдаст 404
   на этом хосте. Если Domain уже существует и указывает на public — она
   переиспользуется; если на другого тенанта — команда откажет.

На проде: `docker compose -f docker-compose.prod.yml exec web python manage.py create_portal …`
(как и остальные manage-команды).

## DNS и TLS

- **Поддомены `*.siteadaptor.de`**: wildcard A-запись уже настроена — ничего
  делать не нужно. Caddy on-demand TLS авторизует любой поддомен автоматически
  (`apps/core/health.py::verify_domain` отвечает «ok» на `*.siteadaptor.de`).
- **Custom-домен** (`angebote-muenchen.de`):
  1. У регистратора: A-запись домена → IP сервера.
  2. `create_portal --host angebote-muenchen.de …` — команда создаст строку
     Domain, после чего `internal/verify-domain` начнёт авторизовать домен.
  3. Сертификат Caddy выпустит сам при первом HTTPS-заходе (on-demand TLS).

## Админка

`AggregatorPortal` доступен в Django admin на основном домене (unfold).
**Внимание:** при создании портала через админку строку `Domain(host → public)`
нужно добавить вручную (admin → Domains), иначе хост отдаст 404. Команда
`create_portal` делает это сама — предпочтительный путь.

## Как это работает (для отладки)

- Карта `host → portal` кэшируется в Redis (TTL 300 с) и сбрасывается сигналом
  при save/delete портала — изменения видны сразу, но при ручной правке в БД
  мимо ORM подожди TTL или сбрось ключ `aggregator:portal_host_map`.
- `is_active=False` выключает портал (хост начнёт отдавать 404 на корне —
  Domain-строка остаётся).
- На хосте портала работают `/health/`, `/health/ready/`, `/sitemap.xml`
  (корень + страницы уточнения), `/robots.txt`.
- Выдача — общий пул `AggregatorListing`; если портал пустой, проверь городские
  страницы `/entdecken/…` на основном домене и `manage.py sync_aggregator`.
