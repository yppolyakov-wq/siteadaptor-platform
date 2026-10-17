# Г1 / T-8.27 «Импорт с сайта клиента» — план (2026-10-17)

План составлен агентом planner по коду. Решения владельца: Р-A визитка · Р-B 50 позиций
(`IMPORT_FREE_ITEMS`) · Р-C v1 только сайт · Р-E общий ИИ-слой (AI-0, сделан).
Открытые вопросы §8 приняты ПО ДЕФОЛТАМ (владелец может поправить).

## 0. Вывод
- **Вариант (1), без новой SHARED-сущности.** «Внешний бизнес» = тенант (быстрый старт T-8.5
  уже создаёт его без пароля). Импорт пишет в его каталог (Product/Service/Category + профиль
  Tenant), дальше — штатный синк каталога города (`sync_*_listing`, `visibility.listable`).
- **Р-A визитка** = профиль витрины `site_config["profile"]="eintrag"` рядом с `aktionen`.
  Листинг товара/услуги в городе ведёт на ВНЕШНИЙ URL позиции.
- **Блокер:** `sync_product_listing` удаляет товарные листинги при `is_aktionen` — для
  `eintrag` своя ветка (листинг жив при проверенном `external_url`).
- `/weiter/<pk>/` уже безопасен (цель из БД, только http(s)).
- **Без ИИ** результат реален на магазинах (Shopify/Woo/Wix/Squarespace/JTL ставят
  Product/Offer JSON-LD); брошюра даёт только профиль (LocalBusiness/часы/адрес/OG) — экран
  честно говорит «Keine Artikel automatisch erkannt». С `AI_ENABLED` — разбор текста.

## 1. Точки в коде
| Что | Где | Вывод |
|---|---|---|
| SSRF | `core/ssrf.py::validate_public_url`, `safe_get` | **Дыра:** `requests.get` идёт по редиректам без проверки хопов; пиннинга IP нет. Новый `safe_fetch`, `safe_get` — на него |
| Парсеры | uv.lock: только nh3 | без новых пакетов: stdlib `html.parser`, `urllib.robotparser`, `xml.etree` с отказом на DOCTYPE/ENTITY |
| Мастер импорта | `apps/imports` (ImportJob/ImportRow, processors) | реюз места в кабинете, паттерна статусов, `_parse_decimal`; применение — свой сервис |
| Фото | `catalog/images.py::validate_image`, `save_product_image` | скачанное → ContentFile → штатное сохранение |
| Санитайз | `core/richtext.py` | описание — ПЛОСКИЙ текст, чужой HTML не переносим |
| ИИ | `apps/ai/api.py` | задача `site_import_extract` в `ImportsConfig.ready()`, вызов вне atomic, в Celery |
| Синк города | `aggregator/tasks.py::_product_snapshot` (фото+цена>0), `sync_*_listing`, `_withheld` | ветка `eintrag` + `external_url` |
| Атрибуция | `AggregatorListing.with_channel` | на чужой хост — только `ch` |
| Профиль | `Tenant.website_url` (уже есть), address, contact_phone, logo_url, opening_hours_structured | нового поля сайта не нужно |
| Права | `CabinetOwnerAccessMiddleware` (W9-10) | экран owner-only |

## 2. Пайплайн
1. **Старт** `/imports/website/`: URL (из `website_url`), обязательное согласие «Inhaber/berechtigt;
   Texte und Fotos dürfen übernommen werden» → `consent_at/by/version` (без IP); 1 активный прогон,
   ≤3 в сутки.
2. **Краулер** (Celery): `ssrf.safe_fetch` — без авто-редиректов, ≤5 хопов с проверкой каждого,
   сверка peer-IP после коннекта (rebinding), порты 80/443, лимиты байт/времени, allowlist
   content-type, инжектируемый транспорт. Тот же хост (+www), robots.txt (наш UA с контактом),
   sitemap.xml (≤1 МБ, ≤5000 loc, ≤1 уровень индекса), ссылки старта; приоритет товарных URL;
   ≤20 страниц × ≤2 МБ, бюджет 120 с, пауза 0,5 с, без query-дублей (`utm_*`). Тела не храним.
3. **Экстракция без ИИ:** JSON-LD (`@graph`, Product/Offer/AggregateOffer lowPrice, ItemList,
   Service, LocalBusiness+подтипы, OpeningHoursSpecification, PostalAddress, telephone, logo/image),
   OG (`og:*`, `product:price:*`), `<html lang>`, `tel:`.
   **С ИИ** (только при включённом слое, страницы без Product-JSON-LD): задача fast, рамка
   `<<<PAGE url=…>>>…<<<END>>>`, ≤6k символов на страницу; схема `items[{name, description, price,
   currency=EUR, kind, page_url, image_url, category_hint, duration_min?}]` — **без старой цены,
   процента, бейджа** (PAngV); пост-валидация: page_url/image_url — только из обойдённого, 0<цена≤100000.
   `AIError` → режим «nur strukturierte Daten». Дедуп: gtin > sku > (url+имя).
4. **Черновик** → `ready` → уведомление владельцу.
5. **«Prüfen & veröffentlichen»**: карточки (фото по внешнему URL с no-referrer), имя/цена/
   категория/источник, бейдж «KI-generiert, bitte prüfen» / «aus strukturierten Daten», статус дифа,
   чекбоксы, правка, категория; профиль — только пустые поля, остальное «Vorschlag»; «N von 50 frei».
6. **Применение** (≤50, лимит перепроверяется на сервере в atomic): Product/Service, базовая
   локаль, плоский текст, `base_price` как на сайте, `list_price=None`, без бейджа и акций,
   `external_url`, `metadata["import"]`; 1 фото через safe_fetch → validate_image → перекодировка;
   без фото/цены — пометка «erscheint nicht im Stadtkatalog».
7. **Повторный сбор + диф** (чистая функция): new/changed/unchanged/removed по `identity_key`/
   `fingerprint`; removed → «deaktivieren»; «Bestätigen» → `confirmed_at` (шов Г3). Без расписания.
8. **Язык:** `<html lang>` ≠ de → предупреждение; перевода нет.

## 3. Модели
TENANT `apps/imports` (`imports/0002`): `SiteImportRun` (start_url, host, status, consent_*, pages,
html_lang, method, ai_used, error_code, stats, previous_run, started/finished) и `SiteImportItem`
(run, kind, diff, decision, source_url, data, fingerprint, identity_key, ai_generated, target_kind/id,
applied_at, confirmed_at, errors). `catalog/0037` Product.external_url, `booking/0029`
Service.external_url (аддитивные). SHARED-миграций нет. Settings: `IMPORT_FREE_ITEMS=50`,
`SITE_IMPORT_MAX_PAGES=20`, `…_MAX_PAGE_BYTES`, `…_MAX_IMAGE_BYTES`, `…_TIME_BUDGET_S=120`,
`…_USER_AGENT`, `…_DAILY_RUNS=3`.

## 4. Визитка «eintrag»
Главная = карточка бизнеса (`core/business_card.py`) + «Zur Website →»; акции работают; каталог/
корзина/наборы → 302 (`catalog_hidden` = профиль ∈ {aktionen, eintrag}). Синк: листинг товара
пишется, только если `external_url` https и хост = хост `website_url` (иначе удаляется — защита от
подмены), `detail_url = external_url`; бизнес-листинг — на визитку. `with_channel` на чужой хост —
только `ch`. Обычный тенант со своей витриной: `external_url` лишь хранится («Original»).

## 5. Безопасность
SSRF (каждый хоп, peer-IP, порты, размер/время, content-type; фикс редиректов `safe_get` отдельным
коммитом), XML без DOCTYPE/ENTITY, prompt injection (рамка, схема без опасных полей, allowlist URL,
только черновик), XSS (plain + autoescape, только http(s) URL), owner-only + login_required, лимиты,
robots + UA, согласие правообладателя, тела страниц не храним, фото перекодируем.

## 6. Замки (до кода, без сети)
`core/tests/test_ssrf_fetch.py` · `imports/tests/test_site_crawl.py` · `test_site_structured.py` ·
`test_site_ai.py` · `test_site_apply.py` · `test_site_diff.py` · `test_site_views.py` ·
`aggregator/tests/test_eintrag_profile.py` (поимённо — отчёт planner'а, сохранён в истории сессии).

## 7. Инкременты
a транспорт `safe_fetch` · b обход + structured + черновик (`imports/0002`) · c «Prüfen &
veröffentlichen» + применение (`catalog/0037`, `booking/0029`) · d профиль `eintrag` + синк ·
e ИИ-экстракция · f повторный сбор + диф · g i18n, демо, доки. Отложено: Google/Instagram/Shopify,
Г3, перевод, несколько фото, варианты, PDF-меню, вход с `/aktion-starten/`.

## 8. Вопросы владельцу — приняты по дефолту
1. robots.txt запрещает — уважаем и объясняем, как разрешить.
2. Лимит 50 — на тенантов без активной подписки; считаем активные импортированные позиции.
3. Ссылка на чужой сайт — только `?ch=portal`.
4. Вход v1 — кабинет «Von Website importieren» (поле на `/aktion-starten/` — позже).
5. Заполненные поля профиля — только предложение.
6. Без фото/цены — в каталог с пометкой, в город не выкладываем.
7. Визитка — своя страница на поддомене (бизнес-листинг ведёт на неё).

## 9. Ревью перед мержем (django-reviewer + security-reviewer) — закрыто

- **Владение сайтом (security H1/H2, django HIGH 3).** Токен бизнеса = HMAC(SECRET_KEY, схема)[:24];
  владелец кладёт `<meta name="siteadaptor-verify" content="…">` на главную или
  `/.well-known/siteadaptor-verify.txt`. Проверка — `apps/imports/site/verify.py` через `safe_fetch`,
  при выполнении прогона и кнопкой «Jetzt prüfen». Результат — `SiteImportRun.verified_at/
  verified_method` (схема тенанта; в `site_config` не храним — туда пишет сам владелец). Повторные
  импорты того же сайта подтверждаются по прежнему (`known`). Без подтверждения: прогон только
  просмотр (`ApplyError("unverified")`, профиль не пишется), `website_url` не ставится, внешние ссылки
  каталога города (`_external_url`) и кнопка «Zur Website» сверяются с подтверждённым хостом, а не с
  `website_url`. IP-литералы и хосты платформы как «свой сайт» не принимаются.
- **«Nur Eintrag»** проверяется на сервере (`_can_eintrag`: применён, подтверждён, `website_url` https
  на подтверждённом хосте), запись — свежей строкой тенанта, затем `reconcile_city_catalog`.
- **Прогоны:** reaper (`queued/crawling` старше 15 мин → `failed/stale`), сбой брокера →
  `failed/queue`, `soft_time_limit=600`, advisory-lock старта.
- **Транспорт/обход:** `not is_global` (+6to4/Teredo/mapped), битый порт и scope-id → `SsrfError`,
  https→http редирект запрещён, общий `deadline`; robots 401/403/5xx → не обходим, 404 → без правил,
  robots и для цели редиректа, Crawl-delay (≤5 с), кап 500 ссылок/страница и 5000 адресов; неполный
  обход (`partial`) не порождает «removed».
- **Применение:** UUID-категория; повторный импорт не трогает `is_active`/`list_price`/`badge`/
  `primary_action` и не ставит цену 0 без цены на сайте; удалённая цель → позиция «новая», лимит не
  занят; статус перепроверяется под lock (`not_ready`/`stale`), при лимите/ошибке прогон остаётся
  «Bereit», ошибки показываются по названиям; Pillow `formats=JPEG/PNG/WEBP`, ≤25 Мпикс, без
  анимации; dedupe-ключ фото со временем; профиль — в свежую строку тенанта.
- **Схема:** `UniqueConstraint(run, identity_key)`, частичный индекс `(identity_key, -applied_at)`.
- **Не делали (низкий риск, записано):** L3 `plain()` раскрывает сущности — вывод везде под
  автоэкранированием; L8 фото с CDN сайта не ограничены хостом; L9 rate-limit старта — суточный
  лимит прогонов + один активный.
