# A8 Aggregator/Portal (локальный discovery-портал, e.g. hotels.<base>) — рынок ↔ функционал — 2026-06-30

> **Шаг 7** серии (индекс: `docs/market-gap-audit-2026-06-30-index.md`).
> Метод: воркфлоу 15 агентов → синтез → **адверсариальная проверка 11 гэпов**
> (6 CONFIRMED_MISSING, 5 PARTIAL, 0 ложных). Бенчмарк: Google Business Profile/Maps,
> Yelp, TripAdvisor, Trustpilot, Das Örtliche/Gelbe Seiten/11880, Trivago/HRS/Booking,
> TheFork/Lieferando, Treatwell, Regiondo/GetYourGuide, региональные city-порталы.
> **Отдельного демо-кита НЕТ** — портал `hotels.<base>` как side-effect `--kit hotel`.
> Снапшот 2026-06-25 — `market-analysis/a8-aggregator.md`.

## 0. Вывод одной фразой

A8 — **достоверный discovery-скелет** с реальным **структурным преимуществом**
(агрегатор = вид поверх ПЛАТЯЩИХ тенантов, нет cold-start/crawl/dedupe) и двумя
сильными столбами: **hotel-метапоиск** (Trivago-shaped: живой поиск дат/гостей с
cheapest-room/тариф/авто-скидкой per-hotel) и **программные city×type SEO-страницы**.
Отстаёт от лидеров на: **claim-your-business** (вся воронка монетизации, отсутствует),
review-доверие/право (ответы владельца, жалобы, EU-Omnibus/UWG), портал-only асимметрия
(бизнес-страница/отзывы 404 на главном `/entdecken`), отдельный демо-кит.

## 1. Структура сайта (карта страниц)

| Страница | Статус | Заметка |
|---|:--:|---|
| Главная агрегатора `/entdecken/` | ✅ | city-директория + «Ending soon» + поиск |
| Результаты поиска | ✅ | `listings_for()`, cursor-пагинация, featured-блок, рейтинги; deep-link на витрину |
| **City landing (SEO)** `/entdecken/<city>/` | ✅ | type-чипы, sort, rating/open-now фасеты, карта, near-me, ItemList JSON-LD, canonical, sitemap |
| **City+type landing (SEO)** | ✅ | сужение по business_type, отдельные пары в sitemap |
| Брендовый vertical/city-портал (hotels.<base>) | ✅ | мультидомен, middleware-swap urlconf; hotel-порталы collapse по отелю + живой поиск дат |
| Портал facet (одна свободная ось) | ✅ | city-портал→по типу, vertical→по городу |
| **Деталь листинга на портале** | ❌ | нет — карточка deep-link'ит на витрину тенанта |
| Бизнес-профиль `/unternehmen/<slug>/` | 🟡 | **только на портале** (404 на главном `/entdecken`); контакты+листинги+рейтинг+отзывы+форма, LocalBusiness+AggregateRating JSON-LD |
| Отзывы + сабмит | 🟡 | часть бизнес-страницы (портал); вход PortalUser; 1 отзыв/юзер/бизнес; «Verifizierter Gast» badge |
| Favorites/saved | 🟡 | только портал (FavoriteListing) |
| Портал-логин (PortalUser, magic-link) | 🟡 | только портал; на главном `/entdecken` логина нет |
| ЛК (cross-tenant) | 🟡 | saved + брони по email + central marketing opt-out (только портал) |
| **Правовое (Impressum/Datenschutz/AGB) на портале** | ❌ | нет — у тенант-витрин есть, у портала нет |
| Sitemap/robots (main + per-portal) | ✅ | |
| **Claim-your-business** | ❌ | нет flow вообще |

## 2. Что уже есть (сильные столбы)

Мультитенантная cross-schema директория (денормализ. snapshot) · **city + city×type
SEO-страницы** · гео/near-me/карта · **hotel-метапоиск** (живой поиск дат с
cheapest-room/тариф/авто-скидкой + collapse per-hotel + date-carrying deep-links) ·
агрег. рейтинги (BusinessRating) + **отзывы с верифиц. «Verifizierter Gast»** ·
favorites · **magic-link портал-логин** (PortalUser) · cross-tenant ЛК ·
**featured/sponsored через Stripe self-serve** (P2.4b: 7/14/30 дней, webhook) ·
ItemList/LocalBusiness/AggregateRating/CollectionPage JSON-LD (частично) ·
sitemap/robots/canonical · deep-link-handoff в рабочую воронку брони тенанта.

## 3. Матрица «рынок ↔ наш статус»

| Фича рынка | Важн. | Статус | Заметка |
|---|:--:|:--:|---|
| Cross-listing директория | must | ✅ | snapshot-синк |
| **Full-text поиск + autosuggest/typo/synonyms** | must | 🟡 | только icontains по 3 полям, main-домен; нет ранжирования/typeahead |
| Category/city/type фасеты | must | ✅ | |
| Rating-фасет (min ★) | should | ✅ | только city-страницы |
| Open-now фасет | should | ✅ | фильтр (не per-card badge) |
| Гео/карта/near-me/radius | must | ✅ | |
| **City + category SEO landing** | must | ✅ | сильная сторона |
| Listing/business detail | must | 🟡 | бизнес-страница только на портале; на главном нет |
| Агрег. отзывы+рейтинг + верифик. | must | ✅ | «Verifizierter Gast» (но не gating сабмита) |
| **Ответы владельца на отзывы** | must | ❌ | нет поля/вьюхи |
| **Report/flag + fake-review контроль** | must (EU Omnibus/UWG) | ❌ | авто-публикация, только ручной super-admin hide |
| Фото в листингах | should | 🟡 | один image; **нет галереи/лайтбокса** (CDN есть) |
| **Per-card live open/closed badge** | should | ❌ | open-now только как фильтр |
| Часы работы | should | ✅ | данные есть |
| **Claim-your-listing + owner-management** | must | ❌ | **отсутствует** (вся воронка монетизации) |
| **Featured/sponsored (монетизация)** | should | 🟡 | **Stripe self-serve ЕСТЬ**; label «Empfohlen», не «Anzeige» (UWG) |
| **Sort (rating/price/popularity/relevance) + price-фасет** | must | 🟡 | только newest/name; price-фасета нет (хотя цены хранятся) |
| Structured data (LocalBusiness/ItemList/AggregateRating) | must | 🟡 | ItemList на city; LB+AggRating только на портал-бизнес-странице |
| **openingHoursSpecification/Review/Breadcrumb/sameAs JSON-LD** | should | ❌ | не эмитятся |
| Sitemaps/canonical | must | ✅ | |
| hreflang/мультиязык на портале | should | ❌ | DE-only, нет переключателя на портале/`/entdecken` |
| Favorites/saved | should | ✅ | только портал |
| Deep-link/booking handoff | must | ✅ | в рабочую воронку тенанта |
| **Claim→manage→insights→ads флайвил** | — | ❌ | нет owner-аналитики/leads/click-tracking |
| Vertical-порталы | should | ✅ | hotels.<base> |
| **Правовое оператора (Impressum/DSGVO/AGB)** | must (DACH) | ❌ | у портала нет |
| **Отдельный демо-кит A8** | — | ❌ | только side-effect `--kit hotel` (1 отель, без гео/featured) |

## 4. Недостающий функционал — приоритизировано (верифицировано)

### 4a. SEO-полнота (дёшево, высокий органик-ROI)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| G1 | **openingHoursSpecification + Review + BreadcrumbList + sameAs JSON-LD** + вывести LocalBusiness/AggregateRating на главный `/entdecken` (данные часов уже есть) | CONFIRMED_MISSING | S |
| G2 | **Вынести портал-only фичи** (бизнес-страница/отзывы/favorites/логин) на главный `/entdecken` ИЛИ cross-linked detail (сейчас рейтинги на `/entdecken` ведут «в никуда») | CONFIRMED_MISSING | M |
| G3 | **Правовое оператора** (Impressum/Datenschutz/AGB) на портале + переключатель языка/hreflang | CONFIRMED_MISSING | S |

### 4b. Монетизация / data-quality флайвил (то, чем живут все лидеры)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| G4 | **Claim-your-business flow + verified-owner badge** (верхушка воронки монетизации; полностью отсутствует) | CONFIRMED_MISSING | **L** |
| G5 | **Self-serve featured: корректная маркировка «Anzeige/Sponsored»** (Stripe self-serve УЖЕ есть; нужен только UWG-лейбл вместо «Empfohlen») | PARTIAL | **S** |
| G6 | **Owner-аналитика/leads dashboard** + outbound click/call/route-tracking (обоснование featured-fee) | CONFIRMED_MISSING | M |

### 4c. Доверие / право отзывов (EU Omnibus/UWG)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| G7 | **Ответы владельца на отзывы + report/flag + fake-review контроль** (+ transaction-gating сабмита, раскрытие верифик.) | PARTIAL | M |

### 4d. Поиск / выдача / карточки
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| G8 | **Sort-оси** (rating/price/popularity/relevance) + **price-фасет** (цены хранятся, не используются) | PARTIAL | M |
| G9 | **Full-text поиск** с autosuggest/typo/synonyms (Postgres FTS/trgm → Typesense/OpenSearch) | PARTIAL | L |
| G10 | **Фото-галереи** (multi-image + лайтбокс) + **per-card live open/closed badge** (CDN уже есть) | PARTIAL | M |

### 4e. Демо
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| G11 | **Отдельный A8 демо-кит**: мультибизнес + геокодинг + featured + отзывы (сейчас только 1 негеокодированный отель как side-effect) — D10 общего аудита | CONFIRMED_MISSING | M |

## 5. Сравнение с лидерами

- **vs Google Business/Maps** — паритет директории + city×type SEO + гео + deep-link +
  агрег. рейтинги + частичный JSON-LD. Отсутствует defining-флайвил Google:
  **claim→manage→insights→ads** (нет claim, нет owner-аналитики, нет ответов владельца,
  нет openingHoursSpec/Review/Breadcrumb, нет autosuggest, нет per-card live-badge).
- **vs Yelp** — есть отзывы с верифик. механизмом + AggregateRating (верный фундамент);
  не хватает fraud-фильтра, report-flow, ответов владельца, и критично — отзывы/
  бизнес-страница **404 на главном `/entdecken`**. Featured есть (Stripe self-serve),
  но label «Empfohlen» вместо UWG «Anzeige».
- **vs Trivago** — **сильнейшая зона**: живой поиск дат с cheapest-room/тариф/авто-скидкой
  per-hotel + date-carrying deep-links = реально метапоиск-shaped. Гэп: мультиисточниковое
  сравнение цен (индексим только своих тенантов, не конкур-OTA — G11c-e отложено) + демо
  с 1 негеокодированным отелем.
- **vs TheFork** — хорошо повторяем deep-link-в-воронку-брони (нет cold-start, каждый
  листинг = реальный тенант). Не хватает: трекинг outbound-конверсий для биллинга/статы,
  transaction-tied отзывы, живой availability для deals/events (не только отели).

**Net:** A8 — один из более зрелых архетипов со структурным преимуществом (вид поверх
платящих тенантов). Приоритет к паритету: (1) дешёвая SEO-полнота (JSON-LD + вынос
бизнес-страницы на главный домен); (2) флайвил claim→manage→insights→self-serve-featured;
(3) review-доверие/право (ответы/жалобы/Omnibus-UWG); (4) отдельный геокодированный демо-кит.

## 6. Сквозные подтверждения

- **Featured-монетизация уже есть** (Stripe self-serve P2.4b) — поправка к старым доводам;
  нужен только UWG-лейбл. Adversarial-проверка это уточнила.
- AGB/правовое — снова подтверждено (теперь и на стороне портала, не только тенанта).
- Язык/hreflang — портал DE-only (как и публичный домен; см. общий аудит, заметка корректна).
- D10 (отдельный демо-кит портала) — подтверждён.

## 7. Связанные
`docs/archetype-completeness-audit-2026-06-30.md` (D10) · `docs/market-gap-a5-2026-06-30.md`
(hotel-метапоиск/Channel) · `docs/portal-setup.md` · `docs/market-analysis/a8-aggregator.md`
(снапшот) · `apps/aggregator`, `config/urls_public.py`, `config/urls_portal.py`.
