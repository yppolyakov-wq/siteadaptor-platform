# FB-27 R4 — настройки типа страницы в «Seitenaufbau» + снос «Seitenvorlagen»

Дата: 2026-11-11. Основание — `fb27-seitenaufbau-impl-plan-2026-11-11.md` §C (R4), §D;
разведка кода (Explore) — в этом документе §1. Решения владельца: «Seitenvorlagen убрать
сразу», «основной список = блок „Hauptliste“ (вкладки „Darstellung“ нет)», развилки — «по
рекомендации».

## 1. Что показала разведка

- **Пакетной записи настроек нет.** `page_settings.write` — одна настройка = одна транзакция;
  «на все списки» — цикл из нескольких `write`. Черновик `aufbau_draft` хранит только блоки.
- **`schema()` читает только сохранённый конфиг** (`tenant.site_config`) — панели нужен черновик.
- **Не у каждого типа с настройками есть строка в «Seitenaufbau».** `structure_types` берёт
  типы с `block_host`, по одному на хост:
  - `category` — делит хост с `catalog` (настройки `category_page_style`, `catalog_subcats`);
  - `promos`, `promo_group`, `promo` — без `block_host` (6 настроек акций);
  - `legal` — без блоков (только `text_width`).
- **Большинство настроек — общие ключи сайта**, показанные на нескольких типах:
  `product_card_form` (≈13 типов), `text_width` (≈17), `catalog_layout/sort/filters`
  (каталог + категория), `promo_index_layout` (обзор + группа).
- **Типы без маркера основного списка**: `home` (баннер `home_hero`), детали
  (`*_detail_layout`, `product_related`), корзина (`cart_upsell`), текстовые (`text_width`).
- `?tpl=` в превью сильнее `?aufbau=` и черновик игнорирует.
- Точки `reverse` на «Seitenvorlagen»: `page_templates.cabinet_url` (→ сводки Студии,
  `assistant_actions._page_url`), `setup_assistant` ×3, `assistant_actions.PAGE_SETTING`,
  `nav_registry` (пункт меню + описание), `view_perms`.
- В `page_templates.py` должны остаться `PLAN_LIMIT/PLAN_WINDOW/_setup_plan/setup_plan_for`.

## 2. Решения (по рекомендации)

| № | Вопрос | Решение |
|---|---|---|
| D1 | Где настройки типа без основного списка | Фикс-строка «Einstellungen der Seite» (`ref="__page"`) первой в схеме: у главной, деталей, корзины, текстовых. У типов со списком — те же настройки в панели «★ Hauptliste». |
| D2 | Акции | Тип `promos` получает строку в «Seitenaufbau» (хост `promos` уже есть и выводится). Настройки `promo_group` и `promo` — в той же панели, группами «Seite eines Aktionstyps» / «Aktionsseite». |
| D3 | Категория | Настройки `category` — в панели каталога группой «Kategorieseiten» (своя схема категории — R7). |
| D4 | Rechtstexte | Отдельной строки нет: `text_width` общий, правится на любой текстовой странице; 302 ведёт на `text`. |
| D5 | Общие ключи | Подпись «gilt für alle Seiten» у `product_card_form` и `text_width`. Значение общего ключа входит в отпечаток черновика (конфликт виден). |
| D6 | Живое превью плиток | v1 — без него: «Übernehmen» → черновик → «Vorschau» (`?aufbau=`). `?tpl=` остаётся в `page_settings` (помощник). |
| D7 | Запись | Одна транзакция в `aufbau_draft.commit`: блоки + настройки; `page_settings.apply_many` — общий помощник; кэш витрины сбрасывается. |

## 3. Срезы

- **R4a — сервис.** `page_settings.schema(tenant, types, config=None)`; `apply_many(cfg, pending,
  tenant, gate)` (валидация каждой настройки + `apply_override`); `write_many` поверх него.
  Замки: значение из черновика видно в `schema`; `apply_many` = последовательность `write`;
  мусор отклоняется целиком (ничего не записано).
- **R4b — черновик.** `draft["settings"] = {code: {"v":…, "o":…}}`; `_saved_state(…, type_code)`
  со снимком ключей типа; чтение старых черновиков через `.get`; `op="settings"`;
  `overlay`/`changes`/`commit`. Замки: до «Speichern» сайт прежний; «вернул как было» —
  черновика нет; старый черновик без `settings` не падает; конфликт по общему ключу.
- **R4c — панель.** `site_schema.settings_groups(tenant, code, config)`; строка `__page`;
  партиал настроек (плитки/радио/сетка — из `page_templates.html`); по форме на настройку,
  сентинел `out_mode`. Замок: **каждая настройка `schema()` каждого активного типа достижима
  из «Seitenaufbau»** (по всем 16 типам бизнеса).
- **R4d — снос.** `cabinet_url` и остальные `reverse` → `site-schema`; три вьюхи → 302 по карте;
  `_render` и `page_templates.html` удаляются; пункт меню снят, имена — в `EXPECTED_UNLISTED`;
  тесты экрана переписаны осознанно (список — в плане §D5 + `test_sidebar_st4b`,
  `test_stu19e_ownership`).

## 4. ECC-прогоны

- До кода: `django-patterns`, `django-tdd`, `accessibility` (загружены в сессии).
- R4a/b: `django-reviewer` + `security-reviewer` (запись настроек, права, превью).
- R4c: `a11y-architect` + стенд Playwright 1440/390.
- R4d: `django-reviewer` (редиректы, NoReverseMatch), обход экранов по 16 типам.
