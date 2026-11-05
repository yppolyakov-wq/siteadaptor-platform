# План: главная портала города — вариант A «Heute in Solingen» + бренд «SolingenMarkt» (2026-11-05)

Решение владельца 2026-11-05: утверждён вариант A из канваса `docs/design/portal-home-2026-11-05/` (Main · Menu · Mobile · Card). Бренд — «SolingenMarkt». Собственный домен SolingenMarkt.de появится позже, пока портал остаётся на `solingen.<base>`.

Исходные материалы: исследование `docs/portal-home-redesign-research-2026-11-05.md`, текущая главная `portal_views._render_home` (`apps/aggregator/portal_views.py:956–1007`), блоки `apps/aggregator/portal_home_blocks.py`.

## 0. Рамки и инварианты (действуют во всех инкрементах)

**Кэш страницы**
- Анонимный GET корня без query кэшируется: `apps/core/pagecache.py`, TTL 120 с (`config/settings/base.py:414`).
- В разметке главной не должно быть ни `{% csrf_token %}`, ни данных конкретного пользователя (замок `test_home_is_cached_without_csrf_token`, `test_portal_discover.py:357`).
- Всё «живое» (часы работы, отсчёт до конца) считается на сервере в момент рендера. Устаревание до 120 с допустимо; отсчёт дотикивает JS.

**UWG §5a**
- Платные позиции — только в подписанной полосе «Anzeige», метка на каждой карточке («★ Anzeige»).
- В органических блоках платных нет. «Deal des Tages» выбирается органическим правилом и никогда не бывает featured.
- Показы платных позиций считаются только на чистом корне: `featured(..., count_impressions=not request.GET)`, `portal_views.py:969`.

**Блок ⊆ ленты** (`test_every_block_more_link_contains_all_block_cards`, `:236`). У каждого блока одна область, «Alle →» ведёт на ленту, где есть все его карточки. Лимит на бизнес — `Window(RowNumber)` (`portal_home_blocks.py:355`). Дублей между блоками нет.

**Бюджет запросов** (`test_query_count_does_not_grow_with_data`, `:341`, сейчас ≤ 14). Число запросов не зависит от объёма данных. Добавленные запросы — константы; кап поднимаем один раз, осознанно и с расшифровкой в тесте.

**Замки, которые сохраняются**
- `test_portal_discover`, `test_flt_*`, `test_portal_block_a/b` (в `block_b:98` маркер `data-district-chips` обязан отсутствовать на ленте), `test_portal_seo`, `test_demo_hygiene`, `test_districts_portal` (`:148` — маркер `data-district-chips` на главной), `test_theme_portal`.
- `_cards.html` подключают ещё 15 мест: лента, `/entdecken/`, offer, business, favorites, finder, а также превью акции в кабинете `templates/promotions/promotion_preview.html:29`. Карточку меняем один раз — для всех.

**Миграций нет ни в одном инкременте** (кроме опционального PH-9, см. вопрос владельцу).

**Шрифт.** Plus Jakarta Sans из макета с Google Fonts не грузим (DSGVO). Для заголовков берём уже self-hosted Manrope 800 (latin/latin-ext/cyrillic, `static/fonts/manrope-*`), для текста — текущий стек.

**Акцент.** `primary_color` портала = `#C2410C`: контраст белого текста 5,2 : 1, проходит AA. Чернила по контрасту — тем же правилом, что `apps/core/context.py:152 _accent_ink` (вынести в общий хелпер, если он приватный).

---

## PH-0. Предохранители и рефактор без смены вида

Цель — следующие инкременты меняют вёрстку и не ломают регулярки замков.

**Файлы**
- `templates/aggregator/_cards.html`: заголовку карточки — `data-card-title`; цене — `data-card-price`.
- `templates/aggregator/_section_tiles.html`: счётчику плитки — `data-tile-count`.
- `apps/aggregator/views.py:249–308`: общий `open_snapshot(schemas, now)` — один запрос к `Tenant` и словарь `{schema: status}`. `_open_now_schemas` и `_attach_open_status(cards, snapshot=None)` становятся его тонкими обёртками, поведение 1:1.
- `scripts/portal_home_stand.py` — Playwright-стенд, скриншоты 1440 и 390 текущей главной («до»).

**Замки — переписать на маркеры до редизайна**
- `test_portal_discover.py:491` — регулярка сейчас завязана на класс `text-xs text-gray-400`, станет `data-tile-count="(\d+)"`.
- `test_portal_discover.py:500` — сейчас `<h2 class="font-semibold…">`, станет `data-card-title`.
- Новый `test_open_snapshot_shared`: при переданном снимке `_attach_open_status` не делает запросов; паритет со старым результатом на демо-часах, Betriebsferien и бизнесе без часов (`apps/core/tests/test_closures_owner_portal.py:177` остаётся зелёным).

**Риски:** низкие (чистый рефактор).

---

## PH-1. Бренд «SolingenMarkt» и шапка-вордмарк

**Откуда берутся бренд, логотип и цвет.** Всё — из записи `AggregatorPortal` (`apps/aggregator/models.py:534–637`): `title`/`tagline` (i18n-JSON), `logo_url`, `primary_color`. Новых полей нет.

- **Сидер** `seed_demo_tenants._ensure_city_portal` (`apps/tenants/management/commands/seed_demo_tenants.py:~465–526`) сейчас делает `get_or_create`, и `defaults` применяются только при создании. Значит, прод-портал сам не переименуется.
  - Добавить реестр `CITY_PORTAL_BRANDS = {"solingen": {"title": "SolingenMarkt", "tagline": {de: "Alles aus der Klingenstadt", en/ru/uk/tr: …}, "color": "#C2410C"}}`.
  - Фолбэк для прочих городов — прежние «Angebote in {city}».
  - Идемпотентный шаг `_refresh_portal_brand(portal, city)` меняет `title`/`tagline`/`primary_color` только если они равны прежним сидерным значениям: `title["de"] == f"Angebote in {city}"`, `primary_color == "#111827"`. Правки оператора в админке не трогаем.
  - Бренд не переводится: `title` = одинаковое «SolingenMarkt» во всех 5 локалях, иначе `title_text` на en уйдёт в фолбэк «Angebote in …».
  - Поднять `SEEDER_VERSION`.
- **Вордмарк.** Новый тег `apps/aggregator/templatetags/portal_brand.py::portal_wordmark portal`. Если `title_text` начинается с `portal.city` и длиннее него, разбиваем: «Solingen» тёмным + «Markt» акцентом. Иначе — весь заголовок акцентом (текущее поведение). Это работает для любого будущего «<Город>Markt» без поля в БД.
- **`templates/aggregator/portal_base.html:26–43`** — шапка по Main.dc.html (строки 20–40):
  - вордмарк и tagline под ним;
  - слот кнопки «☰ Kategorien» (заполняется в PH-2);
  - поиск в шапке — вынести разметку из `_portal_search.html`, чтобы на главной не было двух форм;
  - «♡ Gemerkt», «Anmelden»/«Mein Konto», «Für Unternehmen» обведённой пилюлей;
  - язык остаётся.
  - Hover/active в стилях — через `--portal-color`; новая CSS-переменная `--portal-ink`.
- **SEO.**
  - `portal_discover.html:3`, `<title>`: «SolingenMarkt — Angebote, Läden & Termine in Solingen» (шаблон: `{{ title }} — {% blocktrans %}Angebote, Läden & Termine in {{ city }}{% endblocktrans %}`).
  - H1 переносится в hero (PH-4).
  - `og:site_name`, футер, Atom/JSON-фиды, `llms.txt`, MCP `serverInfo` читают `title_text` — подхватят сами.
  - В тестах заданы свои заголовки («Entdecke Solingen» в `test_machine_readable.py:40`, `test_mcp_protocol.py:26`), они не ломаются.
- **Подготовка к SolingenMarkt.de: код сейчас не нужен.** Хардкода хоста портала вне сидера нет: canonical, sitemap, robots и фид строятся от `request.build_absolute_uri`, `other_portals` — от `p.host`. Runbook переезда — PH-D в конце. Миграцию `aliases` не делаем.

**Тесты до кода**
- Сидер: старый дефолт → бренд; отредактированный `title` не трогается; повторный прогон ничего не меняет.
- `portal_wordmark`: «SolingenMarkt» → две части; «Gesund in Solingen» → одна часть; пустой город.
- Главная: `<title>` содержит бренд и город; `og:site_name` = бренд.

**i18n:** tagline ×5 (в сидере), новые msgid шапки → 5 `.po`, `scripts/i18n_quickcheck.py`.

**Риски:** средние. Переименование видно в Telegram-боте портала и в письмах сводки — это ожидаемо. ⚠️ ops: после деплоя `seed_demo_tenants --kit <любой кит Solingen>` (или `--group all --changed`).

---

## PH-2. Иконочная полоса разделов и мега-меню «Kategorien»

**Файлы**
- `apps/core/city_categories.py`: `SECTION_ICONS: dict[str, str]` — SVG-path `d` на каждый из 15 разделов.
  - 13 путей берём из словаря `I` в `Main.dc.html:184–201`.
  - Недостающие нарисовать: `dienstleistungen`, `tiere`, `kunst-geschenke`, `reisen-uebernachten` (сейчас «reise»).
  - Эмодзи `Section.icon` остаётся для бота и кабинета.
- `apps/aggregator/templatetags/portal_brand.py::section_icon key [size]` — inline `<svg aria-hidden="true">`, `stroke="currentColor"`.
- `apps/aggregator/portal_home_blocks.py`:
  - `presence()` (`:233`) дополнительно возвращает `categories: {cat_key: n}` — без нового запроса, тот же цикл.
  - Новый `menu_sections(present, path)`: разделы со счётчиком; описание в одну строку = первые 3 подписи категорий раздела (новых текстов не нужно); бейдж «Beliebt» у топ-3 разделов по числу (это факт); подкатегории `[(key, label, n, url)]` только непустые; url — `scope_url(FeedScope("alle", kat=…))`.
  - `cached_menu_sections(portal, lang)` для страниц, кроме главной: Redis `portal_menu:<pk>:<lang>`, TTL 300, fail-open, считается одним `presence()`. На главной переиспользуем уже посчитанный `present`, ноль дополнительных запросов.
- **Шапка** (`portal_base.html`): под строкой шапки `<nav aria-label="Bereiche">` с горизонтальным скроллом — иконка и подпись, первая «Alles» = корень. Активный раздел подчёркнут `--portal-color`, когда в контексте есть `active_kat`; лента его передаёт.
- **`templates/aggregator/_portal_menu.html`** — `<dialog id="portal-menu" aria-labelledby=…>`, левая панель 440 px (Menu.dc.html):
  - вход «Anmelden · Registrieren» (ссылка);
  - строки разделов (иконка в плитке акцентного тона, название, описание, счётчик, шеврон);
  - группа «Nach Art» — существующие `home.tabs()` с маркерами `data-portal-tab`, перенос вкладок с главной, см. PH-6;
  - правая панель — подкатегории активного раздела.
  - Переключение правой панели — в `static/js/portal.js` делегированием на `document` (`mouseenter`/`focus` строки → `hidden` у панелей; урок Ф1 и KAT-5). Закрытие: Esc, клик по подложке, ✕. Фокус возвращается на кнопку.
  - Мобильный вид: полноэкранный лист, подкатегории — аккордеоном (`<details>` внутри строки).
  - «Thema der Woche» в v1 не делаем: нет данных. Позже — ссылкой на тематический портал `gesund-<город>`, если он есть.
- **Прогрессивное улучшение.** Кнопка «☰ Kategorien» — это `<a href="{% url 'portal-home' %}#kategorien">`; при наличии JS она открывает `dialog.showModal()` и снимает навигацию. Без JS ведёт к якорю `#kategorien` — существующему `_section_tiles.html`, который на главной переезжает вниз под заголовком «Alle Bereiche», с SVG вместо эмодзи и сохранёнными `data-section-tile`/`data-tile-count`.

**Тесты до кода**
- Каждый раздел реестра имеет SVG (15/15) — замок на будущие разделы.
- Меню показывает только непустые разделы; счётчики = `presence`; url подкатегории ⊆ ленты (`parse_scope` + `apply_scope`).
- В диалоге нет csrf; ключ кэша меню содержит язык; на не-главной странице меню не добавляет запросов при тёплом кэше (`django_assert_max_num_queries`).
- Якорь `id="kategorien"` есть на главной.

**Риски:** средние. Меню в шапке на каждой странице портала — либо кэш, либо +1 запрос. Эмодзи на портале полностью исчезают — сверить `test_portal_discover:130–160`.

---

## PH-3. Карточка нового вида (`_card.html` + `_cards.html`)

**Файлы**
- `templates/aggregator/_card.html` (новая, одна карточка) и `templates/aggregator/_cards.html` (обёртка-сетка: `{% include "_card.html" %}` в цикле).
- Параметр `layout` в `_cards.html`: `"grid"` по умолчанию — текущая сетка 2/3/4 (`_cards.html:2`); `"row"` — на `<sm` горизонтальная лента со snap (`flex overflow-x-auto snap-x`, `flex: 0 0 270px`), на `sm+` та же сетка. Внешние вызовы без параметра не меняются.
- Анатомия по Card.dc.html:
  - **Фото 4:3** (было `aspect-square`). Столбик бейджей слева сверху: условие цены / «−N %» / тег («Endet heute», «Neu», «Regional» из `city_tags`, «Bio»).
  - **Полоса отсчёта внизу фото** для `ends_at` ≤ 24 ч: «Endet in 02:14 h».
  - **Строка бизнеса:** аватар-инициал (логотипа в листинге нет, `models.py:113`), имя и район.
  - **H3** `data-card-title` (на главной карточки внутри H2-секций; на ленте под H1 тоже корректно).
  - **Строка рейтинга** ★ (`business_rating`) и **строка часов** «Geöffnet bis 18:00» / «Geschlossen · öffnet Mo 09:00» / «Betriebsferien bis …». Это прежние поля `_attach_open_status`, переезжают из бейджа в строку.
  - **Цена** крупно; UVP/зачёркнутая; строка 30 дней (`_cards.html:59–86` переносится 1:1 — замки PAngV/SF-8).
  - **Пилюля действия** по виду листинга — визуальный `<span>` внутри той же ссылки, не вложенная ссылка (a11y): promotion «Zum Angebot», product «Ansehen», service «Termin», event «Tickets», stay «Verfügbarkeit», menu «Anfragen», business «Zum Geschäft». Честно: «Coupon holen»/«Zurücklegen» не пишем — в листинге нет снимка отклика акции (см. PH-9).
  - **Сердечко:** при `portal_user` — прежняя POST-форма (страница вне кэша: есть сессия). Для анонима на портале — ссылка `portal-login?next=` с `rel="nofollow"` и иконкой ♡, кэшируется. На `/entdecken/` остаётся shortlist.
  - Сохранить все маркеры: `data-pstat`, `★ Anzeige`, `rel="sponsored nofollow"`, `data-demo-badge`, `data-price-condition`, `data-availability`, `data-condition`, `data-kind-badge`, `data-new-badge`, `data-holiday`, `data-report-link`.
- **`apps/aggregator/portal_cards.py`** (новый):
  - `ends_label(listing, now)` → `(text, iso)`: «Endet heute um 18:00», «Endet in N Std.» (plural), «Endet morgen»; пусто при `ends_at` > 7 дней или `None`.
  - `prepare_cards(cards, snapshot=None, now=None)` — общий вызов `open_snapshot` + `ends_label` + `initial`. Зовётся в `_render_home` и в ленте `portal_home` (`portal_views.py:374…`; сейчас на портале часы не прикрепляются вовсе) — +1 запрос к `Tenant` на ленте.
- **`static/js/portal.js`:** тик `[data-ends-at]` раз в минуту. Пересчёт текста по ISO; на 0 — «Beendet» и `opacity-60`. Это закрывает устаревание кэша до 120 с. `aria-live` не ставим: тик раз в минуту — шум для скринридера.

**Тесты до кода**
- Все маркеры выше есть в разметке (адверсариально: карточка featured, демо, распроданное, mystery без цены, событие).
- `ends_label` — границы суток в TZ Europe/Berlin, plural ru/uk.
- Лента портала прикрепляет часы одним запросом; бюджет ленты — смежные `test_flt_*`.
- Главная анонимно — без csrf.
- Сердечко аноним → ссылка, логин → форма.
- Превью кабинета `promotion_preview` рендерится без ошибок.

**Риски:** высокие (15 поверхностей).
- Гонять смежные тесты: `apps/aggregator`, `apps/promotions/tests` (превью), `apps/core/tests/test_closures_owner_portal.py`.
- Новые Tailwind-классы → `npm run build:css` и коммит `static/css/app.css`.

---

## PH-4. Hero «Was gibt's heute in {city}?» и «Deal des Tages»

**Файлы:** `apps/aggregator/portal_home_blocks.py` (+ `templates/aggregator/_portal_hero.html`).

- **`home_stats(base, now)`** — один `aggregate`:
  - `businesses = Count("tenant_schema", distinct=True)`;
  - `offers = Count("id", filter=Q(listing_kind__in=OFFER_KINDS))` — пул `public()`, то есть «действует сейчас»;
  - `new_week = Count("id", filter=Q(created_at__gte=now-7d))`.
  - «N Geschäfte geöffnet» в надзаголовке — `len(open_set)` из снимка (PH-0), без отдельного запроса. Снимок строится от схем, которые приходят из агрегата районов (PH-6): один запрос `values("district", "tenant_schema")` даёт и районы, и множество схем.
  - Каждая цифра — ссылка на ленту: `?kind=business`, `?kind=angebote`, `?kind=alle&neu=1`. Цифра 0 — без ссылки, весь ряд скрыт при пустом пуле.
- **`deal_of_day(base, *, exclude_pks, now)`** — органическое правило, 1 запрос:
  - пул: `listing_kind=promotion`, есть картинка (`image` ≠ {}), `discount_percent` не null, нет `price_condition`, не mystery (цена известна);
  - исключить `featured_until > now`: платное в hero = нарушение §5a;
  - порядок: заканчивается сегодня → `discount_percent desc` → дневная ротация `MD5(id ‖ дата)` (как `daily_rotation`, `:312`);
  - результат исключается из блоков (`seen`).
  - Подпись под бейджем «Deal des Tages»: «Größter Rabatt, endet heute» / «Größter Rabatt» — честно о правиле.
  - CTA — пилюля по виду (как в PH-3). Отсчёт — `ends_label` крупными цифрами (`Main.dc.html:80–82`) с `aria-label`.
  - Нет кандидата — правая колонка hero не рисуется, левая растягивается на 12 колонок.
- **Быстрые чипы** `hero_chips(present, stats, open_count)` — из данных, без журнала поиска, каждый только при непустом результате:
  - «Jetzt geöffnet» → `?kind=alle&offen=1` (если `open_count`);
  - «Heute» → `?kind=alle&datum=heute`;
  - самая наполненная категория → `?kind=alle&kat=<cat>` с её подписью;
  - «Unter 10 €» → `?kind=alle&preis_bis=10`, если есть цены ≤ 10 (флаг в том же `aggregate`).
- **H1:** «Was gibt's heute in {city}?» (`blocktrans`). Под ним абзац из `portal.intro_text` либо генерируемый «N Angebote von Läden, Cafés und Handwerkern aus {city} …». День недели — `{% now "l" %}` в языке запроса (ключ кэша содержит язык).
- **`portal_discover.html:9–16`:** старые H1/интро/`_portal_search` удаляются (поиск уже в шапке). Маркер `data-portal-search` переносится на форму в шапке — замок `test_portal_discover:115`. `data-portal-home` остаётся на hero.

**Тесты до кода**
- Featured никогда не становится deal (адверсариально: featured с самой большой скидкой).
- Предпочтение «заканчивается сегодня»; стабильность в пределах дня; deal не повторяется в блоках.
- Без кандидата hero без правой колонки; цифры = посчитанным вручную.
- Каждая ссылка чипа или цифры даёт непустую ленту: `parse_filters` + `apply_filters` поверх `listings_for`.
- Кэш без csrf; бюджет запросов (кап поднимается здесь же: 14 → N с расшифровкой).

**Риски:** средние — UWG (правило deal) и SEO (смена H1). Позвать `seo-specialist`.

---

## PH-5. Строка быстрых фильтров на главной (только ссылки)

**Файлы:** `templates/aggregator/_home_quick_filters.html`, `portal_home_blocks.quick_filters(stats, present, districts, open_count)`, `static/js/portal.js`.

- **Тумблеры-ссылки.** На главной состояния «включено» нет, поэтому `aria-pressed` не ставим — это обычные ссылки на ленту:
  - «Jetzt geöffnet» → `?kind=alle&offen=1`;
  - «Angebote» → `?kind=angebote`;
  - «Neu» → `?kind=alle&neu=1`;
  - «Heute abholen» → `?kind=product&verfuegbar=1&datum=heute`: T-8.34 сужает товары по часам работы на дату, то есть «товар в наличии и магазин сегодня открыт»;
  - «In der Nähe» — `<button hidden>`. JS показывает его при наличии `navigator.geolocation` и при клике переходит на `?kind=alle&lat&lng&sort=naehe`; логика скопирована из `_map.html:20–34`, вынести её в `portal.js`. Без JS кнопки нет: обещания без исполнения не даём (STU-9). Учесть, что в `parse_filters` (`search.py:429`) `naehe` без точки сбрасывается.
  - Каждый тумблер показывается только при непустом результате (по `stats` и `present`).
- **Выпадашки** — `<details>`-поповеры со ссылками, без формы и csrf:
  - «Stadtteil» — районы с числом предложений, ссылка на `portal-district`;
  - «Preis» — `preis_bis` 10/20/50 € и «ab 50 €»;
  - «Merkmale» — признаки, присутствующие в пуле: `city_tags`, их счёт складывается в `presence` (тот же запрос: `values(... , "city_tags")` раздует строки, поэтому отдельный лёгкий запрос — `jsonb_array_elements_text` + `Count`, +1 к капу).
  - Мобильная прокрутка — механика FLT уже есть в `portal.js:83` (пилюля ▾ на телефоне открывает шторку). На главной шторки нет, поэтому на телефоне выпадашки ведут ссылкой на ленту `?kind=alle#filter`.
- **«Alle Filter»** → `?kind=alle#filter`. В `portal.js` при загрузке: если `location.hash == "#filter"` и шторка FLT на странице есть — `openDrawer()`.
- Правый край строки: «N Angebote heute» (из `stats`); «Treffer / Sortiert nach» на главной не имеет смысла.

**Тесты до кода**
- Каждая ссылка строки парсится `parse_filters` без потерь: параметр в ссылке = параметр в `SearchFilters` (класс-замок, как T-8.26 п.5c).
- Все ключи ⊆ `FEED_PARAMS`, иначе корень откроет главную — проверено: `ansicht` не входит, поэтому ссылки на карту всегда с `kind=alle`.
- Пустые тумблеры скрыты; нет csrf; `#filter` на ленте открывает шторку (Playwright).

**Риски:** низкие.

---

## PH-6. Блоки главной по макету

**Файлы:** `apps/aggregator/portal_home_blocks.py`, `templates/aggregator/portal_discover.html`, `_home_block.html`, новые `_home_ads.html`, `_home_districts.html`, `_home_new_businesses.html`.

- **Расширение `FeedScope`** (`:57`) кортежем `extra: tuple[tuple[str, str], ...]` — параметры единого поиска (`sort`, `datum`, `offen`). Выборка блока = `apply_scope(...)` + `search.apply_filters(qs, parse_filters(QueryDict(extra)))`; `more_url` = `scope_url` + `extra`. Один разбор — тот же, что у ленты, поэтому ⊆ сохраняется по построению.
- **Новый порядок `BLOCKS`** (`:92`):
  1. `endet` «Endet heute» — `FeedScope("angebote", extra=(("datum","heute"),("sort","endet")))`, выборка `ends_at < конец дня`. Фолбэк при пустоте — заголовок «Endet bald» (порядок `urgent`, без фильтра дня). Подзаголовок — по макету. «Alle N anzeigen» — число из `count_capped`: +1 запрос, либо без числа, если упираемся в кап (решить по бюджету).
  2. **Полоса «Anzeige»** (не блок, отдельная секция, `data-home-featured` сохраняется). Жёлтая рамка, плашка «ANZEIGE» не слабее CTA по контрасту и размеру, подпись «Bezahlte Platzierung — getrennt von den Empfehlungen». Компактная горизонтальная карточка `_ad_card.html` с «★ Anzeige · {biz}» на каждой, `rel="sponsored nofollow"`, ссылка через `aggregator-featured-click`, `data-pstat`. Замок `test_featured_is_marked_separate_and_not_duplicated` (`:196`) — как есть.
  3. `offen` «Jetzt geöffnet» — `FeedScope("alle", extra=(("offen","1"),))`, выборка `tenant_schema__in=open_set`, порядок `daily_rotation`, без бизнесов, `per_business=1`.
     - Подзаголовок честный: «Gerade geöffnet · täglich neu gemischt». «Sortiert nach Entfernung» у анонимной кэшируемой страницы невозможно: координат центра города в реестре нет (`apps/core/districts.py`).
     - Справа «Karte öffnen →» = `?kind=alle&offen=1&ansicht=karte` + кнопка «📍 Nach Entfernung» (JS, как в PH-5).
  4. Прежние `produkte` («Produkte aus {city}»), `essen`, `freizeit` — без изменений, остаются наполнением главной.
  5. **«Deine Stadtteile»** — плитки 5 колонок на десктопе, лента на телефоне. Название, «N Angebote», «N offen». Один запрос `values("district","tenant_schema").annotate(n=Count("id"))` (тот же, что дал схемы для снимка в PH-4) заменяет `_district_choices` (`portal_views.py:66–77`). Порядок — реестр, только непустые, маркер `data-district-chips` сохраняется.
  6. `neu_firmen` «Neu in {city}» — `FeedScope(L.KIND_BUSINESS, new_only=True)`, `per_business=1`, лимит 6; круглая плитка (фото листинга или инициал), имя, отрасль, район.
     - «+ Folgen» = ссылка `{% url 'aggregator-follow' %}?unternehmen=<tenant_slug>&next=/`, `rel="nofollow"`, без формы.
     - Демо-бизнес подписку не принимает (`follow.business_target`, `follow.py:106–114`), поэтому у `is_demo` вместо «Folgen» — «Ansehen».
     - Меньше 3 новых — блок превращается в прежний `unternehmen` «Lokale Unternehmen» (`daily_rotation`), иначе «Neu» было бы неправдой.
  7. Блок `neu` (все виды, `:127`) снимается: его покрывают тумблер «Neu» и цифра hero.
  8. «Alle Bereiche» `#kategorien` (PH-2), «Branche», «More local portals» — внизу, как сейчас.
- **Вкладки видов** на главной уходят в группу «Nach Art» мега-меню (PH-2). Маркеры `data-portal-tab` остаются в DOM главной (в диалоге), замки `:110/:116/:119` целы. На ленте вкладки без изменений.

**Тесты до кода**
- `test_every_block_more_link…` расширяется: `extra` разбирается `parse_filters` + `apply_filters`; `_seed_everything` дополняется акцией с концом сегодня и открытым бизнесом (часы в `Tenant.opening_hours_structured` фабрики).
- «Endet heute» содержит только сегодняшние, фолбэк меняет заголовок.
- «Jetzt geöffnet» не содержит закрытых и бизнесов на Betriebsferien.
- Районы: числа и «offen» сверены вручную; пустой район скрыт.
- «Neu in»: демо без Folgen; меньше 3 новых — фолбэк.
- Лимит на бизнес и отсутствие дублей (`:254`) — как есть.
- Бюджет запросов: финальный кап с расшифровкой построчно в docstring `_render_home` (`:956–961`).

**Риски:** средние. Перепись замка ⊆ — осознанная, ДО кода. Объём HTML главной растёт: проверить TTFB на стенде.

---

## PH-7. Мобильная версия (390)

**Файлы:** `portal_base.html`, `portal_discover.html`, `_cards.html` (`layout="row"`), `static/js/portal.js`.

- Блоки главной на `<sm` — свайп-ленты (`layout="row"`, snap, видна часть следующей карточки). «Alle N →» в шапке блока.
- Шапка по Mobile.dc.html: квадратная кнопка меню, вордмарк, ♡; поиск второй строкой; иконочная полоса; липкая.
- Нижняя навигация в `portal_base.html` на всех страницах портала, `sm:hidden`, `nav aria-label`:
  - Entdecken — `portal-home`;
  - Karte — `?kind=alle&ansicht=karte`;
  - Gemerkt — `portal-account` при логине, иначе `portal-login?next=/konto/`;
  - Konto.
  - `aria-current="page"` по `request.resolver_match`. `main` получает `pb-24` на `<sm`. Учесть `env(safe-area-inset-bottom)`.
- Фильтры на телефоне — существующая шторка FLT на ленте, вход `#filter` (PH-5). Новой шторки нет.

**Тесты до кода:** серверно — нижняя навигация есть, ссылки reverse'ятся, без csrf. Остальное — Playwright: нет горизонтального переполнения страницы, ленты листаются, нижняя навигация не перекрывает последний блок и футер.

**Риски:** низкие и средние — перекрытие фиксированной панелью и iOS safe-area.

---

## PH-8. Полировка: i18n, a11y, стенд, скриншоты, документация

- **i18n.** Каждый инкремент сам добавляет msgid в 5 `.po` (`de/en/tr/ru/uk`) — иначе красный гейт `i18n_gap`. Здесь — сводная проверка `scripts/i18n_quickcheck.py` + `scripts/i18n_untranslated.py`, plural «N Std.»/«N Angebote» (4 формы ru/uk). Не писать `_()` в аргументах `{% include with %}` (грабля DL-20) — только `{% trans … as %}`.
- **a11y.**
  - Диалог меню: `aria-modal`, ловушка фокуса — нативная у `showModal`; возврат фокуса; Esc.
  - Иконки `aria-hidden`, подписи текстом; контраст бейджей и «ANZEIGE»; цели ≥ 44 px (макет).
  - Отсчёт с `aria-label` словами; карточка — одна ссылка (пилюля — `span`); свайп-ленты доступны клавиатурой (`tabindex` карточек естественный).
- **Стенд** `scripts/portal_home_stand.py`: 1440 и 390 × de/ru, «до» (PH-0) и «после».
  - Проверки: 0 JS-ошибок; нет переполнения; открытие и закрытие меню мышью и клавиатурой; переключение подкатегорий; тик отсчёта; `#filter` открывает шторку; «In der Nähe» скрыт без геолокации.
  - Запуск на `config.settings.stand` (dev-settings дают 500 на витрине из-за djdt).
- **Документация:** `docs/build-log.md`, `docs/task-catalog.md`, строка в §3 `CLAUDE.md`; демо-хвосты — в `roadmap-next-sprints.md §Отложено`.

---

## PH-9 (опционально, нужно решение владельца). Снимок отклика и остатка в листинге

Кнопки «Coupon holen / Zurücklegen / Termin» и строка «noch N Stück» из макета требуют данных, которых в `AggregatorListing` нет. Сейчас там есть только `availability` (`models.py:165`).

- Аддитивная миграция `aggregator/00xx` (SHARED): `action` (код отклика `promotions/response.py`) и `remaining` (nullable).
- Синк во всех построителях листинга, `sync_aggregator` после деплоя, пилюля и полоса в карточке.
- Без PH-9 пилюля ведёт на страницу предложения с нейтральной подписью по виду (PH-3) — это честно и уже работает.

---

## PH-D (позже, когда домен SolingenMarkt.de куплен). Runbook переезда, код минимальный

1. В записи портала `host` → `solingenmarkt.de`. Строки `Domain` для `solingenmarkt.de` и `www.solingenmarkt.de` → public-тенант (как в сидере, `seed_demo_tenants.py:400–409`). Тогда `verify_domain` (`apps/core/health.py:74–96`) пропустит выпуск сертификата сам.
2. Старый `solingen.<base>` — 301 на новый хост с сохранением path+query.
   - Без миграции: env-настройка `PORTAL_HOST_REDIRECTS="solingen.siteadaptor.de=solingenmarkt.de"`, обработка в `apps/aggregator/middleware.py` до резолва портала (`resolve_portal`, `:39`).
   - `www` → apex тем же механизмом.
   - Старая строка `Domain` старого хоста остаётся, иначе TLS и роутинг для 301 не работают.
3. Сверить `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS`: вход на портал — POST, cookie `__Host-csrftoken` без wildcard (SEC волна 4).
   - Сессии на старом хосте теряются — сообщить в релизе.
   - Карта хост→портал сбрасывается сигналом (`middleware.py:34`).
4. Canonical, sitemap, robots, фид и `llms.txt` строятся от запроса — после 301 подхватят новый хост сами. Search Console: добавить ресурс + Change of Address; `show_demo` снять на запуске (T-8.26).
5. Telegram-бот портала: в админке «Portal bots» нажать «Connect» заново (webhook на хосте портала `/tg/<secret>/`).
6. Письма сводок и отписки (`follow`) и ссылки `other_portals` строятся от `portal.host`; старые ссылки в уже отправленных письмах идут через 301.
7. Замок: 301 сохраняет query; несуществующий маппинг не трогает чужие хосты; на новом хосте строится canonical.

---

## Порядок и зависимости

PH-0 → PH-1 → PH-2 → PH-3 → PH-4 → PH-5 → PH-6 → PH-7 → PH-8. Каждый инкремент — отдельный батч, локальный гейт, зелёный CI, FF в `main`.

- PH-2 и PH-3 независимы между собой.
- PH-4 и PH-6 опираются на `open_snapshot` (PH-0) и карточку (PH-3).
- PH-5 можно делать параллельно с PH-6.

**Финальный гейт каждого батча:** `ruff check .` + `ruff format --check .` целиком; `npm run build:css` + коммит `app.css`; `apps/core/tests/test_template_comments.py`; `scripts/i18n_quickcheck.py`; pytest `apps/aggregator apps/promotions/tests apps/core/tests/test_closures_owner_portal.py apps/tenants/tests` (сидер) с `--reuse-db`.

---

## ECC-прогоны

| Инкремент | Скиллы до кода | Агенты |
|---|---|---|
| PH-0 | django-patterns, django-tdd, postgres-patterns | `django-reviewer`; `database-reviewer` (общий снимок `Tenant`) |
| PH-1 | django-patterns, seo, deployment-patterns (сидер/ops) | `django-reviewer`; `seo-specialist` (title/H1/og, prep домена) |
| PH-2 | accessibility, django-patterns, redis-patterns (кэш меню) | `django-reviewer`; `a11y-architect` (dialog/меню/полоса); `e2e-runner` (Playwright: клавиатура, no-JS якорь) |
| PH-3 | accessibility, django-tdd, error-handling | `django-reviewer`; `a11y-architect` (карточка, одна ссылка, отсчёт); `database-reviewer` (часы на ленте, N+1); `silent-failure-hunter` (тик JS / fail-open снимка) |
| PH-4 | postgres-patterns, seo, django-tdd | `django-reviewer`; `database-reviewer` (aggregate счётчиков, deal-запрос, кап); `seo-specialist` (H1/ld); `security-reviewer` — проверка UWG-правила deal и отсутствия платного в органике |
| PH-5 | api-design (контракт ссылок ленты), accessibility | `django-reviewer`; `e2e-runner` (`#filter`, геолокация скрыта/видна) |
| PH-6 | django-patterns, postgres-patterns, django-tdd | `django-reviewer`; `database-reviewer` (районы/открытые одним запросом, итоговый бюджет); `a11y-architect` (полоса «Anzeige», плитки) |
| PH-7 | e2e-testing, accessibility | `django-reviewer`; `e2e-runner` (390 px, переполнение, нижняя панель); `a11y-architect` |
| PH-8 | e2e-testing, seo | `e2e-runner` (сводный стенд 1440/390 × de/ru, скриншоты до/после); `seo-specialist` (итог: canonical, noindex превью, sitemap); `doc-updater` (build-log/task-catalog/CLAUDE.md §3) |
| PH-9 (если да) | database-migrations | `database-reviewer`; `django-reviewer` |
| PH-D (позже) | deployment-patterns, seo, django-security | `security-reviewer` (301/host header, CSRF origins); `seo-specialist` (Change of Address) |

Сразу после утверждения плана — `planner`/`architect` не нужны. Ревью плана PH-4 (правило deal) — `security-reviewer` до кода.

---

## Вопросы владельцу (только необходимые)

1. **PH-9:** добавляем в листинг снимок отклика акции и остатка (одна аддитивная SHARED-миграция), чтобы на карточках были «Coupon holen / Zurücklegen» и «noch N Stück» как на макете? Рекомендация — да, отдельным инкрементом после PH-6. Без этого кнопка нейтральная по виду («Zum Angebot»).
2. **Бренд для других городов:** будущие городские порталы называем так же — «<Город>Markt» (вордмарк разбивается автоматически)? Рекомендация — да. До ответа сидер переименовывает только Solingen.

## Решения владельца (2026-11-05)

1. **PH-9 — да:** снимок отклика акции и остатка в листинге (аддитивная SHARED-миграция) — после PH-6.
2. **Бренд — «<Город>Markt» для всех городских порталов** (вордмарк делится автоматически);
   сидер переименовывает порталы со старым сидерным заголовком.
