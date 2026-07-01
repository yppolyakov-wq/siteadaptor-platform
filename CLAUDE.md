# CLAUDE.md — siteadaptor-platform

Claude Code загружает этот файл автоматически в начале каждой сессии (память
проекта). **Держим актуальным:** после каждой завершённой задачи и каждого нового
решения — обновляем разделы «Сделано» / «Конвенции» / «Дальше». Глубокие детали —
в `docs/` (ссылки в §6).

## 1. Что это
Мультитенантный Django 5.1 SaaS для маленьких оффлайн-бизнесов DACH (пекарни,
мясные, кафе, ритейл): мини-сайт на субдомене, каталог, акции/резервирование с
anti-oversell, инструменты лояльности/ваучеров, локальный агрегатор (в планах),
тариф ~39 €/мес.

Стек: Django 5.1, django-tenants (схема-на-тенанта, Postgres 16), Redis 7,
Celery 5 (worker+beat), HTMX/Alpine/Tailwind, django-allauth, dj-stripe,
django-unfold (admin), django-storages (S3/Hetzner), Caddy 2 (on-demand TLS).
Python 3.12, менеджер uv.

## 2. Архитектура / где что
- `config/` — settings/{base,development,production,test}.py, urls_tenant.py
  (субдомены бизнеса), urls_public.py (онбординг + admin на public), celery.py.
- `apps/core/` — fsm.py (StateMachine), jobs.py (idempotent_task), audit.py,
  models.py (Timestamped/I18n/SoftDelete-миксины), pagination.py, health.py.
- `apps/tenants/` — Tenant, Domain; services.create_business; формы онбординга и
  настроек. Tenant: контакты, право, billing-поля, auto_redeem_on_scan.
- `apps/catalog/` — Product/Category, images.py, CRUD.
- `apps/imports/` — мастер импорта CSV/Excel.
- `apps/promotions/` — ядро акций: models, state_machine (PromotionSM/
  ReservationSM), services (reserve/confirm/fulfill/cancel/expire + anti-oversell,
  vouchers, loyalty), tasks (beat), notifications, views (кабинет), public_views
  (витрина).
- `apps/billing/` — Sprint 5: SubscriptionSM, plans, (далее) services/webhooks/
  middleware/tasks. **SHARED** (статус подписки — на Tenant в public-схеме).
- `apps/audit/`, `apps/integrations/webhooks/` — SHARED.
- `scripts/deploy.sh`, `scripts/dev-services.sh`, docker-compose.prod.yml, caddy/.

Главный документ по архитектуре: **`docs/platform-core-architecture.md`**.

## 3. Сделано — статус
Полная хронология завершённых задач — **`docs/build-log.md`** (извлечена из этого
файла 2026-06-22). Срез/оценка — **`docs/audit-2026-06-22.md`**. Здесь — только
верхнеуровневый статус:

- **Stage 1 (архетипы A1–A9 → ~100% «из коробки»)** — завершён: каталог/Click&Collect/
  доставка, бронь по времени и датам (Übernachtung), события/билеты, сметы Handwerker,
  Werkstatt, финансы (счета/DATEV/GoBD), агрегатор+порталы, отзывы+гео.
- **Stage 2 (Phase 2)** — частично: порталы, поиск/фильтры, отзывы, гео, органик-постинг
  (GBP/FB/IG/Telegram/Pinterest), in-app OAuth, Telegram-боты/Mini App. Осталось:
  PWA/push/Wallet (P2.8), импорт Shopify/Woo (M21), платная реклама (M23c).
- **Stage 3 («лёгкий ERP»)** — только архитектурные швы (`core.Membership`/роли,
  `Order.parent_order`/`supplier_tenant_schema`). Не начато: склад-леджер (M10),
  маркетплейс-корзина (M14), закупки (M12), dropshipping (M15), AI (M18),
  workflow-билдер (M19), drag-drop конструктор (M20).
- **Последнее:** **архетип A5 «Отель» — H1–H9 + бэклог роста G1–G11**. Помимо H-ядра
  (тарифы/питание, поиск, богатая карточка, промокоды/самоотмена, дети, Kurtaxe, SEO
  `Hotel`+Hausordnung, агрегатор отелей): **G1** Geschenkgutscheine, **G2** pre/post-stay,
  **G3** рассылки гостям (Double-Opt-In, UWG §7), **G4** многоступенчатые авто-скидки
  (LOS/Frühbucher/Last-Minute, неск. правил на тип), **G5** мультикомнатная бронь,
  **G6** Online-Checkin + цифровой Meldeschein (BMG, retention 1 год), **G7** гибкая
  предоплата по тарифу (0/частично/100 %), **G8** фид цен/наличия для метапоиска
  (Google Free Booking Links), **G9** отчёты Belegung/ADR/RevPAR, **G10** iframe-виджет,
  **G11a/b** фундамент Channel Manager (модель `Channel` + идемпотентный импорт броней
  из OTA; реальные API Booking/Expedia/Airbnb — партнёрство, отложено G11c–e). UX витрины
  номера: 2 колонки (галерея/бронь), лайтбокс, карточки номеров на главной, полное меню.
  Демо — **по нескольку примеров на фичу**: `seed_demo_tenants --kit hotel --recreate`
  (+ `hotels.<base>`). Доки: `docs/hotel-demo.md`, планы `hotel-archetype-plan.md` /
  `hotel-growth-plan.md` / `hotel-channel-manager-plan.md`.
- **Самое свежее (2026-06-26): этап «витрина/UX + анти-Битрикс» — Спринт E закрыт + кусок F.**
  E.1–E.4 on-canvas редактор (Undo/Redo, click-to-edit→попап, инсертер «+», drag-on-canvas).
  F: A7 Handwerker-кит · RV3 грид событий+countdown · RV2 agenda-timeline · A5 PAngV+рейтинг+
  **визуальный календарь наличия номера C1–C4** · A4 аллергены+Kombo-тизер · A9/A7 Festpreis ·
  A8 сортировка выдачи. Всё в `main` (`90107c6`), **без миграций**. Точка входа след. сессии —
  `docs/next-session-brief.md` (обновлён 2026-06-26); статусы — `archetype-ux-execution-plan.md`.
- **Самое свежее (2026-07-01): старт РЕАЛИЗАЦИИ «единого слоя продаваемой сущности» + мультиязычности.**
  Планы этапа интегрированы (merge ветки `nifty-einstein`: market-gap A1–A9, `unified-sellable-entity`
  master-track/U-A…U-E/decisions/priority-review, **план Волны L**) + код UA1-1 (деталь услуги). Начата
  **Волна L (мультиязычность, N локалей)**: **L1 ✅** — рантайм-биндинг локалей
  (`Tenant.active_locales`-резолвер, `set_language` валидирует по включённым локалям, оверлей витрины
  генерик по `settings.LANGUAGES`, переключатель шапки — N кнопок). **L2 ✅** — кабинет «Sprachen»
  (`/dashboard/settings/languages/`: чекбоксы языков реестра + дефолт → `enabled_locales`/`default_locale`).
  Обе без миграции. **L3-модель ✅** — i18n на `Service`/`StayUnit` (`name_i18n`/`description_i18n`,
  overlay-семантика: база в плоском поле, переводы в оверлее; `I18nMixin.get_overlay`/`i18n_full`;
  миграции `booking/0011`+`stays/0020`, чистый AddField) — фундамент адаптера U-A. Решения владельца
  S-1(a)/S-2(b LegalDoc)/S-3(реестр DE+EN). SOURCE OF TRUTH этапа —
  `docs/unified-sellable-entity-master-track-2026-06-30.md §4` (очередь волн) + `docs/multilanguage-wave-L-plan-2026-07-01.md`.
  Волна U-A: **UA1-1** (деталь услуги), **UA2-1** (контракт `sellable` в контексте деталей),
  **UA3-1** (override primary-CTA услуги), **UA4-3** (богатая карточка услуги: attributes+FAQ+primary_action),
  **L3c-рендер** (`*_localized` на витрине Service/StayUnit), **UA4-4a** ✅ — generic-модель отзыва
  `reviews.Review` (`entity_kind`+`entity_id`) + data-migration из `catalog.ProductReview` + product
  переключён на generic (список/деталь/submit/демо); per-kind верификатор fail-closed. Дальше по очереди:
  **UA4-4b** (отзывы+JSON-LD на Service/Stay/Event через generic), UA4-1 (реестр секций детали).
- Самые свежие миграции: `reviews/0001`+`reviews/0002` (UA4-4a generic Review + data-migration из
  ProductReview); ранее `booking/0012` (UA4-3 attrs/faq/primary_action), `booking/0011` + `stays/0020`
  (L3-модель i18n Service/StayUnit); ещё ранее `stays/0014–0019` + `promotions/0018` (этап витрины/UX;
  L1/L2 миграций НЕ добавляли). Полный список — в build-log.

**Конвенция памяти:** завершая инкремент — дописывать строку в `docs/build-log.md`,
а ЗДЕСЬ обновлять только верхнеуровневый статус и раздел «Дальше».

## 4. Маршруты
- Корень субдомена `/` = витрина; акция `/p/<uuid>/`, бронь `/p/<uuid>/reserve/`,
  waitlist `/p/<uuid>/waitlist/`, подтверждение `/r/<code>/`, QR `…/qr.svg`,
  отписка `/u/<token>/`, право `/impressum /datenschutz /widerruf`.
- Витрина-бронь по времени `/termin/` → `/t/<code>/`; по датам (Übernachtung)
  `/unterkunft/` (юнит → даты → buchen) → `/s/<code>/`; Click&Collect `/warenkorb/`
  → `/bestellung/<code>/`; Handwerker `/anfrage/` (заявка) + `/angebot/<token>/`
  (публичная смета: принять/отклонить).
- Кабинет (под логином): `/dashboard/`, `/catalog/`, `/promotions/` (+ redeem/,
  vouchers/, loyalty/, analytics/), `/imports/`, `/dashboard/settings/`,
  `/dashboard/domains/` (custom-домены), `/dashboard/booking/` (по времени),
  `/dashboard/stays/` (по датам), `/dashboard/auftraege/` (Aufträge/Angebote),
  `/dashboard/orders/`, `/dashboard/finance/`.
- Django admin — только на public (urls_public).

## 5. Конвенции
- **Проверки — на git (GitHub Actions).** Локальный прогон — ФОЛБЭК, только если
  CI на git показал красный (для воспроизведения/отладки).
- **Скорость локального прогона: `--reuse-db`.** Вся стоимость локального pytest — в
  пересоздании тест-БД миграциями каждый раз (~70с даже для 1 теста). С `--reuse-db`
  БД переиспользуется → повторный прогон ~1-3с (замер 2026-06-28: 69с→1.1с). Для
  батч-режима/локального гейта гоняем `uv run pytest <модули> -k <...> --reuse-db`.
  ⚠️ При изменении МИГРАЦИЙ — добавить `--create-db` (иначе стале-схема даст ложные
  падения). CI всегда на свежей БД (контейнер эфемерный) — там `--reuse-db` нейтрален.
- CI (`.github/workflows/ci.yml`) гоняется на push в `main` и `claude/**` + на PR:
  `ruff check .`, `ruff format --check .`, `pytest -ra` на Postgres16 + Redis7.
- **Рабочий цикл (по подзадачам):** крупную задачу разбиваем на подзадачи и
  показываем разбивку владельцу. Одна подзадача = один инкремент: ветка
  `claude/<кратко>` → push → **CI на git зелёный** → **чекпоинт с владельцем**
  (показать, что дальше; опц. деплой на сервер `./scripts/deploy.sh single` и
  проверка там) → следующая подзадача. Создание/мерж PR через GitHub API
  недоступны (403) → в `main` мержим git-only push (main не защищён, FF/cherry-pick).
- **ВСЕГДА сначала подготовительная работа, потом код (обязательно).** Перед
  каждым нетривиальным инкрементом — план-док/разведка ДО кода (крупные доработки —
  план-доком до кода, источник правды — соответствующий план в `docs/`). **Паузы на
  проверку (ожидание CI, серийный раннер) НЕ простаивать** — в них вести
  подготовку следующих шагов параллельно: разведка кодовой базы (фоновые
  Explore/Plan-агенты — карта точек изменения, риски, переиспользование), уточнение
  развилок у владельца, проектирование схемы/резолверов, тест-кейсы. Затем
  разрабатывать СТРОГО по этим планам. Незакоммиченные планы/скелеты — сохранять
  (scratchpad или сразу в `docs/`), чтобы не терять между ходами/сжатием контекста.
- **Батч-режим (чтобы не платить латентность CI за каждый микрошаг).** CI — финальный
  гейт, но локальный прогон гоняет ТЕ ЖЕ проверки (`ruff check`/`ruff format --check`/
  `pytest`). Поэтому связные зависимые шаги пишем подряд, каждый гейтим ЛОКАЛЬНО (ruff+
  pytest затронутых модулей), коммитим отдельными коммитами (чистая история/ревью), пушем
  стопкой → **один** прогон CI на верхушке батча → merge по зелёному. На ветке включён
  `concurrency: cancel-in-progress` — промежуточные пуши отменяют устаревший прогон, копится
  только последний. Независимые треки (разные файлы) можно вести параллельными агентами в
  worktree. Размер батча — связный вертикальный срез (напр. резолвер→рендер→UI одной фичи);
  не раздувать так, чтобы при красном CI было трудно локализовать.
- После мержа с миграциями — деплой на сервере (вручную владельцем):
  `git pull origin main && ./scripts/deploy.sh single`.
- Миграции последовательные; новые TENANT-приложения — в base.py TENANT_APPS
  (test.py подхватит как SHARED). Billing — SHARED.
- Тесты django-tenants: вьюхи через RequestFactory; Tenant — через TenantFactory
  (`auto_create_schema=False`).
- Смена статусов — только через FSM `.apply()`; внешние действия (письма/
  публикации) — через Celery + idempotent_task / dedupe_key.
- Секреты не коммитить; идентификатор модели не светить в артефактах репозитория.
- Замечания «на будущее»/отложенные решения — сразу в `docs/roadmap-next-sprints.md`
  §«Отложено / заметки на будущее» (чтобы не терять между сессиями).
- Локальные службы для фолбэка: `bash scripts/dev-services.sh` (Postgres + Redis +
  роль/БД). Автоматически — SessionStart-хук (`.claude/hooks/session-start.sh`).

## 6. Документация (docs/)
- **`build-log.md`** — 📜 хронология ВСЕХ завершённых задач (извлечена из §3
  2026-06-22). Source of truth по сделанному; новые инкременты дописываем сюда.
- **`audit-2026-06-22.md`** — срез состояния + оценка готовности (Stage 0/1/2/3,
  архетипы A1–A9, модули M1–M23, риски). Периодически обновляем.
- **`master-plan.md`** — 🧭 КАНОНИЧЕСКИЙ мастер-план (сводит vision+roadmap+verticals;
  стадии: архетипы→100% + Phase 2 → глобальные функции; модули M1–M23; архитектурные
  швы под миграции). Создан 2026-06-14. Верхний уровень планирования.
- **`roadmap-next-sprints.md`** — операционный план (Sprint 5/4/6, Hardening, Phase 2 P2.x).
- **`platform-core-architecture.md`** — архитектура ядра; `full-platform-vision.md`
  (северная звезда, модули M1–M21, Phase 1–4+).
- `references/patterns/` — state-machine, anti-oversell, notification-dedupe,
  audit-log, soft-delete, cursor-pagination, webhook-hmac-signing,
  csv-import-wizard, magic-link-auth.
- `DEVELOPMENT-GUIDE.md`, `phase1-*.md`, `monetization-unit-economics.md`,
  `hetzner-claude-code-setup.md`.
- `billing-stripe-setup.md` — настройка Stripe (ключи, Price 39 €, webhook, §4
  featured, §5 Connect/оплата клиента) в `.env.prod`.
- **`external-integrations-backlog.md`** — 🔌 пункты бэклога, требующие ВНЕШНИХ
  провайдеров (Stripe live, Resend, SMS, OTA-API, метапоиск, Shopify/Woo импорт, Ads,
  Push/Wallet). «Внутреннее» делаем сначала; эти — на этапе внедрения (что подключить +
  блокер владельца). Создан 2026-06-30.
- **`micro-business-verticals.md`** — карта вертикалей DACH (потребности → полнота,
  бэклог G1–G9, порядок retail-пакета и P2.5).
- **`archetype-ux-execution-plan.md`** — 🧭 ПОШАГОВЫЙ план текущего этапа (витрина/UX +
  «анти-Битрикс», Спринты A–F, по файлам/критериям/статусам). Идём строго по нему.
- **`archetype-market-analysis.md`** — сводный рыночный анализ по архетипам A1–A9 +
  «анти-Битрикс»-блюпринт; детальные отчёты — `market-analysis/*`.

## 7. Дальше (актуальный порядок, 2026-07-01)

**🧭 АКТУАЛЬНАЯ ОЧЕРЕДЬ (этап реализации «единого слоя»):**
`docs/unified-sellable-entity-master-track-2026-06-30.md §4` — SOURCE OF TRUTH порядка волн.
Порядок: **Волна L (мультиязычность)** → **U-A** (адаптер SellableEntity) → U-B → U-C → U-D → U-E.
Решения владельца зафиксированы — `docs/unified-sellable-entity-decisions-2026-06-30.md` (A/B/C),
приоритеты — `…-priority-review-2026-07-01.md` (P/PR), план L — `docs/multilanguage-wave-L-plan-2026-07-01.md`.
**Статус Волны L:** L1 ✅ (рантайм-биндинг), L2 ✅ (кабинет «Sprachen»), **L3-модель ✅** (i18n
`Service`/`StayUnit`, overlay + миграции). Дальше: **L3c** (per-locale инпут форм/редактора + засев
демо + рендер витрины `*_localized` — идёт с UA1-3) → L4 (хром `.po/.mo`, вкл. кабинет — S-1a) → L5
(правовое i18n+AGB через модель `LegalDoc` — S-2b). Решения S-1/S-2/S-3 зафиксированы (реестр DE+EN).
**Статус U-A:** UA1-1 ✅ (деталь услуги), UA1-2 ✅ (регистрация в превью), **UA1-3 ✅** (контракт
`apps/core/sellable.py::SellableEntity` + 5 адаптеров, делегируют i18n/цену/фото; `jobs` не sellable).
Дальше: **UA2-1** (единый шаблон детали через контракт + вписать `product_detail` в каркас — наибольшая
зона регрессии, снапшот-паритет) → {UA3-* buy-box} ∥ {UA4-* секции/атрибуты/generic-Review}.
**Мерж-политика владельца (2026-07-01): FF-мерж в `main` после каждой фазы и на багфиксе** (main
не защищён; после мержа с миграциями — деплой `./scripts/deploy.sh single`).

**🔎 Аудит наполненности архетипов + план доработок (2026-06-30) —
`docs/archetype-completeness-audit-2026-06-30.md`.** Проверены 9 китов (демо/функ-
ционал), витрина (главная/категории/деталь товара+услуги/текст/право/ЛК), языковой
модуль; все ключевые факты адверсариально верифицированы. **Главные дыры:** (1) нет
ДЕТАЛЬНОЙ страницы услуги (A3, и через `booking.Service` — A7/A9); (2) AGB нет; (3)
правовое не засеяно в демо (Datenschutz → placeholder); (4) «описание услуг как FAQ»
не выделено. **Бэклог волны** — D1…D10 в §9 того дока (старт: D1 деталь услуги + D2 FAQ).

**🔬 Детальная проверка архетипов «рынок ↔ функционал» (2026-06-30, серия завершена 8/8) —
индекс `docs/market-gap-audit-2026-06-30-index.md`, капстоун `docs/market-gap-synthesis-2026-06-30.md`.**
Пошаговые доки `docs/market-gap-<a1a2|a3|a4|a5|a6|a7|a8|a9>-2026-06-30.md` (каждый: структура
сайта + матрица фич рынка DACH ↔ наш статус + приоритизир. гэпы, всё адверсариально
верифицировано против кода). **Сквозные темы (≥3 архетипов):** деталь услуги (A3/A7/A9),
платёжный микс DACH (PayPal/Klarna Kauf-auf-Rechnung/SEPA + `Order.payment_method`), верифиц.
отзывы per-item, AGB+правовое+§312j+PAngV, языковой модуль, JSON-LD по архетипу, переиспользование
движков между архетипами, SMS-канал. **Единый бэклог** — эпики E-1…E-15 в капстоуне (Tier 1 —
сквозные дешёвые победы; старт волны 1: деталь услуги → правовой пакет → JSON-LD → отзывы → reuse).

**🏗️ МАСТЕР-ТРЕК (решение владельца 2026-06-30, DRAFT на согласование) —
`docs/unified-sellable-entity-master-track-2026-06-30.md`.** Единый слой представления
продаваемой сущности (товар/услуга/номер/событие/заявка) для всех архетипов кроме
агрегатора: протокол `SellableEntity` (адаптер, модели НЕ сливаем) + единая деталь/
листинг/фасеты/категории; **отличается только buy-box по `purchase_mode`**. Поглощает
E-1 (деталь услуги) + T3/T6 (отзывы/JSON-LD) + весь редактор. Фазы: U-A контракт+деталь,
U-B листинг/фасеты, U-C **универсальный визуальный редактор на всех страницах/блоках**,
U-D **унифицированный заказ + Kanban-доска + склад-леджер** (подъём отложенного Stage 3
M10/M14), U-E **канва акций (Canva-like)** — двигать кнопки/шрифты/цвета, виды вывода
скидок. Идём инкрементально за каркасом M20U; старт U1 = вписать `Service` в `detail.html`.

**Языковой модуль (статус 2026-06-30):** фундамент НА ВИТРИНЕ тенанта уже есть —
переключатель DE/EN (`set_language`+`storefront-set-language`+`_base.html`), оверлей
`siteconfig.localize`, модельная i18n `{de,en}`, поля `Tenant.default_locale/
enabled_locales`. НЕ работает: `enabled_locales`/`default_locale` не читаются в
рантайме; `.po/.mo` пусты; хром/письма/правовое — DE-only; EN-контент только у
`pranasy`; нет кабинетного UI языков; на ПУБЛИЧНОМ домене переключателя нет (заметка
`roadmap §Отложено` про публичный домен — корректна). План достройки — L1…L6 (§6.4 дока).

Архетип A5 «Отель» закрыт: H1–H9 + бэклог роста G1–G10 + фундамент G11 (a/b).
Демо наполнено по нескольку примеров на фичу, агрегатор согласован. История —
build-log; планы — `hotel-growth-plan.md` / `hotel-channel-manager-plan.md`.
Текущий порядок (выбор владельца, 2026-06-23: сначала G11, затем M20):

1. **G11 (Channel Manager):** ✅ фундамент G11a/b (модель `Channel` + идемпотентный
   импорт броней из OTA + кабинет). **Отложено G11c–e** — реальные API
   Booking/Expedia/Airbnb (партнёрские аккаунты/сертификация — шаг владельца).
2. **M20 — Site Builder.** Аудит ✅ (2026-06-23). Адаптивный билдер + нативный кабинет
   (таб-бар `nav_primary`, поиск меню, липкая шапка). План — `docs/m20-site-builder-plan.md`.
   **M20U «унификация страниц» 🚧 (2026-06-25, активный трек, план
   `docs/m20-retreat-pages-plan.md`):** «архетип = главный товар + способ покупки»
   поверх JSON, без новых моделей. ✅ единая главная (слайдер/категории/события +
   реестры `archetypes.primary_item`/`purchase_mode`/`purchase_label`, hero-CTA, пилюли
   действия, мобильный buybar), каталог (подкатегории-первыми, фильтры свёрнуты на
   маленьком сайте), **единая детальная `storefront/detail.html`** (product/stay/event
   сведены), билдер: пер-секционные контролы (раскладка/число/заголовок/источник/«View all»),
   layout-движок на всех секциях-сетках, **per-page раскладки + вкладка «Pages»**
   (каталог/номера/события/похожие), archetype-aware дефолт главной — всё с live-preview.
   Осталось (опц.): per-page блок-редактор с панелью по клику, реестр секций детальной
   (отложен), realtime-чат (отдельный трек), применение к pranasy. Хронология — build-log.
3. **Наполнение архетипов — витрина/UX + «анти-Битрикс» 🚧 (активный трек, обновлён 2026-06-26).**
   **Точка входа — `docs/next-session-brief.md` (обновлён 2026-06-26).** SOURCE OF TRUTH этапа —
   `docs/archetype-ux-execution-plan.md` (Спринты A–F, статусы по инкрементам, идём строго по нему).
   **Сделано:** Спринт A–D ✅, **Спринт E ✅ (on-canvas E.1–E.4)**, Спринт F частично (A7-кит, RV3,
   RV2, A5 PAngV/рейтинг/**календарь наличия C1–C4**, A4 аллергены/Kombo, A9/A7 Festpreis, A8 sort).
   **Дальше (остаток F):** A6 RV1/RT1/RT2(онлайн-события, нужна миграция Event)/RT3/RT4 · A4 диет-фильтр ·
   A3 богатая карточка услуги (миграция Service)/мастера · A9 авто-данные · A7 before/after · A8 фасеты ·
   A1/A2 отзывы о товаре. Рыночный анализ — `docs/archetype-market-analysis.md` (+ `market-analysis/*`);
   карта потребностей — `micro-business-verticals.md`; крупные доработки — план-доком до кода.
4. **Спринт G — «настоящий анти-Битрикс»: кабинет/админка + онбординг 🆕 (фидбэк владельца
   2026-06-26).** План — `docs/anti-bitrix-admin-plan.md`: AB1 группировка меню кабинета по
   задачам · AB2 страница «Module» (рекомендовано/прочее/премиум + «для каких архетипов») ·
   AB3 мастер онбординга v2 (демо-дефолты + живое превью + язык задач) · AB4 чек-лист готовности
   сайта на дашборде · AB5 регистрация→мастер (high-risk). Цель: «чтобы ребёнок собрал магазин».
5. **Рефактор-гигиена (по желанию):** loyalty/vouchers уже вынесены в `apps.loyalty`.

**Параллельно — Stage 0 (на владельце, блокер боевого запуска):** Stripe live
(ключи/Price 39 €/Connect/webhook — `billing-stripe-setup.md`), инфра (отдельный
Postgres, бэкапы, `SECRETS_ENCRYPTION_KEY`, SENTRY_DSN, RESEND_API_KEY), право DACH
(AVV — `dsgvo-review.md`, прогон k6 — `scripts/load/README.md`).

**Stage 2/3 (после M20+архетипы):** P2.8 PWA/push/Wallet, M21 импорт Shopify/Woo,
M23c платная реклама; затем Stage 3 (склад-леджер, маркетплейс-корзина, закупки,
dropshipping, AI, workflow). Подробно — `master-plan.md` / audit §6.

UX-принцип (владелец, 2026-06-09): для конечного потребителя — максимально
просто, понятно и без навязчивости (бронь без аккаунта, one-click отписка,
Double-Opt-In по UWG §7 до маркетинговых рассылок, без трекинг-куки на витрине).

## 8. Деплой / инфраструктура
- Сервер Hetzner `siteadaptor-dev` (178.105.206.209), режим single (bundled
  Postgres + Redis + Caddy). Деплой: `git pull origin main && ./scripts/deploy.sh single`.
- Домен Hostinger (A-записи), Caddy on-demand TLS. Почта Resend (anymail) — пока
  console-fallback, ключ в проде не прописан.
- `.env.prod`, БД и медиа — только на сервере (в git их нет).

## 9. Заметки
- Репозиторий: `yppolyakov-wq/siteadaptor-platform` (старый аккаунт adaptor2024
  приостановлен по ToS; история/ветки перенесены).
- Перед боевым запуском: настроить Resend, вынести Postgres на отдельный сервер,
  перегенерировать секреты.
