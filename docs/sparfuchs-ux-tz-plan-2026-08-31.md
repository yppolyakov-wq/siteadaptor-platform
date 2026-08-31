# План SF: ТЗ «UX/UI Sparfuchs» ↔ платформа — волны SF-1..SF-4 (2026-08-31)

Источник: внешнее UX-ТЗ по демо-сайту `aktionsmarkt.siteadaptor.de` (PDF владельца,
80 разделов, P0/P1/P2). ТЗ писалось в предположении standalone-проекта; фактически
это демо-кит `AKTIONSMARKT` (business_type=grocery, бандл `fokus_angebote`,
`apps/tenants/demo_kits.py:3596+`) мультитенантной платформы. Сверка каждого
кластера ТЗ с кодом выполнена воркфлоу (12 разведчиков + адверсариальная
перепроверка ключевых вердиктов вручную, file:line). Итог сверки — в чате сессии
2026-08-31; здесь — только то, что ДЕЛАЕМ. Отмашка владельца: «Давай все
последовательно» (2026-08-31).

## 0. Что НЕ делаем (вердикт сверки, для истории)

- Не переписываем OfferCard/PriceBlock — уже единые (`_promo_card.html`,
  `_discount_display.html`, 9 стилей скидки, паритет-замок).
- Не откатываем секции-группы `/aktionen/` к плоскому списку — секции введены по
  фидбэку владельца 2026-07-29/08-07; ТЗ этого контекста не знало.
- Не строим storeConfig (есть `Tenant`), не переводим Merkzettel на localStorage
  (сессия DSGVO-чище), не вводим жёсткий кап «4 пункта меню» (fitNav по пикселям
  лучше), не подключаем клиентскую аналитику/пуши (external-gated, P2.8).
- «Немецкий по умолчанию» — уже так (`default_locale=de`, LANGUAGE_CODE=de);
  наблюдение ТЗ «встречает английским» = Accept-Language наблюдателя. Отдельный
  реальный дефект негоциации — в SF-1.7.

## SF-1 — батч фиксов «сегодня» (без миграций)

1. **Кит: город.** `city="Köln"` в AKTIONSMARKT (кит задаёт address «…Köln», city
   не задан → сидер ставит Hilden всем: `seed_demo_tenants.py:77`,
   гейт `if kit.city:` demo_kits.py:11306). Прецедент: кит `city="Düsseldorf"`
   (строка 8614). ⚠️ ops: `seed_demo_tenants --kit aktionsmarkt --recreate`.
2. **en.po: `Korb` → «Cart»** (сейчас «Box», locale/en/…:17408 — DeepL-омоним,
   класс X1). Проверить tr/ru/uk переводы «Korb» заодно.
3. **Тёмная тема: чипы скидок.** В dark-карте app.css есть
   `.dark .text-green-800{color:#d1fae5}`, но НЕТ `.dark .bg-green-100` →
   мятный текст на светло-зелёном фоне (чип «🌱 Überraschungstüte» — фирменная
   механика кита). Дочинить карту для палитр чипов `_discount_display.html`
   (bg-green-100, bg-emerald-100, bg-sky-100, text-emerald-700, text-sky-700 и
   смежные, по факту разведки) + `npm run build:css` в том же коммите (замок
   свежести app.css).
4. **Mystery-утечки** (деталь `/p/<uuid>/`, promotion_detail.html):
   savings-строка (part="savings", :97) и строка PAngV lowest_30d (:93-96) —
   под mystery-гейт до reveal (по сумме+проценту цена восстанавливается);
   миниатюры галереи — data-mystery-blur (сейчас только главное фото);
   og:image для mystery не отдавать фото товара-носителя; JSON-LD Offer для
   mystery — без price (Product остаётся). Скрытие остаётся визуальным
   (не security) — но исходник страницы не должен печатать цену прямым текстом.
5. **Reveal-персист** (ТЗ P1, дёшево здесь же): sessionStorage-ключ по pk акции —
   раскрытая mystery-акция не прячется заново при back/переходе карточка→деталь.
   Реализация в делегированном хендлере `_base.html:459+` + восстановление на
   load; карточка несёт pk data-атрибутом.
6. **telegram-web-app.js** (`_base.html:23`) — убрать render-blocking: defer либо
   условная загрузка (по факту разведки, где читается Telegram.WebApp; Mini App
   не должен сломаться).
7. **i18n-мелочи витрины:** `🌱 Überraschungstüte` в `_discount_display.html:36`
   через gettext; `Geschlossen`/WEEKDAYS_DE из openinghours — через gettext на
   момент вызова (аккуратно: тесты с немецкими ассертами, план по разведке);
   msgid — во все 5 .po, дуп-чек polib, гейты i18n_gap/quickcheck.
8. **Accept-Language ограничить локалями тенанта** (реальный дефект за
   наблюдением ТЗ «встречает английским»): посетитель с браузером pl/fr/it/es/
   nl/pt (есть в LANGUAGES, .po нет) получает сырые msgid-микс. Витринный слой
   должен клампить негоциацию к `tenant.active_locales` (кабинетные пути не
   трогать — там CabinetLocaleMiddleware). Точная механика — по разведке
   (middleware после LocaleMiddleware, переактивация при invalid).

## SF-2 — /aktionen/ на рельсы U-B (фильтры/сортировка/поиск)

Сейчас `promotion_list` (public_views.py:272) читает из GET только `gruppe`;
нет ?q=, сортировки, счётчика, пагинации; empty-state один на всё. Данные в
модели есть (ends_at/discount_percent/promo_type/is_new/group), механизм есть
(каркас `templates/storefront/listing.html` + `FacetProvider`, 4 листинга).

- **PromoFacets** в реестр `apps/core/facets.py::provider_for("promotion")`:
  фасеты Heute / Diese Woche (ends_at-окна), «−N %+» (discount_percent__gte,
  пресеты 20/30/50), Reservierbar (promo_type='reservation'), группа (замена
  текущего `?gruppe=`, ключ совместим); поиск `?q=` по title/description
  (+ `*_i18n` JSON-KeyTransform, паттерн UB2-2); сортировки: Neu (-created_at,
  дефолт), Rabatt (discount_percent desc), Preis (new_price asc),
  Endet bald (ends_at asc nulls_last).
- **Шаблон**: promotions_list.html → наследник каркаса listing.html.
  **Секции-групп СОХРАНЯЮТСЯ** (решение владельца 2026-07-29): дефолтный вид без
  фильтров — группы-секции в блоке grid; при любом активном фильтре/поиске/
  сортировке — плоская сетка (как сейчас при ?gruppe=). Характеризационные
  замки ДО свода (прецедент UB1-3: test_index_parity) — секции, чипы, MIN_GROUP_SECTION,
  «More offers».
- **Endet bald**: компактная полоса над списком (3-4 акции, ends_at ≤ 3 дней,
  скрыта если пусто) — перенос логики `apps/aggregator/recommendations.py::ending_soon`
  на Promotion тенанта.
- **Счётчик результатов** при активных фильтрах + честные empty-states
  («по фильтру ничего» + CTA сброса ≠ «акций нет вовсе»).
- Поиск шапки: `_SEARCH_ROUTES` не трогаем (primary grocery = каталог, это
  правильно); `?q=` на самой странице акций достаточно.

## SF-3 — конец жизни акции + мобильный CTA + PAngV

- **Expired-страница вместо голого 404**: деталь закончившейся акции
  (status='ended'/'archived', ссылка/QR с флаера) → страница «Dieses Angebot ist
  leider beendet» + CTA «Aktuelle Angebote ansehen» (/aktionen/) + 2-3 актуальные
  акции. Резерв/покупка остаются заблокированы (status='active' в POST-гейтах
  не трогаем). Отдельно: **кастомные 404/500 витрины** в бренде тенанта
  (сейчас — голые django-страницы; handler404/500 в config/urls_*).
- **Sticky buybar на детали акции**: `_detail_buybar.html` уже подключён к 5
  деталям — добавить акцию (цена + «Reservieren», якорь к CTA/модалу, гейты
  sold_out/mystery).
- **PAngV §11 на карточках**: строка lowest_30d сейчас только на детали; добавить
  на карточку акции со скидкой (мелким текстом, part в _discount_display; данные
  батчем, без N+1) + на rose-тизер акции в детали товара.

## SF-4 — Merkzettel для акций + промо-цена в корзине (денежный путь)

За отмашкой «последовательно» — но с чекпоинтом перед стартом: меняет денежный
маршрут PL.

- **4a. Merkzettel**: generic-хранение (kind+id, сессия как сейчас) → сердечко на
  `_promo_card.html`/детали акции; «Beendet»-пометка вместо молчаливого выпадения;
  тумблер `wishlist` в кабинете (ключ site_config уже переживает normalize, UI
  нет); кит aktionsmarkt включает; вход на мобильном (пункт bottom-меню кита).
- **4b. Промо-цена в каталоге и корзине**: карточка товара с активной акцией-целью
  показывает промо-цену (не только бейдж; festpreis-бейдж «%» → человеческий);
  quick-add/корзина списывают промо-цену через тот же ценовой слой PL
  (custom-строка с маркером {"promo": id}, списание/возврат лимита кампании —
  зеркально promotions.services.purchase, та же atomic). Отдельный план-раздел
  перед кодом: гонки лимита при смешанной корзине, повторное добавление,
  паритет-замки цен «карточка = корзина = заказ».

## Порядок и правила

SF-1 → SF-2 → SF-3 → SF-4a → SF-4b. Каждый инкремент: локальный гейт
(`ruff format --check .` целиком, pytest затронутых модулей `--reuse-db`,
i18n_quickcheck, при шаблонах — test_template_comments, при новых Tailwind-классах
— пересборка app.css) → пуш стопкой → зелёный CI → чекпоинт. Без миграций во всех
волнах, кроме возможной SF-4a (generic-ключ Merkzettel — сессия, миграция не
нужна). ⚠️ ops после SF-1: `seed_demo_tenants --kit aktionsmarkt --recreate`.
