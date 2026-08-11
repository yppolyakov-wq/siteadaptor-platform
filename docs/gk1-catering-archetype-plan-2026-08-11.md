# План GK-1 «Архетип Catering» + GK-4 «Полоса цифр» (2026-08-11)

Источник: `goodkarma-catering-gap-analysis-2026-08-11.md` §3 (C-1, C-4); отмашка
владельца «делаем C-1 и далее». Прецеденты: S6a (friseur/handwerker/werkstatt/events),
online_shop (2026-07-10), спейсер ST-7a (для C-блока). Разведка — 2 Explore-агента,
чек-листы сверены с кодом (file:line в отчётах). Ветка та же
(`claude/goodkarma-catering-analysis-fea071`), волна AF уже в ней — кит Catering
сразу использует `anfrage_form` и `anfrage_ref`.

## §1. GK-1 — решения

1. **Тип**: `("catering", "Catering / Partyservice")` перед `other`
   (⚠️ миграция `tenants/0028`, AlterField choices-only, DDL нет). Метка → 5 .po
   (замок test_smoke_i18n).
2. **Пресет модулей** (`recommended_for` += catering): **jobs (primary)** +
   универсальный набор promotions/reviews/gift/blog/inbox/customer_account + crm.
   ⚠️ blog ОБЯЗАН получить catering (замок test_blog:116 «blog у всех типов»).
   `suited_for` += catering: booking (Beratungstermin), orders (C&C по желанию),
   events, loyalty. booking выключен по умолчанию → `_PRIORITY` даёт jobs
   автоматически; кит дополнительно пишет `primary_module="jobs"` (страховка
   класса bakery). `FOOD_BUSINESS_TYPES` += catering (аллергены/LMIV на
   Speisekarte — catalog core, форма гастро-маркировки).
3. **JSON-LD**: `_SCHEMA_TYPES["catering"] = "FoodEstablishment"` (в schema.org
   НЕТ CateringService; FoodEstablishment — валидный LocalBusiness-подтип).
4. **Карточка мастера/регистрации**: `BUSINESS_TYPE_META["catering"] = ("🍽️",
   blurb языком задач)`; `DEMO_KIT_HOST["catering"]="catering"` (кнопка «Demo
   ansehen» сама гаснет до пересева — гейт по Domain).
5. **/branchen/catering**: DISPLAY_NAME + CONTENT (5-6 highlights ТОЛЬКО из
   реально существующих фич: Anfrage с событийными полями AF-1 · Sofort-Angebot/
   Angebot онлайн с Anzahlung · Speisekarte с диетами/аллергенами · акции ·
   отзывы · мультиязычность); модуль-грид/док-URL — авто. `feature_demos` +=
   запись «Event-Anfrage» (host catering, path /anfrage/). Замки-счётчики:
   test_industry_pages 14→15, sitemap test_seo 21→22.
6. **Look'и**: `ARCHETYPE_LOOK_ACCENTS["catering"]` — тройка (klar/warm/nacht)
   в зелёной гамме (bio/frisch); замок test_looks 14→15.
7. **Шаблон витрины**: НОВЫЙ entry `catering` в sitetemplates.TEMPLATES
   (sections: hero/usp_bar/process/products/gallery/testimonials/faq/contact —
   сверить гейты секций по факту; `site_defaults.hero_widget="catering"`),
   recommended_for=("catering",).
8. **hero_tiles**: сет `catering` зеркалом handwerker: 📝 Angebot anfordern →
   storefront-anfrage (gate jobs) · 🍽 Menüs & Pakete → storefront-products
   (без гейта) · ☎ Rückruf → storefront-rueckruf (gate jobs) · 🔥 Aktionen →
   gate "deal". Замки test_hero_tiles (авто-параметризация + «плитка не ведёт
   в 404 при выключенном модуле»).
9. **Мастер-наполнение**: promotions/presets.py `PRESETS["catering"]`
   (frühbucher/saison-акции); demo.py `_HERO_TEXT`/`_ABOUT_TEXT`/`_PRODUCTS`
   (≥6 позиций, прецедент-замок online_shop).
10. **Демо-кит `catering`** («Grüne Tafel», веган/вегетарианский кейтеринг —
    референс goodkarma): business_type=catering, subdomain="catering",
    primary_module="jobs", enable_modules=[jobs, promotions, reviews, gift,
    blog, inbox, crm…], `anfrage_form` (Hochzeit/Firmenfeier/Geburtstag/Messe/
    Privatfeier/Sonstiges), job_samples (Hochzeit 80 P., Firmenfeier 25 P.),
    Speisekarte-товары с диет-метками (browse-only — orders off), 4 акции
    (promotions_spec), team/faq/testimonials/trust/process/gallery, menus
    top+bottom (замок «у каждого кита своё меню», цели резолвимы КАК ДАННЫЕ),
    heroes ≥1 (замок первого экрана), встраиваемый `anfrage_ref` на странице
    info (показ AF-2). Все немецкие строки → `demo_i18n_{en,ru,uk,tr}.json`
    (замки: <40 % непереведённого, без identity-записей). Контент держим
    компактным — каждая строка = 4 перевода.
11. **Замки-обновления** (полный список — отчёт разведки §8): industry 15 ·
    looks 15 + accents · sitemap 22 · test_modules параметр ("catering", {...})
    · test_archetypes_s6 блок catering · test_demo_kits apply-тест ·
    demo_menus/hero_tiles — авто-параметризация (должны пройти без правок).

## §2. GK-4 — «полоса цифр» (stats)

1. Тип `stats` в REPEATABLE_BLOCKS (валиден на главной И страницах автоматически;
   golden цел — C-блоки в normalize только из входа). Данные:
   `{"rows": [{"value": ≤12, "label": ≤40}]}`, кап `_MAX_STAT_ITEMS = 4`.
   ⚠️ ключ данных **`rows`, НЕ `items`** — `{{ block.items }}` в Django-шаблоне
   вызывает метод dict.items() (находка разведки).
2. Санитайзер-ветка в `_clean_cblock_data` (образец clean_usp: список, skip
   не-dict, обязателен value, кап); пустое → `{}`.
3. UI редактора — **textarea «wert | label», строка на пару** (паттерн usp_text;
   прецедента списочных полей в C-блоках нет, фикс-8-инпутов хуже);
   `_read_cblock_data` парсит на месте; обратная сериализация — хелпер
   `stats_to_text` для value textarea. Гейт visual-контролов `_cb_row.html:149`
   += stats.
4. Рендер `_block_stats.html`: section my-8 + `cb-box`, грид 2/3/4 колонок
   ЛИТЕРАЛЬНЫМИ классами (purge-safe, ветвление по `block.rows|length`),
   value крупно акцентом (var(--accent)), label text-sm; пусто → ничего,
   в превью → `_block_placeholder`.
5. CBLOCK_DEMO_DATA (= байт-в-байт выходу санитайзера — замок round-trip
   builder:201), CBLOCK_VARIANTS 4 шт (3 пары/4 пары/широкий/компакт — каждый
   переживает normalize, замок variants), block_types (🔢), variantThumb-ветка,
   **`collect()` в site_home += "rows"** (иначе live-канал не видит поле —
   находка разведки), пресеты страниц — опционально.
6. Тесты: новый `test_stats_block.py` (кап >4, мусор, рендер 2/3/4, пусто,
   round-trip save, вставка add_block даёт демо) + авто-замки demo-data/variants.

## §3. Порядок инкрементов (батч, локальные гейты)

GK-1a тип+миграция+META+HOST+.po → GK-1b модули+FOOD+замки modules →
GK-1c seo+looks+шаблон+presets+demo.py → GK-1d branchen+feature_demos+счётчики →
GK-1e hero_tiles → GK-1f демо-кит+i18n×4+тесты кита → GK-1g s6-блок+широкий гейт →
GK-4 (отдельными коммитами: реестры+рендер → редактор+live → тесты).
Затем Tier 2 (GK-5..9) — по одному, каждый со своим мини-планом в build-log.

## §4. Не-цели / риски

Не-цели v1: finder-дерево catering (модульный фолбэк работает) · dedicated
фото-сет (SVG/токен-фолбэк; фото — ops-задача) · Combo-пакеты Klassik/Plus/
Premium в ките (обычные товары+jobs достаточно; пакеты — GK-10 кандидат).
Риски: счётчики-замки (5 файлов — все в чек-листе); demo_i18n объём; шаблон
витрины — сверить секции с гейтами SECTIONS; nightly-конфликт с параллельной
сессией только по .po/докам (append).
