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

---

## 6. Апдейт 2026-09-03 (после первого прогона)

* Воркфлоу `wf_36de8d71-b98` **упал на лимите аккаунта** («session limit resets
  11:30pm UTC»): из 19 агентов прошли 2 (`registries`, `storage`) — но прошли
  хорошо, с эмпирикой (гоняли `normalize`/`apply_look`/`apply_bundle` на живом
  конфиге). 17 агентов — ошибка лимита.
* Результат сведён в **`docs/style-inheritance-audit-2026-09-03.md`** (запушен).
* Остались непроверенными измерения: `resolution`, `newtenant`, `propagation`,
  `css`, `isolation`, `platform_access`, `guards`.
* **Перезапуск после сброса лимита (23:30 UTC):**
  `Workflow({scriptPath: "/root/.claude/projects/-home-user-siteadaptor-platform/a267d1f9-23a3-5838-85e1-7884b6c350ca/workflows/scripts/style-inheritance-and-isolation-audit-wf_671d1aa7-26b.js", resumeFromRunId: "wf_36de8d71-b98"})`
  — два прошедших агента реплеятся из кэша, остальные пойдут живьём.
* Таймер на 23:34 UTC уже стоит (`trig_01B9nbCbAQrUJt9996mcQZrv`).
* Найдено попутно (кандидаты в работу, кода не трогал):
  1. демо-киты не пишут `design` → на демо нет `data-sf-look` → фирменный CSS-слой
     Look'а не включается (`demo_kits.py:11705`, `_base.html:123`);
  2. `design` = «метка клика», бейдж «✓ Aktiv» может врать;
  3. `card_chrome`/`media_shape` захардкожены в двух местах.

## 7. Режим параллельной разработки (указание владельца 2026-09-04)

Параллельно идут другие сессии. Правила этой ветки:

* Перед каждым инкрементом: `git fetch origin main && git rebase origin/main`.
* В `main` — только FF после зелёного CI и свежего ребейза.
* **Golden-эталоны `normalize` не регенерировать вслепую** — сверять, чьё это
  изменение: чужая волна могла добавить секцию, мой diff её затрёт.
* **Порядок работ переставлен по конфликтности** (не по важности):
  1. §6.4 матрица проверки наследования — НОВЫЙ файл теста, ноль пересечений;
  2. §6.2 `reconcile_site_config` — новая management-команда, тоже новый файл;
  3. §6.1 единый резолвер + «пусто = наследовать» — правит `siteconfig.normalize`
     и `sitetemplates._apply` (самые горячие файлы); делать по одной оси за
     инкремент и только когда соседние волны не сидят в `siteconfig.py`.
     Риск класса W6: чужая волна добавляет ключ, я меняю семантику
     материализации → ключ молча теряется у всех тенантов.

## 8. СОСТОЯНИЕ НА 2026-09-04 ~04:45 UTC (сохранено перед лимитом)

### Сделано и запушено в ветку
1. `docs/style-inheritance-audit-2026-09-03.md` — аудит ЦЕЛИКОМ, включая §9
   «результаты полного прогона» (9 измерений из 9, 82 утверждения, 19 прошли
   скептика). Там же §9.2 (10 дефектов наследования) и §9.3 (безопасность).
2. `apps/tenants/tests/test_inheritance_matrix.py` — НОВЫЙ замок (§6.4 плана):
   **50 passed, 1 xfailed, 42 c**. Держит: рендер чистого тенанта всех 15
   архетипов; `data-sf-look` после apply_look (16 семейств × 15 типов); рендер
   рекомендованных сборок + `design.bundle`; идемпотентность НА УРОВНЕ РАЗМЕТКИ;
   xfail на дефект 5 (`apply_look` затирает `site_defaults`).
   CI по ветке не гонялся — прогон локальный (`--reuse-db`), ruff чист.

### В полёте
Воркфлоу `wf_36de8d71-b98` (задача `wr92kmrgu`) дозапущен в 04:39 UTC: осталось
12 агентов — 3 синтеза, критик полноты, проверяющие `css`/`platform_access`/
`guards`. Если снова упадёт на лимите — **резюмировать той же командой**:
`Workflow({scriptPath: "/root/.claude/projects/-home-user-siteadaptor-platform/a267d1f9-23a3-5838-85e1-7884b6c350ca/workflows/scripts/style-inheritance-and-isolation-audit-wf_671d1aa7-26b.js", resumeFromRunId: "wf_36de8d71-b98"})`
Результаты прошлых прогонов (не потерять, там вся эмпирика):
`/tmp/claude-0/-home-user-siteadaptor-platform/a267d1f9-23a3-5838-85e1-7884b6c350ca/tasks/wlqhz3rlp.output`

### Очередь дальше (в этом порядке)
1. **Замок на демо-киты**: матрица покрывает `apply_look`/`apply_bundle` (они
   `design` пишут), а `demo_kits.py:11705` — нет; дефект 1 аудита остаётся
   непокрытым. Короткий инкремент, новый файл/дополнение матрицы.
2. **P0 безопасности** (после проверки скептиком, §9.3): CSRF-токен в кэше
   витрины (`pagecache.py:52-96`, отдаётся голый HttpResponse без Set-Cookie/
   Vary, тело закэшировано с `{% csrf_token %}`); публичная раздача `/media/`
   без префикса схемы + `imports/<исходное имя>`; `|| true` у deploy-check
   (`scripts/deploy.sh:71`); `_voucher_cap_percent()` читает Tenant из public.
3. §6.2 `reconcile_site_config` (новая команда, конфликтов нет).
4. §6.1 единый резолвер — только в окно без чужих волн в `siteconfig.py`.

### Что НЕ решено владельцем
Порядок §6.1/§6.2 и вообще старт правок движка конфигов. Пока трогал только
новый тест-файл и доки — поведение платформы не менялось.

## 9. Грабля 2026-09-04: мусор агентов в коммите

CI падал на `ruff lint` (не доходя до тестов): агенты-скептики писали временные
пробники `apps/core/tests/test_zz_skeptic*.py` и не все убрали, а `git add -A`
их закоммитил. Правило: **в сессиях с агентами коммитить перечислением путей**
(`git add <файл> <файл>`), а перед пушем гонять `uv run ruff check .` ЦЕЛИКОМ —
проверка своих файлов точечно этого класса не ловит.
Также: 4 локальных падения (`test_today_label`, `test_menu_slide_chips_*`,
`test_hero_widget_*`, `test_services_section_*`) — ПРЕД-СУЩЕСТВУЮЩИЕ (проверено
откатом `demo_kits.py` к origin/main), это известная локальная грабля «нет
gettext → немецкие ассерты»; на CI они зелёные.
