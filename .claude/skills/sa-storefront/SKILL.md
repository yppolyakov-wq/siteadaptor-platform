---
name: sa-storefront
description: Витрина siteadaptor-platform — продаваемая сущность и карточки, листинги и фасеты, детальные страницы, настройки сайта (site_config), кэш страниц, SEO и JSON-LD, работа без JS, ценовой слой акций. Грузить ДО кода при любой правке sellable.py, facets.py, card_forms.py, compositions.py, list_blocks.py, page_settings.py, detail_sections.py, seo.py, pagecache.py, siteconfig.py, price_layer.py, шаблонов templates/storefront/ и tailwind.config.js.
metadata:
  origin: project
---

# Витрина: сущность, карточки, листинги, детали, кэш, SEO, цена акции

Все единые точки — `docs/project-memory.md` §3; грабли целиком — `docs/pitfalls.md` §3 и §5;
маршруты витрины — `CLAUDE.md` §4. Здесь — что звать и на чём уже ошибались. Дата у грабли —
последнее срабатывание. Редактор страниц и окно блока — скилл `sa-block-editor`, не здесь.

## Когда грузить
До плана и до кода любой правки публичной витрины бизнеса: карточка, листинг, фильтр, детальная
страница, buy-box, ключ `site_config`, мета и JSON-LD, кэш главной, показ цены и скидки.

## Единые точки
**Продаваемая сущность и карточка:**
- контракт и адаптеры (товар, услуга, номер, событие, комбо) —
  `apps/core/sellable.py::SellableEntity, sellable_for, display_fields, SELLABLE_KINDS`;
  модели сущностей не сливаем, отличается только buy-box;
- карточка услуги/номера/события — `templates/storefront/_sellable_card.html` и тег
  `apps/core/templatetags/sellable_ui.py::sellable_card`; товар —
  `templates/storefront/_product_card.html`, комбо — `templates/storefront/_combo_card.html`;
- buy-box, диспатч по `purchase_mode` — `templates/storefront/_buybox.html`;
- форма карточки «объект → категория → сайт» —
  `apps/core/card_forms.py::card_form, forms_for_view, normalize_for_view, card_applies, own_form`
  (вид списка побеждает форму); тег — `apps/tenants/templatetags/siteui.py::card_form`;
- предзагрузка карточек товаров — `apps/catalog/prefetch.py::prefetch_cards`;
- адрес товара — `get_absolute_url` модели в `apps/catalog/models.py`.

**Листинги:**
- каркас всех листингов — `templates/storefront/listing.html`;
- фильтры, поиск, сортировка — `apps/core/facets.py::FacetProvider, provider_for, NullFacets`;
  акции — `apps/promotions/facets.py::PromoFacets`; ветка категории —
  `apps/catalog/facets.py::branch_ids`;
- шаблоны (композиции) страниц —
  `apps/core/compositions.py::SURFACES, LISTING_SURFACES, styles_for, valid_for, resolve`
  (стили категорий и групп акций — производные от него);
- оси листингов, Team, Galerie — `apps/core/listing_parts.py::effective, code_for`;
- блок «Liste» и встроенные списки —
  `apps/core/list_blocks.py::resolve_for, resolve_section, effective_view, apply_type_scope`;
- сетка: `apps/tenants/templatetags/siteui.py::sf_grid_attrs, grid_classes` — единственное
  место правила «раскладка владельца сильнее литерала».

**Детальные страницы:**
- реестр разделов (порядок, подписи, скрытие) —
  `apps/core/detail_sections.py::DetailSection, sections_for, flow_keys, in_place_keys`;
- разделы строками, якоря, неподвижные строки —
  `apps/core/detail_parts.py::flow, fixed_parts, flow_section_keys, PINNED, shared_host`;
- раскладка детали — `apps/tenants/siteconfig.py::detail_layout`.

**Настройки сайта:**
- нормализация и реестры `site_config` —
  `apps/tenants/siteconfig.py::normalize, PAGE_BLOCK_HOSTS, LIST_STYLES, OPTIONAL_PAGE_LAYOUTS,
  TRANSLATABLE_KEYS, split_translation, PAGE_WIDTH_CLASSES`;
- схема, проверка и запись одного ключа настроек страницы —
  `apps/core/page_settings.py::schema, validate, write, write_many, raw_config`;
- дизайны и сборки —
  `apps/tenants/sitetemplates.py::LOOK_FAMILIES, BUNDLES, templates_for, apply_look, apply_preview_bundle`;
- меню и подвал — `apps/tenants/menu.py::resolve_menu, resolve_footer, target_sets, target_options`;
- чернила на акцентном цвете — `apps/core/colors.py::ink_on`.

**Кэш страниц:** `apps/core/pagecache.py::cache_storefront_page, bump_storefront_cache,
cache_public_page`. Ключ — хост + схема + путь + язык + версия; мимо кэша — непустая сессия,
query-параметры, не-GET, ответ с CSRF-токеном или Set-Cookie, `response.no_store`. Сброс при
публикации — `bump_storefront_cache`. В тестах TTL 0 — кэш выключен.

**SEO, тексты, право:**
- JSON-LD — `apps/core/seo.py::entity_ld, offer_ld, localbusiness_ld, localbusiness_data,
  itemlist_ld, breadcrumb_ld, faqpage_ld`; поля сущности — из адаптера (`price_value`, `ld_extra`);
- мета title/description — `apps/core/seo_meta.py::resolve, render_template, DEFAULTS, clamp`;
- rich-text — `apps/core/richtext.py::sanitize, sanitize_page, editor_rules, to_plain`
  (`to_plain` — для фида, PDF и JSON-LD);
- правовые тексты — `apps/core/legal.py::legal_text, save_legal_doc`.

**Цена акции:** `apps/promotions/price_layer.py::promo_line_price, attach_promos,
promo_for_product, product_promo_map, promo_for_service, stay_promo, deal_counts` — «показано =
списано»; «акция в продаже» — `on_sale_q` в `apps/promotions/models.py`; показ цены и условий —
`templates/storefront/_discount_display.html`; § 11 PAngV —
`apps/catalog/price_history.py::lowest_price_30d_bulk`.

## Нельзя
- Заводить вторую карточку, второй buy-box, второй список видов/форм/сортировок или считать
  цену акции в шаблоне либо вьюхе мимо `price_layer`.
- Читать тип страницы витрины по пути — только штатным резолвером `config/urls_tenant.py`;
  пустой тип — «неизвестная страница», а не главная.
- Писать анониму в сессию ради плашек, тостов и счётчиков (кука и запись в Redis на каждого
  бота; ответ уходит мимо кэша) — localStorage и фрагмент.
- Класть в общий кэш персональное; ключ кэша — только через `pagecache`, сырой `get_host()` в
  ключ не брать.
- Класть Google-рейтинг в JSON-LD; закрывать от индекса через robots `Disallow` (он прячет от
  робота сам `noindex`) — `<meta>` и `X-Robots-Tag`.
- Писать многострочные `{# #}`; давать деталям кабинета голые имена классов (`.btn`, `.card`) —
  один `static/css/app.css` на кабинет, витрину, портал и Mini App.
- Показывать бейджи и счётчики ниже порога («Verkauft N» только ≥ 5; `stock=None` ≠ ноль);
  раскрывать содержимое mystery-акции в показе цены.
- Заводить второй слайдер (`templates/storefront/_slider_script.html`) и автопрокрутку по умолчанию.

## Грабли
Сущность и карточки:
- Правка адаптеров `SellableEntity` гейтится ВМЕСТЕ с `apps/tenants`: секции главной рендерят
  карточки через `SimpleNamespace`-стабы контракта; хелперы связей молча отдают пусто для
  несохранённых и стабов («сохранена ли» — `obj._state.adding`, не `pk`) · посл. 2026-10-24.
- Настоящий N+1 — карточки товаров на витрине; скорость — замером `CaptureQueriesContext`, замок
  «N и 3N строк» — с прогревом · посл. 2026-10-26.
- Перед сводом переплетённых шаблонов (карточки, buy-box, листинги) — паритет-замки ДО правок;
  партиал в паритетной разметке — БЕЗ конечного перевода строки, тег на своей строке сдвигает
  пробелы · посл. 2026-11-21.

Листинги и настройки:
- `normalize` выбрасывает неизвестные ключи `site_config`: новый ключ — сразу в normalize и в
  замок, иначе Save его стирает · посл. 2026-08-27.
- Снятый чекбокс не приходит: булев ключ требует сентинела `*_present`, иначе первый Save
  обнуляет выбор владельца · посл. 2026-09-09.
- Тег, которому нужен `site` (`grid_classes`), молча берёт дефолт, если вьюха не кладёт `site`
  в контекст; литерал `cols=` не должен побеждать раскладку владельца · посл. 2026-09-10.
- Настройка панели обязана действовать на странице, а действующая ось — быть предложена (два
  встречных замка); скрывая поле, проверять побочные эффекты значения · посл. 2026-11-19.

Детальные страницы и SEO:
- Раздел «на месте» — `in_place=True`; поток, вкладки и якоря читают `flow_section_keys`, а не
  `section_keys` · посл. 2026-11-19.
- `{{ block.super }}` гасит `VariableDoesNotExist` в пустой `<main>` с кодом 200 — значения
  для фильтров резолвить во вьюхе · посл. 2026-10-01.

Кэш страниц:
- Сверка «до == после» рендером идёт мимо кэша только с НЕПУСТОЙ сессией и хостом сайта (не
  `testserver`): ключ не зависит от `site_config`, в проде «после» отдало бы закэшированное
  «до», а в тестах TTL 0 дефект невидим · посл. 2026-11-18.
- Точечная запись конфига через `.update()` кэш не сбрасывает — `bump_storefront_cache` в
  on_commit · посл. 2026-11-01.

CSS и шаблоны:
- Новый Tailwind-класс → `npm run build:css` и закоммитить `static/css/app.css`; в свежем
  контейнере сначала `npm ci` (иначе сборка молча не идёт), проверять `grep -c` класса в
  собранном файле; замок свежести падает и при удалении классов · посл. 2026-11-20.
- Классы, собираемые в Python (сетки движка, `PAGE_WIDTH_CLASSES`, цвета плашек), и классы
  `@layer components` — в safelist `tailwind.config.js`, иначе выбор владельца молча падает в
  одну колонку · посл. 2026-10-30.
- Многострочный `{# #}` утекает текстом на страницу — гнать замок в каждом шаблонном батче
  · посл. 2026-09-04.
- `hidden` и display-класс Tailwind на одном элементе — элемент виден; `sr-only` в ленте без
  `relative` у карточки растягивает страницу (390 → 455 px) · посл. 2026-11-21.

Без JS и стенд:
- JS-фичу не принимать по curl или серверному тесту — только Playwright; данные в инлайн-JS —
  `json_script`, не `escapejs` · посл. 2026-08-03.
- Стенд: Django кэширует шаблоны и в DEBUG (рестарт runserver), curl без сессии грепает тело
  302, ждать только конечные анимации (слайдер крутится бесконечно) · посл. 2026-11-21.

## Что гейтить
- `uv run python scripts/preflight.py` (правка `apps/core` тянет `apps/tenants` сама);
  локально — `--reuse-db`.
- Контракт и карточки: `apps/core/tests/test_sellable.py`, `apps/core/tests/test_sellable_card.py`,
  `apps/tenants/tests/test_services_section.py`, `apps/catalog/tests/test_listing_parity.py`,
  `apps/core/tests/test_lay4_card_forms.py`, `apps/core/tests/test_axis_coverage.py`.
- Кэш, SEO, цена: `apps/core/tests/test_pagecache.py`, `apps/core/tests/test_entity_jsonld.py`,
  `apps/core/tests/test_seo_meta.py`, `apps/promotions/tests/test_price_layer_storefront.py`.
- Шаблоны: `apps/core/tests/test_template_comments.py`,
  `apps/core/tests/test_frame_escape_links.py`, `apps/tenants/tests/test_template_sweep.py`,
  `uv run python scripts/i18n_quickcheck.py`; хук `.githooks/pre-commit` пересобирает CSS.
- Вёрстка и JS — стенд Python-Playwright 1440/390, de/ru; мерить `documentElement.scrollWidth`.

## Агенты ECC
`django-reviewer` — каждый срез; `seo-specialist` — мета, JSON-LD, robots; `e2e-runner` — JS и
вёрстка витрины; `a11y-architect` — новые элементы; `database-reviewer` — выборки листингов и
N+1; `silent-failure-hunter` — цена акции и кэш; `security-reviewer` — ввод, rich-text, фильтры.
