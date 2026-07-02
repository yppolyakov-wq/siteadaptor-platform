# Волна L — детальный план подзадач (МУЛЬТИЯЗЫЧНОСТЬ: витрина + кабинет/админка, N локалей) — 2026-07-01

> Новая приоритетная волна (решение владельца 2026-07-01, `…-priority-review-2026-07-01.md` PR-1/PR-3):
> **полноценная мультиязычность**, а не «DE/EN». Языки админки И витрины добавляем со временем; сейчас
> DE+EN, архитектура — **N локалей без хардкода**. Поднята в приоритет как **зависимость U-A** (адаптер
> `SellableEntity`): **L1+L2 — ДО кода U-A** (без миграции), **L3 — ПАРАЛЛЕЛЬНО U-A** (i18n-поля Service/Stay,
> миграция) → адаптер сразу locale-clean, без рефактора. Формат — как U-A…U-E. Все пути/поля — верифицированы
> разведкой против кода (источник: `…-priority-review…` §2, `archetype-completeness-audit §6.4`).

## 0. Принцип: N локалей, не «два языка» (дизайн)

Мультиязычность = **генерик по локали**, языки добавляются как данные, не как код:
- **Центральный реестр поддерживаемых языков** — `settings.LANGUAGES` (сейчас `[("de",…),("en",…)]`),
  растёт добавлением локали + её `.po/.mo`. Один источник «какие языки в системе вообще есть».
- **Per-tenant подмножество** — `Tenant.enabled_locales` (список) + `Tenant.default_locale` (`models.py:32-33`):
  каждый тенант включает свой набор из реестра; дефолт — фолбэк.
- **Контент** — i18n-JSONField `{de, en, …}` по **произвольной локали** (`I18nMixin.get_i18n` уже
  фолбэчит locale→de→en→first, `core/models.py:31-52`). Модельный слой УЖЕ N-locale — не хардкод двух.
- **Оверлей витрины** — `localize()`/`_deep_overlay` (`siteconfig.py:1006-1020`): сейчас
  **`OVERLAY_LOCALES=("en",)` захардкожен** (`:974`) → сделать **динамическим по `enabled_locales`**.
- **Хром/письма** — Django gettext (`{% trans %}` + `.po/.mo`), локаль-агностично; добавить язык = добавить
  `.po/.mo`, не править шаблоны.
- **Покрытие ОБА:** и **витрина** (посетитель), и **кабинет/админка** (владелец) — два independent-переключателя
  локали (посетитель — cookie на витрине; владелец — Django-locale в кабинете).

## 1. Текущий статус (верифицировано против кода)

| Слой | Есть ✅ | Сломано/нет ❌ |
|---|---|---|
| Модельный i18n | `I18nMixin` (`core/models.py:31-52`); i18n-JSONField у Product/Category (`catalog/models.py:14,48-52`), Event (`events/models.py:27,42-43`), Promotion (`promotions/models.py:92,97-98`) | **`Service` (`booking/models.py:61-92`) и `StayUnit` (`stays/models.py:40,58-60`) — БЕЗ i18n** (плоские DE-строки) |
| Рантайм-локаль | Переключатель витрины DE/EN (`urls_tenant.py:133`, `_base.html:87-90`, `set_language` `public_views.py:445-452`); `LocaleMiddleware`/`USE_I18N` (`settings/base.py:185-192`) | `Tenant.enabled_locales`/`default_locale` **не читаются** (валидация против `settings.LANGUAGES`); `OVERLAY_LOCALES=("en",)` **захардкожен** (`siteconfig.py:974`) |
| Контент-оверлей | `localize`/`_deep_overlay`/`_clean_i18n` (`siteconfig.py:977-1020`); контекст по `get_language()` (`context.py:123-129`) | оверлей только на **EN** (один захардкоженный язык) |
| Хром/письма/правовое | — | Хром витрины/кабинета — **не в `{% trans %}`**; `.po/.mo` **пусты** (`/locale/`=`.gitkeep`); письма DE-only; правовое (`tenants/models.py:116-118`) — плоский `TextField`, **AGB-поля нет**, не засеяно (placeholder `:248`) |
| Демо-контент | EN только у `pranasy` (`demo_kits.py:785-879`) | остальные 8 китов — DE-only |
| Публичный домен | — | переключателя языка **нет** (`urls_public.py`) |
| Кабинет | — | UI «Sprachen» (включить языки/дефолт) **нет** |

## 2. Партиция (что унифицируем / провайдер / раздельно)
- **УНИФИЦИРУЕМ:** резолвер локали (один `active_locales(tenant)` + `default_locale` — читают и витрина, и
  кабинет, и оверлей, и формы); генерик-оверлей по `enabled_locales`; per-locale-инпут-виджет форм (N колонок
  по включённым локалям); gettext-хром (`.po/.mo`) — один механизм на весь UI.
- **ПРОВАЙДЕР (per-слой):** источник локали — витрина (cookie `set_language`) vs кабинет (Django-locale) vs
  письмо (локаль получателя/заказа); правовой контент (i18n-модель vs JSONField — под-решение S-2).
- **РАЗДЕЛЬНО (не трогаем):** `I18nMixin.get_i18n`-фолбэк (уже верный); анти-оверселл/движки/FSM (язык не
  касается); URL-локаль-префиксы (L6, опц., отдельно — SEO-слой).

## 3. Подзадачи Волны L (сводка)

| ID | Заголовок | Разм. | Мигр. | Зависит | Когда |
|---|---|:--:|:--:|---|---|
| **L1** | Рантайм-биндинг локалей: `active_locales(tenant)`/`default_locale` читаются; `OVERLAY_LOCALES` динамический; переключатель показывает только `enabled_locales` | S | — | — | **ДО U-A** |
| **L2** | Кабинет «Sprachen»: включить/выключить языки из реестра + выбрать дефолт (пишет `enabled_locales`/`default_locale`) | M | — | L1 | **ДО U-A** |
| **L3** | Per-locale инпут форм (N колонок) + **i18n-поля на `Service`/`StayUnit` (миграция)** + засев мультиязыч. контента во все киты | M | **да** | L1 | **∥ U-A** (крит. зависимость адаптера) |
| **L4** | Хром **витрины И кабинета/админки** в `{% trans %}` + `makemessages`/`.po`/`compilemessages` + локаль-aware письма | M | — | L1 | ∥/после U-C |
| **L5** | Правовое мультиязычное: `impressum/datenschutz/widerruf` + **новое AGB** → i18n + автоген EN-шаблонов + засев (сходится с E-2/P3) | M | **да** | L3 | с E-2 (U-C) |
| **L6** | *(опц., отложено)* Язык в URL `/<locale>/…` + hreflang/canonical (SEO) — генерик по локали | L | возм. | L4 | по запросу |

**Старт = L1** (рантайм-биндинг, без миграции). **Миграции волны:** **L3** (i18n-поля Service/Stay), **L5**
(правовое i18n + AGB); L6 — возможно. L1/L2/L4 — без миграций.

## 4. Подзадачи (детально: файлы/критерии/тесты)

### L1 — Рантайм-биндинг локалей (N-locale фундамент) · S · без миграции
Резолвер `active_locales(tenant)` (пересечение `settings.LANGUAGES` × `Tenant.enabled_locales`, фолбэк на
`[default_locale]` при пустом) — единый источник «какие языки у этого тенанта». `set_language`
(`public_views.py:445-452`) валидирует против `active_locales`, не `settings.LANGUAGES`. `OVERLAY_LOCALES`
(`siteconfig.py:974`) → функция от тенанта (итерирует `active_locales` минус `default_locale`), не `("en",)`.
Переключатель `_base.html:87-90` рендерит `active_locales` (N кнопок, не 2 захардкоженных).
- **Файлы:** `apps/tenants/models.py` (+`active_locales` property/helper), `apps/promotions/public_views.py`
  (`set_language`), `apps/tenants/siteconfig.py` (`localize`/`OVERLAY_LOCALES` → per-tenant), `apps/core/context.py`,
  `templates/storefront/_base.html`.
- **Критерии:** тенант с `enabled_locales=["de","fr"]` показывает DE/FR (не EN); неизвестная локаль → `default_locale`;
  оверлей применяет любую включённую локаль (не только EN); пустой `enabled_locales` → текущее поведение (DE), без регресса.
- **Тесты:** `apps/tenants/tests/test_locale.py` (новый) — active_locales/фолбэк/оверлей на 3-й локали; `test_siteconfig`.

### L2 — Кабинет «Sprachen» · M · без миграции
Дашборд-вью: чекбоксы включения языков **из реестра `settings.LANGUAGES`** (→ `enabled_locales`) + радио дефолта
(→ `default_locale`). Здесь владелец «добавляет языки витрины» (из доступных в системе). Пункт в nav.
- **Файлы:** `apps/core/views.py` (+вью+маршрут), `templates/…/languages.html` (новый), `apps/core/modules.py`
  (nav-пункт в группе «Einstellungen»), `config/urls_tenant.py`.
- **Критерии:** сохранение пишет `enabled_locales`/`default_locale` (без миграции — поля есть); дефолт обязан быть
  во включённых; витрина/оверлей сразу отражают (через L1); гейтинг как прочий кабинет.
- **Тесты:** `apps/core/tests/test_languages_cabinet.py` (новый) — GET/POST, инвариант «дефолт ∈ enabled».

### L3 — Per-locale формы + i18n Service/Stay + засев · M · **МИГРАЦИЯ** (крит. зависимость U-A)
(1) **i18n-поля на `booking.Service`** (`name_i18n`/`description_i18n` или `I18nMixin`) и `stays.StayUnit`
(`name_i18n`/`description_i18n`) — **миграция** + бэкфилл текущих DE-строк в `{de: …}`. (2) Per-locale инпут-виджет
в формах/админке (Product/Category/Event/Promotion/Service/StayUnit) — **N колонок по `active_locales`** (не 2
захардкоженных). (3) Засев мультиязыч. контента во все киты (сейчас EN только у pranasy) — структура на N локалей.
- **Файлы:** `apps/booking/models.py`+миграция, `apps/stays/models.py`+миграция, `apps/{catalog,events,promotions,
  booking,stays}/admin.py` (per-locale виджет), `apps/tenants/demo_kits.py`+`seed_demo_tenants.py`.
- **Критерии:** Service/Stay несут i18n (миграция без потерь — тест бэкфилла DE); формы рендерят инпут на каждую
  `active_locale`; **адаптер U-A (UA1-3) читает `*_i18n` для ВСЕХ 5 kind единообразно** (снимает i18n-асимметрию
  UC2-4); демо двуязычно (де-факто — на включённых локалях).
- **Тесты:** модельные (i18n Service/Stay + бэкфилл), `apps/booking/tests`, `apps/stays/tests`, seed-smoke.
- ⚠️ **Синхронизировать с UA1-3:** L3 должен смёржиться до/вместе с UA1-3, иначе адаптер печёт DE-only (P1).

### L4 — Хром витрины+кабинета + письма + `.po/.mo` · M · без миграции
Обернуть строки хрома **витрины И кабинета/админки** в `{% trans %}`/`gettext`; `makemessages` (de/en + процесс
добавления локали) → заполнить `.po` → `compilemessages` → `.mo`. Письма — локаль-aware (по локали
получателя/заказа): либо `{% trans %}` в шаблоне под `override(locale)`, либо per-locale-варианты.
- **Файлы:** `templates/storefront/*` + кабинет/дашборд-шаблоны (`{% trans %}`), `apps/*/emails/*` +
  места отправки (`translation.override`), `locale/<lang>/LC_MESSAGES/*.po/.mo`.
- **Критерии:** на EN-витрине хром на EN (не немецкий); кабинет владельца локализуется; письмо приходит на локали
  адресата; добавление 3-й локали = добавить `.po/.mo` (без правки шаблонов); CI гоняет `compilemessages`.
- **Тесты:** `apps/core/tests/test_i18n_chrome.py` (рендер под `override('en')` не содержит немецких маркеров);
  письмо под локалью.
- ⚠️ **CI:** добавить шаг `compilemessages` (иначе `.mo` пусты в контейнере).

### L5 — Правовое мультиязычное + AGB · M · **МИГРАЦИЯ** (сходится с E-2/P3)
`impressum/privacy_policy/withdrawal_policy` (`tenants/models.py:116-118`) + **новое `agb`** → i18n (JSONField
`{locale:text}` ∥ отдельная i18n-модель — под-решение S-2). Автоген EN(и N)-шаблонов правового (каркас DSGVO
одинаков, меняется язык). Засев правового в демо. Маршрут `/agb/` + футер-ссылка. **Совмещается с E-2 (P3):**
AGB-поле/маршрут/засев — общий инкремент.
- **Файлы:** `apps/tenants/models.py`+миграция (i18n legal + agb), `apps/tenants/legal.py` (автоген),
  `config/urls_tenant.py` (`/agb/`), `templates/storefront/legal_*` + футер, seed.
- **Критерии:** правовое отдаётся на `active_locale` (фолбэк дефолт); AGB-страница+ссылка; демо засеяно на
  включённых локалях (не placeholder); §312j-кнопка/PAngV — из E-2.
- **Тесты:** `apps/tenants/tests/test_legal_i18n.py` (правовое per-locale + AGB-маршрут + засев).

### L6 — *(опц., отложено)* Язык в URL · L · миграция возможна
`/<locale>/…`-префиксы (`i18n_patterns` ∥ кастомный middleware) + hreflang/canonical, генерик по `active_locales`.
SEO-слой; расходится с текущей маршрутизацией → отдельно, по запросу.
- **Критерии (если делаем):** префикс сохраняет локаль в URL; hreflang на все `active_locales`; canonical; редирект
  дефолта; не ломает субдомены тенантов/публичный домен.

## 5. Последовательность + пересечение с U-A
```
L1 → L2            ─── ДО кода U-A ───           (рантайм-локали + кабинет; без миграции)
L1 → L3 ───────────── ∥ U-A (мёрж до/с UA1-3) ── (i18n Service/Stay + миграция → адаптер locale-clean)
L4 ── ∥/после U-C (хром стабилен)
L5 ── с E-2 (U-C, правовое)
L6 ── опц., последним
```
**Пересечение с U-A (несущее):** UA1-3 адаптер декларирует `title_i18n`/`description_i18n`; **L3 даёт эти поля
Service/Stay** → адаптер читает i18n единообразно для 5 kind, **UC2-4 инлайн-диспетчер теряет спец-случай
«service — плоские строки, fail-closed»** (i18n-асимметрия исчезает). Без L3 к U-A — рефактор адаптера позже (P1).
**Пересечение с E-2 (P3):** L5 (правовое i18n) и E-2 (AGB/§312j/PAngV засев) — общий инкремент в U-C.
Публичный домен (агрегатор/онбординг) — переключатель добавить в L1/L4 (сейчас нет, `urls_public.py`).

## 6. Риски
1. **L3 — крит. зависимость U-A по времени.** i18n-поля Service/Stay должны смёржиться до/с UA1-3; иначе адаптер
   печёт DE-only → рефактор адаптера+инлайна+шаблонов. Гейт: L3 в том же батче, что UA1-3.
2. **Миграции на tenant-схемах** (L3 Service/Stay, L5 legal): бэкфилл DE-строк в `{de:…}` без потерь;
   `./scripts/deploy.sh single`, локально `--create-db`.
3. **`.po/.mo` в CI** (L4): без `compilemessages` в контейнере `{% trans %}` покажет исходник — добавить CI-шаг.
4. **N-locale, не хардкод 2:** все новые места (виджет форм, оверлей, переключатель, hreflang) итерируют
   `active_locales`, НЕ `["de","en"]` — иначе добавление 3-й локали потребует правок кода (цель владельца — «добавлять
   языки в процессе» без кода).
5. **Оверлей vs модельный i18n:** витрина-контент из `site_config` идёт через `localize`-оверлей; модельный
   (Product/Service) — через `get_i18n`. Не смешать; оба питаются одним `active_locales`.
6. **Кабинет/админка локаль ≠ витрина локаль** (владелец правит на DE, посетитель смотрит FR) — два независимых
   источника локали; не связывать.

## 7. Под-решения (✅ РЕШЕНО владельцем 2026-07-01)
- **S-1 — язык кабинета/админки: ✅ (a)** кабинет владельца ТОЖЕ мультиязычный → **L4 оборачивает в
  `{% trans %}` хром витрины И кабинета/админки**; язык кабинета — независимый источник (Django-locale
  владельца ≠ locale посетителя).
- **S-2 — правовое i18n (L5): ✅ (b) отдельная модель `LegalDoc(tenant, kind, locale, text)`** (не
  JSONField на Tenant). Гибче для версий/аудита. Влияние на L5: **новая модель + миграция + админка/кабинет
  CRUD**, крупнее исходной оценки; правовое отдаётся per-locale через `LegalDoc` (фолбэк на дефолт), автоген
  N-локалей каркаса, засев в демо. Сходится с E-2 (§312j/PAngV/AGB-маршрут) — но AGB теперь ещё и `kind` в
  `LegalDoc`, а не поле Tenant.
- **S-3 — стартовый набор языков: ✅ оставить DE+EN**, добавлять по запросу. Реестр `settings.LANGUAGES`
  сейчас не расширяем → L3/L5-засев и `.po` (L4) — только DE+EN. Архитектура N-locale готова: добавить локаль
  = добавить в `settings.LANGUAGES` (+`.po/.mo` + засев), без правки кода.

## 8. Верификация Волны L (end-to-end)
- `uv run ruff check .` + `ruff format --check`; `uv run pytest apps/tenants apps/core apps/booking apps/stays
  apps/catalog apps/events apps/promotions -k "locale or i18n or language or legal or chrome" --create-db` (L3/L5 — миграции).
- `uv run python manage.py makemessages -l de -l en` (без новых непереведённых) + `compilemessages` (L4).
- Браузер: `seed_demo_tenants --recreate`; кабинет «Sprachen» — включить 3-ю локаль, задать дефолт; витрина —
  переключатель показывает N языков, контент/хром/правовое на выбранной локали; Service/Stay-деталь двуязычна;
  письмо на локали адресата; публичный домен — переключатель.
- CI зелёный (вкл. `compilemessages`); чекпоинт с владельцем (S-1/S-2/S-3).

## 9. Связанные
`docs/unified-sellable-entity-priority-review-2026-07-01.md` (PR-1/PR-3 — приоритет/зависимость) ·
`docs/archetype-completeness-audit-2026-06-30.md §6.4` (исходный L1-L6) · `docs/market-gap-synthesis-2026-06-30.md`
(E-6) · `docs/unified-sellable-entity-ua-plan-2026-06-30.md` (UA1-3 адаптер — L3 снимает i18n-асимметрию) ·
`docs/unified-sellable-entity-uc-plan-2026-06-30.md` (UC2-4 fail-closed → снят L3; E-2 правовое → L5) ·
`apps/core/models.py` (`I18nMixin`) · `apps/tenants/models.py` (`enabled_locales`/`default_locale`/legal) ·
`apps/tenants/siteconfig.py` (`localize`/`OVERLAY_LOCALES`) · `apps/promotions/public_views.py` (`set_language`).

## 10. Статус и остаток (по аудиту 2026-07-01)

> Верифицировано против кода (`docs/audit-2026-07-01.md §1.1/§5`). **Сделано:** L1 ✅, L2 ✅,
> L3-модель ✅ (с отклонением), L3c-рендер ✅. **Остаток:**

| ID | Статус | Остаток / что доделать | Размер |
|---|---|---|:--:|
| **L1** | done_with_deviation | `overlay_locales()` сделан tenant-free (реестр минус базовая), а не «от тенанта» (§4). Осознанно. Публичный домен (`urls_public.py`) — переключателя нет (отложено на L4, явно не зафиксировано). | — |
| **L3-модель** | done_with_deviation | **Overlay-семантика** (база в плоских `name`/`description`, `*_i18n` — только неосновные локали) вместо планового «бэкфилл `{de:…}`». ⚠️ **§4 L3 этого плана НЕ актуализирован** — поправить формулировку. | S (доки) |
| **L3-остаток** | not_started | (1) per-locale инпут-виджет форм (N колонок по `active_locales`) — `catalog/forms.py` хардкод пар `de/en`, у `Service`/`StayUnit` форм i18n нет; (2) мультиязычный демо-засев — EN только у `pranasy`, `demo_kits.py` не пишет `name_i18n`/`description_i18n`. | M |
| **combo i18n** | not_started | 5-й kind адаптера `SellableEntity` без i18n (`catalog.Combo` без `*_i18n`) → «i18n для 5 kind» = 4/5. Сходится с U-A. | S |
| **L4** | not_started | Хром в `{% trans %}` уже частично есть, но с **английскими** `msgid` при пустых `.po/.mo` → DE-посетитель видит EN-хром. Нужны `.po/.mo` + `compilemessages` в CI + локаль-aware письма. ⚠️ §1 таблица статуса «хром не в trans» устарела. | M |
| **L5** | not_started | Модель `LegalDoc` (S-2b) + `/agb/` + i18n правового + засев (сейчас placeholder). **Сходится с E-2** (§312j/PAngV/AGB) — общий инкремент в U-C. | M (миграция) |
| **L6** | not_started | URL-локаль — опц., по плану отложено. | L |

> Привязка к очереди волн — `unified-sellable-entity-master-track-2026-06-30.md §7.0`.
