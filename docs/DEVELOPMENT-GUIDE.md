# SiteAdaptor — Полное руководство разработчика

> **Единый источник правды для разработки.** Здесь всё: setup, полный список
> задач по спринтам (базовый план + дополнения, слитые в один чеклист с
> отметками ✅/⬜), git-флоу, деплой и команды. Остальные документы — деталировка.

Актуально на: **2026-05-29**. Если правишь план — правь **этот** файл.

**Стек:** Python 3.12 · Django 5.1 · django-tenants (schema-per-tenant) ·
PostgreSQL 16 · Redis 7 · Celery 5 · HTMX/Alpine/Tailwind · django-allauth ·
dj-stripe · django-unfold · Caddy 2 · Hetzner Cloud (EU).

---

## 0. Карта документации

| Файл | Для чего |
|---|---|
| **`docs/DEVELOPMENT-GUIDE.md`** (этот) | Главный. Начинай отсюда. |
| `docs/phase1-implementation-guide.md` | Базовый план Phase 1: модели (готовый код), спринты, промпты. |
| `docs/phase1-plan-additions.md` | Слой улучшений поверх базового плана. |
| `docs/platform-core-architecture.md` | Архитектура: схемы, потоки, сервисы. |
| `docs/full-platform-vision.md` | Продуктовое видение (Phase 1–3+). |
| `docs/monetization-unit-economics.md` | Цены, тарифы, unit-экономика. |
| `docs/hetzner-claude-code-setup.md` | Поднятие серверов Hetzner. |
| `docs/references/patterns/*.md` | Готовые паттерны с кодом (см. §6). |

> Раздел §4 уже **сводит** базовый план и дополнения — отдельно их сверять не
> нужно, но первоисточники оставлены для деталей и готового кода моделей.

---

## 1. Архитектура за 2 минуты (держать в голове)

- **Schema-per-tenant.** Каждый бизнес = отдельная PostgreSQL-схема. `django-tenants`
  определяет арендатора по домену: `Host` → модель `Domain` → схема.
- **SHARED vs TENANT приложения** (`config/settings/base.py`):
  - `SHARED_APPS` (public-схема): `tenants`, admin, allauth, celery, djstripe,
    `aggregator`, `global_categories`.
  - `TENANT_APPS` (схема бизнеса): `core`, `catalog`, `promotions`,
    `subscriptions`, `publishing`, `notifications`, `billing`.
  - Приложения раскомментируются в `base.py` **по мере спринтов**.
- **Два urlconf:** `config/urls_public.py` (главный домен `siteadaptor.de`: admin,
  агрегатор, health) и `config/urls_tenant.py` (субдомены бизнесов: дашборд,
  лендинг, health). **Django admin — только на public.**
- **Поддомен → арендатор:** `baeckerei-test.siteadaptor.de` → `Domain` → схема
  `baeckerei_test`. Главный домен → public.
- **Порядок миграций:** сначала `migrate_schemas --shared`, потом `migrate_schemas`.
- **PK моделей — UUID** (`TimestampedModel` в `apps/core`), кроме `Tenant/Domain`
  (BigAuto от django-tenants).
- **i18n-конвенция:** переводимые поля = `JSONField` `{"de": "...", "en": "..."}`.
  Дефолт `de`. Фолбэк: запрошенный → `de` → `en` → пусто (`I18nMixin.get_i18n`).
- **Сквозные конвенции (паттерны §6):** soft-delete (`deleted_at` + partial unique),
  `metadata=JSONField` на runtime-моделях, `dedupe_key` (unique) для
  идемпотентности, audit с первого дня, cursor-пагинация вместо offset.
- **Биллинг (Phase 1):** один тариф **€39/мес**, **14 дней trial**, далее Stripe
  списывает (детали и unit-экономика — `monetization-unit-economics.md`).

---

## 2. Локальная разработка: первый запуск

```bash
# 1. uv (один раз)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. venv + зависимости
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. инфра (postgres + redis)
docker compose up -d db redis

# 4. окружение
cp .env.example .env            # отредактируй SECRET_KEY и пр.

# 5. миграции: сначала shared, потом tenant
python manage.py makemigrations tenants
python manage.py migrate_schemas --shared

# 6. суперпользователь (public-схема)
python manage.py createsuperuser

# 7. тестовый арендатор (public + baeckerei_test в Hilden)
python manage.py create_test_tenant
#   другой базовый домен:  --base-domain siteadaptor.de

# 8. dev-сервер
python manage.py runserver 0.0.0.0:8000
```

Воркеры (по мере появления задач):
```bash
celery -A config worker -l info
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

**Доступ:** admin → http://localhost:8000/admin/ · арендатор →
http://baeckerei-test.siteadaptor.de:8000 · health → `/health/` · readiness →
`/health/ready/`.

> **Локальные субдомены:** либо wildcard-DNS `*.siteadaptor.de` → IP dev-сервера,
> либо `/etc/hosts`: `127.0.0.1 baeckerei-test.siteadaptor.de`.

---

## 3. Ежедневный цикл

```bash
git checkout main && git pull origin main
git checkout -b claude/sprintN-taskX-кратко

# ... код + тесты ...

ruff check . && ruff format . && pytest

# миграции, если менял модели:
python manage.py makemigrations <app>
python manage.py migrate_schemas --shared   # если менял SHARED-модель
python manage.py migrate_schemas            # tenant-схемы

git add -A && git commit -m "Sprint N / Task X: что сделано"
git push -u origin <branch>
# → Pull Request в main → ревью → merge → деплой (§5)
```

**Правило миграций:** SHARED-модель (`Tenant`…) → `migrate_schemas --shared`;
TENANT-модель (`Product`…) → `migrate_schemas`. Сомневаешься — гоняй обе.

---

## 4. Дорожная карта Phase 1 — единый чеклист

6 спринтов по ~2 недели. Для каждого: **базовые задачи** (из
`phase1-implementation-guide.md`) + **дополнения** (из `phase1-plan-additions.md`),
слитые вместе. ✅ = сделано, ⬜ = осталось. Готовый код моделей — в Части 2
базового плана.

---

### Sprint 1 — Foundation & Multi-tenancy · частично готов

**Цель:** рабочий Django + django-tenants; можно создать арендатора и зайти в его
схему по субдомену; бизнес может зарегистрироваться.

**Базовые задачи:**
1. ✅ Bootstrap проекта, зависимости (`pyproject.toml`).
2. ✅ Settings `base/development/production`.
3. ✅ App `tenants`: модели `Tenant`/`Domain`.
4. ✅ Middleware django-tenants + роутинг.
5. ✅ `urls_public.py` + `urls_tenant.py` (admin только на public).
6. ✅ Management-команда `create_test_tenant`.
7. ⬜ Полная настройка django-allauth (шаблоны login/signup/reset; в settings/urls — есть).
8. ⬜ **Onboarding-view**: форма бизнеса → создаёт `Tenant` + `Domain` + первого `User`.
9. ⬜ Базовый layout (Tailwind) `templates/base.html`.
10. ⬜ Dashboard-placeholder view арендатора.
11. ✅ Health-endpoint (`/health/` liveness + `/health/ready/` readiness в `apps/core`).
12. ✅ Базовые тесты (pytest + factory-boy) **+ тест изоляции арендаторов**
    (`apps/tenants/tests/test_isolation.py`).

**Дополнения:**
- ⬜ **1.1 Audit** с первого дня (`apps/core/audit/`, `AuditEvent` в SHARED) →
  `patterns/audit-log.md`.
- ⬜ **1.2 Cursor pagination** util (`apps/core/pagination.py`) →
  `patterns/cursor-pagination.md`.
- ⬜ **1.3 SoftDeleteMixin** + `TimestampedModel` в `apps/core/models.py` →
  `patterns/soft-delete.md`.
- ⬜ **1.4 Webhooks scaffold** (`apps/integrations/webhooks/`, только модели) →
  `patterns/webhook-hmac-signing.md`.
- ✅ **1.5 Инфра-хардненинг** (Redis cache+сессии, Celery results→Redis,
  `CONN_MAX_AGE`, индексы `Tenant`).
- ⬜ **CI** (рекомендация): GitHub Actions `ruff` + `pytest`, pre-commit.

**DoD:** `migrate_schemas --shared` чисто · арендатор резолвится на субдомене ·
**изоляция проверена тестом** (✅) · регистрация бизнеса создаёт рабочего
арендатора · audit пишется на create Tenant + login/logout · `pytest`/`ruff` зелёные.

---

### Sprint 2 — Catalog & Tenant Dashboard

**Цель:** владелец управляет каталогом через HTMX-дашборд.

**Базовые задачи:**
1. ⬜ App `catalog`: `Product`, `Category` (JSONField i18n, иерархия).
2. ⬜ Django Admin (unfold) для Product/Category.
3. ⬜ Layout дашборда (sidebar + content, Tailwind).
4. ⬜ `ProductListView` (HTMX live-search + фильтры category/is_active, пагинация 25).
5. ⬜ Формы create/edit товара.
6. ⬜ Загрузка картинок (django-storages; в dev FileSystemStorage).
7. ⬜ Компонент превью картинки.
8. ⬜ UI управления категориями (CRUD, parent, sort_order).
9. ⬜ CSV-импорт.
10. ⬜ i18n-виджет (мультиязычные input'ы для name/description).
11. ⬜ Тесты CRUD продуктов.

**Дополнения:**
- ⬜ **2.1 4-шаговый CSV-wizard** вместо one-shot django-import-export
  (`uploaded→mapped→previewed→running→completed`) → `patterns/csv-import-wizard.md`.
- ⬜ **2.2 FileRef-envelope** для `Product.images` (фиксированная форма массива).
- ⬜ Применить **SoftDeleteMixin** к Product/Category (из 1.3).

**DoD:** полный CRUD товаров в дашборде · картинка грузится и видна в превью ·
CSV-импорт с маппингом колонок и превью на ≥100 строк · поля de/en редактируются.

---

### Sprint 3 — Promotions & Reservations

**Цель:** владелец создаёт акцию (опц. с бронированием); бронь корректна под
конкурентной нагрузкой.

**Базовые задачи:**
1. ⬜ App `promotions`: `Promotion`, `Reservation` (+ `Customer` из `subscriptions`).
2. ⬜ CRUD акций (HTMX, как catalog) + bookable-toggle.
3. ⬜ Service переходов статусов (`draft→scheduled→active→ended/cancelled`).
4. ⬜ Service бронирования (атомарно).
5. ⬜ Celery beat: авто-`ended` по `ends_at` (каждые 5 мин).
6. ⬜ Celery: `pending→expired` через 30 мин.
7. ⬜ Генератор `pickup_code` (уникальный, читаемый).
8. ⬜ Tenant-view: список броней с фильтрами + «Mark collected».
9. ⬜ Reservation API endpoint (DRF) `/api/v1/promotions/{id}/reserve`.
10. ⬜ Тесты: конкурентная бронь, переходы статусов, expiration.

**Дополнения:**
- ⬜ **3.1 Anti-oversell** через conditional `UPDATE`+`F()` (НЕ `select_for_update`);
  правила изоляции + настоящий параллельный тест → `patterns/anti-oversell.md`.
- ⬜ **3.2 Формальная FSM** (явная таблица переходов) → `patterns/state-machine.md`.
- ⬜ **3.3 `metadata=JSONField`** на Reservation (и на будущих runtime-моделях).

**DoD:** акция создаётся/активируется через UI · бронь через `curl` отдаёт
`pickup_code` · **100 параллельных броней на 50 единиц → ровно 50, ноль
перепродаж** · по `ends_at` акция авто-завершается.

---

### Sprint 4 — Publishing Engine & Landing Pages

**Цель:** активная акция автоматически появляется на субдомене; у покупателя есть
публичная страница с бронированием.

**Базовые задачи:**
1. ⬜ App `publishing`: `Channel`, `Publication`.
2. ⬜ Интерфейс `BasePublisher` + registry.
3. ⬜ `SubdomainPublisher`.
4. ⬜ Signals: `promotion active` → создать `Publication` для `is_default` каналов;
   `ended` → unpublish.
5. ⬜ Public-views лендинга: `LandingHomeView`, `PromotionDetailView`.
6. ⬜ Public reservation-form (использует service из Sprint 3).
7. ⬜ Tenant settings: branding (logo, primary_color) + custom domain.
8. ⬜ Верификация custom-домена (проверка CNAME).
9. ⬜ Caddy verify-endpoint — ✅ реализован (`/internal/verify-domain` в `apps/core`).
10. ⬜ Confirmation-email при брони.
11. ⬜ Integration-тест: create→activate→виден на субдомене→reserve→email.

**Дополнения:**
- ⬜ **4.1 `dedupe_key` в Publication — В ЯДРЕ** (идемпотентная публикация, без
  дублей при ретраях/повторных webhook) → `patterns/notification-dedupe.md`.
- ⬜ **4.2 `BasePublisher` с audit-callback** (`publication.published/failed/...`).

**DoD:** активация публикует без ручных действий · повторная публикация
идемпотентна (нет дублей) · public-страница работает без auth · reservation
e2e + email · branding меняет вид · custom-domain верификация работает.

---

### Sprint 5 — Aggregator & Customer Experience

**Цель:** покупатель видит акции всех бизнесов города, фильтрует, подписывается.

**Базовые задачи:**
1. ⬜ App `aggregator` (SHARED): `AggregatorListing`.
2. ⬜ App `global_categories` (SHARED): `GlobalCategory` + seed + admin.
3. ⬜ Signal: публикация в aggregator-канал → наполнить `AggregatorListing`.
4. ⬜ Public-views: `CityFeedView` (`/{city}/`), `CategoryFilterView`
   (`/{city}/{category}/`), `BusinessDetailView` (`/biz/{slug}/`).
5. ⬜ Подписка покупателя (double opt-in).
6. ⬜ UI маппинга tenant-категорий на global.
7. ⬜ Тесты: агрегация, подписка, фильтрация.

**Дополнения:**
- ⬜ **5.1 Cursor pagination** в фиде (из 1.2) → `patterns/cursor-pagination.md`.
- ⬜ **5.2 Anti-spam reorder** (не более 2 акций одного бизнеса подряд).
- ⬜ **5.3 Magic-link** авторизация покупателя (без паролей) →
  `patterns/magic-link-auth.md`.
- ⬜ **5.4 Facets-endpoint** (`/{city}/facets/`, counts, кэш Redis 60с).
- ⬜ **5.5 Материализация `AggregatorListing`** через сигнал → idempotent-задача
  (НЕ обход схем в цикле!) + `search_vector` (полнотекст, GIN).
- ⬜ **5.6 `AggregatorPortal`** — шов под вертикальные/мультидоменные агрегаторы
  (Phase 1: один портал через абстракцию; мультидомен + on-demand TLS → Phase 2).

**DoD:** `/{city}/` показывает акции всех бизнесов города · cursor-пагинация ·
фильтр по global-категории · покупатель входит по magic-link · не >2 акций
одного бизнеса подряд · `AggregatorListing` наполняется автоматически.

---

### Sprint 6 — Notifications, Billing & Launch

**Цель:** подписчики получают уведомления; биллинг Stripe; платформа готова к запуску.

**Базовые задачи:**
1. ⬜ App `notifications`: модели.
2. ⬜ `NotificationService` + каналы (email Resend, telegram).
3. ⬜ Signal/task: акция active → match подписок → enqueue.
4. ⬜ Celery-task отправки с rate-limit.
5. ⬜ Email-шаблоны (Resend).
6. ⬜ Telegram-бот.
7. ⬜ dj-stripe: Checkout + webhook handler.
8. ⬜ Billing-дашборд (статус, trial_ends_at, история).
9. ⬜ Trial-логика (14 дней → авто-списание).
10. ⬜ Синхронизация `subscription_status` через Stripe webhooks.
11. ✅/⬜ Sentry (в `settings/production.py` подключён ✅; проверить DSN на проде ⬜).
12. ✅ Health-checks (готово в Sprint 1).
13. ⬜ Backup-cron (`pg_dump` → Object Storage).
14. ✅/⬜ Прод-деплой (инфра готова ✅: Dockerfile/compose/Caddy/deploy.sh — см. §5; launch-чеклист ⬜).
15. ⬜ Тесты: matching уведомлений, billing-flows.

**Дополнения:**
- ⬜ **6.1 `Notification.dedupe_key` UNIQUE** с первого дня →
  `patterns/notification-dedupe.md`.
- ⬜ **6.2 Web Push** (`PushDevice`, pywebpush/VAPID, Service Worker).
- ⬜ **6.3 `idempotent_task`** обёртка для всех рисковых задач
  (notify/publish/reminders).
- ⬜ **6.4 Trial-reminders с dedupe** (`trial_ending:3d/1d`, `trial_expired`).
- ⬜ **6.5 Политика ретраев/DLQ по каналам** (email 7д exp, telegram 3×, push без
  ретраев на 410…).
- ⬜ **6.6 FSM жизненного цикла подписки** (`trial→active→past_due→suspended`) →
  `patterns/state-machine.md` (раздел Subscription).

**DoD:** подписчик получает email/telegram по подходящей акции · Stripe Checkout
(test) создаёт подписку, webhook обновляет статус · авто-истечение триала
(3d/1d → suspend) · Sentry ловит ошибки · `/health/ready/` = 200 · backup работает.

---

## 5. Деплой на сервер

### 5.1 Два режима

| | **SINGLE** (сейчас, dev/тест) | **PROD** (боевой запуск) |
|---|---|---|
| Серверы | один (всё в Docker) | App CPX21 + DB CCX13 |
| Postgres | сервис `db` в Docker, профиль `single` | отдельный db-сервер, приватная сеть |
| `DB_HOST` в `.env.prod` | `db` | приватный IP db-сервера |
| Команда | `./scripts/deploy.sh single` | `./scripts/deploy.sh` |

Когда переходить на PROD: перед боевым запуском с реальными платящими
арендаторами (≈ Sprint 6). Переезд = `pg_dump`→`restore` + сменить `DB_HOST`.
Claude Code на прод **не ставится**.

### 5.2 Разовая подготовка сервера
```bash
# репозиторий (на dev-сервере он уже в ~/projects/siteadaptor-platform)
cd ~/projects/siteadaptor-platform     # или /opt/... при первом clone
cp .env.prod.example .env.prod         # заполни все CHANGE-ME; для single: DB_HOST=db

# DNS: A-записи  @ (siteadaptor.de)  и  * (*.siteadaptor.de)  → публичный IP сервера.
# Caddy выпускает сертификаты по HTTP-01 (главный домен) + on-demand (субдомены).
# Нужны только порты 80/443 открыты; DNS-API-токен НЕ требуется.
# (Wildcard через DNS-01 — опция на будущее, требует Cloudflare/др. провайдера.)

# Первый запуск (SINGLE — поднимает локальный Postgres):
docker compose -f docker-compose.prod.yml --profile single build
docker compose -f docker-compose.prod.yml --profile single up -d db
docker compose -f docker-compose.prod.yml --profile single run --rm web python manage.py migrate_schemas --shared
docker compose -f docker-compose.prod.yml --profile single run --rm web python manage.py createsuperuser
docker compose -f docker-compose.prod.yml --profile single run --rm web python manage.py create_test_tenant --base-domain siteadaptor.de
docker compose -f docker-compose.prod.yml --profile single up -d
```
(Для PROD — те же команды без `--profile single`, Postgres готовится на db-сервере.)

### 5.3 КОМАНДА ДЕПЛОЯ (каждый релиз)

**SINGLE (твой случай сейчас):**
```bash
cd ~/projects/siteadaptor-platform && ./scripts/deploy.sh single
```
**PROD (отдельный db-сервер):**
```bash
ssh hetzner-app 'cd /opt/siteadaptor-platform && ./scripts/deploy.sh'
```

`scripts/deploy.sh`: `git pull` (main) → `build` → [single: поднять `db`] →
`migrate_schemas --shared` → `migrate_schemas` → `collectstatic` → `up -d` →
`check --deploy` → проверка `/health/ready/`. Идемпотентно.

> **Порт 5432.** В dev `docker-compose.yml` Postgres проброшен на хост
> (`0.0.0.0:5432`). В `docker-compose.prod.yml` (single) сервис `db` **не**
> публикует порт наружу — доступен только из контейнеров по имени `db`. Перед
> прод-стартом останови dev-стек (`docker compose down`), чтобы не конфликтовали.

> **Что значит «миграция» здесь:** Django-миграции БД (напр. `0002_tenant_indexes`)
> применяются шагами `migrate_schemas` внутри `deploy.sh` — на сервере. Merge PR
> сам по себе ничего на сервере не меняет; выкат запускает `deploy.sh`.

### 5.4 Эксплуатация
```bash
C="docker compose -f docker-compose.prod.yml"
$C logs -f web         # логи приложения
$C logs -f worker      # логи celery
$C ps                  # статус
$C exec web python manage.py shell
# откат: git checkout <prev-tag> && ./scripts/deploy.sh
```
**DB-сервер:** установка PostgreSQL 16, пользователь/база, `listen_addresses`
на приватный IP, `pg_hba.conf` для `10.0.0.0/16`, бэкап `pg_dump`→Object Storage
по cron — см. `hetzner-claude-code-setup.md`.

> **TLS:** сейчас HTTP-01 + on-demand (стоковый Caddy, без DNS-плагина) — нужны
> лишь A-записи и порты 80/443. Для боевого масштаба (>~50 серт./нед) перейди на
> wildcard через DNS-01: смени NS на Cloudflare, собери Caddy с
> `--with github.com/caddy-dns/cloudflare` (см. `caddy/Dockerfile`), верни
> `tls { dns ... }` в Caddyfile и токен в `.env.prod`.

---

## 6. Каталог паттернов (`docs/references/patterns/`)

| Паттерн | Когда | Спринт |
|---|---|---|
| `soft-delete.md` | мягкое удаление, partial unique | 1→2 |
| `audit-log.md` | журнал действий (нельзя backfill) | 1 |
| `cursor-pagination.md` | keyset-пагинация лент | 1 / 5 |
| `webhook-hmac-signing.md` | исходящие вебхуки + HMAC | 1 / 2 |
| `csv-import-wizard.md` | 4-шаговый импорт | 2 |
| `anti-oversell.md` | резервации без перепродажи | 3 |
| `state-machine.md` | FSM (Promotion/Reservation/Subscription) | 3 / 6 |
| `notification-dedupe.md` | идемпотентность уведомлений/публикаций | 4 / 6 |
| `magic-link-auth.md` | беспарольный вход покупателя | 5 |

---

## 7. Быстрый справочник команд

```bash
# Миграции
python manage.py makemigrations <app>
python manage.py migrate_schemas --shared                 # public
python manage.py migrate_schemas                          # все tenant-схемы
python manage.py migrate_schemas --schema=baeckerei_test  # одна схема

# Арендаторы
python manage.py create_test_tenant [--base-domain siteadaptor.de]

# Запуск
python manage.py runserver 0.0.0.0:8000
celery -A config worker -l info
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler

# Качество
ruff check . && ruff format . && pytest

# Деплой
ssh hetzner-app 'cd /opt/siteadaptor-platform && ./scripts/deploy.sh'
```

**Внешние ссылки:** uv — https://astral.sh/uv · Hetzner Console —
https://console.hetzner.com/projects · Stripe — https://dashboard.stripe.com/ ·
Resend — https://resend.com/ · Sentry — https://sentry.io/ · DNS-плагины Caddy —
https://github.com/caddy-dns
