# A8 — Агрегатор / Marktplatz / локальный портал: рыночный анализ

Дата: 2026-06-25. Архетип A8 («городской портал, где конечный потребитель сам
ищет / бронирует / заказывает / покупает по разным бизнесам»). Источник истины
по сделанному — `docs/build-log.md`; смежные планы — `docs/master-plan.md` (M5
Aggregator / M14 Marketplace), `docs/micro-business-verticals.md` (§A8, G8),
`docs/portal-setup.md`, `docs/m20-site-builder-plan.md`.

Принцип позиционирования (важно для всех выводов ниже): платформа — **«39 €/мес
без комиссии с оборота», ANTI-Bitrix, anti-marketplace, GDPR-first без трекинг-
куки**. Агрегатор у нас — слой **discovery + доверие + лидогенерация на витрины
бизнесов**, а НЕ комиссионный маркетплейс с эскроу. Это намеренное ограничение,
а не пробел; см. развилку §8 master-plan.

---

## Current coverage

Код: `apps/aggregator/` (SHARED, public-схема). Денормализованный снимок активных
предложений из tenant-схем (`AggregatorListing`, наполняется `sync_listing`),
поверх которого работают и «портал по умолчанию» на основном домене, и
брендированные мульти-доменные порталы.

**Модель данных (`models.py`):**
- `AggregatorListing` — единый пул карточек трёх видов: `promotion` / `stay`
  (Übernachten) / `event`. Поля: бизнес (schema/slug/name/`business_type`/`city`),
  `category` (направление событий — yoga/meditation/…), цена (old/new/`discount_percent`),
  окно (`starts_at`/`ends_at`), `detail_url`, denorm-гео (`latitude`/`longitude`),
  `is_surprise` (Überraschungstüte), `featured_until` (платное продвижение),
  i18n-`title`/`teaser`/`image`. Индексы по city/business_type/kind/category.
- `AggregatorPortal` — брендированный хост (`*.siteadaptor.de` или custom-домен),
  три типа: `city` / `vertical` / `combo`; брендинг (title/tagline/intro/logo/
  primary_color); резолвер `middleware` → `request.portal` → `urls_portal`.
- `PortalBot` — Telegram-бот портала (Mini App на /start).
- `PortalUser` — клиентская идентичность по **magic-link** (без пароля, без
  django User), лёгкая сессия; central `marketing_opt_out`.
- `FavoriteListing` — избранное клиента (CASCADE — предложение временное).
- `BusinessReview` + `BusinessRating` (G8) — один отзыв на бизнес от автора
  (`PortalUser`), авто-публикация + модерация (hidden), denorm-агрегат звёзд.

**Discovery / поиск / фильтры (`views.py`, `portal_views.py`):**
- `listings_for()` — единый seam-фильтр: city, business_type, q (текст по
  имени/заголовку/городу, icontains), kind, category, month. Истёкшие события
  скрываются.
- `discover_index` (`/entdecken`): индекс городов + рейл «Endet bald»
  (`recommendations.ending_soon`, срочность ухода предложения), при наличии
  параметров — страница результатов с фильтрами (q / city / type / kind / cat /
  month).
- `city_listing` (`/entdecken/<city>/[<type>/]`) — выдача по городу, чипы типов,
  перелинковка соседних городов + ссылка на брендированный портал города.
- `split_featured` — платное продвижение: featured закреплены сверху ПЕРВОЙ
  страницы (бейдж «★ Empfohlen»), курсорная пагинация (keyset, по 24).
- Порталы: `portal_home` сужает по city/business_type, фасет-уточнение по
  свободной оси; для hotel-портала — схлопывание номеров в карточку отеля
  (`_collapse_hotels`) + живой поиск по датам/гостям (`hotel_search`,
  `hotel_availability`) с deep-link в прямое бронирование.

**Гео (`geo.py`, G8c):** haversine, «In meiner Nähe» (геолокация браузера →
`?lat=&lng=` → сортировка ближайших), точки для карты Leaflet/OSM (`_map.html`,
без API-ключа).

**Доверие / отзывы (`reviews.py`):** denorm-рейтинг, `attach_ratings` (звёзды на
карточках выдачи), `verified_emails` (бейдж «Verifizierter Gast» — есть Customer
в схеме бизнеса).

**SEO (`apps/core/seo.py`):** `LocalBusiness` + **`AggregateRating`** в `<head>`
страницы бизнеса портала (`reviews_views.business_page`), `CollectionPage`/
`ItemList` JSON-LD на выдаче города/портала, per-host sitemap.xml + robots.txt.
(Замечание: пометка в `micro-business-verticals.md` §A8 «до полноты: JSON-LD
AggregateRating» — устарела; AggregateRating уже реализован для страницы бизнеса.)

**Аккаунты / каналы:** magic-link вход (`auth.py`, `account_views.py`),
кросс-tenant «свои брони» по email, центральная отписка (UWG §7), Telegram Mini
App портала. Карточки (`_cards.html`): фото, скидка-бейдж, Empfohlen-бейдж,
звёзды, тип-пилюли (Übernachten/Event/Überraschungstüte), цена «ab …€» / зачёркнутая,
сердечко избранного. Тесты — широкое покрытие (`tests/test_*`).

**Оценка готовности A8: ~80 %** относительно «полноценного локального discovery-
портала» по меркам рынка (по нашей же шкале в master-plan стоит ~97 %, но та
шкала меряет «закрыто относительно нашего скоупа», без consumer-discovery планки
рынка). Ядро discovery/доверия/SEO есть; пробелы — в богатстве карточки/листинга
бизнеса, картовом UX, фасетных фильтрах и (опционально, с оговоркой по
позиционированию) Stadtgutschein/единой корзине.

---

## Market benchmark

Что делают эталоны DACH-локального discovery и чего ждёт потребитель:

**Atalanda / Online City Wuppertal / Monheimer Lokalhelden** — региональный
online-маркетплейс «локально покупать онлайн»: продажа товаров, запись на услуги,
**локальная доставка день-в-день**, и центральный элемент — **City-Gutschein /
Stadtgutschein**, который покупается на портале и принимается у многих локальных
продавцов ([atalanda](https://atalanda.com/wuppertal), [Stadtgutscheinsystem](https://atalanda.com/features/stadtgutscheinsystem)).
Stadtgutschein-системы (stadtguthaben.de, AVS, appylio, city-portal.software)
подчёркивают: **частичное погашение**, объединение нескольких карт, погашение
QR/код-вводом на кассе, авто-Abrechnung для торговца, «связывание Kaufkraft
города» как главный аргумент для Stadtmarketing/Werbegemeinschaft
([stadtguthaben](https://www.stadtguthaben.de/), [AVS](https://www.avs.de/staedte/citygutschein),
[proKommun FAQ](https://prokommun.de/cms/333-prokommun-blog/faqs-moeglichkeiten-und-einfuehrung-eines-city-gutscheinsystems.html)).

**Stadtportal-софт (ebiz-trader, IQ-markt, fietz-medien, marktplatz-digital)** —
ожидаемые блоки: **категории с подпиской на темы**, **карта города с
пиктограммами по отраслям** (искать «рестораны» → все рестораны на карте),
рейтинги/комментарии «как TripAdvisor», справочник бизнесов с полным описанием
компании, чат/тайм-лайн сообщества
([ebiz-trader](https://www.ebiz-trader.de/stadtportal-marktplatz.htm),
[IQ-markt](https://www.iq-markt.de/stadtportal-erstellen-software.php),
[fietz-medien](https://www.fietz-medien.de/unternehmen/leistungen/regionale-marktplaetze/index.html)).

**Вертикальные агрегаторы (Quandoo, Treatwell)** — планка consumer-UX: фильтры
**цена / расположение / оценка**, бронь в несколько тапов, превью **меню/услуг,
фото и проверенных отзывов ДО брони**, «рядом со мной», сравнение цен
([Quandoo G2](https://www.g2.com/products/quandoo/reviews),
[Treatwell GetApp](https://www.getapp.com/retail-consumer-services-software/a/treatwell/)).

**Google Business Profile / Map Pack** — фактический стандарт ожиданий локального
потребителя: **Map Pack ≈ 44 % кликов** локальных запросов (vs 29 % органика);
**41 % «всегда» читают отзывы**, **31 % берут только бизнесы ≥4.5★**; **45 %**
уже используют ИИ (ChatGPT/Gemini) для локальных рекомендаций; бизнесы со 100+
фото получают кратно больше звонков/маршрутов; потребитель ждёт **часы работы,
фото, отзывы, маршрут, контакты** в одном месте
([BrightLocal/Searchlab](https://searchlab.nl/en/statistics/google-business-profile-statistics-2026),
[VyomEdge GBP 2026](https://www.vyomedge.com/blog/google-business-profile-complete-guide-2026)).

**Search/List UX (Baymard, Algolia)** — фасетные фильтры (чекбоксы для
мульти-выбора, слайдеры для диапазонов, тогглы), **автоподсказки при вводе**,
4 типа сортировки (цена/оценка/популярность/новизна — 68 % сайтов не дают всех),
дружелюбные empty-state, мобильный приоритет (≈73 % e-com — мобайл)
([Baymard](https://baymard.com/blog/current-state-product-list-and-filtering),
[Algolia](https://www.algolia.com/blog/ux/mobile-search-ux-best-practices)).

---

## Visual gaps

VIS-1. **Карта-первый просмотр с пиктограммами по отраслям** — *partial.* Сейчас
карта (Leaflet/OSM) есть, но как вторичный режим (маркеры из текущей выдачи,
активируется через «рядом»). Эталонные Stadtportal'ы дают карту города как
равноправный режим просмотра с иконками-категориями
([ebiz-trader](https://www.ebiz-trader.de/stadtportal-marktplatz.htm)). Нет
переключателя «Список / Karte», нет типизированных пиктограмм, нет кластеризации
маркеров. **Effort: M.**

VIS-2. **Богатая карточка бизнеса (часы, фото-галерея, маршрут)** — *partial.*
`portal_business` показывает контакты + листинги + отзывы, но не дотягивает до
GBP-планки: нет Öffnungszeiten («открыто сейчас»), фото-галереи, кнопки «Route»
(maps deep-link), телефона-tap. Потребитель ждёт это в одном месте, и фото
драматически двигают конверсию (100+ фото → кратный рост звонков/маршрутов)
([Searchlab](https://searchlab.nl/en/statistics/google-business-profile-statistics-2026)).
**Effort: M.**

VIS-3. **Фасетные фильтры + автоподсказки + сортировка** — *partial.* Текущий
поиск — простые `<select>` (city/type/kind/cat) + один текст-input без подсказок;
нет диапазона цены/скидки, нет «открыто сейчас», нет сортировки (цена/оценка/
ближе/новизна), фильтры не свёрнуты в фасет-панель/drawer на мобиле. Рынок ждёт
faceted search с автокомплитом ([Baymard](https://baymard.com/blog/current-state-product-list-and-filtering),
[Algolia](https://www.algolia.com/blog/ux/mobile-search-ux-best-practices)). **Effort: M.**

VIS-4. **Presentation отзывов на выдаче** — *partial.* На карточке — компактные
звёзды + счётчик, но нет распределения (5★→1★), нет «свежие отзывы», нет ответа
бизнеса. С учётом что 41 % всегда читают отзывы и 31 % берут только ≥4.5★, отзыв
должен быть заметнее в discovery ([Searchlab](https://searchlab.nl/en/statistics/google-business-profile-statistics-2026)).
**Effort: S–M.**

VIS-5. **Просмотр по категориям/темам как первичная навигация** — *partial.* Есть
индекс городов и чипы типов, но нет богатого «category browse» с иконками и
описаниями отраслей, нет лендингов категорий (SEO-ценных) кроме city/type-страниц.
Stadtportal'ы строят навигацию вокруг категорий с подпиской на темы
([IQ-markt](https://www.iq-markt.de/stadtportal-erstellen-software.php)). **Effort: M.**

VIS-6. **Empty-state и «ничего не найдено»** — *gap.* Индекс при пустом пуле
отдаёт сухое «No offers yet»; для результатов поиска нет дружелюбного
empty-state с альтернативами/сбросом фильтра (Baymard: дружелюбный empty-state
удерживает значимо больше). **Effort: S.**

---

## Technical gaps

TECH-1. **Stadtgutschein / City-Gutschein (городской ваучер)** — *gap (с оговоркой
позиционирования).* Это **центральная** фича DACH-городских порталов и главный
аргумент для Stadtmarketing/Werbegemeinschaft: один ваучер, покупается на портале,
принимается у многих локальных продавцов, частичное погашение, QR/код на кассе,
авто-Abrechnung ([atalanda Stadtgutscheinsystem](https://atalanda.com/features/stadtgutscheinsystem),
[stadtguthaben](https://www.stadtguthaben.de/)). У нас loyalty/vouchers — per-tenant;
кросс-бизнес-ваучера на уровне портала нет. **Конфликт с инвариантом «без
комиссии»**: продажа/погашение ваучера через портал = денежный поток и почти
неизбежно settlement/комиссия. Решать как осознанную развилку (см. Recommendations).
**Effort: L.**

TECH-2. **Единая корзина / cross-business checkout (M14)** — *gap (намеренно
отложено в Stage 3).* Рынок «локально покупать онлайн» (Atalanda) это даёт; у нас
checkout есть per-бизнес (orders), но не кросс-tenant корзина+escrow+выплаты+
комиссия. Это **самый тяжёлый** конфликт с anti-marketplace/без-комиссии
([master-plan §8](../master-plan.md)). **Effort: L.**

TECH-3. **Öffnungszeiten + «открыто сейчас» (данные + фильтр + JSON-LD)** —
*gap.* Нет структурированных часов работы на Tenant/листинге → нельзя ни показать
«geöffnet», ни фильтровать, ни отдать `openingHoursSpecification` в `LocalBusiness`
JSON-LD (важный сигнал Map Pack). GBP-планка делает это базовым ожиданием.
**Effort: M.**

TECH-4. **Self-serve Featured через Stripe (P2.4b)** — *partial.* `featured_until`
есть, но ставит только супер-админ; самообслуживания (бизнес сам оплачивает
продвижение через Stripe) нет. Это **монетизация, совместимая с позиционированием**
(плата за продвижение, не комиссия с оборота). **Effort: M.**

TECH-5. **Поиск: PG full-text / триграммы вместо icontains** — *partial.* `q` —
`icontains` по JSON `title` (матчит сериализованный текст, «для v1 достаточно» по
комментарию). Нет ранжирования по релевантности, опечаток, автоподсказок-бэкенда.
При росте пула качество поиска просядет. **Effort: M.**

TECH-6. **«ИИ-discovery» / структурированные данные для LLM** — *gap (стратег.).*
45 % потребителей уже спрашивают локальные рекомендации у ChatGPT/Gemini
([VyomEdge](https://www.vyomedge.com/blog/google-business-profile-complete-guide-2026)).
JSON-LD у нас частично есть (LocalBusiness/AggregateRating/ItemList), но нет
полноты (часы, цены-Offer на листингах портала, sameAs, geo на всех типах),
которая делает листинги «цитируемыми» ИИ. **Effort: S–M (доращивание JSON-LD).**

TECH-7. **Сезонные/тематические лендинги + локальный контент-SEO** — *gap.* Кроме
city/type и ending-soon рейла нет тематических коллекций («Weihnachtsmärkte»,
«Brunch München»), которые приносят локальный органик-трафик и удерживают портал
как контент-витрину. **Effort: M.**

---

## Recommendations

Цель: довести агрегатор до планки consumer-discovery **без** превращения в
комиссионный маркетплейс. Фокус — discovery + доверие + лидген на витрины
бизнесов; денежный поток оставляем на витринах тенантов (39 € без комиссии).

REC-1 (P0, дешево и в духе позиционирования). **Доращивание JSON-LD до
GBP/AI-планки** (TECH-6, TECH-3-данные): добавить `openingHoursSpecification`,
`Offer` с ценой на листингах портала, `geo`/`sameAs` везде. Это усиливает Map
Pack и делает листинги цитируемыми ИИ — чистый upside, ноль конфликта с
монетизацией. Сначала структура часов работы на Tenant.

REC-2 (P0, UX-планка). **Фасетные фильтры + сортировка + автоподсказки +
empty-state** (VIS-3, VIS-6, TECH-5): чекбоксы/слайдер цены-скидки, «открыто
сейчас», сортировка (ближе/оценка/цена/новизна), drawer-фасеты на мобиле,
дружелюбный empty-state. Чисто consumer-side, без бизнес-модели.

REC-3 (P1, доверие). **Богатая карточка бизнеса + лучшая презентация отзывов**
(VIS-2, VIS-4): Öffnungszeiten «открыто сейчас», фото-галерея (из витрины),
кнопки Route/Anrufen, распределение звёзд + свежие отзывы + ответ бизнеса.
Двигает конверсию и доверие; данные у нас уже почти все есть.

REC-4 (P1, карта). **Режим «Список / Karte» с пиктограммами по отраслям +
кластеризация** (VIS-1, VIS-5): сделать карту равноправным режимом портала/города,
типизированные иконки, category-browse с лендингами категорий (SEO). Leaflet/OSM
уже есть — без новых внешних зависимостей/ключей.

REC-5 (P1, монетизация-БЕЗ-комиссии). **Self-serve Featured через Stripe**
(TECH-4): дать бизнесу платить за продвижение строки самому. Совместимо с «39 €
без комиссии с оборота» (это плата за видимость, не % с продаж), и это
естественная вторая выручка портала.

REC-6 (P2, развилка — НЕ начинать без решения владельца). **Stadtgutschein**
(TECH-1) и **единая корзина** (TECH-2): максимально востребованы рынком, но прямо
конфликтуют с anti-marketplace/без-комиссии. Рекомендация: **не строить как
комиссионный маркетплейс.** Если Stadtgutschein всё же нужен под Stadtmarketing-
партнёрство — реализовать как **white-label для города/Werbegemeinschaft** с
прозрачной фикс-платой за обслуживание системы (не % с оборота бизнеса), сохраняя
инвариант. Единую корзину оставить в Stage 3 как явный opt-in отдельной модели.

REC-7 (P2, контент-SEO). **Тематические/сезонные лендинги категорий** (TECH-7):
дешёвый локальный органик-трафик, усиливает discovery без бизнес-модельных рисков.

Consumer-facing блоки/фильтры к добавлению (приоритет сверху): «открыто сейчас»,
диапазон цены/скидки, сортировка (ближе/оценка/цена/новизна), переключатель
Список/Karte, фото-галерея + Route/Anrufen на карточке бизнеса, распределение
звёзд, автоподсказки поиска, лендинги категорий.

Чего НЕ делать (защита позиционирования): эскроу/выплаты/комиссия с оборота;
обязательный аккаунт для брони (сохранить magic-link/гость); трекинг-куки на
витрине; навязчивые маркетинговые письма без Double-Opt-In (UWG §7).

---

## Prioritized backlog table

| ID | Заголовок | Тип | Почему (рынок) | Effort | Partial? | Приоритет |
|---|---|---|---|---|---|---|
| REC-1 / TECH-6,3-data | JSON-LD до GBP/AI-планки (часы/Offer/geo) | Tech | Map Pack ≈44 % кликов; 45 % спрашивают ИИ | S–M | partial | **P0** |
| REC-2 / VIS-3,6 + TECH-5 | Фасет-фильтры + сортировка + автоподсказки + empty-state | Visual/Tech | Baymard/Algolia faceted UX | M | partial | **P0** |
| REC-3 / VIS-2,4 | Богатая карточка бизнеса + презентация отзывов | Visual | 41 % всегда читают отзывы; фото→конверсия | M | partial | **P1** |
| REC-4 / VIS-1,5 | Режим Karte с пиктограммами + category-browse | Visual | Stadtportal-стандарт (карта+категории) | M | partial | **P1** |
| REC-5 / TECH-4 | Self-serve Featured (Stripe) | Tech | монетизация без комиссии с оборота | M | partial | **P1** |
| REC-7 / TECH-7 | Тематические/сезонные лендинги категорий | Tech | локальный контент-SEO | M | gap | **P2** |
| TECH-3-fn | Öffnungszeiten: данные + «открыто сейчас» фильтр | Tech | GBP-планка ожиданий | M | gap | **P1** |
| REC-6 / TECH-1 | Stadtgutschein (white-label, фикс-плата) | Tech | центральная фича Atalanda/Stadtportal | L | gap | **P2 (развилка)** |
| REC-6 / TECH-2 | Единая корзина / cross-business checkout (M14) | Tech | «локально покупать онлайн» | L | gap | **P3 (Stage 3, развилка)** |

P0 — дёшево и строго в духе позиционирования (SEO/AI + UX-планка). P1 — доверие/
карта/монетизация-без-комиссии. P2/P3 — рыночно сильное, но требует решения по
монетизации (защитить инвариант «39 € без комиссии»).

### Источники
- atalanda / Online City Wuppertal: https://atalanda.com/wuppertal , https://atalanda.com/features/stadtgutscheinsystem , https://www.monheimer-lokalhelden.de/mitmachen/haendler
- Stadtgutschein-системы: https://www.stadtguthaben.de/ , https://www.avs.de/staedte/citygutschein , https://prokommun.de/cms/333-prokommun-blog/faqs-moeglichkeiten-und-einfuehrung-eines-city-gutscheinsystems.html
- Stadtportal-софт: https://www.ebiz-trader.de/stadtportal-marktplatz.htm , https://www.iq-markt.de/stadtportal-erstellen-software.php , https://www.fietz-medien.de/unternehmen/leistungen/regionale-marktplaetze/index.html
- Вертикальные агрегаторы: https://www.g2.com/products/quandoo/reviews , https://www.getapp.com/retail-consumer-services-software/a/treatwell/
- Google Business Profile / Map Pack: https://searchlab.nl/en/statistics/google-business-profile-statistics-2026 , https://www.vyomedge.com/blog/google-business-profile-complete-guide-2026
- Search/List UX: https://baymard.com/blog/current-state-product-list-and-filtering , https://www.algolia.com/blog/ux/mobile-search-ux-best-practices
