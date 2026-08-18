# MEN-24 — прайс-виды: маркировка, «сетка 2–4», кап строк, каталог во всю ширину (2026-08-18)

Фидбэк владельца (скриншоты главной и /sortiment/ демо catering):
«добавим в каждый вид настройки вывода пиктограмок с диетами и аллергенами ·
переключение на вид с сеткой по 2–4 · в вид списка кнопку "показать ещё" с
переходом в меню + настройку в админке сколько строк (сейчас 3) · на странице
ассортимента товары по ширине и переключатели видов рядом с сортировкой».

Разведка: 3 Explore-агента (реестры food, тулбар/carry каталога, секция/контролы
билдера). Ключевые факты — в тексте по месту.

## A. MEN-24a — маркировка в прайс-строках

- `food.py`: диеты уже с эмодзи (`diet_badges`); аллергены без иконок → поднимаем
  позиционный буквенный маппинг `_allergen_letters()` из `pdf.py:25` в
  `food.py::allergen_letters()` (a..n, порядок реестра) — витрина и PDF дают
  одинаковые сноски; `pdf.py` — тонкий импорт.
- Ключ `menu_labels` (bool, presence-minimal, дефолт ВЫКЛ) — normalize рядом с
  `menu_show_prices` (siteconfig.py:2760). Чтение — НЕ `site.*` (на /sortiment/
  `site` в контексте нет — ловушка из разведки): тег
  `siteui.menu_labels_active` (takes_context, паттерн `speisekarte_pdf_available`
  siteui.py:537 — гейт FOOD_BUSINESS_TYPES + fail-closed try/except).
- Рендер `_price_list.html`: в ОБЕИХ ветках строки — эмодзи диет
  (`<span title>{{ d.icon }}</span>`, паттерн `_product_card.html:153`) + буквы
  аллергенов суперскриптом (text-[10px] text-gray-400, title=полные метки).
  Легенда встреченных букв под контейнером — тег `allergen_legend(groups)`
  (формат `a = Glutenhaltiges Getreide · …`, как pdf.py:131).
- Кабинет: чекбокс на экране «Pages» под существующим сентинелом `cl_present`
  (site_pages.html:23; POST-ветка core/views.py:2671), показывается только
  FOOD-типам.
- Демо: catering/restaurant — `config_patch={"menu_labels": True}` (top-level,
  прецедент catalog_layout у catering).

## B. MEN-24b — 4-е состояние «сетка 2–4» (class-swap, главная)

- Кнопка `data-plv-btn="grid"` в `_price_view_toggle.html`; скрипт: whitelist
  строка 182 += "grid"; классы групп — читать `data-gcls-<view>` с фолбэком на
  stack (вместо тернара cols/stack).
- `_price_list.html:28`: `data-cls-grid="max-w-none"` + `data-gcls-grid=""`
  (⚠️ НЕ между `data-price-list` и `data-pl-style` — негативные замки).
- Вёрстка карточек — ЧИСТО CSS-каскадом под `[data-plv="grid"]` (прецеденты
  `[data-galv="gross"]` и `.is-list` в app.css): группы grid 2/md:3/xl:4,
  заголовок col-span-1/-1, строка → колонка-карточка (border-b→0, radius, pad),
  `.plv-img` w-full h-32, распорка `span.flex-1` скрыта. Мобайл = 2 колонки
  (замок «мобильный ≤2»).

## C. MEN-24c — кап строк секции + «Показать ещё»

- `price_list_groups(limit=40, rows=0)` (siteui.py:492): rows>0 → срез
  `items[:rows]` + флаг `g.more`; запрос при rows>0 расширяется (limit=200),
  иначе 40 не хватает «по 3 в каждой из многих групп».
- Ключ секции `rows` (products-only, presence-minimal, clamp 1..20) —
  `_section_entry` рядом с limit (siteconfig.py:2196); geттер рядом с
  `section_limit`. 6 точек: normalize · POST-свип `rows_products`
  (core/views.py:1473) · контекст панели (:1864) · input в site_home.html:484
  (data-expert) · live-draft JS :2049 + серверный draft-whitelist :2328 ·
  витрина `{% price_list_groups rows=... %}`.
- Кнопка: НЕ плодим третью — существующая «Ganze Speisekarte» (:27-30
  _products.html) при обрезке меняет подпись на «Mehr anzeigen →» (тот же URL
  /sortiment/). Замок test_price_list.py:102 правится осознанно.
- Демо: `DemoKit.section_rows: dict` рядом с section_styles (:277), цикл
  9329-9339 доклеивает; CATERING `{"products": 3}`.

## D. MEN-24d — каталог: полная ширина + серверный переключатель у сортировки

Решение: на СТРАНИЦЕ каталога посетительский вид — GET `?ansicht=<preset>`
с серверным ре-рендером (работает при ЛЮБОМ стиле владельца, вкл. karte/buch;
сорт/фильтры и так перезагружают страницу). Class-swap MEN-22 остаётся только
на главной; каталожный `data-plv`-режим выключается (замок
test_catalog_page_toggle_uses_catalog_key переписывается осознанно).

- Оверрайд: public_views.py между :660 и :661 — `normalize_layout({...,"preset":
  ansicht}, default=выбор владельца, extra_presets=PAGE_EXTRA_PRESETS)` —
  мусор → вид владельца; затем пересчёт catalog_grid. Значения ссылок: 4 вида —
  `preisliste` (список) · `preisliste_foto` · `preisliste_foto_2sp` (2 колонки) ·
  `cols3` (карточная сетка 2–4 — штатная грид-ветка).
- Carry: `_facets["ansicht"]` только при отличии от владельческого (пустое
  `_carry_qs` отбрасывает) + `filter_form_hidden`; ручные ссылки products.html
  (:43,:48,:63,:76,:79,:86,:181) получают `{% if ansicht %}&ansicht=…{% endif %}`;
  «Reset filters» вид сохраняет. Для ссылок самого переключателя — отдельный
  `ansicht_base_qs` (carry БЕЗ ansicht).
- Партиал `_price_view_links.html`: иконки-ссылки `data-ansicht="<preset>"`
  (НЕ data-plv-btn — их перехватывает preventDefault; НЕ data-grid-view — замок),
  aria-current у активного. Рендер в `listing_bar_view` products.html в ОБЕИХ
  ветках (грид + прайс); мобильный «список/плитка» (_grid_view) в грид-ветке
  остаётся (замок test_grid_view).
- Тулбар: в listing.html [сорт-форма]+[listing_bar_view] оборачиваются одним
  `ml-auto flex items-center gap-2`, у формы ml-auto снимается (двойной ml-auto
  сейчас делит свободное место — разведка §1). Порядок sort < view цел
  (test_listing_parity).
- Ширина: include-параметр `pl_page=1` у _price_list на каталоге → базовые
  max-w-2xl → max-w-none И отключение plv-атрибутов (class-swap там больше не
  нужен); buch (max-w-4xl) не трогаем — «книга» шире теряет разворот.

## Порядок и гейты

A → B → C → D одним батчем на ветке `claude/goodkarma-catering-analysis-fea071`;
локальные гейты: test_price_list / test_listing_bar / test_listing_parity /
test_grid_view / test_menu_pdf / test_demo_kits(catering) / golden; i18n_gap;
`npm run build:css` ПОСЛЕДНИМ; стенд Playwright на демо catering (маркировка,
grid-вид, кап 3 + кнопка, каталог: ширина+виды у сортировки при karte);
push → CI → FF-merge. Новые msgid ×5 .po (чекбокс, «Mehr anzeigen», подписи
кнопок вида).
