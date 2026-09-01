# Волна DL «5 Look'ов акционного сайта + переключатель шаблонов» — план (2026-09-01)

Отмашка владельца: «внедряй все 5 и текущий, и текущий довести до ума; сделай
переключатель шаблонов» + дополнение «проверь, чтоб новые шаблоны подходили под
другие страницы (ассортимент, товар, отзывы, о нас, технические) — если нет
шаблонов, доделай».

Источник дизайна — утверждённый канвас «Sparfuchs Aktionsmarkt Redesign»
(артефакт 80e8e43b…, 30 артбордов: 5 вариантов × 3 страницы × десктоп+мобайл).
Разведка: 4 Explore-агента (Look-механика · промо-поверхности · кит aktionsmarkt ·
второстепенные страницы), ключевые факты сверены по file:line.

## 0. Маппинг «вариант → платформа»

| Вариант | Look-ключ | Label | Шрифт (head) | Фон/чернила | Акцент (grocery) | Хром карточек | theme |
|---|---|---|---|---|---|---|---|
| V1 Prospekt-Pop | `prospekt` | Prospekt | Barlow Condensed | #ffffff / #171717 | #dc2626 (+жёлтые стикеры) | `hard` (рамка 2px + жёсткая тень) | "" |
| V2 Frischmarkt | `frisch` | Frischmarkt | Bricolage Grotesque | #faf6ef / #26301e | #2e6b3c | мягкий (radius 20, тень) | "" |
| V3 Nachtmarkt | `neon` | Nachtmarkt | Space Grotesk | #0e1013 / #e8eaed | #c8f542 | тонкая рамка на тёмном | `dark` |
| V4 Markthalle | `blatt` | Markthalle | Playfair (реюз DS-1) + Karla body | #f7f5f0 / #191817 | #b3202c | `hairline` (1px, без тени, radius 0) | "" |
| V5 Marktplatz | `smart` | Marktplatz | Schibsted Grotesk | #f4f6f9 / #101828 | #1d4ed8 | тонкая рамка, radius 12 | "" |

Текущий вид (klar + fokus_angebote) остаётся шестым выбором и полируется (DL-4).

Идентичность варианта раскладывается на оси, которые УЖЕ есть: Look-семейство
(шрифт/типографика/site_defaults/nav_style/hero_style/theme, `sitetemplates.py:205-285`)
+ сборка-Startpaket (`BUNDLES`, оси `_apply_bundle_axes` :797-837) + стили секций
(`SECTION_STYLES`) + `--sf-*`-каскад (`_base.html:52-64,86`). Новая ось — только
«хром карточек» (§2).

## 1. DL-1 Шрифты (self-hosted, прецедент DS-1/2)

Файлы уже скачаны (woff2, latin+latin-ext, суммарно ~168 КБ):
Barlow Condensed 700 · Bricolage Grotesque 700 · Space Grotesk 700 ·
Schibsted Grotesk 700 · Karla 700. Все OFL (провенанс — в `static/fonts/SOURCES.md`).

- `static/fonts/*.woff2` + `@font-face` в `static/src/app.css` (блоки как у Playfair,
  `font-display: swap`, `unicode-range` per-subset; ленивость = «семейство не
  упомянуто — не грузится»).
- `siteconfig.FONTS` (:1737-1752) += 4 ключа: `markant` (Barlow Condensed head),
  `frischtyp`→имя решу по коду `font_stacks()` (Bricolage head), `tech` (Space
  Grotesk head), `sachlich` (Schibsted head); V4 — новый ключ `zeitung`
  (Playfair head + Karla body) ЛИБО реюз `editorial`, если `font_stacks()` не
  разделяет body/head — решение по факту чтения кода.
- **Починка существующей дыры**: `font_options` в `apps/core/views.py:2309-2313`
  не знает даже `editorial`/`organic` → пересохранение типографики сбрасывает
  DS-Look'и. Добавляю ВСЕ ключи FONTS в селект.
- Кириллица: у 4 новых face нет кириллических сабсетов на GF → честные
  фолбэк-стеки (как в макетах); Playfair-кириллица уже есть.
- `npm run build:css` в том же коммите (CI-замок свежести).

## 2. DL-2 Look-семейства ×5 + ось «хром карточек»

- `LOOK_FAMILIES` += 5 записей (полный набор ключей — `_apply` читает их без
  гардов: font/typography/site_defaults/nav_style/hero_style/theme).
- `ARCHETYPE_LOOK_ACCENTS`: все 15 кортежей 5→10 колонок (порядок = порядок
  семейств; подбираю по 5 гармоничных hex на архетип в характере каждого
  семейства). Замки `test_looks.py:20-34` (`==5`, список ключей) переписываются
  ОСОЗНАННО на 10.
- **Новая ось** `site_defaults.card_chrome` ∈ ("hard","hairline","line") —
  presence-minimal в `normalize_site_defaults` (голдены целы: ключ появляется
  только заданным). Эмиссия: пара `--sf-bw`/`--sf-bc` (+вариант тени) на `<body>`
  рядом с `--sf-r/sh/bg/pad` (`_base.html:86`), потребление — правила при
  `[style*="--sf-bw"]` на `.sf-card`/`.cb-box` (паттерн :52-64 сохранён; имена
  выбираю без префикс-коллизий — урок `--sf-r`≠`--sf-rest`).
- `theme="dark"` у `neon` — механика ST-1a готова (посетительский тумблер сильнее).
- **Обязательные починки до/вместе с этим инкрементом** (иначе новые Look'и
  ломаются первым Save):
  - `apps/core/views.py:1810-1825` — билдер-Save пересобирает `site_defaults` из
    подмножества и ДРОПАЕТ `page_bg`/`hero_widget` (и уронил бы `card_chrome`).
    Лечение класса W0/W6: presence-preserve непредставленных ключей + hidden/контролы.
  - `site_home.html:189` `data-look` JSON не несёт `page_bg`/`card_style` →
    живой клик по Look в билдере не красит фон. Расширяю payload + JS.
- Замок волны: 10 Look'ов apply→normalize идемпотентны (расширение test_looks),
  golden-эталоны normalize НЕ трогаются.

## 3. DL-3 Сборки ×5 + переключатель

- `BUNDLES` += 5 записей с СОБСТВЕННЫМИ label (Prospekt/Frischmarkt/Nachtmarkt/
  Markthalle/Marktplatz), `look` = свой ключ семейства, universal (видны всем
  типам — это полноценные шаблоны сайта). Замки `test_bundles.py:68-76`
  («ровно 1 сборка у отеля» и т.п.) переписываются осознанно: мир изменился —
  сборок стало 6 на тип.
- Состав (оси уже существуют): `hero_style` (split у prospekt/frisch/neon/blatt,
  plain у smart), `nav_cta`, `nav_style` (blatt=centered), `card_style`,
  `section_styles`, `sections_on/off`, `catalog_layout`.
- **SECTION_STYLES["promotions"]** (оси не было — точка врезки): += `spotlight`
  (первая акция крупной featured-карточкой + полоса «Endet bald» при
  ends_at≤3д + грид) и `rows` (компактные строки V5 с процентом-героем).
  Рендер в `sections/_promotions.html` ветками; "" = байт-в-байт прежний грид
  (характеризационный замок ДО правки).
- **Оси сборки расширяю**: `page_presets` ({host: preset_id} через готовый
  `apply_page_preset`) — сборка красит и «О нас»/корзину/контакт (ST-2), не
  только главную. `listing`-раскладки уже покрыты `catalog_layout`.
- **Переключатель**:
  - мастер «Stil»: карточки сборок получают такие же ленивые scaled-iframe
    превью, как Look-карточки (`_step_stil.html:14-25` ← :57-60);
  - stateless-превью `apps/core/context.py:204-224` учится `&bundle=<key>`
    (поверх look-оверлея — `apply_bundle_config` на нормализованном cfg,
    re-derive `nav_style`); по-прежнему read-only (замок test_looks:142-151
    расширяется);
  - область «✨ Look» билдера: серверные кнопки `use_bundle:` уже есть —
    добавляю 5 карточек с мини-превью.
- Применение в 1 клик: `apply_bundle` (look → axes → save) — готов.

## 4. DL-4 Текущий вид aktionsmarkt «до ума»

- Кит остаётся `klar + fokus_angebote` (дефолт не меняю — переключатель даёт
  остальные пять).
- Латентный баг сидинга: `hero_widget="aktionsmarkt"` затирается сборкой
  (`_FOKUS_BASE.hero_widget="none"` на шаге 7 против шага 6;
  `demo_kits.py:11229-11236`) — комментарий кита врёт. Чиню: `config_patch`
  кита восстанавливает `site_defaults.hero_widget` (шаг 8 мерджит dict'ы
  поkey-но) ЛИБО убираю поле и комментарий, если по факту виджет-слот сплит-hero
  не поддерживает грид плиток — по коду `_hero_widget.html` (ветки нет —
  проверить else-ветку hero_tiles).
- Главная кита переходит на `promotions: spotlight` (featured-дил + Endet-bald
  полоса) — это «довести до ума» из макетов без смены идентичности.
- Деталь акции/карточки уже полированы прошлыми волнами (07-29/30, SF-2/3/4) —
  не трогаю, паритет-замки целы.

## 5. DL-6 Охват ВСЕХ страниц (требование владельца)

По карте разведки второстепенных страниц (агент, отчёт в tasks/):
- страницы с захардкоженными `bg-white`/`text-gray-*`/hex, ломающими тёмный
  `neon` и кастомные фоны, переводятся на токены/`.dark`-пары (прецедент SF-1);
- сборкам добавляются `page_presets` для info («О нас»)/cart/contact;
  правовые страницы/404/410/подтверждения — только токены (пресеты не нужны);
- листинги: /sortiment/ через `catalog_layout`; /aktionen/ и деталь — стили из
  DL-3; отзывы/галерея/команда (ST-8) — токены + существующие SECTION_STYLES.
- Гейт: Playwright-матрица «6 шаблонов (5 новых + текущий) × маршруты
  (главная, /aktionen/, деталь акции, /sortiment/, деталь товара, /bewertungen/,
  /galerie/, /ueber-uns/, /warenkorb/, чекаут, подтверждение, право ×4,
  Merkliste, 404/410) × (1440, 390)» — скриншот-прогон на сиде, ручной просмотр
  тёмного и бумажного.

## 6. Порядок и правила

DL-1 → DL-2 → DL-3 → DL-4 → DL-6 → DL-5 (кит/стенд/доки). Ветка
`claude/aktionsmarkt-analysis-45t2vu`, батч-режим: локальный гейт (ruff+pytest
затронутых модулей+i18n_quickcheck+template_comments+build:css) → пуш → зелёный
CI → FF-мерж в main (правило владельца). Все новые владельческие строки —
gettext + 5 .po. Без миграций (вся волна — site_config/реестры/статика).

## 7. Границы v1 / отложено

- Проценты скидок по-прежнему считаются от `compare_at_price`; выравнивание с
  30-Tage-Bestpreis (EuGH Aldi, § 11 PAngV) — отдельное решение владельца
  (озвучено в чате 2026-09-01), в эту волну не входит.
- «Preisverlauf»-спарклайн V5 на детали товара/акции (данные PriceLog есть) —
  кандидат отдельного инкремента после волны: требует своего среза данных на
  детали; в v1 смарт-Look живёт без графика.
- Групповые плитки V1-главной («ленты групп») — через существующие категории
  compact; отдельная секция групп акций — по спросу.
- SMS/прочее вне темы.

## 8. DL-7 Фидбэк-батч владельца (2026-09-01, скриншот канвы)

Диагностика стендом (Playwright, логин демо-владельцем): клик по Look-карточке
Studio перекрашивает канву (chrome=hard, Barlow), POST `use_bundle:` применяет и
сохраняет — механика жива. Реальные причины фидбэка: (а) в области «⚡ Start»
Studio и на слайде «Stil» галерея из ВСЕХ ~14 легаси Layout-Vorlagen чужих
отраслей — «посторонние шаблоны», и их Apply меняет раскладку секций, не тему;
(б) выбор темы живёт только внутри Studio.

- **DL-7a** `templates_for` → рекомендованные типу + универсальные (пустой
  recommended_for); чужие отраслевые пресеты из Studio/мастера уходят.
- **DL-7b** НОВАЯ страница кабинета `/dashboard/design/` — «Design & Vorlagen»:
  карточки сборок (bundles_for, ленивые scaled-iframe `?preview=1&look&bundle`)
  + Look'и (looks_for) + вход в Studio; применение POST'ом (apply_bundle/
  apply_look — сохранение сразу, без зависимости от Save канвы). Подпункт
  «Design» якоря Website (nav_registry, hub site — прецедент SM-4; палитра
  даром). Чек-лист cabinet-screen-dod соблюдён.
- **DL-7c** выравнивание spotlight-грида: большая карточка растягивается на
  высоту двух правых рядов (CSS-каскад `[data-promo-spotlight]` — flex-колонка,
  фото flex-1 вместо aspect-square; шаблон карточки не трогаем).
- **DL-7d** варианты отображения промо-блока: SECTION_STYLES["promotions"] +=
  "banner" (первая акция широкой горизонтальной картой, остальные сеткой);
  итого 4 вида: сетка "" · Deal der Woche groß · Kompakte Zeilen · Banner;
  переключение — инспектором секции в Studio и со страницы Design не уводим
  (вид секции — на канве, как решено UC2).
