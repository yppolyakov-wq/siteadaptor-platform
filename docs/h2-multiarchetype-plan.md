# H2 — Мультиархетип-композиция (план, 2026-06-30)

Источник правды этапа H2 (поверх `archetype-entities-plan.md`). Составлен по разведке
(workflow `h2-multiarchetype-recon`) + реальным данным `pranasy`. **Миграций НЕТ** — всё
в `site_config` JSON.

## Два дилеверабла (видение владельца)
- **D-MENU:** в мультиархетипе каждый активный архетип = пункт меню-«категория» →
  страница с **описанием + слайдером + товарами/услугами**.
- **D-HOME:** главная **агрегирует «главный» блок каждого архетипа**, авто-порядок по
  реестру (`_PRIORITY`), ручная перекомпоновка в билдере.

## Что УЖЕ есть (не переделывать) — подтверждено разведкой + pranasy
- `modules.storefront_archetypes(tenant)` — активные архетипы с label/blurb/icon/landing.
- `archetypes._PRIORITY` (events>stays>booking>catalog>promotions) + `PRIMARY_SECTION`
  (module→секция главной) + `primary_module/primary_section/primary_item`.
- **Обложки S3:** `site_config["archetypes"][key]{intro, hero_image, gallery}` уже хранят
  ОПИСАНИЕ (`intro`) + hero + **галерею-картинки** (pranasy: events 3 шт, catalog 4 шт) —
  это и есть источник описания+слайдера. Редактор — `sections_view`; рендер — `_archetype_cover.html`;
  инъекция — `context.py` `archetype_cover` по `url_name`→`archetype_by_landing`.
- **Меню:** `menu.py` `resolve_menu`/`_node_url` (узел `archetype` → landing-URL), билдер
  `menu_builder_view`/`site_menu.html`. pranasy: кастомные пункты Restaurant/Shop/Catering/Retreats.
- Лендинги сами рендерят свои ITEMS (product_list/termin_index/stays/events) — items НЕ трогаем.
- Пер-секционный конфиг (`normalize_sections` сохраняет доп-ключи) + `home_builder_view` order_*/enabled_*.

## Реальные пробелы (H2)
**D-HOME:** нет `aggregate_primary_sections` (главная включает ТОЛЬКО одну primary, и лишь
когда в конфиге нет `sections`); нет авто-порядка по реестру; нет связи секция↔архетип в
конфиге; нет авто-реконсиляции при вкл/выкл модуля; нет UI билдера «какие архетипы на главной».
**D-MENU:** меню-узлы только URL (без teaser-данных); нет страницы «описание+слайдер+items»
как единого блока; **нет компонента-СЛАЙДЕРА нигде** (gallery = статичный грид, нет `slides`);
меню не авто-сидится из активных архетипов.

## Порядок инкрементов (вертикальные срезы)
Сначала **D-HOME** (ценнее, без миграций/шаблонов), потом общий **слайдер**, потом **D-MENU**.

| # | Что | Миграция | Браузер |
|---|---|---|---|
| **H2-1** | `aggregate_primary_sections(tenant)` (резолвер по `_PRIORITY`, [{key,module,order}]) | нет | нет (CI) |
| **H2-2** | Вписать агрегацию в дефолт главной (заменить M20U-2: при отсутствии `sections` включить ВСЕ primary архетипов в порядке реестра; пометить секции `archetype`/`module`). **Гард: если `sections` есть — НЕ трогать.** | нет | нет (CI) |
| **H2-3** | Билдер: список секций с архетип-бейджем + чекбокс «включить» + тумблер «по реестру / вручную»; реконсиляция при вкл/выкл модуля | нет | **да** |
| **H2-4** | ~~Схема слайдера~~ — **ОТМЕНЕНО:** обложка уже хранит `gallery` (pranasy: events 3, catalog 4 картинки). Реюзим `gallery` как источник слайдера, новый `slides`-schema не нужен. | — | — |
| **H2-5** | ~~Редактор слайдера~~ — **ОТМЕНЕНО:** `gallery` уже редактируется в `sections_view` (cover-форма). | — | — |
| **H2-6 ✅** | Единая страница архетипа: `_archetype_cover` (описание) + **карусель из `gallery`** над ITEMS; вставить в stays/events/booking лендинги (products — эталон). Реюз существующего `gallery` обложки. | нет | **да** |
| **H2-7** | Меню: авто-сид из активных архетипов (порядок `_PRIORITY`) + rich-режим узла (link/card, depth≤2 → mega/side-panel), «Add all archetypes» в билдере | нет | **да** |
| **H2-8** | (опц.) пер-архетип hero на агрегированных блоках главной | нет | да |

## Риски (соблюдать)
- **H2-2 (наивысший риск):** авто-агрегировать ТОЛЬКО когда `raw["sections"]` отсутствует;
  НИКОГДА не переписывать уже скомпонованную владельцем главную. M20U-2-паритет для одного архетипа.
- **H2-4:** `slides` обязательно в allowlist `normalize`, иначе теряется на следующем save.
- **H2-7:** карточки меню не должны требовать 3-й уровень (`MENU_MAX_DEPTH=2`) → mega-menu/side-panel.
- **H2-3:** при тумблере модуля сохранять ручной выбор (carry-forward), авто-вставлять/убирать только свою primary.
- **Мобайл (H2-6/7):** слайдер и карточки-меню — явный small-screen путь (упрощённое превью/модалка).

## Связанные файлы
`apps/core/archetypes.py`, `apps/promotions/public_views.py` (storefront_home), `apps/tenants/storefront.py`,
`apps/tenants/menu.py`, `apps/tenants/siteconfig.py`, `apps/core/context.py`, `apps/core/views.py`
(home_builder_view/sections_view/menu_builder_view), `templates/storefront/_archetype_cover.html`,
`templates/storefront/home.html`, `templates/storefront/_base.html`, `templates/tenant/site_menu.html`.
