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

## 13. Решения владельца (2026-10-17)

1. Атрибуция — **скрытые поля форм + уже необходимая сессия корзины**, новых cookie нет;
   `_capture_channel` акций переводится на ту же схему (V5-5).
2. Окно атрибуции — **только тот же визит**; на экране так и написано.
3. Остальное — **по рекомендации**: показ = карточка ≥ 50 % на экране ≥ 1 с (JS);
   ретеншн 13 месяцев (400 дней); фид/сводка жителю и tel:/WhatsApp — v2; сводка по всем
   бизнесам — в админке платформы только суперпользователю. Строка о статистике в
   Datenschutzerklärung платформы — за владельцем/юристом.

## 14. Отступление при реализации V5-1

Буфер в Redis (§2.6, `HINCRBY`/`RENAME` + beat flush) не делаем: кэш проекта — штатный
`django.core.cache.backends.redis.RedisCache`, этих команд в его API нет. Запись — сразу,
после дедупа, ОДНИМ `INSERT … ON CONFLICT DO UPDATE` на пачку (маячок шлёт до 48 карточек =
один запрос). Замки буфера/flush (§9 п.9) заменены на «сбой БД не роняет страницу» и
«недоступный кэш — не считаем». Beat один — `purge-portal-stats`.

## §15. V5-2 — детальный план (портал: view + click)

Что сделано перед планом: сверка с кодом на 2026-10-17. Все `file:line` проверены. Миграций нет. Новых msgid нет. Новых экранов кабинета нет.

### 15.1 Факты из кода (опора плана)

| Что | Где | Вывод |
|---|---|---|
| страница предложения | `apps/aggregator/views.py:962-1016` — `@cache_public_page def offer_page(request, pk)`. 404: `raise Http404` (:976-977). kind=business → 301 на `portal-business` (:978-984) | 404 — это исключение, оно проходит сквозь внешний декоратор. 301 — статус не 200. Ни то ни другое не считается само собой |
| кэш | `apps/core/pagecache.py:193-222` `cache_public_page`; hit → `_unpack` (:126-139) возвращает `HttpResponse` со статусом 200; miss → ответ вьюхи. Мимо кэша идут: `request.GET` непуст, не-GET, непустая сессия. `_cacheable` :71-116 | внешний декоратор видит `status_code` и при hit, и при miss. Учёт не трогает ни сессию, ни cookie, поэтому `_cacheable` не меняется |
| область портала | `views.py:887-895` `_offer_in_scope(listing, portal)`: при portal=None всё в области (включая демо); демо на портале только при `show_demo`; город и тип портала | для учёта используем ту же функцию. Модуль держим в `views.py`, чтобы не было циклического импорта |
| профиль бизнеса | `apps/aggregator/reviews_views.py:55-117` `business_page(request, slug)`. Гейт `_business_or_404` :30-52 (visibility + область, демо по `tenant.is_demo`). `business_card` = `public()` с kind=business (:97-99). Кэша НЕТ | роуты: портал `config/urls_portal.py:63` `unternehmen/<slug>/`, главный домен `config/urls_public.py:88-92` `entdecken/unternehmen/<slug>/`. Имя одно — `portal-business` |
| ключ карточки бизнеса | `apps/aggregator/tasks.py:1247-1251`: `(schema, "business", "business")` | строка view бизнеса совпадает с ключом листинга |
| featured-клик | `views.py:319-337` `featured_click`: `public()` БЕЗ проверки области, редирект на `portal_url`. Роуты `urls_portal.py:72`, `urls_public.py:73-77` | образец; добавляем `record(click)` |
| атрибуция | `apps/aggregator/models.py:294-315` `with_channel(ch, lang)`: только http(s), иначе `""`; `ch`/`hl` не дублируются. `portal_url` :317-323 = `with_channel("portal", lang=текущий)` | новый kwarg `listing_ref=False` |
| catch-all | портал: `<str:facet>/` (`urls_portal.py:88`), один сегмент. Главный домен: `entdecken/<city>/<business_type>/` (`urls_public.py:111-115`) **съел бы `entdecken/weiter/7/`** (city="weiter") | на главном домене роут обязан стоять ВЫШЕ :110 (рядом с `klick/`, :73-77). На портале — рядом с :72 |
| robots | `views.py:796-801` `PLATFORM_DISALLOW`; `portal_views.py:832` `PORTAL_DISALLOW` | дописать `weiter` |
| боты | `apps/core/bots.py:31-39` метод не проверяет | GET проверяем сами |

**Все ссылки «к продавцу» на поверхностях портала и `/entdecken/`:**

| Ссылка | Место | Решение |
|---|---|---|
| CTA «Zum Angebot bei …» | `templates/aggregator/offer.html:63` | **перепривязать** |
| «Zur Website» | `templates/aggregator/portal_business.html:43-44` | **перепривязать** |
| shortlist: заголовок и «Zum Angebot» | `templates/aggregator/shortlist.html:19,42` (только `/entdecken/`) | **перепривязать** |
| попап карты (не featured) | `apps/aggregator/geo.py:117-123` `_url` → `card.portal_url` | **перепривязать** через `reverse("aggregator-outbound")` с `NoReverseMatch` → `portal_url`. **Исключение:** у отельной выдачи с датами (`portal_views.py:340-349`) `c.detail_url` переписан `_with_dates`, а у карточки есть `range_nights`. Такие ссылки оставить прямыми: редирект брал бы листинг из БД и потерял бы даты (известный недосчёт v1) |
| карточки | `templates/aggregator/_cards.html:8-9`: обычная карточка ведёт на `aggregator-offer`, featured — на `featured-click`; `\|default:l.portal_url` — фолбэк для urlconf без роута (тенант, замок `test_offer_page.py:133`) | не трогаем: внутренние ссылки, featured уже идёт через счётчик |
| «Alle Angebote von …», блоки главной | `portal_home.html:59`, `_home_block.html:5` | внутренние, не трогаем |
| фид | `open_feed.py:201,297` `with_channel("feed")` | **оставить** (§13 — v2; `url` фида и так ведёт на `aggregator-offer`, там считается view) |
| сводка жителю | `follow_digest.py:142` `with_channel("digest")` | **оставить** (v2) |
| canonical/JSON-LD | `views.py:1012`, `structured.py:116` | **оставить**: чистый `detail_url` |

### 15.2 Изменения (по файлам)

1. **`apps/aggregator/models.py:294`** — `with_channel(self, ch, lang="", listing_ref=False)`: при `listing_ref and self.pk` и отсутствии `cl` в query дописать `("cl", str(self.pk))` после `hl`. Значение по умолчанию False, поэтому `portal_url`, фид и сводка байт-в-байт прежние.

2. **`apps/aggregator/portal_stats.py`** — две вещи:
   - `channel_for(request) -> str`: `"portal"`, если `getattr(request, "portal", None)`, иначе `"entdecken"`;
   - `def should_count(request) -> bool`: `request.method == "GET" and _cfg("enabled") and not bots.is_bot(request)`. Это дешёвый пред-гейт ДО запроса в БД, чтобы краулер на cache hit не платил запросом.

3. **`apps/aggregator/views.py`**:
   - `_scoped_listing(request, pk)`: `AggregatorListing.objects.public().filter(pk=pk).only("pk", "tenant_schema", "listing_kind", "source_ref", "is_demo", "city", "business_type", "detail_url").first()` + `_offer_in_scope(...)` → listing или None.
   - Декоратор `count_offer_view(view)` (определить перед `offer_page`):
     - вызывает `view`;
     - если `response.status_code == 200 and portal_stats.should_count(request)`, берёт `listing = _scoped_listing(request, pk)`;
     - при `listing` вызывает `portal_stats.record(request, action="view", channel=channel_for(request), listings=[listing])`;
     - весь учётный блок — в `try/except Exception` (fail-safe, лог только типом), потому что запрос `_scoped_listing` идёт вне `record`;
     - сессию и cookie не трогает;
     - порядок: `@count_offer_view` → `@cache_public_page` → `def offer_page`.

     Повторная проверка `public()` и области на hit нужна: листинг мог быть скрыт после записи в кэш (TTL).
   - `def _seller_redirect(listing)`: `url = listing.with_channel("portal", lang=translation.get_language() or "", listing_ref=True)`. Если `url` не начинается с `http://`/`https://` → `redirect("/")`. Иначе `HttpResponseRedirect(url)`. Плюс `Cache-Control: no-store` и `X-Robots-Tag: noindex, nofollow`. Цель — ТОЛЬКО из БД-листинга (`detail_url` пишет синк), из запроса ничего не берётся → open redirect исключён.
   - `@require_safe def outbound_click(request, pk)`:
     - `listing = _scoped_listing(request, pk)`; None → `redirect("/")` без счёта (корень валиден на обоих хостах);
     - при `portal_stats.should_count(request)` → `record(request, action="click", channel=channel_for(request), listings=[listing])`. Лимит частоты внутри `record`: при превышении редирект всё равно уходит, просто без счёта;
     - `return _seller_redirect(listing)`.
   - `featured_click` (:319-337):
     - `featured_clicks` +1 — как было (замок D2.3);
     - дополнительно `record(click)`, но только если листинг в области `_offer_in_scope` (на настоящем портале демо не пишем) и `should_count`;
     - цель — `_seller_redirect(listing)`, то есть тоже с `cl=` и `no-store`. Решение D-1 ниже.
     - Поведение редиректа для листинга вне области НЕ меняем (минимальная правка).

4. **`apps/aggregator/reviews_views.py:55-117`** — в `business_page` перед `return render(...)`:

   ```python
   if portal_stats.should_count(request):
       if card:
           portal_stats.record(request, action="view", channel=channel_for(request), listings=[card])
       else:
           portal_stats.record(
               request,
               action="view",
               channel=channel_for(request),
               tenant_schema=business.schema_name,
               kind="business",
               ref="business",
               is_demo=business.is_demo,
           )
   ```

   `card` — вынести `business_card` в локальную переменную (сейчас он считается внутри dict контекста — :97-99). Почему вызов внутри вьюхи, а не декоратор: страница не кэшируется, тенант и карточка уже загружены, декоратор дублировал бы 2 запроса. Комментарий-предупреждение: «если сюда придёт `@cache_public_page`, учёт выносится в декоратор снаружи (как у offer_page)». Ветки, где страница не отдаётся, считать не нужно: `_business_or_404` бросает `Http404` раньше.

5. **URL**:
   - `config/urls_portal.py` — после :72: `path("weiter/<int:pk>/", aggregator_views.outbound_click, name="aggregator-outbound")`.
   - `config/urls_public.py` — после :77, **выше** `entdecken/<str:city>/` (:110): `path("entdecken/weiter/<int:pk>/", aggregator_views.outbound_click, name="aggregator-outbound")`.

6. **Шаблоны** (паттерн «url as var + фолбэк», как в `_cards.html:8`):
   - `offer.html:63`: `{% url 'aggregator-outbound' listing.pk as out_url %}<a href="{{ out_url|default:listing.portal_url }}" rel="nofollow" data-offer-cta`.
   - `portal_business.html:44`: то же с `business_card.pk`, `rel="nofollow"`; условие `{% if business_card.portal_url %}` оставить (нет сайта → нет кнопки).
   - `shortlist.html:19,42`: `{% url 'aggregator-outbound' l.pk %}` + `rel="nofollow"` на обеих ссылках.
   - `geo.py:117-123`: не-featured и без `getattr(card, "range_nights", None)` → `reverse("aggregator-outbound", args=[card.pk])`, фолбэк `portal_url`. Попап карты рисуется через DOM (`_map.html:54-60`), `rel` там не ставится; заметка: добавить `a.rel = "nofollow"` в `popupLink` — опционально.

7. **robots**: `PORTAL_DISALLOW += ("/weiter/",)` (`portal_views.py:832`), `PLATFORM_DISALLOW += ("/entdecken/weiter/",)` (`views.py:796-801`). Индексируемого контента под ними нет, поэтому урок «Disallow прячет noindex» здесь неприменим.

### 15.3 Решения внутри инкремента

- **D-1.** `cl=` добавляется и у `featured_click`. Без этого сделки с featured-карточек в V5-5 падали бы на «бизнес целиком». Цена — осознанная переписка двух замков D2.3 (`test_featured.py:142,150`: Location = `with_channel(..., listing_ref=True)`). Счётчик `featured_clicks` не меняется.
- **D-2.** Канал = поверхность: `portal` или `entdecken`. Переходы из фида на страницу предложения считаются view той поверхности (атрибуция фида — v2, §13).
- **D-3.** На превью-портале (`show_demo`) и на `/entdecken/` демо-листинги в области → строка с `is_demo=True` (берётся из листинга/тенанта в `_rows`). На настоящем портале демо вне области → 404/«/», строки нет.

### 15.4 Замки (написать ДО кода)

В `apps/aggregator/tests/test_portal_stats.py` — новая секция «V5-2». Она переиспользует autouse-фикстуру `_private_cache` (+`isolated_ratelimit`). Запросы — RequestFactory с `HTTP_USER_AGENT=UA`, разными `REMOTE_ADDR`, `req.portal = portal` и `req.session = SessionStore()`.

1. `test_offer_view_counted_on_miss_and_hit_without_cookies` (§9 п.4, P0-1). `@override_settings(ROOT_URLCONF="config.urls_portal", CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)`; spy на `apps.aggregator.structured.listing_ld`.
   - Два GET от разных IP: оба 200.
   - После первого `cache.get(f"pubpage2:testserver:/angebot/{pk}/:de")` не None.
   - Spy вызван 1 раз (второй ответ — из кэша).
   - `not r1.cookies and not r2.cookies`; у обоих запросов `session.modified is False` и `session.is_empty()`.
   - `_count(action="view", channel="portal") == 2`.
   - Третий GET тем же посетителем → по-прежнему 2.
2. `test_offer_view_channel_entdecken_on_main_domain`: `urls_public`, без portal → `channel="entdecken"`.
3. `test_offer_view_not_counted_for_bot_head_404_and_business_redirect`:
   - Googlebot → 0, и при прогретом кэше `django_assert_num_queries(0)` (бот не тратит запрос);
   - HEAD → 0;
   - демо на портале без `show_demo` → `Http404`, 0;
   - kind=business → 301, 0.
4. `test_offer_view_demo_on_preview_portal_is_flagged`: `show_demo=True` → строка `is_demo=True`.
5. `test_business_page_view_counts_business_card_or_tenant_row`: с карточкой → строка `(schema, "business", "business")` с `listing_id=card.pk`; без карточки → та же тройка, `listing_id=None`, `is_demo` = флаг тенанта.
6. `test_outbound_redirect_counts_click_and_appends_cl` (§9 п.6): 302; `Location == listing.with_channel("portal", lang="de", listing_ref=True)` и оканчивается на `&cl=<pk>`; `Cache-Control` содержит `no-store`; `_count(action="click") == 1`.
7. `test_outbound_unknown_hidden_or_out_of_scope_goes_home_without_count`: 999999 / `hidden_at` / чужой город / демо без `show_demo` → `Location == "/"`, строк нет.
8. `test_outbound_non_http_target_goes_home`: `detail_url="ftp://x/"` и `"javascript:alert(1)"` → «/».
9. `test_outbound_rate_limited_still_redirects`: monkeypatch лимита в 1 → второй посетитель с того же IP получает редирект к продавцу, счёт остаётся 1.
10. `test_outbound_head_redirects_without_count_and_post_is_405`.
11. `test_featured_click_records_click_and_keeps_featured_counter` (§9 п.7): `featured_clicks == 1` и строка `click` == 1.
12. `test_with_channel_listing_ref_is_opt_in`: `portal_url` без `cl`; `listing_ref=True` → `cl` ровно один раз; уже заданный `cl` не дублируется.
13. `test_outbound_routes_resolve_before_catch_all`: `resolve("/weiter/7/", urlconf="config.urls_portal").func is views.outbound_click`; `resolve("/entdecken/weiter/7/", urlconf="config.urls_public").func is views.outbound_click` (а не `city_listing`).
14. `test_seller_links_go_through_outbound`: CTA offer (`href="/weiter/<pk>/" rel="nofollow" data-offer-cta`), «Zur Website», обе ссылки shortlist (`/entdecken/weiter/<pk>/`), `map_points` без `range_nights` → outbound, с `range_nights` → `portal_url` с датами; canonical и JSON-LD offer-страницы — чистый `detail_url`.
15. `test_robots_disallow_outbound`: `Disallow: /weiter/` на портале и `Disallow: /entdecken/weiter/` на главном домене.

**Осознанные переписки старых замков:**
- `test_offer_page.py:73` — href CTA → outbound;
- `test_portal_block_a.py:205` — «Zur Website» → `/unternehmen/...` на `href="/weiter/<card.pk>/"`;
- `test_featured.py:124` — карта → outbound;
- `test_featured.py:142,150` — D-1;
- `test_machine_readable.py:285` — в цикл добавить `"/weiter/"`.

`test_offer_page.py:133` (фолбэк карточек без роута) и `test_catalog_hygiene.py:223-227` (`portal_url`) не меняются.

### 15.5 i18n, навигация, CSS

- **i18n:** новых строк нет (тексты кнопок прежние). Гейт `scripts/i18n_quickcheck.py` всё равно прогнать — шаблоны правятся.
- **nav_registry / EXPECTED_UNLISTED:** не нужно. Замки X7 (`apps/core/tests/test_x0_x7_locks.py:158-175`) обходят только `config.urls_tenant`; `test_nav_reachability` — тоже тенантный urlconf.
- **CSS:** новых Tailwind-классов нет, пересборка `app.css` не нужна. Прогнать `test_template_comments.py`.

### 15.6 Риски

- **Лишний запрос на каждый человеческий cache hit** страницы предложения: один запрос по pk + подзапрос `withheld_schemas`. Боты отсекаются ДО запроса (замок 3). Допустимо.
- **Общий лимит частоты.** Бакет `pstat` 300/ч на IP общий для view и click; офис за NAT получит недосчёт. Это честный недосчёт, страница не страдает.
- **Порядок URL на главном домене.** Если роут поставить ниже :110, он молча уйдёт в `city_listing` (200, пустая выдача) → замок 13.
- **Open redirect.** Цель берётся только из БД-листинга, схемы только http(s) (двойная проверка: `with_channel` + `_seller_redirect`); параметров `next`/`url` нет.
- **Краулеры и предзагрузка.** `rel=nofollow` + Disallow + `no-store` + `X-Robots-Tag` + `bots.is_bot` (включая `Sec-Purpose: prefetch`).
- **Отельная выдача с датами на карте** не считается кликом (её не перепривязываем, иначе потеряются даты) — записать в roadmap §Отложено.
- **Фид и сводка** ведут мимо редиректа — v2 (§13).
- **Перед мержем:** django-reviewer + security-reviewer (редирект и fail-safe-блок декоратора — в центре).

## §16. V5-3 — экран владельца «Besuche aus dem Stadtportal» (план planner, 2026-10-17)

- `/dashboard/stadtportal/` (`portal-stats`), вьюха `apps/aggregator/owner_views.py`
  (`@login_required` + `require_GET`; членство — `CabinetOwnerAccessMiddleware` для `/dashboard/`),
  сервис `apps/aggregator/owner_stats.py` (4 запроса по префиксу уникального ключа).
- Навигация: запись `_e("marketing", "portal-stats", …)` сразу после «Bewertungen»; модуль None,
  новый якорь не нужен (мораторий цел); палитра Ctrl+K и замок X7 — той же записью.
- Воронка 5 плиток в порядке `PortalStat.ACTIONS`; период `?tage=` 7/30/90/365 (по умолчанию 30),
  сравнение с прошлым периодом; спарклайн view+click (на 365 днях — по неделям); топ-10 по view+click;
  строка featured отдельно («seit Beginn der Anzeige»); пустые состояния «не в каталоге» /
  «подтвердите почту» / «не виден» / «нет визитов»; плашка «Demo-Daten» у демо.
- Метрика «Stadtportal (30 Tage): Aufrufe · Klicks» в панели Marketing — вне гейта акций, после
  метрики акций, только при данных.

**Решения внутри инкремента:**
- **D-1.** Действия, которые ещё не пишутся (impression — V5-4, contact/deal — V5-5), показываются
  «—» + «Wird bald gezählt», а не 0: ноль утверждал бы, что никто не смотрел. Константа
  `owner_stats.TRACKED_ACTIONS` расширяется вместе с V5-4/V5-5 (замок 16 переписывается осознанно).
- **D-2 (отступление от §6).** Заголовок в топе — по ключу `(listing_kind, source_ref)`, а не
  `in_bulk(listing_id)`: синк пересоздаёт листинг с новым pk.
- **D-3.** Схема — только `request.tenant.schema_name`, у `public` данных нет.
- **D-5 (вопрос владельцу).** Лёгкий кабинет (`LITE_NAV`, 4 пункта) в v1 не меняем — экран
  доступен прямым адресом и Ctrl+K. Предложение: ссылка «Besuche aus dem Stadtportal →» на экране
  «Fertig»/«Teilen».
- **D-10.** Разбивка по каналам (портал / `/entdecken/`) — v2.
- **D-11.** Экран видят и сотрудники (денег нет); owner-only — одной строкой, если владелец решит.

## §17. V5-4 — показы карточек (план planner, 2026-10-17)

- Маячок `POST /stat/sichtbar/` (портал) и `/entdecken/stat/sichtbar/` (главный домен, ВЫШЕ
  catch-all `<city>/<business_type>`), имя `aggregator-impressions`. Тело form-urlencoded `p=1,2,3`
  (sendBeacon; JSON не CORS-safelisted), ≤1 КБ, ≤48 pk. Ответ ВСЕГДА 204 без тела, `no-store`,
  без cookie/сессии; не-POST → 405.
- `csrf_exempt` (страницы кэшируются без токена, P0-1) → вместо токена same-origin
  (`Sec-Fetch-Site: same-origin`, фолбэк `Origin` = свой хост), пред-лимит `pstat-beacon`
  (`beacon_limit`, 120/ч на IP) ДО БД, бот-гейт `should_count(method="POST")`, белый список pk
  через `public()` + область портала (демо на настоящем портале не пишется).
- Клиент `_pstat_beacon.html` в обеих базах портала: IntersectionObserver ≥50 % ≥1 с при
  видимой вкладке, пачка на pagehide/visibilitychange/10 с; без cookie и localStorage.
  `data-pstat` — в единственном шаблоне карточек `_cards.html` (все поверхности через него).
- Экран владельца: `impression` в TRACKED_ACTIONS + сноска с определением показа.
- Не считаются в v1: попапы карты и таблица сравнения (roadmap §Отложено).
- **Находка стенда:** метки дедупа ставились ДО INSERT — при сбое записи визит пропадал на
  весь день → `_record` снимает метки при исключении `_bump` (замок).

## §18. V5-5 — обращения и сделки (план planner, 2026-10-17)

Нарезка: **V5-5a** (акции, корзина/заказ, билеты, заявки, обращения) → **V5-5b** (запись по
времени, проживание, флип `TRACKED_ACTIONS`, текст экрана владельца, стенд).

- **Атрибуция** — `apps/core/attribution.py`: `ch` (слаг канала) + `cl` (pk листинга портала).
  Порядок: POST `ch/cl` → легаси POST `channel` → GET → Referer ЭТОГО хоста → сессия корзины
  `src_attr` (окно `VISIT_HOURS=4`). Посадка с `?ch=` сессию НЕ создаёт (раньше
  `_capture_channel` писал `src_ch` каждому посетителю — TTDSG §25 + кэш P0-1); в сессию пишет
  только `remember()` из добавления в корзину (сессия там и так нужна); `forget()` после заказа.
- **Тег** `{% portal_attribution_fields %}` — скрытые `ch/cl` из контекста `attr` или GET (НЕ
  из Referer: иначе ссылка «вглубь сайта» тащила бы канал в каждую форму), только очищенные
  значения. Подключён во все формы сделок/обращений витрины.
- **Запись** — `apps/aggregator/conversions.py::count`: только каналы города
  (`PortalStat.CHANNEL_CODES`), после коммита, fail-safe. Строка: `cl` этого же бизнеса →
  листинг объекта сделки (`object_key`) → строка «бизнес целиком». Дедуп по ОБЪЕКТУ
  (`once_key`, по умолчанию `kind:pk`): два заказа = две сделки, повтор одного = одна.
- **Классы:** сделка — заказ, резерв/купон/покупка по акции, билет, заявка (Anfrage);
  обращение — сообщение (inbox), «Rückruf».
- **Изменение поведения:** покупка по акции пишет в `Order.source_channel` пустоту (было —
  канал посадки; заказ остаётся `promo`-маркером), канал — в статистике каталога.
- **Не входит (roadmap §Отложено):** предложения `/o/`, публичная смета, Gutschein/Abo, Warteliste.
- **Ревью V5-5a (django + security):** блокеров нет. Исправлено: зарезервированные метки
  `source_channel` (`quote`/`promo`/`manual`/`offer`/…) снаружи не принимаются (раньше `?ch=quote`
  превращал обычный заказ в смету); повторное добавление в корзину не продлевает окно визита;
  смета без цены — обращение, а не сделка; `cl` засчитывается только на карточку, которую портал
  показывает. Booking/stays (те же мёртвые `request.GET["ch"]` в POST) — V5-5b.
- **V5-5b (запись по времени и проживание):** `service_book`/`termin_book`/`unterkunft_book` берут
  канал резолвером (раньше читали `request.GET["ch"]` в POST — всегда пусто); группа периодов услуги
  = одна сделка (`once_key=booking:<group_code>`). Многошаговый выбор несёт `ch/cl` в хвосте ссылок
  (`_flow_qs` вместе с `embed`, `tail=` у ссылок слотов/дней/длительности), форма дат номера —
  скрытыми полями (fetch-своп сериализует форму целиком). Экран владельца: все пять действий
  считаются (`TRACKED_ACTIONS = ACTIONS_CODES`), сноска «каждое обращение и заказ — отдельно».
- **Ревью V5-5b:** блокеров нет; исправлено — редиректы после ошибки брони (занятый слот, неверные даты) несут `ch/cl` (`_embed_redirect(request=…)`, `_back_to_unit(tail=…)`) + замок.
