# CLAUDE.md — siteadaptor-platform

Claude Code загружает этот файл целиком в начале КАЖДОЙ сессии и каждому субагенту — поэтому
он короткий. Здесь только то, что нужно всегда: что это за проект, где что лежит, текущий
статус, правила работы. История, решения и грабли живут в `docs/` (карта — §6).

**Бюджет файла — 45 КБ (замок `apps/core/tests/test_claude_md_budget.py`).** Завершая
инкремент: хронология → `docs/build-log.md`; статус ID → `docs/task-catalog.md`; новое
решение владельца / единый модуль / ops-шаг → `docs/project-memory.md`; грабля →
`docs/pitfalls.md`. Здесь правится только §3 (две-три строки «сейчас») и §7.

## 1. Что это
Мультитенантный Django 5.2 LTS SaaS для малого оффлайн-бизнеса DACH (16 типов: пекарни,
кафе, рестораны, кейтеринг, салоны, мастерские, ремесло, отели, туры, события, магазины):
сайт на субдомене, каталог, заказы, запись, номера, билеты, заявки и сметы, акции, финансы,
склад, CRM, городской портал-агрегатор (пилот — Solingen), Telegram-боты и Mini App,
ИИ-помощник. Бизнес выбирает направления («как продаёт»), модули включаются по ним.

Стек: Django 5.2, django-tenants (схема на бизнес, Postgres 16), Redis 7, Celery 5
(worker+beat), HTMX/Alpine/Tailwind, django-allauth, dj-stripe, django-unfold (admin),
django-storages (S3/Hetzner), Caddy 2 (on-demand TLS). Python 3.12, менеджер uv (`uv.lock`
в репозитории).

## 2. Архитектура / где что
- `config/` — settings/{base,development,production,test,stand}.py, `urls_tenant.py`
  (субдомены бизнеса), `urls_public.py` (платформа, регистрация, admin), `urls_portal.py`,
  celery.py.
- **SHARED** (public-схема): `tenants` (Tenant, Domain, регистрация, мастер, siteconfig,
  демо-киты), `billing`, `aggregator` (портал, поиск, подписки), `ai`, `partners`,
  `platform_bot`, `audit`, `support`, `secrets`, `integrations/webhooks`.
- **TENANT** (схема бизнеса): `core` (общие слои), `catalog`, `orders`, `booking`, `stays`,
  `events`, `jobs`, `promotions`, `loyalty`, `finance`, `inventory`, `crm`, `inbox`,
  `reviews`, `collections`, `documents`, `community`, `publishing`, `notifications`,
  `telegram`, `imports`, `account`.
- Шесть видов сделок (order · booking · stay · ticket · job · reservation) сведены общими
  слоями в `apps/core/`. **Перед правкой — найти свой модуль в `docs/project-memory.md` §3
  (≈190 «единых точек истины») и звать его, а не заводить второй список или писатель.**
  Самые частые:
  - сделки и деньги: `fsm.py` (`apply` — единственная смена статуса), `transactions.py`
    (`transaction_for`, `apply_action`), `status_registry.py` + `status_effects.py`,
    `money_contract.py`, `folio.py`, `refunds.py`, `money.py` (`parse_amount`),
    `payment_methods.py`, `deal_card.py`, `vat.py`;
  - продаваемое и витрина: `sellable.py` (контракт `SellableEntity`), `facets.py`,
    `card_forms.py`, `compositions.py`, `list_blocks.py`, `page_settings.py`,
    `detail_sections.py`, `seo.py`, `richtext.py`, `legal.py`,
    `apps/tenants/siteconfig.py` (normalize + реестры), `apps/tenants/sitetemplates.py`,
    `apps/tenants/menu.py`, `apps/promotions/price_layer.py`;
  - кабинет: `nav_registry.py` (вся навигация), `permissions.py` + `view_perms.py` +
    `perm_grants.py` (права), `modules.py` + `directions.py`, `readiness.py`,
    `sales_page.py`, `list_filters.py`, `assistant_actions.py`;
  - склад: `apps/inventory/services.py` (единственный складской путь);
  - портал: `apps/aggregator/visibility.py`, `portal_scope.py`, `search.py`;
  - i18n: `i18n_input.py`, `i18n_cabinet.py`, `i18n_seq.py`, `i18n_json.py`;
  - документы/PDF: `documents.py`; исходящие запросы по адресу пользователя — `ssrf.py`.
- `scripts/deploy.sh`, `scripts/dev-services.sh`, `scripts/golden_paths.py` (стенды
  золотых путей), `scripts/i18n_quickcheck.py`, docker-compose.prod.yml, caddy/.

Архитектура ядра: `docs/platform-core-architecture.md`.

## 3. Статус
- **Сделано** (подробно — `docs/build-log.md`, по ID — `docs/task-catalog.md`): все 16 типов
  бизнеса с демо-китами; единый слой продаваемой сущности, листинги, блоки страниц, Студия и
  шаблоны страниц; кабинет (одна навигация, одна поверхность продаж «Verkäufe», единая
  карточка сделки, права сотрудников, шторка); деньги (НДС по позициям, счета, корректуры,
  Anzahlung, банк, Offene Posten, UStVA-срез, DATEV); склад и закупки; акции как ценовой слой;
  i18n на 5 языков (de/en/tr/ru/uk); городской портал T-8 (поиск, подписки, фид, MCP,
  тематические порталы, 79 демо-бизнесов Solingen); Telegram (общий бот, Mini App, бот
  портала); ИИ-слой и помощник A-0…A-6; мастер v4; аудит безопасности SEC (волны 1–4).
- **Сейчас** (2026-11-13): FB-27 «Website: Seitenaufbau» — R0…R9 сделаны (черновик на
  страницу, ширина блоков, блок «Liste» с ручным составом, настройки типа страницы в панели,
  блоки «Textseite» и «Kontakt», готовые строки, своя схема категории; Студия пишет только
  содержимое, пункта «Studio» в меню нет; «Seitenvorlagen» снесены — адреса 302 в
  «Seitenaufbau»; обход владельца R9 — 5 типов бизнеса, 1440/390, de/ru, без JS; экран
  доведён до макета V1–V4, правка в панели без «Übernehmen»), FB-28 (пункты редактора меню
  сворачиваются), экран
  «Seiten» по макетам S1–S3 — список карточками, меню «⋯», вкладки Text · Blöcke ·
  Suchmaschinen), экран «Design» по макетам D1–D2 (вкладки, готовые дизайны с панелью
  подтверждения, главная перестраивается только по галочке); встроенные списки главной
  правятся в панели «Seitenaufbau»; M21.11 P6/P7
  (редактор страниц); прогон переезда haanerteeladen на сервере — за владельцем.
- **Открытое, ops и решения владельца** — `docs/project-memory.md` §1, §2, §5.
- **Миграции к деплою (гипотеза до сверки; истина — `python manage.py migration_state`,
  шаг встроен в `deploy.sh`).** Последняя подтверждённая сверка «всё применено» —
  2026-10-24 (136 схем). После неё: `aggregator` 0037, 0038, 0039, 0040, 0041 · `booking` 0034, 0035, 0036, 0037, 0038, 0039, 0040, 0041, 0042, 0043, 0044, 0045 · `catalog` 0041, 0042, 0043, 0044, 0045 · `core` 0013, 0014, 0015, 0016, 0017, 0018, 0019, 0020, 0021 · `crm` 0003 · `events` 0032, 0033, 0034, 0035, 0036, 0037 · `finance` 0017, 0018 · `inbox` 0002 · `jobs` 0022, 0023, 0024, 0025, 0026 · `loyalty` 0008, 0009 · `orders` 0026, 0027, 0028, 0029 · `promotions` 0032, 0033, 0034, 0035, 0036 · `stays` 0039, 0040, 0041, 0042, 0043, 0044, 0045, 0046, 0047 · `tenants` 0040, 0041, 0042 · `webhooks` 0002. Все аддитивные; `events/0036` переписывает таблицу
  билетов каждой схемы. После деплоя: `sync_aggregator` → `rebuild_search_index` →
  `seed_demo_tenants --group all --changed --jobs 3`.
- Срез истории §3 до 2026-11-11 дословно — `docs/claude-md-archive-2026-11-11.md`.

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
  **Финальный гейт ПЕРЕД пушем батча (уроки CI 1116/1121/1122):** `ruff format --check .`
  ЦЕЛИКОМ (не точечно — особенно после скриптовых/sed-правок); при новых Tailwind-классах
  в шаблонах — `npm run build:css` и закоммитить `static/css/app.css` (CI-замок свежести);
  при правках шаблонов — прогнать `apps/core/tests/test_template_comments.py` (многострочные
  `{# #}` запрещены) И `uv run python scripts/i18n_quickcheck.py` (новый msgid без записи
  в `.po` роняет CI-гейт i18n, а сам гейт локально не запускается — нет gettext). ⚠️ `ruff format` по ЯВНОМУ пути обходит exclude миграций — старые
  миграции не переформатировать. `billing/tests/test_tasks.py` виснет локально (среда,
  на CI зелёный) — локально гейтить с `--ignore`. ⚠️ Правки адаптеров
  `SellableEntity` (apps/core/sellable.py) гейтить ВКЛЮЧАЯ `apps/tenants` —
  секции главной рендерят карточки через SimpleNamespace-стабы контракта
  (test_services_section и т.п.; урок CI 1145).
- После мержа с миграциями — деплой на сервере (вручную владельцем):
  `git pull origin main && ./scripts/deploy.sh single`.
- Миграции последовательные; новые TENANT-приложения — в base.py TENANT_APPS
  (test.py подхватит как SHARED). Billing — SHARED.
- Тесты django-tenants: вьюхи через RequestFactory; Tenant — через TenantFactory
  (`auto_create_schema=False`).
- Смена статусов — только через FSM `.apply()`; внешние действия (письма/
  публикации) — через Celery + idempotent_task / dedupe_key.
- Секреты не коммитить; идентификатор модели не светить в артефактах репозитория.
- **Грабли — `docs/pitfalls.md` (2026-10-24, запрос владельца).** Перед инкрементом —
  раздел своей темы + скиллы ECC из таблицы §0 (грузить В НАЧАЛЕ, не после ревью). Новая
  грабля — строка туда в том же коммите; повторилась — превратить в замок.
- **ECC — обязательный раздел плана (правило владельца 2026-10-24).** Не забывать скиллы и
  агентов ECC при разработке, тестировании и запуске. Сразу после плана (агент `planner`)
  дописать в план раздел «ECC-прогоны»: какие скиллы грузить до кода (django-patterns/tdd/
  security/database-migrations/e2e-testing/accessibility/…), какие агенты гонять и на каком
  шаге (`django-reviewer` всегда; `security-reviewer` — ввод/авторизация/деньги;
  `database-reviewer` — миграции/тяжёлые запросы; `silent-failure-hunter` — деньги/внешние
  вызовы; `e2e-runner`/Playwright — JS и вёрстка; `a11y-architect` — новые UI-элементы).
  Где рационально — запускать сразу после плана (например, ревью плана/разведку), остальное —
  в указанной точке цикла; до мержа все пункты раздела закрыты.
- **Новый экран кабинета — по чеклисту `docs/cabinet-screen-dod.md`** (X7,
  2026-08-19): запись в nav_registry/палитру или осознанно в EXPECTED_UNLISTED;
  состав якорей сайдбара ЗАМОРОЖЕН замком (мораторий владельца).
- Замечания «на будущее»/отложенные решения — сразу в `docs/roadmap-next-sprints.md`
  §«Отложено / заметки на будущее» (чтобы не терять между сессиями).
- **Everything Claude Code (ECC)** — копией в репозитории (2026-10-15): правила `common`+`python`
  в `.claude/rules/ecc/`, 15 агентов в `.claude/agents/`, 24 скилла в `.claude/skills/` (набор под
  Django; дополнен 2026-10-16: API-дизайн, E2E/Playwright, миграции, деплой/Docker, SEO,
  доступность, ошибки, рынок/конкуренты/маркетинг, MCP). Плагином НЕ подключаем — облачные сессии плагины не загружают. При расхождении с
  проектом действуют `.claude/rules/project-overrides.md` и этот файл; состав — `rules/ecc/README.md`.
- Локальные службы для фолбэка: `bash scripts/dev-services.sh` (Postgres + Redis +
  роль/БД). Автоматически — SessionStart-хук (`.claude/hooks/session-start.sh`).
- **Память проекта (2026-11-13).** Что владелец уже решил, какой модуль за что отвечает,
  что открыто и что должен сделать владелец — `docs/project-memory.md`. Читать раздел своей
  области ДО кода; снесённое (classic_ui, режим Простой/Эксперт, таб-бары хабов, рейка
  Студии, `studio_scope`, AI-генерация демо-фото) не восстанавливать.
- **Хотфиксы прямо в `main` запрещены (владелец, 2026-10-16).** Каждый пункт: план (`planner`)
  → замки ДО кода → ревьюеры ECC → зелёный CI → FF в `main`. Исключение — деньги, данные,
  закон: чинить сразу, но тем же циклом.
- **Переработка UI — сначала варианты дизайна на утверждение (канвас), потом код.** Редизайн
  = только рендер: FSM, вьюхи, URL, `nav_registry` не трогать.
- **Параллельные сессии.** Перед сводом веток сверять с `main`; свой дубль снимать целиком,
  оставляя реализацию `main`. Агентов планировать с запасом по лимиту сессии; в отчёте
  писать, какие проверки не доиграли.

## 6. Документация (docs/)
- **`task-catalog.md`** — 🗂 ЕДИНАЯ КАРТА ID задач (создана 2026-07-03 по фидбэку
  владельца). Правила: новая работа берёт ID из каталога ДО план-дока;
  расширяется → углубляется (B1 → B1.1, не новая буква); семейства не плодить;
  коллидирующие коды называть с семейством («идея B1», «архетип A4»).
  Обновлять в том же коммите, что и build-log-строку.
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
- **`project-memory.md`** — 🧠 решения владельца, единые точки истины в коде, открытое,
  ops владельцу (собрано 2026-11-13 из истории этого файла).
- **`pitfalls.md`** — грабли по темам + таблица «какой скилл/агент ECC брать» (§0).
- **`claude-md-archive-2026-11-11.md`** — дословный срез §3 и §7 этого файла до сокращения.
- `cabinet-glossary.md`, `cabinet-screen-dod.md`, `references/patterns/drawer.md` — термины
  кабинета, чеклист нового экрана, контракт шторки.
- `security-audit-report-2026-11-01.md` — отчёт SEC (§6–7 — актуальный ops-список).

## 7. Дальше
Очередь — `docs/task-catalog.md`; открытое и чьё решение нужно — `docs/project-memory.md` §1.
- В работе: M21.11 P6 → P7. FB-29 (`docs/fb29-content-structure-plan-2026-11-13.md`) сделан:
  баннеры, редактор фото, своя структура и свои блоки
  товара/услуги (`object_structure.py`), примеры в предпросмотре дизайна, «Wo zeigen» у баннера (29.2c); место баннеров задаёт
  блок «Banner» в структуре, все баннеры — в библиотеке (перенос — шаг `deploy.sh`).
  FB-27 закрыт, остаток — `docs/roadmap-next-sprints.md`
  (вывод «Liste», число карточек «Empfohlen», наборы блоков страницы акций в Студии).
- За владельцем: решения (Pro-тариф и пакеты, включение ИИ-поиска, оценка пилота MCP),
  юрист/Steuerberater (Anzahlungsrechnung, Widerruf, Datenschutz-абзацы), ops (§2 памяти).
- **Stage 0 — блокер боевого запуска (владелец):** Stripe live (`billing-stripe-setup.md`),
  отдельный Postgres и бэкапы (cron `scripts/backup.sh`), `SENTRY_DSN`, право DACH (AVV —
  `dsgvo-review.md`), нагрузочный прогон k6 (`scripts/load/README.md`).
  **⚠️ При переезде на внешний Postgres роль БД обязана иметь право `CREATE EXTENSION`
  (миграция `aggregator/0023` ставит `pg_trgm`); проверять ДО миграции на пустой копии.**
- Внешние интеграции — `docs/external-integrations-backlog.md`.

UX-принцип (владелец, 2026-06-09): для конечного потребителя — максимально просто, понятно
и без навязчивости (бронь без аккаунта, one-click отписка, Double-Opt-In по UWG §7 до
маркетинговых рассылок, без трекинг-куки на витрине).

## 8. Деплой / инфраструктура
- Сервер Hetzner `siteadaptor-dev` (178.105.206.209), режим single (bundled
  Postgres + Redis + Caddy). Деплой: `git pull origin main && ./scripts/deploy.sh single`.
- Домен Hostinger (A-записи), Caddy on-demand TLS. Почта Resend (anymail) — РАБОТАЕТ
  в проде (сверено владельцем 2026-10-20: `EMAIL_BACKEND = anymail.backends.resend`).
- `.env.prod`, БД и медиа — только на сервере (в git их нет).

## 9. Заметки
- Репозиторий: `yppolyakov-wq/siteadaptor-platform` (старый аккаунт adaptor2024
  приостановлен по ToS; история/ветки перенесены).
- Перед боевым запуском: вынести Postgres на отдельный сервер,
  перегенерировать секреты. **⚠️ При выносе Postgres — роль с правом `CREATE EXTENSION`
  (нужен `pg_trgm` для поиска T-8.20, см. §7).**
