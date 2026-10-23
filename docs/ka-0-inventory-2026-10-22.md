# KA-0 · Инвентаризация экранов кабинета продавца (2026-10-22)

Источник: обход резолвера `config.urls_tenant` (скрипты обхода — в scratchpad сессии, в git не кладём;
данные `routes2.json`, `entries.json`, `perbt.json`). «Кабинет» = префиксы `dashboard/ catalog/ promotions/ imports/ crm/`
(те же, что `apps/core/i18n_cabinet.py:21` CABINET_PREFIXES и замок `test_x0_x7_locks.py:170`).
Метод/«302» определены по декораторам и телу вьюхи (эвристика: `require_POST` / `request.method` / тело без `render`).

## 0. 🚨 Срочные находки (вне плана KA — хотфиксом по обычному циклу)

1. **HIGH — `status_manager_save` без авторизации и без `require_POST`.**
   `apps/core/views.py:5480` `def status_manager_save(request, kind)` — ни `@login_required`, ни `@require_POST`
   (сравни соседний `status_manager` :5459 с `@login_required`). URL `config/urls_tenant.py:327`
   `/dashboard/status-manager/<kind>/save/`. `CabinetOwnerAccessMiddleware` анонима не трогает
   (`apps/core/middleware.py:151`, проверка только при `is_authenticated` :194), модуль-гейт для пути — `dashboard` (core).
   Следствие: **анонимный GET** `/dashboard/status-manager/order/save/` → `request.POST` пуст → `defs=[]`, `edges=[]` →
   `_set_status_config(..., [])` стирает ВСЕ свои статусы и переходы владельца для kind (order/booking/stay/job/ticket/reservation)
   и `tenant.save()`. Замок `test_orphan_decorators.py` этого не видит (декораторов нет вовсе, а не «перехвачены»).
   Фикс: `@login_required` + `@require_POST` + замок «каждая вьюха кабинета имеет login_required» (обход резолвера).
2. **MEDIUM — `finance:invoice-mahnung` меняет состояние по GET.** `apps/finance/views.py:342` — докстринг «POST: level++ …,
   письмо клиенту», но проверки метода нет: GET (ссылка/префетчер/кросс-сайт `<img>` при залогиненном владельце)
   поднимает ступень Mahnung и шлёт письмо клиенту (дедуп раз в день). Нужен `@require_POST`.
3. **LOW — `set-presence` по GET** (`apps/core/views.py:4349`): без проверки метода, GET сбрасывает режим присутствия в auto.
   В EXPECTED_UNLISTED помечен как [POST] (`test_x0_x7_locks.py:108`) — категория неверна.
4. **Права:** «Zahlung & Lieferung» (`payment-settings`, `apps/core/views.py:1208`) пишет **IBAN Vorkasse**
   (`apps/orders/views.py:607`) и Stripe-способы — но НЕ owner-only (middleware `_OWNER_ONLY` `apps/core/middleware.py:165`
   содержит `/dashboard/billing/`, а не `/dashboard/settings/payments/`). Сотрудник может подменить счёт, на который платят
   клиенты, тогда как `billing-payments` (Stripe Connect) — owner-only. Решение владельца (KA-1/DSGVO-роли).

## 1. Сводные числа

| метрика | значение |
|---|---|
| маршрутов в `config.urls_tenant` всего | 457 |
| из них кабинет (5 префиксов) | **280** |
| не-кабинет: витрина 131 · allauth 23 · Kunden-LK `/konto/` 12 · вход/онбординг/TG 8 · служебные 3 | 177 |
| кабинет по методу: GET 70 · GET+POST 87 · POST-only 93 · POST (ручная проверка) 3 · «302/action» 27 | 280 |
| с параметрами (детали/правка/действия) | 121 |
| беспараметрные GET-экраны | 115 (в реестре nav 75, в EXPECTED_UNLISTED 40) |
| записей `nav_registry.ENTRIES` | 80 (6 хабов), якорей 6 |
| из них palette_only (только Ctrl+K) | 18 |
| owner-only (middleware-префиксы ∪ флаг реестра) | 24 маршрута |
| в лёгком меню LITE_NAV (+EINTRAG) | 7 |
| разрешено в Telegram Mini App (TG_LITE_VIEWS, 49 имён) | 45 кабинетных + 4 служебных |
| EXPECTED_UNLISTED | 84 имени |
| легаси-редиректы (живые URL, отдают 302) | 9 (см. §3) |
| экраны-сироты по инварианту X7.3 | 0 (замок держит) — но см. §4 «скрытые сироты» |

Группы таблицы §2 (по якорю реестра; без записи — по модулю/пути, помечено «inferred»):
Verkäufe 75 · Sortiment 80 · Marketing 73 · Website 19 · Einstellungen 24 · Übersicht 1 + служебные 5 · Lite 3.

Модули и их префиксы (гейт `ModuleGatingMiddleware`, `apps/core/modules.py:838` — самый длинный префикс):
core: dashboard `/dashboard/`, board `/dashboard/board/`, catalog `/catalog/ /imports/ /dashboard/stock/ /dashboard/purchasing/`,
settings `/dashboard/site/ /settings/ /recht/ /extras/ /domains/ /modules/ /help/`, billing. Опциональные: promotions `/promotions/`,
crm `/crm/ /promotions/kampagnen/`, reviews, orders, booking, stays, loyalty `/promotions/vouchers/ /promotions/loyalty/`, analytics,
publishing `/dashboard/channels/ /dashboard/posts/`, jobs, events, blog, inbox, finance, telegram; **gift и customer_account без префиксов**.
Без модуля (всегда доступны как core `dashboard`): `/dashboard/collections/`, `/dashboard/reisegruppe/`, `/dashboard/zahlungen/`,
`/dashboard/stadtportal/`, `/dashboard/integrationen/`, `/dashboard/ablaeufe/`, `/dashboard/finder/`, `/dashboard/design/`, `/dashboard/medien/`.


## 3. Кандидаты в ДУБЛИ (одна задача — несколько экранов)

| # | экраны | доказательство | предложение для KA-4 |
|---|---|---|---|
| D1 | 9 легаси-URL, отдающих 302: `board` (`core/views.py:4859`), `orders:order-list` (`orders/views.py:86`), `booking:calendar` (`booking/views.py:74`), `stays:calendar` (`stays/views.py:149`), `stays:today` (`stays/views.py:656`), `jobs:list` (`jobs/views.py:73`), `catalog:product-list` (`catalog/views.py:147`), `site` (`core/views.py:1588`), `site-pages` (`core/views.py:4105`) | все в EXPECTED_UNLISTED [302]; `site-pages` ошибочно числится в «[OK] области Studio» (`test_x0_x7_locks.py:162`) | оставить как редиректы (дешёво), но перенести в отдельный реестр legacy; не считать экранами |
| D2 | «Kunden» `verkaeufe?tab=kunden` (Verkäufe) ↔ «Kontakte» `crm:customer-list` (Marketing) | `nav_registry.py` board-хаб `verkaeufe` q=`?tab=kunden` (mod None) и marketing `crm:customer-list`; SH-волна: вкладка рендерит тот же партиал/контекст, что CRM | один список клиентов, один вход |
| D3 | «Abläufe & Status» (Verkäufe, `ablaeufe?from=board`) ↔ «Abläufe» (Einstellungen) ↔ `status-manager/<kind>/` | две записи реестра (board, settings); `status_manager` докстринг: «тот же редактор встроен секцией на Abläufe … отдельный экран остаётся для deep-link» (`core/views.py:5462`) | один вход + снести отдельный status-manager экран (оставить редирект) |
| D4 | Оплата ×3: «Zahlungen» `payments-page` (журнал оплат сделок) · «Zahlungen empfangen» `billing-payments` (Stripe Connect, owner-only, palette) · «Zahlung & Lieferung» `payment-settings` (способы+Vorkasse+доставка+connect-партиал) | `billing/payments.html:45` уже «всё в одном месте теперь: → payment-settings»; `billing.views.payments` ещё рендерит `method_choices` (`billing/views.py:97`) | `billing-payments` свести в `payment-settings` (owner-гейт на секцию connect); названия развести («Zahlungseingänge» vs «Zahlarten») |
| D5 | Подключения ×5: «Integrationen» (`integrations-home`), «Benachrichtigungen & Kanäle» (`notifications-settings`), «Kanäle» (`channels`, publishing), «Telegram» (`telegram-settings`), лёгкое «Sichtbar» (`lite-visibility`), + «Google-Profil»/«Merchant»/«Google Bewertungen» (palette) | реестр settings/marketing; `lite_visibility.html` ссылается на integrations-home, notifications-settings, payment-settings, domains, gbp-sync | один экран «Verbindungen» с карточками; каналы публикации и уведомлений как секции |
| D6 | Исходящий контент ×4: «Blog & News» (`blog-list`), «Beiträge» (`publishing-posts`), «Newsletter» (`promotions:newsletter`), «Kampagnen» (`promotions:coupon-campaigns`) | все в Marketing-хабе; blog рекомендован ВСЕМ 16 типам (`modules.py` blog REC = все) | владелец: блог/новости убрать; посты+newsletter+кампании — один «Kommunikation» |
| D7 | Погашение ×2: «Einlösen» `promotions:redeem` (код резерва/купона) ↔ `promotions:voucher-redeem` `/promotions/vouchers/redeem/` (ваучеры) | два GET-экрана со сканером; оба в TG_LITE_VIEWS | один «Einlösen» с автоопределением кода |
| D8 | «Reservierungen» `promotions:reservation-list` (palette) ↔ вкладка `verkaeufe?tab=reservation` | W10-2/Р-4: резервы — вкладка Verkäufe; список жив в палитре и в LITE (`tg_login.py` касса) | для полного кабинета — только вкладка; лёгкий — отдельный экран осознанно |
| D9 | Studio vs отдельные экраны: `site-menu` (`core/views.py:4118`, живой GET+POST билдер меню), `site-sections` (обложки, :4046), `site-preview` (:3632) ↔ Studio `site-home` (меню в колонке STU-12c, канва) | EXPECTED_UNLISTED «области Studio: вход из рейки» — но рейка снесена STU-12a | проверить, достижимы ли из Studio; иначе — либо вход, либо снос |
| D10 | «Geschäft» лёгкий (`lite-business`) ↔ «Mein Geschäft» (`settings`) | `lite_business.html` ссылается на `settings`; осознанный сабсет | ок, но один источник полей |
| D11 | «Stadtportal» (`portal-stats`) ↔ лёгкое «Sichtbar» (где видно) ↔ панель результатов `marketing-home` | все показывают «где видно/сколько смотрят» | свести статистику видимости |
| D12 | «Kategorien», «Kollektionen», «Lager», «Einkauf», «Kombi», «Importieren» — по 2 записи (хабы catalog и sellables) | `nav_registry.py` ENTRIES; в catalog-хабе sidebar=False | технический дубль реестра, не UI; хаб `catalog` не имеет собственного якоря-таб-бара (таб-бары сняты R7-1) → кандидат на удаление хаба |

## 4. Сироты и «скрытые сироты»

Формально (инвариант X7.3) сирот **0**: каждый беспараметрный GET-экран кабинета либо в реестре, либо в EXPECTED_UNLISTED.
Но фактически без входа из меню:
- **18 palette_only экранов** — вход только через Ctrl+K (на мобильном палитры нет в таб-баре; в Telegram палитра выключена
  `_base_dashboard.html:167`): «Reservierungen», «Zusatzverkäufe», Finanzen ×5 (Ausgaben/Ergebnis/Offene Posten/Bankabgleich/Rechnungen),
  «Channel Manager», «Tisch-QR», «Neue Aktion», «Firmen», «Google-Profil», «Google Merchant Center», «Von der Website importieren»,
  «Karten & Abos», «Gastgeber», «Google Bewertungen», «Zahlungen empfangen».
  Особо: **Finanzen-подразделы** — 5 рабочих экранов ERP без меню; **«Karten & Abos»** и **«Gastgeber»** — сущности ассортимента без меню.
- **Экраны из EXPECTED_UNLISTED с живым UI**: `site-menu`, `site-sections`, `site-preview` (обоснование «вход из рейки билдера» устарело — рейка снесена STU-12a);
  `promotions:shop-poster` (вход кнопкой из lite-share — ок); `events:teacher-create`, `crm:company-create` (формы создания — ок).
- **Без модуля и без меню у части архетипов**: `/dashboard/reisegruppe/` (community, мото) — проверить вход (не в реестре, параметрические URL).

## 5. Лёгкий тенант «Aktionen», тип bakery

Активные модули (= `default_disabled_for("bakery")` минус `QUICK_REQUIRED_MODULES=("promotions","publishing")`, `tenants/services.py:156,194`):
**dashboard, board, catalog, promotions, crm, reviews, orders, loyalty, gift, publishing, blog, inbox, customer_account, settings, billing.**

- **Меню (сайдбар/таб-бар):** 6 пунктов LITE_NAV (`lite_cabinet.py:21`): Start · Aktionen · Angebot · Sichtbar · Geschäft · Teilen.
- **Ctrl+K в браузере (не TG):** `nav_palette` гейтит только модулем/типом/owner (`templatetags/cabinet.py:81-89`), НЕ лёгким профилем →
  **51 запись + 6 якорей полного кабинета**, включая Blog & News, Newsletter, Beiträge, Treuepunkte, Gutscheine, Kampagnen, Lager, Einkauf,
  Kombi, Lieferungen, Zahlungen, Funktionen, Design/SEO/Domains/Medien, Team, Abo.
- **По прямому URL:** 76 беспараметрных GET-экранов (dashboard 19, settings 17, catalog 9, promotions 8, crm 6, orders 4, publishing 4,
  loyalty 3, billing 2, inbox 2, blog 1, reviews 1). Лёгкий режим «упрощает вход, а не запрещает» (`lite_cabinet.py:6`).
- **Целевой минимум владельца vs факт:**

| нужно владельцу | есть в LITE_NAV? | где живёт сейчас |
|---|---|---|
| Aktionen (создать/список/статистика) | ✅ Aktionen | `promotions:promotion-list`, `promotion-quick` |
| Start/кабинет | ✅ Start | `dashboard` → `lite_home.html` |
| **Чат с покупателем (Nachrichten)** | ❌ **нет** | `inbox:list` — ни в LITE_NAV, ни в TG_LITE_VIEWS, ни ссылкой из lite-шаблонов |
| Контакты/данные бизнеса | ✅ Geschäft | `lite-business` (адрес/тел/WhatsApp) |
| **Правовые тексты (Impressum/Datenschutz)** | ❌ **нет** | `legal-docs` `/dashboard/recht/` — нет в LITE_NAV/TG, нет ссылки из lite-шаблонов |
| Sichtbarkeit/Teilen | ✅ Sichtbar, Teilen | `lite-visibility`, `lite-share` |
| Отклики (отложено/купоны/выдача) | ⚠ нет пункта; касса есть в TG (`reservation-list`, `redeem`) | вход со Start? — проверить в KA-5g |

- **Активно, но НЕ в целевом наборе (лишнее у лёгкого bakery):** blog (`/dashboard/blog/`), publishing-посты/каналы,
  newsletter (внутри promotions), crm (Kontakte/Firmen/Kampagnen), loyalty (Treuepunkte/Gutscheine), gift, reviews,
  orders (Lieferungen/заказы), customer_account, catalog-склад/закупки/импорт, коллекции, Studio/Design/SEO/Domains/Medien,
  Finder, Extras, Team, Abo. Плюс «Angebot» (`sellable-manage`) в LITE_NAV — по ТЗ KA-3 «без каталога-раздела».

## 6. Наблюдения по архетипам (сайдбар полного кабинета, дефолтные модули)

Расчёт: `modules.sidebar_nav(tenant)` на объекте с `disabled_modules=default_disabled_for(bt)`, владелец (user=None).
Оговорка: `sales_page.visible_kinds` на стабе падает → fail-open, поэтому подпункт-вкладка единственного направления
(«Aufträge ?tab=job») может быть посчитан, хотя у реального тенанта с одним направлением VF-11 его прячет.

| тип | якорей | подпунктов (вкл. обзор) | Verkäufe | Sortiment | Marketing | Website | Einstellungen | активные опц. модули |
|---|---|---|---|---|---|---|---|---|
| bakery | 6 | 44 | 5 | 7 | 13 | 5 | 14 | promotions, crm, reviews, orders, loyalty, gift, blog, inbox, customer_account |
| butcher | 6 | 44 | 5 | 7 | 13 | 5 | 14 | promotions, crm, reviews, orders, loyalty, gift, blog, inbox, customer_account |
| grocery | 6 | 44 | 5 | 7 | 13 | 5 | 14 | promotions, crm, reviews, orders, loyalty, gift, blog, inbox, customer_account |
| clothing | 6 | 42 | 5 | 7 | 11 | 5 | 14 | promotions, crm, reviews, orders, gift, blog, inbox, customer_account |
| restaurant | 6 | 46 | 6 | 8 | 13 | 5 | 14 | promotions, crm, reviews, booking, loyalty, gift, blog, inbox, customer_account |
| cafe | 6 | 46 | 6 | 8 | 13 | 5 | 14 | promotions, crm, reviews, booking, loyalty, gift, blog, inbox, customer_account |
| retail | 6 | 42 | 5 | 7 | 11 | 5 | 14 | promotions, crm, reviews, orders, gift, blog, inbox, customer_account |
| online_shop | 6 | 42 | 5 | 7 | 11 | 5 | 14 | promotions, crm, reviews, orders, gift, blog, inbox, customer_account |
| tour_operator | 6 | 40 | 6 | 8 | 7 | 5 | 14 | crm, reviews, booking, gift, blog, inbox, customer_account |
| hotel | 6 | 43 | 8 | 9 | 7 | 5 | 14 | crm, reviews, booking, stays, gift, blog, inbox, customer_account |
| friseur | 6 | 46 | 6 | 8 | 13 | 5 | 14 | promotions, crm, reviews, booking, loyalty, gift, blog, inbox, customer_account |
| handwerker | 6 | 38 | 5 | 7 | 7 | 5 | 14 | crm, reviews, gift, jobs, blog, inbox, customer_account |
| werkstatt | 6 | 41 | 7 | 8 | 7 | 5 | 14 | crm, reviews, booking, gift, jobs, blog, inbox, customer_account |
| events | 6 | 43 | 4 | 9 | 11 | 5 | 14 | promotions, crm, reviews, gift, events, blog, inbox, customer_account |
| catering | 6 | 42 | 5 | 7 | 11 | 5 | 14 | promotions, crm, reviews, gift, jobs, blog, inbox, customer_account |
| other | 6 | 41 | 4 | 7 | 11 | 5 | 14 | promotions, crm, reviews, gift, blog, inbox |

- **bakery**: Übersicht[] · Verkäufe[Abläufe & Status?from=board, Kunden?tab=kunden, Lieferungen, Zahlungen] · Sortiment[Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Gutscheine, Kontakte, Nachrichten, Einlösen, Treuepunkte, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **butcher**: Übersicht[] · Verkäufe[Abläufe & Status?from=board, Kunden?tab=kunden, Lieferungen, Zahlungen] · Sortiment[Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Gutscheine, Kontakte, Nachrichten, Einlösen, Treuepunkte, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **grocery**: Übersicht[] · Verkäufe[Abläufe & Status?from=board, Kunden?tab=kunden, Lieferungen, Zahlungen] · Sortiment[Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Gutscheine, Kontakte, Nachrichten, Einlösen, Treuepunkte, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **clothing**: Übersicht[] · Verkäufe[Abläufe & Status?from=board, Kunden?tab=kunden, Lieferungen, Zahlungen] · Sortiment[Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Einlösen, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **restaurant**: Übersicht[] · Verkäufe[Öffnungszeiten & Ressourcen, Tage blockieren, Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen] · Sortiment[Leistungen, Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Gutscheine, Kontakte, Nachrichten, Einlösen, Treuepunkte, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **cafe**: Übersicht[] · Verkäufe[Öffnungszeiten & Ressourcen, Tage blockieren, Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen] · Sortiment[Leistungen, Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Gutscheine, Kontakte, Nachrichten, Einlösen, Treuepunkte, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **retail**: Übersicht[] · Verkäufe[Abläufe & Status?from=board, Kunden?tab=kunden, Lieferungen, Zahlungen] · Sortiment[Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Einlösen, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **online_shop**: Übersicht[] · Verkäufe[Abläufe & Status?from=board, Kunden?tab=kunden, Lieferungen, Zahlungen] · Sortiment[Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Einlösen, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **tour_operator**: Übersicht[] · Verkäufe[Öffnungszeiten & Ressourcen, Tage blockieren, Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen] · Sortiment[Leistungen, Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Kampagnen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Blog & News] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **hotel**: Übersicht[] · Verkäufe[Öffnungszeiten & Ressourcen, Tage blockieren, Check-ins, Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen, Berichte] · Sortiment[Leistungen, Zimmer & Preise, Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Kampagnen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Blog & News] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **friseur**: Übersicht[] · Verkäufe[Öffnungszeiten & Ressourcen, Tage blockieren, Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen] · Sortiment[Leistungen, Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Gutscheine, Kontakte, Nachrichten, Einlösen, Treuepunkte, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **handwerker**: Übersicht[] · Verkäufe[Aufträge?tab=job, Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen] · Sortiment[Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Kampagnen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Blog & News] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **werkstatt**: Übersicht[] · Verkäufe[Aufträge?tab=job, Öffnungszeiten & Ressourcen, Tage blockieren, Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen] · Sortiment[Leistungen, Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Kampagnen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Blog & News] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **events**: Übersicht[] · Verkäufe[Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen] · Sortiment[Veranstaltungen, Reisen, Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Einlösen, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **catering**: Übersicht[] · Verkäufe[Aufträge?tab=job, Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen] · Sortiment[Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Einlösen, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]
- **other**: Übersicht[] · Verkäufe[Abläufe & Status?from=board, Kunden?tab=kunden, Zahlungen] · Sortiment[Kategorien, Kollektionen, Lager, Einkauf, Kombi, Importieren] · Marketing[Aktionen, Kampagnen, Aktionstypen, Bewertungen, Stadtportal, Kontakte, Nachrichten, Einlösen, Blog & News, Newsletter] · Website[Design, SEO, Website & Domains, Medien] · Einstellungen[Mein Geschäft, Sprachen, Recht & Steuern, Zahlung & Lieferung, Benachrichtigungen & Kanäle, Abläufe, Integrationen, Abo & Rechnung, Team & Zugriff, Zusatzleistungen, Funktionen, Finder, Hilfe]

Выводы по §6:
- Якорей всегда 6 (замок `test_sidebar_anchor_composition_is_frozen`), подпунктов **38–46** на тип.
- **Einstellungen = 14 у всех** (вкл. «Finder», «Zusatzleistungen», «Funktionen», «Hilfe») — без учёта архетипа.
- **Website = 5 у всех.**
- **Sortiment у сервисных типов (hotel/handwerker/friseur/werkstatt/tour_operator) всё равно несёт Lager/Einkauf/Kombi/Importieren**
  (catalog — core, гейт только по модулю) — шум для отеля/ремесла.
- **Marketing 11–13** у типов с promotions/loyalty; **«Blog & News» у всех 16** (blog рекомендован всем).
- **Stadtportal** (owner-only) показан всем владельцам, включая не участвующих в каталоге города.

## 7. Вход сотрудника vs владельца
owner-only экраны (сайдбар их прячет, middleware 403): `billing*`, `legal-docs`, `team`, `portal-stats`, `imports:website`,
`gbp-*`, channels config/connect/toggle, `/dashboard/settings/notifications/telegram/`, `/dashboard/integrationen/telegram-aktivieren/`,
`/dashboard/telegram/connect|disconnect/` (`middleware.py:165-186`). Пробел — `payment-settings` (IBAN), см. §0.4.

## 8. Telegram Mini App (TG_LITE_VIEWS, `tg_login.py:45`)
49 имён: лёгкие экраны + полная форма товара/акции (+варианты/модификаторы) + касса (резервы/redeem/voucher-redeem).
**Нет:** inbox (чат с клиентами), legal-docs, notifications, verkaeufe. Чат с клиентом в Telegram недоступен вовсе.

## 9. Полная таблица кабинетных маршрутов (280)
Колонки: method — GET / GET+POST / POST / POST(manual) / 302 (тело без render: легаси-редирект или action с редиректом);
module (`*` = core); nav entry — `<якорь>/<хаб>` + флаги (adv)=ящик Erweitert, (palette)=только Ctrl+K, (nosb)=не в сайдбаре;
own=owner-only; lite=LITE_NAV; TG=TG_LITE_VIEWS; unl=EXPECTED_UNLISTED.

### Übersicht (1)

| path | name | view (file:line) | method | module | nav entry | own | lite | TG | unl |
|---|---|---|---|---|---|---|---|---|---|
| `/dashboard/` | dashboard | dashboard `apps/core/views.py:253` | GET | dashboard* | ANCHOR:Übersicht |  | Y | Y |  |

### Verkäufe (75)

| path | name | view (file:line) | method | module | nav entry | own | lite | TG | unl |
|---|---|---|---|---|---|---|---|---|---|
| `/dashboard/ablaeufe/` | ablaeufe | ablaeufe_view `apps/core/views.py:5362` | GET | dashboard* | Verkäufe/board(adv)?from=board; Einstellungen/settings |  |  |  |  |
| `/dashboard/auftraege/` | jobs:list | job_list `apps/jobs/views.py:73` | 302 | jobs | — (inferred group) |  |  |  | Y |
| `/dashboard/auftraege/<uuid:pk>/` | jobs:detail | job_detail `apps/jobs/views.py:122` | GET+POST | jobs | — (inferred group) |  |  |  |  |
| `/dashboard/auftraege/<uuid:pk>/angebot.pdf` | jobs:pdf | job_pdf `apps/jobs/views.py:455` | GET | jobs | — (inferred group) |  |  |  |  |
| `/dashboard/auftraege/<uuid:pk>/delete/` | jobs:delete | job_delete `apps/jobs/views.py:441` | POST | jobs | — (inferred group) |  |  |  |  |
| `/dashboard/auftraege/anfrage-formular/` | jobs:anfrage-form-settings | anfrage_form_settings `apps/jobs/views.py:83` | POST | jobs | — (inferred group) |  |  |  | Y |
| `/dashboard/auftraege/neu/` | jobs:new | job_new `apps/jobs/views.py:45` | GET+POST | jobs | — (inferred group) |  |  |  | Y |
| `/dashboard/board/` | board | board `apps/core/views.py:4859` | 302 | board* | — (inferred group) |  |  |  | Y |
| `/dashboard/board/<str:kind>/<uuid:pk>/action/` | board-action | kanban_action `apps/core/views.py:4926` | POST | board* | — (inferred group) |  |  |  |  |
| `/dashboard/board/settings/` | board-settings | board_settings `apps/core/views.py:4878` | POST | board* | — (inferred group) |  |  |  | Y |
| `/dashboard/booking/` | booking:calendar | calendar `apps/booking/views.py:74` | 302 | booking | — (inferred group) |  |  |  | Y |
| `/dashboard/booking/<uuid:pk>/action/` | booking:booking-action | booking_action `apps/booking/views.py:224` | POST | booking | — (inferred group) |  |  |  |  |
| `/dashboard/booking/leistungen/<uuid:pk>/` | booking:service-edit | services_view `apps/booking/views.py:684` | GET+POST | booking | — (inferred group) |  |  |  |  |
| `/dashboard/booking/new/` | booking:booking-create | booking_create `apps/booking/views.py:317` | POST | booking | — (inferred group) |  |  |  | Y |
| `/dashboard/booking/ressourcen/` | booking:resources | resources `apps/booking/views.py:487` | GET+POST | booking | Verkäufe/board(adv) |  |  |  |  |
| `/dashboard/booking/services/inline-edit/` | booking:service-inline-edit | service_inline_edit `apps/booking/views.py:963` | POST | booking | — (inferred group) |  |  |  | Y |
| `/dashboard/booking/services/photo-edit/` | booking:service-photo-edit | service_photo_edit `apps/booking/views.py:976` | POST | booking | — (inferred group) |  |  |  | Y |
| `/dashboard/booking/termin/<uuid:pk>/` | booking:booking-detail | booking_detail `apps/booking/views.py:178` | GET | booking | — (inferred group) |  |  |  |  |
| `/dashboard/booking/verfuegbarkeit/` | booking:availability | availability_calendar `apps/booking/views.py:354` | GET+POST | booking | Verkäufe/board(adv) |  |  |  |  |
| `/dashboard/externe-nummer/<str:kind>/<uuid:pk>/` | deal-external-edit | deal_external_edit `apps/core/views.py:5225` | POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/finance/` | finance:journal | journal `apps/finance/views.py:29` | GET+POST | finance | Verkäufe/board(adv) |  |  |  |  |
| `/dashboard/finance/ausgaben/` | finance:expenses | expenses `apps/finance/views.py:87` | GET+POST | finance | Verkäufe/board(palette) |  |  |  |  |
| `/dashboard/finance/ausgaben/datev.csv` | finance:expenses-datev | expenses_export_datev `apps/finance/views.py:393` | GET | finance | — (inferred group) |  |  |  | Y |
| `/dashboard/finance/bank/` | finance:bank | bank_import `apps/finance/views.py:279` | GET+POST | finance | Verkäufe/board(palette) |  |  |  |  |
| `/dashboard/finance/datev.csv` | finance:export-datev | journal_export_datev `apps/finance/views.py:434` | GET | finance | — (inferred group) |  |  |  | Y |
| `/dashboard/finance/ergebnis/` | finance:ergebnis | ergebnis `apps/finance/views.py:219` | GET | finance | Verkäufe/board(palette) |  |  |  |  |
| `/dashboard/finance/export.csv` | finance:export-csv | journal_export_csv `apps/finance/views.py:418` | GET | finance | — (inferred group) |  |  |  | Y |
| `/dashboard/finance/offene/` | finance:offene | offene_posten `apps/finance/views.py:259` | GET | finance | Verkäufe/board(palette) |  |  |  |  |
| `/dashboard/finance/rechnungen/` | finance:invoices | invoices `apps/finance/views.py:450` | GET+POST | finance | Verkäufe/board(palette) |  |  |  |  |
| `/dashboard/finance/rechnungen/<uuid:pk>/` | finance:invoice-detail | invoice_detail `apps/finance/views.py:533` | GET+POST | finance | — (inferred group) |  |  |  |  |
| `/dashboard/finance/rechnungen/<uuid:pk>/mahnung/` | finance:invoice-mahnung | invoice_mahnung `apps/finance/views.py:342` | 302 | finance | — (inferred group) |  |  |  |  |
| `/dashboard/finance/rechnungen/<uuid:pk>/pdf/` | finance:invoice-pdf | invoice_pdf `apps/finance/views.py:593` | GET | finance | — (inferred group) |  |  |  |  |
| `/dashboard/kunde/<str:kind>/<uuid:pk>/` | deal-customer-edit | deal_customer_edit `apps/core/views.py:5030` | POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/orders/` | orders:order-list | order_list `apps/orders/views.py:86` | 302 | orders | — (inferred group) |  |  |  | Y |
| `/dashboard/orders/<uuid:pk>/` | orders:order-detail | order_detail `apps/orders/views.py:214` | GET | orders | — (inferred group) |  |  |  |  |
| `/dashboard/orders/<uuid:pk>/action/` | orders:order-action | order_action `apps/orders/views.py:458` | POST | orders | — (inferred group) |  |  |  |  |
| `/dashboard/orders/<uuid:pk>/bearbeiten/` | orders:order-edit | order_edit `apps/orders/views.py:283` | POST | orders | — (inferred group) |  |  |  |  |
| `/dashboard/orders/<uuid:pk>/lieferschein.pdf` | orders:order-delivery-note | delivery_note_pdf `apps/orders/views.py:492` | GET | orders | — (inferred group) |  |  |  |  |
| `/dashboard/orders/kitchen/` | orders:kitchen | kitchen `apps/orders/views.py:150` | GET | orders | Verkäufe/board(adv) |  |  |  |  |
| `/dashboard/orders/kitchen/<uuid:pk>/action/` | orders:kitchen-action | kitchen_action `apps/orders/views.py:197` | POST | orders | — (inferred group) |  |  |  |  |
| `/dashboard/orders/kitchen/board/` | orders:kitchen-board | kitchen_board `apps/orders/views.py:191` | GET | orders | — (inferred group) |  |  |  | Y |
| `/dashboard/orders/lieferungen/` | orders:deliveries | deliveries `apps/orders/views.py:95` | GET | orders | Verkäufe/board(adv) |  |  |  |  |
| `/dashboard/orders/tisch-qr/` | orders:table-qr | table_qr `apps/orders/views.py:164` | GET | orders | Verkäufe/board(palette) |  |  |  |  |
| `/dashboard/rabatt/<str:kind>/<uuid:pk>/` | deal-discount-edit | deal_discount_edit `apps/core/views.py:5185` | POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/rechnung/<str:kind>/<uuid:pk>/` | deal-invoice | deal_invoice `apps/core/views.py:5140` | POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/rechnungsempfaenger/<str:kind>/<uuid:pk>/` | deal-billing-edit | deal_billing_edit `apps/core/views.py:5066` | POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/status-labels/<str:kind>/` | status-labels-save | status_labels_save `apps/core/views.py:4985` | POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/status-manager/<str:kind>/` | status-manager | status_manager `apps/core/views.py:5459` | GET | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/status-manager/<str:kind>/save/` | status-manager-save | status_manager_save `apps/core/views.py:5480` | 302 | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/status-transitions/<str:kind>/` | transitions-save | transitions_save `apps/core/views.py:5008` | POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/stays/` | stays:calendar | calendar `apps/stays/views.py:149` | 302 | stays | — (inferred group) |  |  |  | Y |
| `/dashboard/stays/<uuid:pk>/action/` | stays:stay-action | stay_action `apps/stays/views.py:326` | POST | stays | — (inferred group) |  |  |  |  |
| `/dashboard/stays/berichte/export.csv` | stays:reports-export | reports_export_csv `apps/stays/views.py:1273` | GET | stays | — (inferred group) |  |  |  | Y |
| `/dashboard/stays/buchung/<uuid:pk>/` | stays:booking-detail | booking_detail `apps/stays/views.py:665` | GET | stays | — (inferred group) |  |  |  |  |
| `/dashboard/stays/buchung/<uuid:pk>/loeschen/` | stays:booking-delete | booking_delete `apps/stays/views.py:732` | POST | stays | — (inferred group) |  |  |  |  |
| `/dashboard/stays/channels/` | stays:channels | channels `apps/stays/views.py:1351` | GET+POST | stays | Verkäufe/board(palette) |  |  |  |  |
| `/dashboard/stays/checkins/` | stays:checkins | checkins `apps/stays/views.py:1337` | GET | stays | Verkäufe/board(adv) |  |  |  |  |
| `/dashboard/stays/heute/` | stays:today | today_view `apps/stays/views.py:656` | 302 | stays | — (inferred group) |  |  |  | Y |
| `/dashboard/stays/inline-edit/` | stays:stay-inline-edit | stay_inline_edit `apps/stays/views.py:1419` | POST | stays | — (inferred group) |  |  |  | Y |
| `/dashboard/stays/neu/` | stays:stay-new | stay_new `apps/stays/views.py:62` | GET | stays | — (inferred group) |  |  |  | Y |
| `/dashboard/stays/new/` | stays:stay-create | stay_create `apps/stays/views.py:567` | POST | stays | — (inferred group) |  |  |  | Y |
| `/dashboard/stays/photo-edit/` | stays:stay-photo-edit | stay_photo_edit `apps/stays/views.py:1432` | POST | stays | — (inferred group) |  |  |  | Y |
| `/dashboard/stays/reports/` | stays:reports | reports `apps/stays/views.py:1244` | GET | stays | Verkäufe/board(adv) |  |  |  |  |
| `/dashboard/stays/units/<uuid:pk>/` | stays:unit-edit | units `apps/stays/views.py:746` | GET+POST | stays | — (inferred group) |  |  |  |  |
| `/dashboard/stays/units/<uuid:pk>/feature/` | stays:unit-feature | unit_feature `apps/stays/views.py:1470` | GET | stays | — (inferred group) |  |  |  |  |
| `/dashboard/stays/units/<uuid:pk>/feature/checkout/` | stays:unit-feature-checkout | unit_feature_checkout `apps/stays/views.py:1494` | POST | stays | — (inferred group) |  |  |  |  |
| `/dashboard/stays/zimmer/<uuid:pk>/sauber/` | stays:room-clean | room_clean `apps/stays/views.py:721` | POST | stays | — (inferred group) |  |  |  |  |
| `/dashboard/verkaeufe/` | verkaeufe | verkaeufe `apps/core/views.py:4541` | GET | dashboard* | ANCHOR:Verkäufe |  |  |  |  |
| `/dashboard/verkaeufe/view/` | verkaeufe-view | verkaeufe_view_set `apps/core/views.py:4697` | POST(manual) | dashboard* | — (inferred group) |  |  |  | Y |
| `/dashboard/verkaeufe/zusatz/` | verkaeufe-zusatz | zusatzverkaeufe `apps/core/views.py:4605` | GET+POST | dashboard* | Verkäufe/board(palette) |  |  |  |  |
| `/dashboard/verknuepfen/<str:kind>/<uuid:pk>/` | deal-link | deal_link_view `apps/core/views.py:5256` | GET+POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/verknuepfen/<str:kind>/<uuid:pk>/loesen/` | deal-unlink | deal_unlink_view `apps/core/views.py:5343` | POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/zahlungen/` | payments-page | payments_page `apps/core/views.py:5814` | GET | dashboard* | Verkäufe/board(adv) |  |  |  |  |
| `/promotions/analytics/` | promotions:analytics | analytics_overview `apps/promotions/views.py:1278` | GET | analytics | Verkäufe/board(adv) |  |  |  |  |
| `/promotions/reservations/` | promotions:reservation-list | reservation_list `apps/promotions/views.py:1397` | GET | promotions | Verkäufe/board(palette) |  |  | Y |  |

### Sortiment (80)

| path | name | view (file:line) | method | module | nav entry | own | lite | TG | unl |
|---|---|---|---|---|---|---|---|---|---|
| `/catalog/categories/` | catalog:category-list | category_list `apps/catalog/views.py:567` | GET+POST | catalog* | Sortiment/catalog; Sortiment/sellables(adv) |  |  |  |  |
| `/catalog/categories/<uuid:pk>/delete/` | catalog:category-delete | category_delete `apps/catalog/views.py:842` | GET+POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/categories/<uuid:pk>/edit/` | catalog:category-edit | category_edit `apps/catalog/views.py:691` | GET+POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/categories/<uuid:pk>/images/<str:image_id>/delete/` | catalog:category-image-delete | category_image_delete `apps/catalog/views.py:809` | 302 | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/categories/<uuid:pk>/images/<str:image_id>/primary/` | catalog:category-image-primary | category_image_primary `apps/catalog/views.py:829` | 302 | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/categories/inline-edit/` | catalog:category-inline-edit | category_inline_edit `apps/catalog/views.py:719` | POST | catalog* | — (inferred group) |  |  |  | Y |
| `/catalog/categories/new/` | catalog:category-create | category_create `apps/catalog/views.py:668` | GET+POST | catalog* | — (inferred group) |  |  |  | Y |
| `/catalog/combos/` | catalog:combo-list | combo_list `apps/catalog/views.py:902` | GET | catalog* | Sortiment/catalog(adv)(nosb); Sortiment/sellables(adv) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/delete/` | catalog:combo-delete | combo_delete `apps/catalog/views.py:1049` | GET+POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/edit/` | catalog:combo-edit | combo_edit `apps/catalog/views.py:982` | GET+POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/feature/` | catalog:combo-feature | combo_feature `apps/catalog/views.py:1185` | GET | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/feature/checkout/` | catalog:combo-feature-checkout | combo_feature_checkout `apps/catalog/views.py:1209` | POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/groups/<uuid:gid>/delete/` | catalog:combo-group-delete | combo_group_delete `apps/catalog/views.py:1103` | POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/groups/<uuid:gid>/options/<uuid:oid>/delete/` | catalog:combo-option-delete | combo_option_delete `apps/catalog/views.py:1141` | POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/groups/<uuid:gid>/options/<uuid:oid>/update/` | catalog:combo-option-update | combo_option_update `apps/catalog/views.py:1129` | POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/groups/<uuid:gid>/options/add/` | catalog:combo-option-add | combo_option_add `apps/catalog/views.py:1111` | POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/groups/<uuid:gid>/update/` | catalog:combo-group-update | combo_group_update `apps/catalog/views.py:1078` | POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/groups/add/` | catalog:combo-group-add | combo_group_add `apps/catalog/views.py:1058` | POST | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/images/<str:image_id>/delete/` | catalog:combo-image-delete | combo_image_delete `apps/catalog/views.py:1017` | 302 | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/<uuid:pk>/images/<str:image_id>/primary/` | catalog:combo-image-primary | combo_image_primary `apps/catalog/views.py:1036` | 302 | catalog* | — (inferred group) |  |  |  |  |
| `/catalog/combos/new/` | catalog:combo-create | combo_create `apps/catalog/views.py:948` | GET+POST | catalog* | — (inferred group) |  |  |  | Y |
| `/catalog/products/` | catalog:product-list | product_list `apps/catalog/views.py:147` | 302 | catalog* | — (inferred group) |  |  |  | Y |
| `/catalog/products/<uuid:pk>/delete/` | catalog:product-delete | product_delete `apps/catalog/views.py:472` | GET+POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/edit/` | catalog:product-edit | product_edit `apps/catalog/views.py:197` | GET+POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/images/<str:image_id>/delete/` | catalog:product-image-delete | product_image_delete `apps/catalog/views.py:485` | 302 | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/images/<str:image_id>/primary/` | catalog:product-image-primary | product_image_primary `apps/catalog/views.py:506` | 302 | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/modifiers/<uuid:gid>/delete/` | catalog:modifier-group-delete | modifier_group_delete `apps/catalog/views.py:412` | POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/modifiers/<uuid:gid>/options/<uuid:oid>/delete/` | catalog:modifier-option-delete | modifier_option_delete `apps/catalog/views.py:464` | POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/modifiers/<uuid:gid>/options/<uuid:oid>/update/` | catalog:modifier-option-update | modifier_option_update `apps/catalog/views.py:441` | POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/modifiers/<uuid:gid>/options/add/` | catalog:modifier-option-add | modifier_option_add `apps/catalog/views.py:420` | POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/modifiers/<uuid:gid>/update/` | catalog:modifier-group-update | modifier_group_update `apps/catalog/views.py:388` | POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/modifiers/add/` | catalog:modifier-group-add | modifier_group_add `apps/catalog/views.py:369` | POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/variants/<uuid:vid>/delete/` | catalog:variant-delete | variant_delete `apps/catalog/views.py:356` | POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/variants/<uuid:vid>/update/` | catalog:variant-update | variant_update `apps/catalog/views.py:290` | POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/<uuid:pk>/variants/add/` | catalog:variant-add | variant_add `apps/catalog/views.py:242` | POST | catalog* | — (inferred group) |  |  | Y |  |
| `/catalog/products/inline-edit/` | catalog:product-inline-edit | product_inline_edit `apps/catalog/views.py:751` | POST | catalog* | — (inferred group) |  |  |  | Y |
| `/catalog/products/merge/` | catalog:products-merge | products_merge `apps/catalog/views.py:1149` | POST(manual) | catalog* | — (inferred group) |  |  |  | Y |
| `/catalog/products/new/` | catalog:product-create | product_create `apps/catalog/views.py:169` | GET+POST | catalog* | — (inferred group) |  |  | Y | Y |
| `/catalog/products/photo-edit/` | catalog:product-photo-edit | product_photo_edit `apps/catalog/views.py:765` | POST | catalog* | — (inferred group) |  |  |  | Y |
| `/dashboard/angebote/` | sellable-manage | sellable_manage `apps/core/views.py:5570` | GET | dashboard* | ANCHOR:Sortiment |  | Y | Y |  |
| `/dashboard/angebote/<str:kind>/<uuid:pk>/sichtbar/` | sellable-visibility | sellable_visibility `apps/core/views.py:5657` | POST | dashboard* | — (inferred group) |  |  | Y |  |
| `/dashboard/angebote/ansicht/` | sortiment-view | sortiment_view_set `apps/core/views.py:5633` | POST | dashboard* | — (inferred group) |  |  | Y | Y |
| `/dashboard/booking/karten/` | booking:passes | passes_view `apps/booking/views.py:872` | GET+POST | booking | Sortiment/sellables(palette) |  |  |  |  |
| `/dashboard/booking/leistungen/` | booking:services | services_view `apps/booking/views.py:684` | GET+POST | booking | Sortiment/sellables(adv) |  |  |  |  |
| `/dashboard/collections/` | collections:list | collections_view `apps/collections/views.py:34` | GET+POST | dashboard* | Sortiment/catalog(adv); Sortiment/sellables(adv) |  |  |  |  |
| `/dashboard/events/` | events:list | event_list `apps/events/views.py:55` | GET | events | Sortiment/sellables(adv) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/` | events:detail | event_detail `apps/events/views.py:109` | GET | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/action/` | events:action | event_action `apps/events/views.py:143` | POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/dokumente/` | events:documents | event_documents `apps/documents/views.py:99` | GET | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/edit/` | events:edit | event_edit `apps/events/views.py:83` | GET+POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/feature/` | events:feature | event_feature `apps/events/views.py:740` | GET | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/feature/checkout/` | events:feature-checkout | event_feature_checkout `apps/events/views.py:768` | POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/logistik/` | events:logistics | event_logistics `apps/events/views.py:792` | GET+POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/roster.csv` | events:roster-csv | roster_csv `apps/events/views.py:636` | GET | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/series/` | events:series | event_series `apps/events/views.py:544` | POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/tickets/<uuid:tid>/action/` | events:ticket-action | ticket_action `apps/events/views.py:230` | POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/tickets/add/` | events:ticket-add | ticket_add `apps/events/views.py:157` | POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/<uuid:pk>/waitlist/notify/` | events:waitlist-notify | waitlist_notify `apps/events/views.py:130` | POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/checkin/<str:code>/` | events:checkin | checkin `apps/events/views.py:567` | GET+POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/inline-edit/` | events:event-inline-edit | event_inline_edit `apps/events/views.py:689` | POST | events | — (inferred group) |  |  |  | Y |
| `/dashboard/events/new/` | events:create | event_create `apps/events/views.py:61` | GET+POST | events | — (inferred group) |  |  |  | Y |
| `/dashboard/events/photo-edit/` | events:event-photo-edit | event_photo_edit `apps/events/views.py:702` | POST | events | — (inferred group) |  |  |  | Y |
| `/dashboard/events/teachers/` | events:teacher-list | teacher_list `apps/events/views.py:596` | GET | events | Sortiment/sellables(palette) |  |  |  |  |
| `/dashboard/events/teachers/<uuid:pk>/delete/` | events:teacher-delete | teacher_delete `apps/events/views.py:627` | POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/teachers/<uuid:pk>/edit/` | events:teacher-edit | teacher_edit `apps/events/views.py:612` | GET+POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/teachers/new/` | events:teacher-create | teacher_create `apps/events/views.py:602` | GET+POST | events | — (inferred group) |  |  |  | Y |
| `/dashboard/events/ticket/<uuid:pk>/` | events:ticket-detail | ticket_detail `apps/events/views.py:189` | GET | events | — (inferred group) |  |  |  |  |
| `/dashboard/events/touren/` | events:tour-list | tour_list `apps/events/views.py:300` | GET+POST | events | Sortiment/sellables(adv) |  |  |  |  |
| `/dashboard/events/touren/<uuid:pk>/` | events:tour-edit | tour_edit `apps/events/views.py:314` | GET+POST | events | — (inferred group) |  |  |  |  |
| `/dashboard/purchasing/` | purchasing | purchasing_view `apps/inventory/views_purchasing.py:34` | GET+POST | catalog* | Sortiment/catalog(adv)(nosb); Sortiment/sellables(adv) |  |  |  |  |
| `/dashboard/purchasing/maengel/<uuid:pk>.pdf` | purchasing-maengel-pdf | maengel_pdf `apps/inventory/views_purchasing.py:82` | GET | catalog* | — (inferred group) |  |  |  |  |
| `/dashboard/reisegruppe/<uuid:pk>/gruppe/` | community:event-space | event_space `apps/community/views.py:198` | GET+POST | dashboard* | — (inferred group) |  |  |  |  |
| `/dashboard/stays/units/` | stays:units | units `apps/stays/views.py:746` | GET+POST | stays | Sortiment/sellables(adv) |  |  |  |  |
| `/dashboard/stock/` | stock | stock `apps/inventory/views.py:108` | GET+POST | catalog* | Sortiment/catalog(adv)(nosb); Sortiment/sellables(adv) |  |  |  |  |
| `/imports/<uuid:pk>/map/` | imports:map | import_map `apps/imports/views.py:144` | GET+POST | catalog* | — (inferred group) |  |  |  |  |
| `/imports/<uuid:pk>/preview/` | imports:preview | import_preview `apps/imports/views.py:198` | GET+POST | catalog* | — (inferred group) |  |  |  |  |
| `/imports/<uuid:pk>/status/` | imports:status | import_status `apps/imports/views.py:218` | GET | catalog* | — (inferred group) |  |  |  |  |
| `/imports/start/` | imports:start | import_start `apps/imports/views.py:108` | GET+POST | catalog* | Sortiment/catalog(adv)(nosb); Sortiment/sellables(adv) |  |  |  |  |
| `/imports/website/` | imports:website | website_start `apps/imports/views.py:232` | GET+POST | catalog* | Sortiment/sellables(adv)(palette) | Y | Y |  |  |
| `/imports/website/<uuid:pk>/` | imports:website-run | website_run `apps/imports/views.py:307` | GET+POST | catalog* | — (inferred group) | Y |  |  |  |

### Marketing (73)

| path | name | view (file:line) | method | module | nav entry | own | lite | TG | unl |
|---|---|---|---|---|---|---|---|---|---|
| `/crm/` | crm:customer-list | customer_list `apps/crm/views.py:90` | GET | crm | Marketing/marketing |  |  |  |  |
| `/crm/<uuid:pk>/` | crm:customer-detail | customer_detail `apps/crm/views.py:144` | GET+POST | crm | — (inferred group) |  |  |  |  |
| `/crm/<uuid:pk>/notes/` | crm:note-add | note_add `apps/crm/views.py:245` | POST | crm | — (inferred group) |  |  |  |  |
| `/crm/export.csv` | crm:customer-export | customer_export_csv `apps/crm/views.py:99` | GET | crm | — (inferred group) |  |  |  | Y |
| `/crm/firmen/` | crm:company-list | company_list `apps/crm/views.py:196` | GET | crm | Marketing/marketing(palette) |  |  |  |  |
| `/crm/firmen/<uuid:pk>/` | crm:company-detail | company_detail `apps/crm/views.py:215` | GET+POST | crm | — (inferred group) |  |  |  |  |
| `/crm/firmen/<uuid:pk>/loeschen/` | crm:company-delete | company_delete `apps/crm/views.py:235` | POST | crm | — (inferred group) |  |  |  |  |
| `/crm/firmen/neu/` | crm:company-create | company_create `apps/crm/views.py:205` | GET+POST | crm | — (inferred group) |  |  |  | Y |
| `/crm/new/` | crm:customer-create | customer_create `apps/crm/views.py:132` | GET+POST | crm | — (inferred group) |  |  |  | Y |
| `/dashboard/blog/` | blog-list | blog_list `apps/events/views.py:387` | GET+POST | blog | Marketing/marketing(adv) |  |  |  |  |
| `/dashboard/blog/<uuid:pk>/` | blog-edit | blog_edit `apps/events/views.py:465` | GET+POST | blog | — (inferred group) |  |  |  |  |
| `/dashboard/channels/` | channels | channels `apps/publishing/views.py:27` | GET | publishing | Marketing/marketing(adv) |  |  |  |  |
| `/dashboard/channels/config/` | channel-config | channel_config `apps/publishing/views.py:70` | POST | publishing | — (inferred group) | Y |  |  | Y |
| `/dashboard/channels/connect/<str:provider>/` | channel-oauth-start | oauth_start `apps/publishing/views.py:95` | 302 | publishing | — (inferred group) | Y |  |  |  |
| `/dashboard/channels/google/` | gbp-sync | gbp_sync `apps/publishing/views.py:256` | GET+POST | publishing | Marketing/marketing(palette) | Y |  |  |  |
| `/dashboard/channels/google/merchant/` | gbp-merchant | merchant_feed `apps/publishing/views.py:491` | GET+POST | publishing | Marketing/marketing(palette) | Y |  |  |  |
| `/dashboard/channels/google/standort/` | gbp-location | gbp_location `apps/publishing/views.py:399` | POST | publishing | — (inferred group) | Y |  |  | Y |
| `/dashboard/channels/google/zeiten/` | gbp-hours | gbp_hours `apps/publishing/views.py:326` | POST | publishing | — (inferred group) | Y |  |  | Y |
| `/dashboard/channels/toggle/` | channel-toggle | channel_toggle `apps/publishing/views.py:49` | POST | publishing | — (inferred group) | Y |  |  | Y |
| `/dashboard/inbox/` | inbox:list | inbox_list `apps/inbox/views.py:80` | GET | inbox | Marketing/marketing |  |  |  |  |
| `/dashboard/inbox/<uuid:pk>/` | inbox:thread | thread `apps/inbox/views.py:108` | GET+POST | inbox | — (inferred group) |  |  |  |  |
| `/dashboard/inbox/<uuid:pk>/angebot/` | inbox:offer-compose | offer_compose `apps/inbox/views.py:307` | GET+POST | inbox | — (inferred group) |  |  |  |  |
| `/dashboard/inbox/<uuid:pk>/entwurf/` | inbox:reply-draft | reply_draft_start `apps/inbox/views.py:191` | POST | inbox | — (inferred group) |  |  |  |  |
| `/dashboard/inbox/<uuid:pk>/poll/` | inbox:thread-poll | thread_poll `apps/inbox/views.py:443` | GET | inbox | — (inferred group) |  |  |  |  |
| `/dashboard/inbox/<uuid:pk>/typing/` | inbox:thread-typing | thread_typing `apps/inbox/views.py:477` | POST(manual) | inbox | — (inferred group) |  |  |  |  |
| `/dashboard/inbox/deal/<str:kind>/<uuid:pk>/` | inbox:deal-thread | deal_thread `apps/inbox/views.py:362` | GET+POST | inbox | — (inferred group) |  |  |  |  |
| `/dashboard/inbox/entwurf/<str:job>/` | inbox:reply-draft-result | reply_draft_result `apps/inbox/views.py:239` | GET | inbox | — (inferred group) |  |  |  |  |
| `/dashboard/inbox/unread-count/` | inbox:unread-count | unread_count `apps/inbox/views.py:430` | GET | inbox | — (inferred group) |  |  |  | Y |
| `/dashboard/marketing/` | marketing-home | marketing_home `apps/core/views.py:5846` | GET | dashboard* | ANCHOR:Marketing |  |  |  |  |
| `/dashboard/posts/` | publishing-posts | posts `apps/publishing/views.py:123` | GET+POST | publishing | Marketing/marketing(adv) |  |  |  |  |
| `/dashboard/reviews/` | reviews:list | review_list `apps/reviews/views.py:20` | GET | reviews | Marketing/marketing |  |  |  |  |
| `/dashboard/reviews/<uuid:pk>/reply/` | reviews:reply | review_reply `apps/reviews/views.py:99` | POST | reviews | — (inferred group) |  |  |  |  |
| `/dashboard/reviews/<uuid:pk>/toggle/` | reviews:toggle | review_toggle `apps/reviews/views.py:114` | POST | reviews | — (inferred group) |  |  |  |  |
| `/dashboard/reviews/betrieb/<int:pk>/antwort/` | reviews:business-reply | business_review_reply `apps/reviews/views.py:76` | POST | reviews | — (inferred group) |  |  |  |  |
| `/dashboard/stadtportal/` | portal-stats | portal_stats `apps/aggregator/owner_views.py:13` | GET | dashboard* | Marketing/marketing | Y |  |  |  |
| `/dashboard/telegram/` | telegram-settings | settings_view `apps/telegram/views.py:27` | GET | telegram | Marketing/marketing(adv) |  |  |  |  |
| `/dashboard/telegram/connect/` | telegram-connect | connect `apps/telegram/views.py:49` | POST | telegram | — (inferred group) | Y |  |  | Y |
| `/dashboard/telegram/disconnect/` | telegram-disconnect | disconnect `apps/telegram/views.py:82` | POST | telegram | — (inferred group) | Y |  |  | Y |
| `/promotions/` | promotions:promotion-list | promotion_list `apps/promotions/views.py:161` | GET | promotions | Marketing/marketing |  | Y | Y |  |
| `/promotions/<uuid:pk>/ansicht/` | promotions:promotion-preview | promotion_preview `apps/promotions/lite_views.py:62` | GET | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/<uuid:pk>/aushang.pdf` | promotions:promotion-flyer | promotion_flyer `apps/promotions/views.py:635` | 302 | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/<uuid:pk>/edit/` | promotions:promotion-edit | promotion_edit `apps/promotions/views.py:1085` | GET+POST | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/<uuid:pk>/feature/` | promotions:promotion-feature | promotion_feature `apps/promotions/views.py:1194` | GET | promotions | — (inferred group) |  |  |  |  |
| `/promotions/<uuid:pk>/feature/checkout/` | promotions:promotion-feature-checkout | promotion_feature_checkout `apps/promotions/views.py:1216` | POST | promotions | — (inferred group) |  |  |  |  |
| `/promotions/<uuid:pk>/fertig/` | promotions:promotion-quick-done | promotion_quick_done `apps/promotions/views.py:1045` | GET | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/<uuid:pk>/images/<str:image_id>/delete/` | promotions:promotion-image-delete | promotion_image_delete `apps/promotions/views.py:1330` | 302 | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/<uuid:pk>/images/<str:image_id>/primary/` | promotions:promotion-image-primary | promotion_image_primary `apps/promotions/views.py:1349` | 302 | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/<uuid:pk>/teilen/` | promotions:promotion-share | promotion_share `apps/promotions/views.py:1151` | GET+POST | promotions | — (inferred group) |  |  |  |  |
| `/promotions/<uuid:pk>/transition/` | promotions:promotion-transition | promotion_transition `apps/promotions/views.py:1361` | 302 | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/aktionsseite/` | promotions:promotion-page-mode | promotion_page_mode `apps/promotions/views.py:468` | POST | promotions | — (inferred group) |  |  |  | Y |
| `/promotions/heute/ausblenden/` | promotions:today-dismiss | today_dismiss `apps/promotions/views.py:822` | POST | promotions | — (inferred group) |  |  | Y | Y |
| `/promotions/inline-edit/` | promotions:promotion-inline-edit | promotion_inline_edit `apps/promotions/views.py:57` | POST | promotions | — (inferred group) |  |  |  | Y |
| `/promotions/kampagnen/` | promotions:coupon-campaigns | coupon_campaigns `apps/promotions/views.py:1827` | GET+POST | crm | Marketing/marketing |  |  |  |  |
| `/promotions/loyalty/` | promotions:loyalty-list | loyalty_list `apps/promotions/views.py:1755` | GET+POST | loyalty | Marketing/marketing(adv) |  |  |  |  |
| `/promotions/loyalty/<uuid:program_id>/stamp/` | promotions:loyalty-stamp | loyalty_stamp `apps/promotions/views.py:1784` | GET+POST | loyalty | — (inferred group) |  |  |  |  |
| `/promotions/new/` | promotions:promotion-create | promotion_create `apps/promotions/views.py:596` | GET+POST | promotions | — (inferred group) |  |  | Y | Y |
| `/promotions/newsletter/` | promotions:newsletter | newsletter_campaigns `apps/promotions/views.py:1972` | GET+POST | promotions | Marketing/marketing(adv) |  |  |  |  |
| `/promotions/photo-edit/` | promotions:promotion-photo-edit | promotion_photo_edit `apps/promotions/views.py:72` | POST | promotions | — (inferred group) |  |  |  | Y |
| `/promotions/poster/` | promotions:shop-poster | shop_poster_pdf `apps/promotions/views.py:551` | GET | promotions | — (inferred group) |  |  | Y | Y |
| `/promotions/pruefen/` | promotions:promotion-text-check | promotion_text_check `apps/promotions/views.py:922` | POST | promotions | — (inferred group) |  |  | Y | Y |
| `/promotions/pruefen/ki/` | promotions:promotion-text-check-ai | promotion_text_check_ai_start `apps/promotions/views.py:962` | POST | promotions | — (inferred group) |  |  | Y | Y |
| `/promotions/pruefen/ki/<str:job>/` | promotions:promotion-text-check-ai-result | promotion_text_check_ai_result `apps/promotions/views.py:1012` | GET | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/redeem/` | promotions:redeem | redeem_home `apps/promotions/views.py:1507` | GET+POST | promotions | Marketing/marketing(adv) |  |  | Y |  |
| `/promotions/redeem/<str:code>/` | promotions:redeem-detail | redeem_detail `apps/promotions/views.py:1602` | GET | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/redeem/<str:code>/action/` | promotions:redeem-action | redeem_action `apps/promotions/views.py:1636` | 302 | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/reservations/<uuid:pk>/action/` | promotions:reservation-action | reservation_action `apps/promotions/views.py:1469` | 302 | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/schnell/` | promotions:promotion-quick | promotion_quick `apps/promotions/views.py:658` | GET+POST | promotions | Marketing/marketing(palette) |  |  | Y |  |
| `/promotions/schnell/ki/` | promotions:promotion-quick-ai | promotion_quick_ai_start `apps/promotions/views.py:852` | POST | promotions | — (inferred group) |  |  | Y | Y |
| `/promotions/schnell/ki/<str:job>/` | promotions:promotion-quick-ai-result | promotion_quick_ai_result `apps/promotions/views.py:898` | GET | promotions | — (inferred group) |  |  | Y |  |
| `/promotions/typen/` | promotions:promo-type-list | promo_type_list `apps/promotions/views.py:369` | GET | promotions | Marketing/marketing(adv) |  |  |  |  |
| `/promotions/typen/speichern/` | promotions:promo-type-save | promo_type_save `apps/promotions/views.py:396` | POST | promotions | — (inferred group) |  |  |  | Y |
| `/promotions/vouchers/` | promotions:voucher-list | voucher_list `apps/promotions/views.py:1689` | GET+POST | loyalty | Marketing/marketing |  |  |  |  |
| `/promotions/vouchers/redeem/` | promotions:voucher-redeem | voucher_redeem `apps/promotions/views.py:1723` | GET+POST | loyalty | — (inferred group) |  |  | Y | Y |

### Website (19)

| path | name | view (file:line) | method | module | nav entry | own | lite | TG | unl |
|---|---|---|---|---|---|---|---|---|---|
| `/dashboard/design/` | design | design_view `apps/core/design_page.py:112` | GET+POST | dashboard* | Website/site |  |  |  |  |
| `/dashboard/domains/` | domains | domains_view `apps/core/views.py:4391` | GET | settings* | Website/site(adv) |  |  |  |  |
| `/dashboard/domains/<int:pk>/remove/` | domain-remove | domain_remove `apps/core/views.py:4429` | POST | settings* | — (inferred group) |  |  |  |  |
| `/dashboard/domains/<int:pk>/verify/` | domain-verify | domain_verify `apps/core/views.py:4418` | POST | settings* | — (inferred group) |  |  |  |  |
| `/dashboard/domains/add/` | domain-add | domain_add `apps/core/views.py:4405` | POST | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/medien/` | media-library | media_library `apps/core/views.py:4487` | GET+POST | dashboard* | Website/site(adv) |  |  |  |  |
| `/dashboard/site/` | site | site_view `apps/core/views.py:1588` | 302 | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/cblock-photo/` | site-cblock-photo-edit | site_cblock_photo_edit `apps/core/views.py:3913` | POST | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/home/` | site-home | home_builder_view `apps/core/views.py:1968` | GET+POST | settings* | ANCHOR:Website |  |  |  |  |
| `/dashboard/site/menu/` | site-menu | menu_builder_view `apps/core/views.py:4117` | GET+POST | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/pages/` | site-pages | pages_view `apps/core/views.py:4105` | 302 | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/preview/` | site-preview | site_preview `apps/core/views.py:3631` | GET | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/preview/draft/` | site-preview-draft | site_preview_draft `apps/core/views.py:3638` | POST | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/preview/edit/` | site-inline-edit | site_inline_edit `apps/core/views.py:3971` | POST | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/scope/` | site-scope-state | studio_scope_state `apps/core/views.py:4438` | GET | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/scope/save/` | site-scope-save | studio_scope_save `apps/core/views.py:4464` | POST | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/sections/` | site-sections | sections_view `apps/core/views.py:4045` | GET+POST | settings* | — (inferred group) |  |  |  | Y |
| `/dashboard/site/seo/` | site-seo | seo_settings_view `apps/core/views.py:4171` | GET+POST | settings* | Website/site(adv) |  |  |  |  |
| `/dashboard/site/share-preview/` | site-share-preview | share_preview_issue `apps/core/views.py:3881` | POST | settings* | — (inferred group) |  |  |  | Y |

### Einstellungen (24)

| path | name | view (file:line) | method | module | nav entry | own | lite | TG | unl |
|---|---|---|---|---|---|---|---|---|---|
| `/dashboard/billing/` | billing | billing `apps/billing/views.py:23` | GET | billing* | Einstellungen/settings | Y |  |  |  |
| `/dashboard/billing/checkout/` | billing-checkout | checkout `apps/billing/views.py:40` | POST | billing* | — (inferred group) | Y |  |  | Y |
| `/dashboard/billing/payments/` | billing-payments | payments `apps/billing/views.py:82` | GET | billing* | Einstellungen/settings(palette) | Y |  |  |  |
| `/dashboard/billing/payments/callback/` | billing-payments-callback | payments_callback `apps/billing/views.py:135` | 302 | billing* | — (inferred group) | Y |  |  | Y |
| `/dashboard/billing/payments/connect/` | billing-payments-connect | payments_connect `apps/billing/views.py:120` | POST | billing* | — (inferred group) | Y |  |  | Y |
| `/dashboard/billing/payments/methods/` | billing-payments-methods | payments_methods `apps/billing/views.py:112` | 302 | billing* | — (inferred group) | Y |  |  | Y |
| `/dashboard/billing/portal/` | billing-portal | portal `apps/billing/views.py:54` | POST | billing* | — (inferred group) | Y |  |  | Y |
| `/dashboard/einstellungen/` | einstellungen-home | einstellungen_home `apps/core/settings_home.py:70` | GET | dashboard* | ANCHOR:Einstellungen |  |  |  |  |
| `/dashboard/extras/` | extras | extras_view `apps/core/views.py:34` | GET+POST | settings* | Einstellungen/settings(adv) |  |  |  |  |
| `/dashboard/finder/` | finder-settings | finder_settings `apps/core/views.py:1227` | GET+POST | dashboard* | Einstellungen/settings(adv) |  |  |  |  |
| `/dashboard/help/` | support:help | help_list `apps/support/views.py:16` | GET+POST | settings* | Einstellungen/settings(adv) |  |  |  |  |
| `/dashboard/help/<int:pk>/` | support:thread | help_thread `apps/support/views.py:35` | GET+POST | settings* | — (inferred group) |  |  |  |  |
| `/dashboard/integrationen/` | integrations-home | integrations_home `apps/core/views.py:5913` | GET | dashboard* | Einstellungen/settings |  |  |  |  |
| `/dashboard/integrationen/telegram-aktivieren/` | integrations-telegram-activate | integrations_telegram_activate `apps/core/views.py:5998` | POST | dashboard* | — (inferred group) | Y |  |  | Y |
| `/dashboard/modules/` | modules | modules_view `apps/core/views.py:4273` | GET+POST | settings* | Einstellungen/settings(adv) |  |  |  |  |
| `/dashboard/recht/` | legal-docs | legal_docs_view `apps/core/views.py:1466` | GET+POST | settings* | Einstellungen/settings | Y |  |  |  |
| `/dashboard/settings/` | settings | settings_view `apps/core/views.py:1060` | GET+POST | settings* | Einstellungen/settings |  |  |  |  |
| `/dashboard/settings/google-bewertungen/` | google-reviews-settings | google_reviews_settings `apps/core/views.py:6017` | GET+POST | settings* | Einstellungen/settings(palette) |  |  |  |  |
| `/dashboard/settings/languages/` | languages | languages_view `apps/core/views.py:1404` | GET+POST | settings* | Einstellungen/settings |  |  |  |  |
| `/dashboard/settings/notifications/` | notifications-settings | notifications_settings `apps/core/views.py:5674` | GET+POST | settings* | Einstellungen/settings |  |  |  |  |
| `/dashboard/settings/notifications/telegram/connect/` | platform-bot-connect | platform_bot_connect `apps/core/views.py:5774` | POST | settings* | — (inferred group) | Y |  |  | Y |
| `/dashboard/settings/notifications/telegram/disconnect/` | platform-bot-disconnect | platform_bot_disconnect `apps/core/views.py:5799` | POST | settings* | — (inferred group) | Y |  |  | Y |
| `/dashboard/settings/payments/` | payment-settings | payment_settings `apps/core/views.py:1207` | GET+POST | settings* | Einstellungen/settings |  |  |  |  |
| `/dashboard/settings/team/` | team | team_view `apps/core/team.py:77` | GET+POST | settings* | Einstellungen/settings | Y |  |  |  |

### Lite-Kabinett (3)

| path | name | view (file:line) | method | module | nav entry | own | lite | TG | unl |
|---|---|---|---|---|---|---|---|---|---|
| `/dashboard/geschaeft/` | lite-business | lite_business `apps/core/lite_cabinet.py:103` | GET+POST | dashboard* | — (inferred group) |  | Y | Y | Y |
| `/dashboard/sichtbarkeit/` | lite-visibility | lite_visibility `apps/core/lite_cabinet.py:189` | GET | dashboard* | — (inferred group) |  | Y | Y | Y |
| `/dashboard/teilen/` | lite-share | lite_share `apps/core/lite_cabinet.py:135` | GET | dashboard* | — (inferred group) |  | Y | Y | Y |

### Übersicht/служебное (5)

| path | name | view (file:line) | method | module | nav entry | own | lite | TG | unl |
|---|---|---|---|---|---|---|---|---|---|
| `/dashboard/cabinet-lang/` | set-cabinet-lang | set_cabinet_lang_view `apps/core/views.py:4367` | POST | dashboard* | — (inferred group) |  |  | Y | Y |
| `/dashboard/palette-search/` | palette-search | palette_search `apps/core/views.py:5891` | GET | dashboard* | — (inferred group) |  |  |  | Y |
| `/dashboard/presence/` | set-presence | set_presence_view `apps/core/views.py:4349` | 302 | dashboard* | — (inferred group) |  |  |  | Y |
| `/dashboard/setup/` | setup | setup_view `apps/core/views.py:339` | GET+POST | dashboard* | — (inferred group) |  |  |  | Y |
| `/dashboard/stadtkatalog-aktuell/` | city-freshness-confirm | freshness_confirm `apps/aggregator/owner_views.py:43` | POST | dashboard* | — (inferred group) |  |  |  | Y |
## 10. Стенд: обход кабинетов 22 демо (2026-10-23)

Локальный стенд (`config.settings.stand`), 19 отраслевых демо + 3 лёгких/городских, вход
владельцем, обход ссылок кабинета в ширину (до 70 экранов на демо), для каждого экрана —
снимок 1440 px и 390 px и машинные метрики. Всего **1402 экрана**, снимки — в scratchpad
сессии (в git не кладём).

**Находки, исправленные сразу (хотфикс KA-H3, в main):**
- экран «Aktionstypen» (`/promotions/typen/`) падал **500 у всех бизнесов** — шаблон
  наследовал несуществующую базу, а содержимое лежало в блоке, которого у базы нет;
- бейджи в шапке карточек сделок («bezahlt», «🏷 Aktion», номер комнаты) **не выводились
  ни на одной из пяти карточек** — блок жил внутри `{% include %}`, его Django не даёт
  переопределить;
- замок `test_template_extends` ловит оба класса по всем шаблонам.

**Метрики (вход для KA-6/KA-9):**
- горизонтального переполнения на 390 px — **0 экранов**;
- ошибок 500 — 0 (две на главной оказались локальными схемами без свежей миграции);
- **поля без подписи** (нет `<label>`/`aria-label`) — от 223 (лёгкий кабинет) до 929 (магазин)
  на демо; лидеры — `/dashboard/stock/` (матрица склада), `/dashboard/booking/leistungen/`,
  `/dashboard/settings/notifications/` (матрица чекбоксов), `/dashboard/settings/payments/`,
  `/dashboard/ablaeufe/`; это прямой пункт WCAG 1.3.1/4.1.2 (KA-1);
- **мелкие цели нажатия** (меньше 24 px, WCAG 2.5.8) — на 13–25 экранах каждого демо,
  максимум — склад (до 1524 мелких элементов) и коллекции;
- изображений без `alt` — 0.
- **лёгкий бизнес «Nur Aktionen»** (klingenbrot) по ссылкам из своего кабинета дошёл до
  70 экранов полного кабинета (склад, закупки, блог, кампании, лояльность, CRM, Studio…) —
  подтверждает KA-0 §5: лёгкий режим упрощает меню, но не ограничивает доступ.
