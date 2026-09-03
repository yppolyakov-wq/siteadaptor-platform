# HANDOFF — «Наследование стилей + изоляция данных» (сессия 2026-09-03)

> Файл-страховка: если сессия оборвётся (лимит токенов / перезапуск контейнера) —
> новая сессия продолжает ОТСЮДА. Обновляется по ходу работы, коммитится в ветку
> `claude/style-inheritance-sites-archetypes-i8mb17`.

## 1. Запрос владельца (дословно)

> «Запусти проверку наследования стилей для новых сайтов и архетипов. Сейчас идёт
> обновление каждого. Может имеет смысл для общих данных создавать один раздел и
> чтоб туда ссылались все сайты. А для их личных правок в шаблонах или схемах
> делать отдельный файл с их персональными настройками, или как это работает,
> объясни. Так чтоб было максимально для всех безопасно и доступа к личным данным
> не было у нас, только у каждого бизнеса отдельно, с максимальной степенью
> безопасности.»

Плюс два поручения по ходу:
* поставить таймер на 3 ч 25 мин на продолжение — ✅ сделано
  (`send_later`, trigger `trig_01B9nbCbAQrUJt9996mcQZrv`, fire 2026-09-03T23:34Z);
* сохранить историю на случай обрыва по токенам — ✅ этот файл.

## 2. Что запущено

Воркфлоу-аудит `wf_671d1aa7-26b` (9 измерений разведки → скептик на каждое
утверждение → 3 синтеза + критик полноты). Скрипт:
`/root/.claude/projects/-home-user-siteadaptor-platform/a267d1f9-23a3-5838-85e1-7884b6c350ca/workflows/scripts/style-inheritance-and-isolation-audit-wf_671d1aa7-26b.js`
Резюме прогона: `Workflow({scriptPath: <выше>, resumeFromRunId: "wf_671d1aa7-26b"})`.

Измерения: registries · storage · resolution · newtenant · propagation · css ·
isolation · platform_access · guards.

## 3. Установлено чтением кода (до результатов воркфлоу)

1. **Общий слой дизайна = код-реестры, а не БД.** `LOOK_FAMILIES`/`BUNDLES`/
   `COMPOSITIONS`/`TEMPLATES` (`apps/tenants/sitetemplates.py`), `SECTIONS`/
   `SECTION_STYLES`/`LAYOUT_PRESETS`/`CBLOCK_VARIANTS`/`HERO_STYLES`
   (`apps/tenants/siteconfig.py`), `PAGE_PRESETS` (`apps/core/page_presets.py`),
   `CARD_FORMS` (`apps/core/card_forms.py`), `category_styles`, `group_styles`,
   `option_styles`.
2. **Личный слой = ОДНО поле** `Tenant.site_config` (JSONField,
   `apps/tenants/models.py:185`) в public-схеме + per-object поля
   (`Product.card_style`, `Promotion.card_style`, `Category.page_style`, …).
3. **Ключевая механика — `_apply()` в `sitetemplates.py:861`: применение
   шаблона/Look'а КОПИРУЕТ значения семейства в конфиг тенанта** (`font`,
   `typography`, `site_defaults`, `nav.style`, `theme`, `sections`, `hero_style`).
   То есть Look — СНИМОК, а не ссылка → правка `LOOK_FAMILIES` в коде НЕ доезжает
   до уже применивших его сайтов. Это и есть причина «обновления каждого».
   (База копии — `dict(current)`: чужие ключи не теряются, это фикс класса W6.)
4. **`normalize()` (`siteconfig.py:2914`) — двухрежимный:** часть ключей
   presence-minimal (нет ключа = наследовать: `theme`, `board`, `design`,
   `promo_layout`, `catalog_page_style`, `card_style`, `card_chrome`,
   `media_shape`, `page_bg` …), часть МАТЕРИАЛИЗУЕТСЯ всегда (`sections`,
   `hero_style`, `font`, `typography`, `nav`, `faq`, `team`, `trust`, `cta`,
   `menus`, `block_templates`, `page_templates`, `history`, TEXT_FIELDS).
   Материализованные = замороженный снимок дефолта у каждого тенанта.
5. **Резолв «своё бьёт общее» реализован по-разному у разных осей.**
   Каноничный пример — `core/card_forms.py::card_form(entity, site_default, kind)`
   (объект → сайт → ""), у визуала карточек — `siteconfig.effective_card_visual`
   (секция → site_defaults), у категорий — `category_styles.page_style`. Единого
   резолвера наследования НЕТ.
6. **Изоляция:** django-tenants schema-per-tenant; SHARED_APPS/TENANT_APPS —
   `config/settings/base.py`. Стек middleware: `CustomDomainHostMiddleware` →
   `TenantMainMiddleware` → … → `SessionSchemaGuardMiddleware` (кука чужой схемы
   сбрасывается, HIGH-10).
7. **Что лежит в public (вне изоляции):** `Tenant` (контакты бизнеса, billing,
   site_config), `Domain`, `apps.aggregator` (**копии витринных данных тенанта**:
   `AggregatorListing.tenant_schema/title/teaser/цены/гео/detail_url`,
   `BusinessReview` — отзывы посетителей о бизнесе), `apps.billing`,
   `apps.partners`, `apps.support` (переписка бизнес↔платформа), `apps.audit`,
   `apps.secrets`.
8. **Шифрование:** `apps/secrets/crypto.py` — Fernet; мастер-ключ
   `settings.SECRETS_ENCRYPTION_KEY`, **при отсутствии — детерминированный
   фолбэк из SECRET_KEY** (deploy-check ловит в проде). Шифруются:
   `TelegramBot.token`, `GuestRegistration.doc_number` (§30 BMG),
   `apps.documents` (файлы участников). Ключ в любом случае у платформы.
9. **Django admin — только на public** (`config/urls_public.py`), зарегистрированы
   в основном SHARED-модели (promotions/catalog admin — надо проверить, попадают
   ли TENANT-таблицы: admin работает в public search_path).

## 4. Что делать дальше (порядок)

1. Дождаться воркфлоу → свести факты (подтверждённые/опровергнутые).
2. Написать `docs/style-inheritance-audit-2026-09-03.md`: как устроено сейчас
   (общий/личный слой), где ломается наследование, модель изоляции + пробелы.
3. Ответить владельцу по-русски: объяснение + предложение целевой модели
   (4 слоя: платформа → архетип → сайт → страница/объект; «пусто = наследовать»),
   + план усиления безопасности P0/P1/P2.
4. По отмашке — реализация инкрементами (первый кандидат: авто-проверка
   наследования = матрица 16 архетипов × ключевые страницы × Look/сборки).

## 5. Правила этой сессии

* Ветка разработки: `claude/style-inheritance-sites-archetypes-i8mb17`.
* Кода-правок пока НЕТ — только аудит и доки.
* Ultracode: работать воркфлоу-агентами, каждое утверждение верифицировать.
