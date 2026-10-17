# В5 + Е3 — учёт результатов каталога города («Besuche aus dem Stadtportal»)

Дата: 2026-10-17. Решение владельца: `docs/backlog-portal-direction-2026-10-16.md` §3 В5 (строка 54), §6 Е3 (строка 88), §9 (строка 117) — «агрегаты: день × предложение × действие (просмотр · переход · обращение · заказ/заявка), демо отдельно; клик ≠ продажа» + экран владельца.

## 0. Что есть сегодня (разведка)

| Кусок | Где | Что делает | Вывод для В5 |
|---|---|---|---|
| `featured_impressions` / `featured_clicks` | `apps/aggregator/models.py:182-183` | накопительно и только пока позиция оплачена | оставить как есть (§7) |
| показ featured | `apps/aggregator/views.py:297-316` `split_featured` | F()-инкремент при рендере блока | при попадании в кэш страницы показ не считается (тело из кэша) |
| клик featured | `apps/aggregator/views.py:319-337` `featured_click`; роуты `config/urls_portal.py:72`, `config/urls_public.py:74` | +1 и редирект на `portal_url` | образец редирект-счётчика |
| ссылки карточек | `templates/aggregator/_cards.html:8-9` | обычная карточка ведёт на `aggregator-offer` (внутренняя страница), featured — на `klick/` и сразу на сайт бизнеса | «переход к продавцу» для обычных карточек происходит на странице предложения |
| CTA страницы предложения | `templates/aggregator/offer.html:63` `href="{{ listing.portal_url }}"` | прямая ссылка, ничего не считает | переводим на редирект |
| «Zur Website» | `templates/aggregator/portal_business.html:44`; shortlist `templates/aggregator/shortlist.html:19,42` | прямые ссылки | тоже на редирект |
| страница предложения | `apps/aggregator/views.py:962-963` `@cache_public_page def offer_page` | HTML кэшируется (P0-1) | счётчик просмотров — снаружи кэша |
| кэш | `apps/core/pagecache.py:193-222` `cache_public_page`, `_cacheable` :71-116 | GET без query, без сессии; ответ с cookie или изменённой сессией в кэш не идёт | счётчик не должен трогать сессию и cookie |
| атрибуция | `apps/aggregator/models.py:294-323` `with_channel`/`portal_url` | `?ch=portal&hl=<lang>` | ID листинга в ссылку не попадает, добавим `cl=` только в редиректе |
| канал на витрине | `apps/promotions/public_views.py:142-147` `_capture_channel` | пишет `src_ch` в сессию (создаёт cookie) | это уже есть — §12 вопрос 1 |
| каналы сделок | `orders/public_views.py:1017`, `booking/public_views.py:933,1110`, `stays/public_views.py:694`, `jobs/public_views.py:101,187` — `request.GET.get("ch")`; promotions :2370/2467/2575 — форма или сессия | у заказа `ch` читается из GET POST-запроса оформления, а там его почти никогда нет | атрибуция заказов из портала сегодня фактически теряется |
| воронка акции T-8.6 | `apps/promotions/channels.py`, `PromotionChannelView` `promotions/models.py:589-607` | просмотры витринной страницы акции по каналу + резервы и купоны | оставляем: это прибытия на витрину, другой смысл |
| прецедент агрегата | `SearchQueryLog` `aggregator/models.py:373-434`; запись `search_log.py:107-182` (UPDATE → create → IntegrityError → UPDATE в savepoint, fail-safe); purge :185-198; beat `config/settings/base.py:494`; настройки :271 | | копируем шаблон |
| лимит частоты | `apps/core/ratelimit.py:21` `hit()`, fail-open; фикстура `apps/aggregator/tests/conftest.py:8` `isolated_ratelimit` | | |
| фильтр ботов | **нет нигде** (по `HTTP_USER_AGENT` в `apps/` пусто) | | нужен новый хелпер |
| демо | `AggregatorListing.is_demo` `models.py:102`; `_offer_in_scope` `views.py:887-895` | | |
| панель результатов | `apps/core/marketing_home.py:89-162`, `_featured` :109-124 | | добавить метрику и ссылку |
| nav | `apps/core/nav_registry.py:144` `_e(...)`, хаб marketing :469-566 | | новый подпункт, не якорь |
| спарклайн | `apps/core/dashboard.py:8` `_sparkline_points` | | реюз |
| Ticket | `apps/events/models.py` — `source_channel` нет | | атрибутируем только в агрегат, поле не заводим |

## 1. Форма таблицы — РЕКОМЕНДАЦИЯ: одна SHARED-таблица `aggregator.PortalStat`

```
day            DateField
tenant_schema  CharField(63)
listing_kind   CharField(20, blank)   # "" = бизнес целиком (общий контакт)
source_ref     CharField(64, blank)
listing_id     IntegerField(null)     # ссылка для отображения, НЕ FK (листинг пересоздаётся синком)
action         CharField(12)          # impression | view | click | contact | deal
channel        CharField(12)          # portal | entdecken | feed | digest (v1 пишет portal/entdecken)
is_demo        BooleanField           # копия tenant/listing.is_demo, ставится при create
count          PositiveIntegerField
UniqueConstraint(day, tenant_schema, listing_kind, source_ref, action, channel) "agg_pstat_uniq"
Index(tenant_schema, -day) "agg_pstat_tenant_day_idx"   # экран владельца
Index(-day) "agg_pstat_day_idx"                         # purge
```

Почему SHARED, а не per-tenant:
1. Пишет в основном портал, а он работает в контексте public-схемы. Для per-tenant таблицы пришлось бы переключать `schema_context` на каждый просмотр.
2. Ключ `(tenant_schema, listing_kind, source_ref)` совпадает с уникальным ключом листинга (`models.py:201-204`). История переживает удаление и пересоздание листинга.
3. Прецеденты: `featured_*` и `SearchQueryLog` уже лежат в public.

Владелец видит только `tenant_schema=connection.schema_name`, как `_featured` в `marketing_home.py:115`. Это держит замок.

Почему ключ — `source_ref`, а не FK на листинг: FK с `SET_NULL` дал бы NULL в уникальном ключе, а это ломает агрегацию (урок `SearchQueryLog`, комментарий `models.py:393`). `listing_id` нужен только для заголовка на экране.

Почему `is_demo` колонкой, а не частью ключа: демо — свойство бизнеса, а не измерение.

Апсерт — шаблон `search_log._log` (UPDATE с F() → create в savepoint → IntegrityError → UPDATE). Сырой `ON CONFLICT DO UPDATE SET count = count + EXCLUDED.count` можно взять только в flush (§2.6), если database-reviewer выберет его ради пакетности. `bulk_create(update_conflicts=True)` инкремент выразить не умеет.

## 2. Где записывается каждое действие

Единая точка: `apps/aggregator/portal_stats.py` с функцией `record(request|None, *, listing=None, tenant_schema=None, kind="", ref="", action, channel, is_demo)`. Внутри по порядку: фильтр бота → дедуп → лимит частоты → буфер. Функция fail-safe, как `search_log.log`.

### 2.1 view — открыта страница предложения
- Новый декоратор `count_offer_view` СНАРУЖИ `@cache_public_page` (порядок: `@count_offer_view` → `@cache_public_page` → `offer_page`). Он срабатывает и при попадании в кэш, и при промахе. Считает только ответ 200 на GET.
- Листинг грузится одним `values()`-запросом по pk. При промахе это дублирует запрос вьюхи — допустимо. Как альтернативу можно класть `pk/tenant_schema/is_demo` в ключ кэша рядом с телом; не нужно, pk уже в пути.
- Декоратор ничего не пишет в сессию и cookie, поэтому `_cacheable` не меняется. Замок обязателен.
- Ровно та же обёртка — на `business_page` (`reviews_views.py:55`): view бизнеса, `listing_kind="business"`.
- 301-редирект `offer_page` для kind=business (`views.py:978-984`) не считается: статус не 200.

### 2.2 impression — карточка видна в списке (Е3)
РЕКОМЕНДАЦИЯ: JS-маячок, не серверный подсчёт. Списки отдаются из кэша (корень портала, район, `/entdecken/`), и какие карточки были в теле из кэша, сервер не знает. Сэмплинг или запись при рендере врали бы: бот = показ, попадание в кэш = 0.
- `_cards.html` получает `data-pstat="{{ l.pk }}"` на `<article>`. Атрибут одинаковый для всех посетителей, поэтому кэш безопасен.
- Скрипт в `aggregator/portal_base.html` и `aggregator/_base.html` использует IntersectionObserver (≥50 % карточки, ≥1 с). Пачка уходит через `navigator.sendBeacon` на `POST /b/` (портал и `/entdecken/b/`) при `visibilitychange=hidden` или каждые 10 с. В пачке ≤48 pk, повторы внутри страницы снимаются на клиенте.
- Эндпоинт: `@csrf_exempt` (sendBeacon не несёт токен). Принимает только `Sec-Fetch-Site: same-origin` или Origin = хост; тело JSON со списком int, ≤48 pk. pk фильтруется через `AggregatorListing.objects.public()` и `_offer_in_scope(portal)`. Ответ всегда 204 без тела, `Cache-Control: no-store`.
- Бонус: маячок сам отсекает ботов без JS.
- Featured-показы `split_featured` не трогаем (§7).

### 2.3 click — переход к продавцу
РЕКОМЕНДАЦИЯ: серверный редирект на стороне портала, а не подсчёт прибытия `?ch=portal` на витрине. Портал знает pk листинга; витрина не знает, с какой карточки пришёл человек, и до сделки он может уйти дальше.
- Новый роут `weiter/<int:pk>/`, имя `aggregator-outbound`. В `urls_portal.py` — до catch-all `<str:facet>/` (строка 88); в `urls_public.py` — как `entdecken/weiter/<int:pk>/`.
- Логика как у `featured_click`: `public()` + `_offer_in_scope`. Иначе `redirect("/")` без счёта.
- Цель = `listing.portal_url` + `cl=<pk>`: новый параметр `with_channel(..., listing_ref=True)`, по умолчанию False, поэтому замки фида `test_machine_readable.py:577` не меняются. Не-http цель → «/» (`views.py:335`).
- `Cache-Control: no-store`, ссылки получают `rel="nofollow"`.
- Перепривязать ссылки: `offer.html:63`, `portal_business.html:44`, `shortlist.html:19,42`.
- `featured_click` дополнительно вызывает `record(action="click")`; `featured_clicks` по-прежнему +1 (замок регрессии D2.3).
- JSON-LD и canonical не меняются: там чистый `detail_url`.

### 2.4 contact — начатое обращение
v1: обращение отправлено с витрины бизнеса после прихода из портала:
- форма сообщения `apps/inbox/public_views.py:64` `contact` (Conversation создана);
- Rückruf / анкета AF-2 `_message_form` с любой страницы.

Анкета `/anfrage/` (Job) — это «заявка», то есть `deal` (решение владельца: «созданный заказ/заявка»).

Касания `tel:`/WhatsApp на портале — v2 (§12 вопрос 6): нужен редирект на `tel:`, а браузеры ведут себя по-разному.

### 2.5 deal — создан заказ / заявка
Поток атрибуции без cookie (РЕКОМЕНДАЦИЯ, §12 вопрос 1):
1. Редирект §2.3 приводит человека на витрину с `?ch=portal&cl=<pk>&hl=..`. Страница с query мимо кэша (`pagecache.py:163-164`), значит рендерится для этого запроса.
2. Новый тег `{% portal_attribution_fields %}` (`apps/core/templatetags/…`) переносит `ch`/`cl` из GET в скрытые `<input>` с проверкой формата: `ch` ∈ {portal, entdecken}, `cl` — цифры. Тег ставится в общие формы:
   - `_buybox.html` (корзина, бронь, заявка);
   - `_anfrage_form` / `_message_form` (AF-2);
   - формы промо-резерва, купона и билета.

   Промо-форма уже несёт скрытое поле `channel` (`promotions/public_views.py:2362`) — это прецедент.
3. Многошаговый путь корзины: при добавлении в корзину (сессия создаётся для необходимой цели — корзины) `attribution.remember(request)` кладёт `src_ch`/`src_cl` в ту же сессию. Без существующей или необходимой сессии ничего не пишется. Новых cookie нет.
4. Новый `apps/core/attribution.py`:
   - `channel(request)`: POST-поле → GET → сессия → "";
   - `listing_ref(request)`: `cl` проверяется так, что листинг существует и его `tenant_schema` = текущая схема. Иначе отбрасывается, и нельзя накрутить чужого.
5. Точки записи — после создания сделки, через `transaction.on_commit`: `orders/public_views.py:1007` (create_order; заодно `source_channel` берётся из `attribution.channel` вместо GET — фикс), `booking/public_views.py:933,1110`, `stays/public_views.py:694`, `jobs/public_views.py:101,187`, промо-резерв/купон (`promotions/public_views.py:2370,2467,2575`), билеты (events, поле канала не заводим). Пишем только при `channel` ∈ городских.
6. Листинг сделки: `cl`, если он валиден. Иначе отображение самой сделки на `(kind, source_ref)` (акция → promotion, услуга → service, номер → stay, билет → event, товар единственной строки → product). Иначе строка бизнеса (`listing_kind=""`).

Честность: deal засчитывается только внутри того же визита. Вернувшийся через три дня покупатель не попадёт (§12 вопрос 3). На экране это прямо написано.

### 2.6 Буфер и запись
Горячие действия (impression/view/click) пишутся `HINCRBY` в Redis-хэш `pstat:buf`, поле `day|schema|kind|ref|listing_id|action|channel|demo`. Beat `flush_portal_stats` раз в 5 минут:
1. атомарно `RENAME pstat:buf → pstat:flush:<uuid>`;
2. апсерт по строкам;
3. `DEL`.

Повторный flush не удваивает счёт — замок. Redis недоступен → прямой апсерт (fail-safe; сбой пишется в лог только типом исключения).

contact/deal редки — сразу прямой апсерт в `on_commit`.

## 3. Боты и злоупотребления
`apps/core/bots.py: is_bot(request)`. Не считаем:
- пустой UA;
- UA с подстроками bot / crawl / spider / slurp / preview / headless / facebookexternalhit / python-requests / curl / wget / httpclient / monitor / uptime;
- `Purpose: prefetch` или `Sec-Purpose: prefetch`;
- метод не GET (кроме маячка-POST);
- статус ≠ 200.

Дедуп без персональных данных: `v = HMAC(day_salt, ip + "|" + UA)[:16]`. Соль — 32 случайных байта в Redis `pstat:salt:<день>` с TTL 48 ч. После истечения хэш не восстановить. `SET pstat:seen:<день>:<action>:<listing>:<v> NX EX 90000`; ключ уже есть → не считаем. Redis недоступен → не считаем: недосчёт честнее накрутки.

Лимит частоты: `ratelimit.hit("pstat", ip, limit=300, window=3600)`. Превышение → тихо не считаем; страница отвечает как обычно, маячок — 204.

IP и UA в БД не попадают никогда — замок на поля модели, как в T-8.21.

## 4. Демо отдельно
`is_demo` берётся из листинга (`models.py:102`) или тенанта (`Tenant.is_demo`, T-8.15).
- Экран демо-тенанта показывает свои цифры с плашкой «Demo-Daten».
- Админка платформы по умолчанию фильтрует `is_demo=False` (`list_filter` + `get_queryset`).
- Показы демо на превью-портале (`show_demo`) пишутся с `is_demo=True` и не смешиваются в сводках платформы.

## 5. Ретеншн
Данных о людях нет, только объём. `AGGREGATOR_PORTAL_STATS = {"enabled", "retention_days": 400}` в `config/settings/base.py` рядом со строкой 271: 13 месяцев позволяют сравнить год к году. Beat `purge-portal-stats` раз в сутки — по образцу :494. Ранней чистки одиночных строк не нужно: свободного текста нет.

## 6. Экран владельца «Besuche aus dem Stadtportal» (Е3)
- URL `/dashboard/stadtportal/`, имя `portal-stats`, `config/urls_tenant.py`. Вьюха `apps/aggregator/owner_views.py`, сервис `apps/aggregator/owner_stats.py`. Декораторы `@login_required` + доступ к кабинету (замок орфан-декоратора); вьюха без хелперов между декоратором и `def`.
- nav: `_e("marketing", "portal-stats", _("Stadtportal"), "portal-stats", None, search="stadtportal besuche klicks statistik portal")` после «Bewertungen» (`nav_registry.py:511-518`). Не advanced, модуль None. Новый якорь не нужен — мораторий соблюдён. Вход в палитру Ctrl+K получаем вместе с записью.
- Период: чипы 7 / 30 / 90 / 365 дней (`?tage=`, белый список), по умолчанию 30, сравнение «▲/▼ vs. Vorperiode».
- Воронка — 5 плиток: «In Listen gesehen» (impression) → «Angebot geöffnet» (view) → «Weiter zu Ihnen» (click) → «Kontakt aufgenommen» (contact) → «Bestellungen & Anfragen» (deal). Под ней:
  - «Ein Klick ist kein Verkauf.»;
  - «Bestellungen zählen nur, wenn sie im selben Besuch nach dem Stadtportal entstanden sind.»;
  - «Besuche von Suchmaschinen und Bots zählen wir nicht.»
- Спарклайн по дням (view+click) — `dashboard._sparkline_points`.
- Таблица «Top-Angebote», 10 строк: заголовок из текущего листинга (`listing_id`, один запрос `in_bulk`), иначе «(nicht mehr im Stadtportal)»; колонки по 5 действиям.
- Строка «★ Anzeige: Aufrufe · Klicks» из существующих `featured_*` с подписью «seit Beginn der Anzeige» — иная семантика, поэтому не смешиваем.
- Пустые состояния:
  - `in_city_catalog=False` → «Ihr Angebot ist nicht im Stadtkatalog» + ссылка на настройку (T-8.6);
  - `email_pending` → «E-Mail bestätigen»;
  - нет данных → «Noch keine Besuche».
- Один агрегирующий запрос: `values("action").annotate(Sum)` + `values("day")` + top по `(kind, ref)`. Индекс `agg_pstat_tenant_day_idx`.
- `marketing_home.results_panel` получает метрику «Stadtportal (30 Tage): Aufrufe · Klicks» со ссылкой на экран, через `_safe`.
- CSV — v2. Если появится, добавить в `EXPECTED_UNLISTED` (прецедент `export-datev`).

## 7. Существующие featured-счётчики
РЕКОМЕНДАЦИЯ: оставить. `featured_impressions`/`featured_clicks` считают «пока оплачено, накопительно по окнам» и питают D2 и `marketing_home`. Выводить их из новой таблицы — значит data-миграция и потеря смысла.

Новая таблица считает всех, включая featured: клик по featured проходит через `featured_click` и тоже пишет `click`. Слить колонки можно позже отдельным решением.

## 8. Миграции
Одна: `apps/aggregator/migrations/0030_v5_portal_stats.py`. SHARED, аддитивная: CreateModel `PortalStat` + constraint + 2 индекса. Данных не переносит.

Тенантных миграций нет: Ticket атрибутируется только в агрегат, поля канала у моделей сделок уже есть.

database-reviewer проверяет: состав и порядок уникального ключа, индекс под экран, рост (худший случай ≈ листинги × 3 горячих действия в день → при 5 тыс. листингов ≈ 5,5 млн строк за 400 дней), HOT-апдейты (`count` не в индексе), сырой SQL flush (если выбран).

Деплой: `./scripts/deploy.sh single`; beat подхватит 2 новые записи при рестарте.

## 9. Замки (тесты ДО кода)
`apps/aggregator/tests/test_portal_stats.py`:
1. В модели нет персональных полей — whitelist имён полей, как `test_model_has_no_personal_fields` в T-8.21.
2. Дедуп: тот же IP+UA за день → 1; другой UA → 2; новая соль (новый день) → снова считается.
3. Боты: пустой UA, `Googlebot`, `Sec-Purpose: prefetch`, HEAD → 0.
4. P0-1: при включённом `PUBLIC_PAGE_CACHE_TTL` два анонимных GET страницы предложения от разных посетителей → view=2, второй ответ — из кэша. Ответ кэшируем (нет Set-Cookie, сессия пуста).
5. Маячок: чужой или непубличный pk игнорируется; демо на портале без `show_demo` игнорируется; >48 pk обрезается; без same-origin → 0; всегда 204; лимит частоты — с `isolated_ratelimit`.
6. Редирект `aggregator-outbound`: click +1, Location = `portal_url` + `cl=pk`; неизвестный или скрытый pk → «/» без счёта; `Cache-Control: no-store`.
7. `featured_click`: и `featured_clicks` +1, и строка `click` — регрессия D2.3.
8. Демо-листинг → строка `is_demo=True`; админка по умолчанию без демо.
9. flush: буфер → БД; повторный flush не удваивает; Redis недоступен → прямая запись.
10. purge по `retention_days`.

`apps/core/tests/test_attribution.py`:
11. Тег рендерит скрытые поля только для валидных `ch`/`cl`; мусор отбрасывается; XSS-строка не проходит.
12. Заказ с POST `ch=portal&cl=<свой pk>` → deal на этом листинге; `cl` чужого тенанта → по объекту или на бизнес; без `ch` → строки нет.
13. Посадка на витрину с `?ch=portal` не создаёт сессию и не ставит cookie. Отдельно: поведение промо-витрины `_capture_channel` — по решению §12 вопрос 1.

`apps/aggregator/tests/test_owner_stats.py`:
14. Экран видит только строки своей схемы.
15. Аноним → редирект на логин.
16. Воронка по фикстурам; тексты «Ein Klick ist kein Verkauf» и подпись про ботов присутствуют.
17. Пустые состояния (не в каталоге / почта не подтверждена).
18. Вход есть в nav-реестре: замки X7 `test_x0_x7_locks` и `test_nav_reachability` покрывают автоматически.

Стенд Playwright (390/1440): маячок шлёт pk видимых карточек; CTA «Zum Angebot» идёт через редирект; экран рисуется.

## 10. i18n
Новые msgid (≈25): подписи плиток, «Stadtportal», «Besuche aus dem Stadtportal», три поясняющие фразы, пустые состояния, «Top-Angebote», «(nicht mehr im Stadtportal)», «Demo-Daten», чипы периода, verbose_name модели и действий, метка панели `marketing_home`. Все в 5 `.po` (de/en/tr/ru/uk).

Гейт перед пушем: `scripts/i18n_quickcheck.py` + `scripts/i18n_untranslated.py`. Правило: никакого `_()` внутри f-строк.

## 11. Нарезка
- **V5-1 Фундамент** (миграция): модель, `0030`, `portal_stats.py` (record, bot, дедуп, буфер, flush, purge), `apps/core/bots.py`, настройки, 2 beat, админка (суперпользователь, фильтр демо). Замки 1–3, 8–10. Поверхностей нет — мерж безопасен.
- **V5-2 Портал**: `count_offer_view` на offer/business, роут `weiter/`, перепривязка 3 шаблонов, `featured_click` пишет click, `with_channel(listing_ref=)`. Замки 4, 6, 7.
- **V5-3 Экран владельца**: вьюха, сервис, шаблон, nav-запись, метрика `marketing_home`, i18n. Замки 14–18. Уже полезен: view/click есть.
- **V5-4 Показы (Е3)**: маячок JS + эндпоинт + `data-pstat` в `_cards.html` + Playwright. Замок 5. Нужна пересборка `app.css`, если появятся новые классы.
- **V5-5 Обращения и сделки**: `attribution.py`, тег скрытых полей в общих формах, `remember` в корзине, записи в 7 точках создания сделок, фикс `source_channel` заказа. Замки 11–13.

Перед каждым мержем: django-reviewer + security-reviewer. Маячок `csrf_exempt` и редирект — в центре security-ревью. database-reviewer — на V5-1.

## 12. Открытые вопросы владельцу
1. **Атрибуция без cookie.** Рекомендую скрытые поля + запись в уже необходимую сессию (корзина), без новой cookie на посадке. Сегодняшний `_capture_channel` (`promotions/public_views.py:142-147`) создаёт сессию при посадке с `?ch=`, а для атрибуции это спорно по TTDSG §25. Перевести его на ту же схему?
2. **«Показ»** = карточка ≥50 % на экране ≥1 с при включённом JS. Без JS (боты) не считается. Подходит такое определение?
3. **Окно атрибуции** — только тот же визит. Вернувшийся позже покупатель не засчитывается. Честный недосчёт приемлем?
4. **Фид и сводка жителю** (`ch=feed`/`digest`) ведут прямо на сайт бизнеса, мимо редиректа. Учитывать в v2? Это меняет ссылки фида: добавится `cl`.
5. **Ретеншн** 13 месяцев?
6. **Касания телефона/WhatsApp** на портале как «Kontakt» — v2?
7. **Строка в Datenschutzerklärung платформы** («агрегированная статистика посещений без cookie и без хранения IP»). Нужна правка текста владельцем или юристом.
8. **Сводка по всем бизнесам** в админке платформы — нужна (только суперпользователь), или достаточно экрана владельца?
