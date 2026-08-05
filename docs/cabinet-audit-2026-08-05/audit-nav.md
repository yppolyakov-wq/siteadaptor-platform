# AUDIT: nav

## INVENTORY
ПОЛНАЯ КАРТА НАВИГАЦИИ КАБИНЕТА (только чтение, без изменений)

=== 0. ИСТОЧНИКИ ПРАВДЫ (4 параллельных реестра + 3 поколения «продаж») ===
- `apps/core/modules.py` — REGISTRY/NavItem (modules.py:66-518), NAV_GROUPS (555-568), NAV_TASK_LABELS (576-617), sidebar_nav (653-712), _sales_nav_item (629-650), гейты ui_mode/classic_ui (719-764).
- `apps/core/templatetags/cabinet.py` — HUB_TABS (51-132) + тег hub_tabs (135-159) + orders_view_switch (170-180).
- `apps/core/dashboard.py` — home_widgets (107-258), hub_tiles (261-313), dashboard_tiles (12-86, МЁРТВ).
- `apps/core/context.py:250-291` — nav_compact / nav_primary / has_sellables / nav_groups в контекст.
- Шаблон: `templates/tenant/_base_dashboard.html` (компакт-ветка 46-64, классик-ветка 65-110, шапка 115-147, мобильный таб-бар 164-182, JS-поиск 223-246).
- Партиал табов: `templates/tenant/_hub_tabs.html` (ящик «Erweitert» — строки 14-24).

=== 1. САЙДБАР (не-classic, ДЕФОЛТ) — modules.sidebar_nav, 7 якорей + 1 CTA ===
Рендер: `_base_dashboard.html:46-64`. Подсветка ТОЛЬКО по `nav == it.nav_key`.
- 🏠 «Übersicht» → `dashboard` = /dashboard/ · nav_key `dashboard` · гейт нет (modules.py:657-663)
- 🗂️ «Verkäufe» → `orders_view.entry_url_name(tenant)` (modules.py:629-650). НЕ-classic → ВСЕГДА `verkaeufe` = /dashboard/verkaeufe/ (orders_view.py:85-99); nav_key вычисляется по карте {board,orders:order-list,booking:calendar,stays:calendar} → «verkaeufe» там НЕТ → фолбэк `board`. Гейт нет.
- 📦 «Angebote» → `sellable-manage` = /dashboard/angebote/ · nav_key `sellables` · гейт `any(catalog|booking|stays|events)` (modules.py:668) — ФАКТИЧЕСКИ ВСЕГДА TRUE (catalog core=True, modules.py:98+539)
- 📣 «Marketing» → `marketing-home` = /dashboard/marketing/ · nav_key `promotions` · бейдж inbox · ГЕЙТ: модуль promotions активен (modules.py:678)
- 🔌 «Integrationen» → `integrations-home` = /dashboard/integrationen/ · nav_key `integrations` · гейт нет
- ✏️ «Website» → `site` = /dashboard/site/ · nav_key `site` · гейт нет
- ⚙️ «Einstellungen» → `settings` = /dashboard/settings/ · nav_key `settings` · search-строка обещает «finanzen auswertungen funktionen» (modules.py:709)
- ➕ «Funktion hinzufügen» → `modules` = /dashboard/modules/ (шаблон, _base_dashboard.html:60-64)
Гейт ui_mode: НЕТ (simple_hidden_modules в sidebar_nav не вызывается). Гейт архетипа: НЕТ.

=== 1b. САЙДБАР classic_ui — легаси-ветка AB1 (группы) ===
`sidebar_nav` возвращает [] при classic_ui (modules.py:656) → шаблон рендерит `nav_groups` (grouped_active_modules, modules.py:778-797), _base_dashboard.html:65-110. Гейты: активный модуль + simple_hidden_modules (SIMPLE_HIDDEN_MODULES={finance,analytics} modules.py:744 + ARCHETYPE_SIMPLE_HIDDEN{friseur,handwerker,events,hotel→catalog} modules.py:750-755).
- Спец-пункт «📦 Angebote» → sellable-manage (has_sellables, _base_dashboard.html:69-75)
- Группа «Mein Geschäft»: Übersicht → /dashboard/
- Группа «Verkaufen»: Verkäufe(board) → /dashboard/board/; Sortiment(catalog) → /catalog/products/; + сюда же ПАДАЕТ Blog (не описан в NAV_GROUPS → дефолт «sell», modules.py:791) → /dashboard/blog/
- Группа «Kunden & Marketing»: Kunden(crm) → /crm/ (с бейджем inbox); Marketing(promotions) → /promotions/
- Группа «Einstellungen»: Auswertungen(analytics) → /promotions/analytics/; Finanzen(finance) → /dashboard/finance/; Website gestalten(site) → /dashboard/site/; Einstellungen → /dashboard/settings/; Abrechnung(billing) → /dashboard/billing/
Модули с nav_items=() в группах невидимы: orders, booking, stays, events, jobs, reviews, loyalty, publishing, inbox, telegram, gift, customer_account.

=== 1c. МОБИЛЬНЫЙ ТАБ-БАР ===
`context.py:250-269` → nav_primary = первые 4 якоря компакт-сайдбара (или первые 4 nav_items модулей в classic). Рендер `_base_dashboard.html:164-182` + кнопка «☰ Menu» (открывает сайдбар). Т.е. на мобиле: Übersicht · Verkäufe · Angebote · Marketing (Einstellungen/Website/Integrationen — только через ☰).

=== 2. ХАБЫ (HUB_TABS, cabinet.py:51-132) — 6 хабов, гейт только по module_key ===
Гейт ui_mode/архетипа у табов ОТСУТСТВУЕТ. advanced=True → ящик «Erweitert».
(a) «catalog» (Sortiment) — рендерится на /catalog/*, /dashboard/stock/, /dashboard/purchasing/, /imports/*:
   Produkte /catalog/products/ · Kategorien /catalog/categories/ · Lager /dashboard/stock/ · Kombi /catalog/combos/ · Import /imports/start/ · [Erw] Einkauf /dashboard/purchasing/. Все module_key=None (catalog core).
(b) «board» (Verkäufe) — на board.html, orders/order_list, booking/calendar, stays/today, events/event_list, jobs/list:
   Board /dashboard/board/ (mod board) · Bestellungen /dashboard/orders/ (orders) · Termine /dashboard/booking/ (booking) · Übernachtungen /dashboard/stays/ (stays) · Tickets /dashboard/events/ (events) · Aufträge /dashboard/auftraege/ (jobs).
   ВАЖНО: при не-classic 4 из 6 табов скрываются `covered` (cabinet.py:148-150) → остаются только Tickets и Aufträge.
(c) «marketing» — на /promotions/*, /dashboard/reviews/, /dashboard/marketing/, /dashboard/finder/, /dashboard/channels/, /dashboard/posts/:
   Aktionen /promotions/ (promotions) · Bewertungen /dashboard/reviews/ (reviews) · Kampagnen /promotions/kampagnen/ (crm) · Gutscheine /promotions/vouchers/ (loyalty) · [Erw] Reservierungen /promotions/reservations/ · Einlösen /promotions/redeem/ · Treuepunkte /promotions/loyalty/ · Kontakte /crm/ (crm) · Nachrichten /dashboard/inbox/ (inbox) · Telegram /dashboard/telegram/ (telegram) · Care-Zyklus /dashboard/settings/notifications/ (nav_key «care») · Kanäle /dashboard/channels/ (publishing) · Beiträge /dashboard/posts/ (publishing) · Finder /dashboard/finder/.
(d) «sellables» (Angebote) — только на /dashboard/angebote/:
   Angebote /dashboard/angebote/ · [Erw] Produkte · Kategorien · Lager · Einkauf · Kombi · Import (ДУБЛЬ хаба (a)).
(e) «kunden» — на /crm/*, /dashboard/inbox/, /dashboard/telegram/:
   Kontakte /crm/ · Nachrichten /dashboard/inbox/ · Telegram /dashboard/telegram/ (ДУБЛЬ трёх табов хаба (c)). Якоря в сайдбаре нет с ST-4b.
(f) «settings» — на /dashboard/settings/, /dashboard/settings/payments/, /dashboard/settings/notifications/, /dashboard/recht/, /dashboard/extras/, /dashboard/settings/languages/, /dashboard/medien/, /dashboard/domains/, /dashboard/modules/, /dashboard/help/:
   Einstellungen · Zahlung & Versand · Benachrichtigungen · Rechtstexte · Zusatzleistungen · Sprachen · [Erw] Medien · Domains · Funktionen · Hilfe. Все module_key=None.
Хабов НЕТ у: site-билдера (свой card-хаб), finance, analytics, billing, blog, collections, verkaeufe.

=== 3. ГЛАВНАЯ /dashboard/ (views.py:93-154 + templates/tenant/dashboard.html) ===
- Плашка прогресса мастера → /dashboard/setup/ (dashboard.html:8-11), если setup не завершён.
- Карточка присутствия (POST set-presence) + ссылка на settings при пустом WhatsApp (dashboard.html:32).
- ВИДЖЕТЫ `home_widgets` (dashboard.py:107-258), гейт модуль + simple_hidden:
  💶 Umsatz heute → finance:journal /dashboard/finance/ (модуль finance) · 📦 Abholbereit → orders:order-list?status=ready (orders) · 🛎 Anreisen heute → stays:today /dashboard/stays/heute/ (stays) · 📣 Marketing-Puls → promotions:analytics /promotions/analytics/ (promotions) · ⭐ Bewertungen → reviews:list (reviews).
- ПЛИТКИ-ХАБЫ `hub_tiles` (dashboard.py:261-313), БЕЗ гейтов (вопреки докстрингу 264-265):
  Bestellungen → entry_url_name = /dashboard/verkaeufe/ · Angebot → /dashboard/angebote/ · Marketing → /dashboard/marketing/ · Integrationen → /dashboard/integrationen/ · Einstellungen → /dashboard/settings/ · Website (wide) → /dashboard/site/home/.
- Чек-лист готовности `onboarding.completeness` (onboarding.py:488-520): Banner→site · Öffnungszeiten→settings · Kontakt→settings · «Add your first X»→offer_cta (catalog:product-list | stays:units | events:list | booking:services | promotions:promotion-list, onboarding.py:454-460) · Impressum→settings. Показывается только при percent<100; выполненный пункт превращается в НЕ-ссылку (dashboard.html:82-84).
- classic_ui-блок (dashboard.html:97-104): подсказка + 3 кнопки Tasks/board, Your site/site, Settings.
- Канбан на главной + «Full view →» (dashboard.html:115-121) → board ИЛИ sales_entry_url (для календарных архетипов) + отдельный CTA «📅 Belegungsplan» (108-114).
- `dashboard_tiles()` (dashboard.py:12-86) — НЕ ВЫЗЫВАЕТСЯ НИГДЕ (views.py:141 «остаётся для истории»).

=== 4. ВСЕ nav_items В REGISTRY ===
С пунктами (видны только в classic-сайдбаре, кроме site/settings): dashboard→dashboard(71) · board→board(83) · catalog→catalog:product-list(96) · promotions→promotions:promotion-list(112) · crm→crm:customer-list(145) · analytics→promotions:analytics(304) · blog→blog-list(363) · finance→finance:journal(432) · settings→site + settings(493-496) · billing→billing(513).
Свёрнутые nav_items=(): reviews(172) · orders(202) · booking(218) · stays(232) · loyalty(249) · gift(268) · publishing(314) · jobs(325) · events(347) · inbox(400) · telegram(442) · customer_account(456).
Гейт путей — ModuleGatingMiddleware по url_prefixes (middleware.py:64-74, самый длинный префикс, modules.py:889-901). /dashboard/verkaeufe/, /dashboard/marketing/, /dashboard/integrationen/, /dashboard/medien/, /dashboard/collections/ попадают под core-префикс «/dashboard/» → модульного гейта не имеют.

=== 5. ТРИ ПОКОЛЕНИЯ «ПРОДАЖ» ЖИВУТ ОДНОВРЕМЕННО ===
V4 `verkaeufe` (views.py:3110-3158, sales_page.py, templates/core/verkaeufe.html): вкладки по kind (primary всегда + kinds_with_sales, sales_page.py:72-87) + кнопки видов Kalender/Board/Liste (persist sales_views). БЕЗ hub_tabs и БЕЗ orders_view_switch.
ST-5b сегмент `orders_view_switch` (cabinet.py:170-180) — на order_list, booking/calendar, stays/calendar, stays/stay_new, board; там же плашка «Alte Ansicht · 🆕 Alles auf einer Seite →» (_orders_view_switch.html:17).
S2 хаб-табы «board» — на тех же страницах, но урезанные до Tickets/Aufträge.
Плюс третий уровень — строки ссылок внутри тел: `stays/_belegungsplan_body.html:10-24` (Heute/Channels/Check-ins/Reports/Units/Preise) и `booking/_tagesplan_body.html:8-12` (Services/Passes/Tage blockieren/Einstellungen).

=== 6. ГЛУБИНА КЛИКОВ (Expert, дефолтный UI) ===
- Изменить цену товара: сайдбар «Angebote» (1) → «Bearbeiten» на карточке (2) → base_price лежит на первой панели «Basics» (catalog/product_form.html:65-68) → Save (3). Через плитку главной «Angebot» — та же глубина. Через таб «Erweitert→Produkte» — 4 клика. Поиск по меню как ускоритель НЕ работает (см. проблемы).
- Увидеть сегодняшние брони: отель — виджет «🛎 Anreisen heute» (1 клик) либо «Verkäufe»→«📋 Heute →» (2); Friseur/booking — «Verkäufe» (1, Tagesplan = сегодня), виджета «сегодня» для booking НЕТ; кафе с catalog-primary — «Verkäufe» (1) → вкладка «Termine» (2), НО вкладка появляется только когда есть хотя бы одна бронь (sales_page.py:72-87), иначе /dashboard/booking/ достижим лишь через board → hub-таб.
- Настроить оплату: «Einstellungen» (1) → таб «Zahlung & Versand» (2); ИЛИ «Integrationen» (1) → «Zahlung & Stripe» (2); ИЛИ плитка главной «Einstellungen» (1) → таб (2). 2 клика, но 3 пути и 3 разных имени одного экрана.
- Посмотреть счёт за подписку: входов НЕТ (см. проблемы).

## PROBLEMS

### [high] Поиск по меню в сайдбаре сломан в дефолтном (компактном) режиме
JS фильтра итерирует `#dash-nav .nav-group` (_base_dashboard.html:234), но компактная ветка (строки 50-58) рендерит плоские `<a class="nav-link">` БЕЗ обёрток .nav-group — они есть только в классик-ветке (строка 77). Итог: при вводе любого текста ни один пункт не скрывается, а `anyShown` остаётся false → `empty.classList.toggle("hidden", false)` ПОКАЗЫВАЕТ плашку «Nothing found.» (строка 244) поверх полного списка. Т.е. главный ускоритель навигации («ищи, а не броди») в дефолтном UI не работает и вдобавок врёт.
Files: templates/tenant/_base_dashboard.html

### [high] Экран-сирота: Abo & Zahlung (/dashboard/billing/) недостижим из нового кабинета
Пункт есть только как NavItem классик-сайдбара (modules.py:513). В компактном сайдбаре его нет, в HUB_TABS["settings"] (cabinet.py:117-131) вкладки «Abrechnung» нет, среди плиток главной и карточек Integrationen — нет. Единственная ссылка `{% url 'billing' %}` во всём templates/ — «← Billing» внутри самой billing/payments.html:6. Владелец на новом UI не может открыть свою подписку/счета; баннер «Your subscription is inactive» (_base_dashboard.html:150-152) тоже без ссылки.
Files: apps/core/modules.py, apps/core/templatetags/cabinet.py, templates/tenant/_base_dashboard.html

### [high] Экран-сирота: Newsletter-кампании (/promotions/newsletter/) — ноль входов во всём проекте
View `newsletter_campaigns` (apps/promotions/views.py:976) + шаблон templates/promotions/newsletter.html существуют; имя маршрута `promotions:newsletter` встречается ТОЛЬКО в urls.py:44 и в собственном redirect view (views.py:1002). Ни в HUB_TABS, ни в marketing_home.cards, ни в одном шаблоне ссылки нет. Страница даже не рендерит hub-табы — попав туда по URL, вернуться нечем.
Files: apps/promotions/views.py, apps/promotions/urls.py, templates/promotions/newsletter.html

### [high] Экран-сирота: Blog & News (/dashboard/blog/) виден только в классик-режиме
У модуля blog есть NavItem (modules.py:363) и метка NAV_TASK_LABELS["blog"]=«Blog & News» (modules.py:601), но nav_items рендерятся ТОЛЬКО в классик-ветке сайдбара. В HUB_TABS ключа blog нет ни в одном хабе, в hub_tiles и home_widgets — нет. Единственная ссылка в шаблонах — «← All posts» на templates/events/blog_edit.html:6, куда попасть можно лишь со списка блога. Модуль включён по умолчанию у всех архетипов (recommended_for = все типы) — то есть оплаченная функция невидима.
Files: apps/core/modules.py, apps/core/templatetags/cabinet.py, templates/events/blog_list.html

### [high] Finanzen и Auswertungen: сайдбар обещает их в «Einstellungen», а хаб не содержит
search-строка якоря «Einstellungen» — «einstellungen finanzen auswertungen funktionen» (modules.py:709), но HUB_TABS["settings"] (cabinet.py:117-131) содержит только Einstellungen/Zahlung/Benachrichtigungen/Rechtstexte/Zusatzleistungen/Sprachen + Erweitert(Medien/Domains/Funktionen/Hilfe). Финансов и аналитики там нет. /dashboard/finance/ достижим лишь виджетом «Umsatz heute» (dashboard.py:127-155), который сам скрыт в Простом режиме (SIMPLE_HIDDEN_MODULES, modules.py:744) → включив Finanzen на «Funktionen», владелец в Простом режиме теряет к ним доступ полностью. /promotions/analytics/ — только виджет «Marketing-Puls» + метрика на marketing_home.
Files: apps/core/modules.py, apps/core/templatetags/cabinet.py, apps/core/dashboard.py

### [high] Модуль promotions — единственная дверь к CRM/Inbox/Telegram/Bewertungen/Gutscheine
Якорь «Marketing» в компактном сайдбаре гейтится `is_module_active(tenant,"promotions")` (modules.py:678). Хаб «kunden» (cabinet.py:109-113) после ST-4b якоря не имеет, отдельных якорей Kunden/Nachrichten/Bewertungen нет. Выключив «Aktionen & Reservierung» на /dashboard/modules/, владелец теряет из меню ВЕСЬ маркетинг-блок: Kontakte(/crm/), Nachrichten(/dashboard/inbox/), Telegram, Bewertungen, Kampagnen, Gutscheine, Treuepunkte, Kanäle, Beiträge, Care-Zyklus, Finder — вместе с бейджем непрочитанных сообщений (_base_dashboard.html:55-56).
Files: apps/core/modules.py, apps/core/templatetags/cabinet.py, templates/tenant/_base_dashboard.html

### [high] Один экран — два хаба и два разных имени: /dashboard/settings/notifications/
Этот URL — вкладка «Care-Zyklus» (nav_key «care») в хабе Marketing (cabinet.py:89) И вкладка «Benachrichtigungen» (nav_key «notifications») в хабе Einstellungen (cabinet.py:121). Вьюха отдаёт nav="notifications" (views.py:3584), а шаблон рендерит `hub_tabs "settings"` (templates/tenant/notifications.html:6). Итог: nav_key «care» не выставляет НИКТО (grep по apps/: значения nav — без «care»), таб «Care-Zyklus» никогда не подсвечивается, а клик по нему из Marketing выбрасывает пользователя в ЧУЖОЙ таб-бар (Einstellungen) под другим названием, без пути назад в Marketing. Плюс тот же экран — карточка «Erinnerungen & Care-Zyklus» на marketing_home (marketing_home.py:26-31) и карточка «Benachrichtigungen & Telegram» на integrations_home (views.py:3631-3637): 4 входа, 3 имени.
Files: apps/core/templatetags/cabinet.py, apps/core/views.py, templates/tenant/notifications.html, apps/core/marketing_home.py

### [high] Хаб «Kunden» дублирует три вкладки хаба «Marketing» и работает как ловушка
HUB_TABS["kunden"] = Kontakte/Nachrichten/Telegram (cabinet.py:109-113) — ровно те же три URL, что в Erweitert-ящике HUB_TABS["marketing"] (cabinet.py:85-87). Страницы crm/inbox/telegram рендерят `hub_tabs "kunden"` (templates/crm/customer_list.html:6, templates/inbox/list.html:6, templates/telegram/settings.html:6). Пользователь заходит из Marketing → таб-бар молча подменяется на Kunden → вернуться к Marketing-вкладкам можно только браузерной кнопкой «назад».
Files: apps/core/templatetags/cabinet.py, templates/crm/customer_list.html, templates/inbox/list.html

### [medium] Sortiment существует в двух хабах с разными таб-барами и без обратной связи
HUB_TABS["sellables"] (cabinet.py:98-106) кладёт Produkte/Kategorien/Lager/Einkauf/Kombi/Import в «Erweitert», а HUB_TABS["catalog"] (cabinet.py:53-61) те же 6 страниц показывает прямыми табами. Страницы каталога рендерят `hub_tabs "catalog"`, где вкладки «Angebote» НЕТ → уйдя из Angebote в Produkte, обратно в Angebote из таб-бара не вернуться. Сам комментарий в коде признаёт «это дубль-вход, не перенос» (cabinet.py:96-97).
Files: apps/core/templatetags/cabinet.py, templates/catalog/product_list.html, templates/tenant/sellable_manage.html

### [high] Подсветка сайдбара теряется на большинстве экранов
Компактный сайдбар подсвечивает пункт строго по `nav == it.nav_key` (_base_dashboard.html:52) при 7 возможных nav_key (dashboard/board/sellables/promotions/integrations/site/settings). Вьюхи выставляют 43 разных значения nav (catalog, categories, stock, purchasing, combos, imports, orders, booking, stays, events, jobs, crm, inbox, telegram, reviews, campaigns, vouchers, loyalty, reservations, redeem, channels, posts, finder, notifications, payments, legal-docs, extras, languages, media, domains, modules, support, analytics, finance, billing, collections…). На всех этих страницах — включая вкладки собственного хаба Einstellungen (Zahlung, Rechtstexte, Sprachen, Domains, Funktionen) — в сайдбаре не подсвечено НИЧЕГО: владелец не понимает, «где он».
Files: templates/tenant/_base_dashboard.html, apps/core/modules.py

### [medium] Marketing-центр подсвечивает чужую вкладку «Aktionen»
marketing_home отдаёт nav="promotions" (views.py:3609), а шаблон рендерит `hub_tabs "marketing"` (templates/tenant/marketing_home.html:6), где первая вкладка «Aktionen» имеет nav_key «promotions» (cabinet.py:76). На /dashboard/marketing/ таб «Aktionen» выглядит активным, хотя открыт другой экран; клик по нему уводит на /promotions/ — пользователь жмёт «уже активную» вкладку и попадает в другое место. Самого Marketing-центра среди вкладок хаба нет — из /promotions/ на лендинг вернуться нечем.
Files: apps/core/views.py, apps/core/templatetags/cabinet.py, templates/tenant/marketing_home.html

### [medium] Плитки главной игнорируют гейты модулей — «сайдбар говорит одно, главная другое»
hub_tiles (apps/core/dashboard.py:261-313) возвращает 6 плиток безусловно, хотя докстринг (строки 264-265) утверждает «гейты по модулям — плитка выключенного модуля не показывается». При выключенном promotions сайдбар якоря «Marketing» не показывает (modules.py:678), а плитка «Marketing» на главной есть и ведёт на /dashboard/marketing/, где карточки и вкладки отфильтрованы → почти пустой экран.
Files: apps/core/dashboard.py, apps/core/modules.py

### [medium] «Website» — три входа с двумя разными целями под одним именем
Сайдбар «Website» → `site` = /dashboard/site/ (modules.py:698-703); шапка «✏️ Website» → тоже `site` (_base_dashboard.html:143); плитка главной «Website» → `site-home` = /dashboard/site/home/ (dashboard.py:305-311). Одна подпись, два разных экрана (карточный хаб из 6 карточек vs билдер главной). Плюс чек-лист готовности «Add a banner or photo» → снова `site` (onboarding.py:490-495).
Files: apps/core/modules.py, apps/core/dashboard.py, templates/tenant/_base_dashboard.html, apps/tenants/onboarding.py

### [high] Режим Einfach/Experte почти ничего не делает, но занимает главное место в шапке
Тумблер виден на каждой странице (_base_dashboard.html:124-128) с подсказкой «Simple mode hides from the menu: …». Но в дефолтном компактном сайдбаре `simple_hidden_modules` не применяется вообще — sidebar_nav (modules.py:653-712) её не вызывает. Реально ui_mode влияет только на: классик-сайдбар (grouped_active_modules, modules.py:785), виджеты главной (dashboard.py:122), скрытие продвинутых секций в settings.html:57-60 и вкладок формы товара (catalog/product_form.html:55-59). HUB_TABS режим не учитывают вовсе. Обещание «Простой режим упрощает меню» в новом UI ложно; ARCHETYPE_SIMPLE_HIDDEN (modules.py:750-755) и её докстринг «скрыть из сайдбара» — мертвы для дефолтного вида.
Files: apps/core/modules.py, templates/tenant/_base_dashboard.html, apps/core/templatetags/cabinet.py

### [medium] Мёртвый код навигации: dashboard_tiles
`dashboard_tiles()` (apps/core/dashboard.py:12-86) — 75 строк с логикой бейджей «Nicht ausgefüllt» и гейтов — не вызывается ни одной вьюхой; views.py:141 прямо помечает «остаётся для истории». Реестр входов, который выглядит источником правды, но ни на что не влияет.
Files: apps/core/dashboard.py, apps/core/views.py

### [medium] Мёртвый гейт «Angebote» + дублирующая переменная has_sellables
Гейт `any(is_module_active(t,m) for m in ("catalog","booking","stays","events"))` (modules.py:668 и context.py:288) всегда истинен, т.к. catalog объявлен core=True (modules.py:98) и is_module_active возвращает True без проверок (modules.py:539-540). Handwerker без товаров/услуг всё равно получает якорь «Angebote». Плюс has_sellables считается отдельно от sidebar_nav и используется только классик-веткой шаблона — два источника правды для одного пункта.
Files: apps/core/modules.py, apps/core/context.py, templates/tenant/_base_dashboard.html

### [high] Хаб «Verkäufe» разорван: три поколения контролов на одной задаче
Якорь сайдбара ведёт на V4-страницу `verkaeufe` (orders_view.py:85-99), у которой СВОИ вкладки по kind и кнопки видов (templates/core/verkaeufe.html:12-30), но нет ни hub_tabs, ни orders_view_switch. Старые страницы (board, orders/order_list, booking/calendar, stays/calendar) несут ST-5b-сегмент + урезанный до Tickets/Aufträge хаб-бар (cabinet.py:148-150) + плашку «Alte Ansicht · 🆕 Alles auf einer Seite →» (_orders_view_switch.html:17). Итого пользователь видит до трёх параллельных переключателей продаж, называющих одно и то же по-разному (Board/Kanban/Aufgaben-Board, Liste/Feed/Bestellungen, Kalender/Belegungsplan/Tagesplan).
Files: templates/core/verkaeufe.html, apps/core/templatetags/cabinet.py, templates/core/_orders_view_switch.html, apps/core/orders_view.py

### [high] Экраны управления событиями, заявками и доской достижимы только через легаси-петлю
events:list (/dashboard/events/), jobs:list (/dashboard/auftraege/) и сама доска board (/dashboard/board/) присутствуют лишь в HUB_TABS["board"], который рендерится ТОЛЬКО на этих же старых страницах (замкнутый цикл). Единственный вход извне — ссылка «Full view →» на главной (templates/tenant/dashboard.html:118), и та ведёт на board только у НЕкалендарных архетипов; у отеля/салона она ведёт на sales_entry_url = /dashboard/verkaeufe/, откуда табов нет. Следствие: у отеля/Friseur страницы «Veranstaltungen», «Aufträge», «Aufgaben-Board» (и вместе с ней настройка колонок board-settings и редактор статусов status-manager — единственные ссылки в templates/core/board.html:22 и :40) недостижимы через UI.
Files: apps/core/templatetags/cabinet.py, templates/tenant/dashboard.html, templates/core/board.html

### [medium] CTA «Belegungsplan» на главной показывается салонам и ресторанам
Блок dashboard.html:108-114 рендерится при `sales_is_calendar`, который истинен для ЛЮБОГО primary в (booking, stays) (orders_view.py:58-68). Для Friseur/Werkstatt/ресторана заголовок гласит «📅 Belegungsplan» и «Anreisen, Buchungen & Zimmer auf einen Blick» — гостиничная лексика (заезды/номера) в кабинете парикмахерской. Ссылка при этом ведёт не на календарь, а на /dashboard/verkaeufe/.
Files: templates/tenant/dashboard.html, apps/core/orders_view.py

### [medium] Чек-лист готовности ведёт Handwerker в чужой раздел
offer_cta (apps/tenants/onboarding.py:454-473) не содержит ключа "jobs", хотя primary_module его возвращает (archetypes.py:31 _PRIORITY). Для Handwerker (jobs primary) срабатывает фолбэк → «Add your first item to sell» → catalog:product-list, т.е. в каталог товаров вместо Aufträge/Angebote. Тот же дефект попадал бы в мёртвый dashboard_tiles.
Files: apps/tenants/onboarding.py, apps/core/archetypes.py

### [medium] Вход в раздел исчезает, как только задача выполнена
Чек-лист готовности рендерит выполненный пункт как зачёркнутый <span> без ссылки (templates/tenant/dashboard.html:82-84), а весь блок исчезает при readiness.percent == 100 (строка 72). Для events-архетипа это единственный прямой вход на events:list вне легаси-петли — он пропадает ровно тогда, когда организатор начинает работать. То же с «Add your first room» → stays:units и «first service» → booking:services.
Files: templates/tenant/dashboard.html, apps/tenants/onboarding.py

### [medium] Экраны без хаба и без хлебных крошек (тупики)
Страницы, которые не рендерят ни hub_tabs, ни собственную навигацию наверх: promotions/analytics.html, promotions/newsletter.html, finance/journal.html, events/blog_list.html, billing/billing.html, collections/list.html, stays/calendar.html (единственный календарь без хаб-баров — есть только orders_view_switch, в отличие от booking/calendar.html:6-7). Попав туда, вернуться можно только сайдбаром, в котором при этом ничего не подсвечено.
Files: templates/promotions/analytics.html, templates/finance/journal.html, templates/billing/billing.html, templates/collections/list.html, templates/stays/calendar.html

### [low] Подборки (Kollektionen) — полускрытый раздел с nav_key, которого нет нигде
Вьюха collections (apps/collections/views.py:136) выставляет nav="collections", но такого nav_key нет ни в sidebar_nav, ни в HUB_TABS, ни в NAV_TASK_LABELS. Единственные входы — мелкие ссылки «Collections →» в шапках трёх листингов (templates/catalog/product_list.html:11, templates/booking/services.html:10, templates/stays/units.html:14).
Files: apps/collections/views.py, apps/core/modules.py

### [medium] NAV_TASK_LABELS дублирует подписи HUB_TABS и наполовину мертва
Реестр из 37 меток (modules.py:576-617) применяется только к NavItem'ам классик-сайдбара (nav_task_label, шаблон _base_dashboard.html:90-94). Метки stock/categories/combos/imports/orders/booking/stays/events/jobs/campaigns/vouchers/loyalty/channels/posts/reservations/redeem/notifications/languages/legal-docs/extras/media/domains/modules/support не соответствуют ни одному NavItem — их живые аналоги захардкожены второй раз в HUB_TABS (cabinet.py:51-132), местами с другим текстом («Lager» vs «Lager», но «Benachrichtigungen» vs «Care-Zyklus», «Kunden» vs «Kontakte», «Auswertungen» vs отсутствие). Две несинхронизированные таблицы имён.
Files: apps/core/modules.py, apps/core/templatetags/cabinet.py

### [low] NAV_GROUPS не описывает blog и gift — «Blog» падает в группу «Verkaufen»
В NAV_GROUPS (modules.py:555-568) нет ключей blog и gift; grouped_active_modules отправляет неописанные модули в «sell» (modules.py:791). В классик-сайдбаре пункт «Blog & News» отображается в группе «Verkaufen» рядом с заказами. Там же в группе «Einstellungen» лежат Auswertungen и Finanzen — отчёты как настройки.
Files: apps/core/modules.py

### [medium] Reservierungen выпали из «продаж» и живут в Marketing
sales_page.visible_kinds намеренно исключает kind reservation (apps/core/sales_page.py:84-86), а вкладка «Reservierungen» спрятана в ящик Erweitert хаба Marketing (cabinet.py:80). Владелец, у которого резервы по акциям — реальные заявки клиентов, ищет их в «Verkäufe» и не находит; вкладка «Einlösen» (погашение) там же в Erweitert.
Files: apps/core/sales_page.py, apps/core/templatetags/cabinet.py

### [medium] Одна и та же настройка оплаты названа тремя способами в трёх местах
payment-settings достижим из: вкладки хаба «Zahlung & Versand» (cabinet.py:120), карточки Integrationen «Zahlung & Stripe» (views.py:3625-3630), баннера в списке заказов «Payment & shipping» (templates/orders/order_list.html:54), страницы billing/payments.html:46 и шага мастера payment (onboarding.py:137). Пять входов, три разных названия; при этом устаревшая страница /dashboard/billing/payments/ дублирует блок Stripe-Connect, который уже встроен в payment-settings (templates/tenant/_payment_connect.html).
Files: apps/core/templatetags/cabinet.py, apps/core/views.py, templates/orders/order_list.html, templates/billing/payments.html

### [low] Мобильный таб-бар собирается из первой четвёрки якорей и молчаливо меняет состав
nav_primary = `_compact[:4]` (apps/core/context.py:251-263). При выключенном promotions четвёртым пунктом становится «Integrationen», при classic_ui — вообще первые 4 nav_items модулей (context.py:264-269). Т.е. на мобильном нижнее меню у двух тенантов разное и непредсказуемое, а Einstellungen/Website там нет никогда.
Files: apps/core/context.py, templates/tenant/_base_dashboard.html

## QUICK WINS
- Починить фильтр меню: в компактной ветке пункты не обёрнуты в .nav-group, поэтому JS (_base_dashboard.html:227-245) ничего не фильтрует и всегда показывает «Nothing found.». Либо обернуть якоря, либо фильтровать напрямую по .nav-link.
- Вернуть вход в подписку: добавить вкладку «Abrechnung» → billing в HUB_TABS["settings"] (cabinet.py:117-131) и ссылку в баннер о неактивной подписке (_base_dashboard.html:150-152).
- Добавить вкладки «Finanzen» и «Auswertungen» в хаб Einstellungen — сейчас search-строка якоря их обещает (modules.py:709), а хаб не содержит; заодно исчезнет сирота /dashboard/finance/.
- Дать «Blog & News» вход: вкладка в хабе Marketing (рядом с Beiträge) — сегодня модуль включён у всех архетипов, а страницы не видно.
- Убрать nav_key «care» и разнести имена: /dashboard/settings/notifications/ должен называться одинаково в обоих хабах (или быть только в одном) — сейчас таб «Care-Zyklus» не подсвечивается никогда.
- Удалить мёртвый dashboard_tiles (apps/core/dashboard.py:12-86) и мёртвый гейт has_sellables/`any(catalog…)` (modules.py:668, context.py:288) — catalog core=True делает его константой.
- Привести hub_tiles в соответствие с докстрингом: добавить `show` по модулям (dashboard.py:261-313), чтобы плитка Marketing не появлялась при выключенном promotions.
- Добавить jobs в _OFFER_CTA (onboarding.py:454-460), чтобы Handwerker в чек-листе вёл на Aufträge, а не в каталог товаров.
- Заменить у не-отельных архетипов заголовок CTA «Belegungsplan» (dashboard.html:110-113) на нейтральный «Termine/Kalender» — сейчас парикмахер видит «Anreisen … & Zimmer».
- Добавить hub_tabs "board" в templates/stays/calendar.html (единственный календарь без таб-бара, ср. booking/calendar.html:6).
- Либо удалить /promotions/newsletter/, либо дать ему вкладку в Marketing — сейчас у него ноль входов во всём репозитории.
- Добавить вкладку «Angebote» в HUB_TABS["catalog"] (или ссылку-возврат), чтобы из Produkte можно было вернуться в хаб Angebote.

## GROUPING IDEAS
- Свести навигацию к ОДНОМУ реестру: сегодня входы описаны в четырёх местах (REGISTRY.nav_items, NAV_TASK_LABELS, HUB_TABS, hub_tiles/marketing_home.cards/integrations_home.cards). Предложение: один список записей {url_name, label, hub, weight, gate}, из которого генерируются и сайдбар, и таб-бары, и плитки, и мобильный бар — тогда «сайдбар говорит одно, хаб другое» станет структурно невозможно.
- Ввести явное соответствие nav_key → якорь сайдбара (карта дочерний_nav → родительский якорь). Это чинит потерю подсветки на 40+ экранах без переписывания страниц.
- Слить хаб «Kunden» в «Marketing» (или наоборот выделить «Kunden» отдельным якорем сайдбара) — сейчас три одинаковых вкладки в двух хабах и молчаливая подмена таб-бара при переходе.
- Слить хабы «catalog» и «sellables» в один «Angebote/Sortiment»: единый таб-бар Angebote · Produkte · Kategorien · Lager · Kombi · Import · [Erw] Einkauf, рендерящийся и на /dashboard/angebote/, и на страницах каталога.
- Достроить единую страницу продаж до полноценного хаба: добавить на /dashboard/verkaeufe/ вкладки-ссылки на управляющие экраны (Veranstaltungen, Aufträge, Board+настройка колонок, Küchen-Display, Versand) — тогда легаси-петля hub_tabs "board" + orders_view_switch удаляется целиком, а не живёт третьим слоем.
- Разрезать «Einstellungen»: «Betrieb» (контакты/часы/право/языки/домены) отдельно от «Auswertung & Geld» (Finanzen, Auswertungen, Abrechnung) — сегодня отчёты и деньги либо в группе «Einstellungen» (классик), либо нигде (новый UI).
- Отделить настройку от операций внутри Marketing: операционные (Aktionen, Bewertungen, Kampagnen, Reservierungen, Einlösen) — прямые вкладки; настроечные (Care-Zyklus, Kanäle, Finder, Telegram) — вынести в Integrationen/Einstellungen, чтобы ящик «Erweitert» из 10 пунктов перестал быть свалкой.
- Сделать «Erweitert» и Простой режим ОДНИМ механизмом: сейчас advanced-флаг в HUB_TABS никак не связан с ui_mode, а ui_mode не влияет на хабы и компактный сайдбар. Один флаг сложности (basic/advanced) на запись реестра, читаемый и сайдбаром, и табами, и плитками.
- Перенести резервы акций (kind=reservation) во вкладку «Verkäufe», оставив в Marketing только настройку акций — иначе часть заявок клиентов живёт вне единой страницы продаж.
- Ввести обязательный тест-инвариант «каждая cabinet-вьюха достижима ≥1 кликом из sidebar/hub/tile при своих гейтах» — он бы поймал сирот billing, blog, newsletter, finance, analytics, events:list, jobs:list, board.
- Определиться с судьбой classic_ui: сегодня это вторая полная ветка сайдбара + ветки в dashboard/sellable_manage/verkaeufe/orders_view; если владелец её не использует, удаление снимает половину «наслоений» (NAV_GROUPS, grouped_active_modules, nav_items у 10 модулей, covered-логика в hub_tabs).

## VERDICTS
- **CONFIRMED** — Поиск по меню в сайдбаре сломан в дефолтном (компактном) режиме
  Проверено дословно. templates/tenant/_base_dashboard.html:234 — document.querySelectorAll("#dash-nav .nav-group"); компактная ветка {% if nav_compact %} рендерит плоские <a class="nav-link"> на строках 50-58 без обёрток; единственный .nav-group — строка 77 в классик-ветке ({% else %}, строка 65). Значит в компакте цикл не находит ни одной группы, ни один пункт не скрывается, anyShown остаётся false, и строка 244 `empty.classList.toggle("hidden", anyShown)` СНИМАЕТ hidden с #nav-empty (строка 59) → плашка «Nothing found.» показывается поверх полного списка. Второго обработчика фильтра в файле нет (скрипты 184-201, 202-247, 256-283).
- **CONFIRMED** — Экран-сирота: Abo & Zahlung (/dashboard/billing/) недостижим из нового кабинета
  apps/core/modules.py:509-517 — ModuleSpec billing, nav_items=(NavItem("billing", …),) на строке 513, core=True (в /dashboard/modules/ core-модули не показываются). sidebar_nav (modules.py:653-712) якоря billing не содержит; HUB_TABS["settings"] (cabinet.py:117-131) — без вкладки Abrechnung; hub_tiles (dashboard.py:270-312) — 6 плиток без billing; home_widgets — без. Полный grep по templates/: единственная ссылка `{% url 'billing' %}` — templates/billing/payments.html:6 (сама подстраница биллинга). Баннер _base_dashboard.html:149-152 действительно без ссылки. NAV_TASK_LABELS["billing"]=«Abrechnung» (modules.py:616) — метка есть, входа нет.
- **CONFIRMED** — Экран-сирота: Newsletter-кампании (/promotions/newsletter/) — ноль входов во всём проекте
  apps/promotions/views.py:976 def newsletter_campaigns; apps/promotions/urls.py:44 path("newsletter/", …, name="newsletter"); grep по всему репо: имя `promotions:newsletter` встречается ровно дважды — urls.py:44 и собственный redirect views.py:1002. В HUB_TABS, marketing_home.cards (apps/core/marketing_home.py:24-67), hub_tiles, home_widgets, integrations_home cards ссылки нет; templates/promotions/newsletter.html hub_tabs не вызывает (строки 1-12). Уточнение к формулировке: вьюха отдаёт nav="promotions" (views.py:1009), поэтому в компактном сайдбаре подсвечен якорь «Marketing» — глобальная навигация на странице есть, отсутствует именно таб-бар хаба и любые входы.
- **CONFIRMED** — Экран-сирота: Blog & News (/dashboard/blog/) виден только в классик-режиме
  modules.py:359-393 ModuleSpec blog: nav_items=(NavItem("blog-list", …, "blog"),) на строке 363, recommended_for перечисляет все 15 business_type (строки 369-385) → активен из коробки. NAV_TASK_LABELS["blog"]=«Blog & News» — modules.py:601. nav_items рендерятся только в {% else %}-ветке _base_dashboard.html:86-99 (классик); sidebar_nav блога не знает. В HUB_TABS (cabinet.py:51-132) ключа blog нет ни в одном хабе, в hub_tiles/home_widgets — нет. Единственная ссылка на blog-list во всём templates/ — templates/events/blog_edit.html:6. Дополнительно: сам templates/events/blog_list.html hub_tabs не рендерит.
- **CONFIRMED** — Finanzen и Auswertungen: сайдбар обещает их в «Einstellungen», а хаб не содержит
  modules.py:709 — "search": "einstellungen finanzen auswertungen funktionen" на якоре settings; HUB_TABS["settings"] (cabinet.py:117-131) = Einstellungen/Zahlung & Versand/Benachrichtigungen/Rechtstexte/Zusatzleistungen/Sprachen + Erweitert(Medien/Domains/Funktionen/Hilfe) — finance:journal и promotions:analytics отсутствуют. Единственный вход в /dashboard/finance/ из нового UI — виджет «Umsatz heute» (dashboard.py:127-155), гейт `"finance" not in hidden` (строка 127) c SIMPLE_HIDDEN_MODULES={finance, analytics} (modules.py:744) → в Простом режиме исчезает совсем (остальные ссылки на finance:* — только внутри самого finance и jobs/detail.html:51 при наличии счёта). Аналитика — только виджет «Marketing-Puls» (dashboard.py:211-235) и метрика marketing_home.py:135.
- **ADJUSTED** — Модуль promotions — единственная дверь к CRM/Inbox/Telegram/Bewertungen/Gutscheine
  Подтверждается только про САЙДБАР: якорь «Marketing» гейтится is_module_active(tenant,"promotions") — modules.py:678-688, вместе с ним уходит бейдж непрочитанного (_base_dashboard.html:55-56), а отдельных якорей Kunden/Nachrichten/Bewertungen в sidebar_nav нет (HUB_TABS["kunden"] — cabinet.py:109-113 — остался без якоря). Но «теряет ВЕСЬ маркетинг-блок» неверно: плитка «Marketing» на главной (hub_tiles, dashboard.py:287-292) НЕ гейтится и ведёт на marketing_home, который рендерит hub_tabs "marketing" (templates/tenant/marketing_home.html:6); вкладки этого таб-бара гейтятся своими модулями (crm/inbox/telegram/reviews/loyalty/publishing), а не promotions → Kontakte/Nachrichten/Telegram/Bewertungen/Kampagnen/Gutscheine/Kanäle/Beiträge остаются доступны. Тот же таб-бар приходит с виджета «Bewertungen» → reviews:list (dashboard.py:238-257, templates/reviews/review_list.html:6) и с карточки Integrationen «Publishing» → channels (views.py:3646-3651, templates/publishing/channels.html:6). Корректная формулировка: выключение promotions убирает единственный вход в маркетинг ИЗ САЙДБАРА (и бейдж inbox), оставляя доступ только через негейтящуюся плитку главной и случайные виджеты.
- **CONFIRMED** — Один экран — два хаба и два разных имени: /dashboard/settings/notifications/
  cabinet.py:89 — ("notifications-settings", «Care-Zyklus», "care", None, True) в HUB_TABS["marketing"]; cabinet.py:121 — ("notifications-settings", «Benachrichtigungen», "notifications", None, False) в HUB_TABS["settings"]. Вьюха: apps/core/views.py:3584 "nav": "notifications"; шаблон templates/tenant/notifications.html:6 — {% hub_tabs "settings" %}. Полный список литералов "nav" по apps/ (44 значения) НЕ содержит "care" → вкладка «Care-Zyklus» не подсвечивается никогда, а клик по ней из Marketing подменяет таб-бар на Einstellungen. Четвёртый и третий входы тоже на месте: карточка «Erinnerungen & Care-Zyklus» — marketing_home.py:25-31, карточка «Benachrichtigungen & Telegram» — views.py:3631-3637.
- **CONFIRMED** — Хаб «Kunden» дублирует три вкладки хаба «Marketing» и работает как ловушка
  HUB_TABS["kunden"] (cabinet.py:109-113) = crm:customer-list / inbox:list / telegram-settings — те же три url_name, что в advanced-части HUB_TABS["marketing"] (cabinet.py:85-87). Страницы рендерят чужой хаб: templates/crm/customer_list.html:6, templates/inbox/list.html:6, templates/telegram/settings.html:6 — все {% hub_tabs "kunden" %} (плюс templates/crm/company_list.html:6). Marketing-вкладок в этом баре нет → возврат только браузерным «назад» или через плитку главной.
- **CONFIRMED** — Sortiment существует в двух хабах с разными таб-барами и без обратной связи
  HUB_TABS["sellables"] (cabinet.py:98-106): Angebote прямым табом + Produkte/Kategorien/Lager/Einkauf/Kombi/Import с advanced=True; HUB_TABS["catalog"] (cabinet.py:53-61) — те же 6 страниц прямыми табами и БЕЗ «Angebote». Все страницы каталога рендерят catalog-хаб: templates/catalog/product_list.html:6, category_list.html:6, combo_list.html:6, templates/inventory/stock.html:6, purchasing.html:6, templates/imports/import_start.html:7; templates/tenant/sellable_manage.html:6 — hub_tabs "sellables". Признание в комментарии — cabinet.py:95-97 («catalog-хаб на самих страницах каталога цел — это дубль-вход, не перенос»), уточнение: комментарий занимает строки 95-97, не 96-97.
- **CONFIRMED** — Подсветка сайдбара теряется на большинстве экранов
  _base_dashboard.html:52 — единственное условие подсветки {% if nav == it.nav_key %}. Множество nav_key компакт-сайдбара ровно 7: dashboard, board (через _sales_nav_item — при не-classic entry_url_name всегда "verkaeufe", маппинг modules.py:638-643 даёт фолбэк "board"), sellables, promotions, integrations, site, settings (modules.py:653-712). Фактических значений "nav" в apps/ — 44 уникальных (grep: analytics, billing, board, booking, campaigns, catalog, categories, channels, collections, combos, crm, dashboard, domains, events, extras, finance, finder, imports, inbox, integrations, jobs, languages, legal-docs, loyalty, media, modules, notifications, orders, payments, posts, promotions, purchasing, redeem, reservations, reviews, sellables, settings, site, stays, stock, support, telegram, vouchers, x), т.е. на ~37 значениях подсветки нет — включая собственные вкладки хаба Einstellungen (payments/legal-docs/languages/domains/modules/media/support). Единственная неточность: значений 44, а не 43.
- **CONFIRMED** — Marketing-центр подсвечивает чужую вкладку «Aktionen»
  apps/core/views.py:3609 — "nav": "promotions" во вьюхе marketing_home; templates/tenant/marketing_home.html:6 — {% hub_tabs "marketing" %}; cabinet.py:76 — первая вкладка ("promotions:promotion-list", «Aktionen», "promotions", …) → active вычисляется как k == cur (cabinet.py:157) → на /dashboard/marketing/ «Aktionen» подсвечена, а ведёт на /promotions/. Самого marketing-home среди HUB_TABS["marketing"] нет — возврата на лендинг из таб-бара действительно нет (только плитка главной).
- **CONFIRMED** — Плитки главной игнорируют гейты модулей — «сайдбар говорит одно, главная другое»
  apps/core/dashboard.py:261-313: докстринг на строке 265 обещает «гейты по модулям — плитка выключенного модуля не показывается», но список tiles (строки 270-312) собирается безусловно и возвращается как есть (return tiles, строка 313) — ни одного is_module_active/hidden. Контраст с sidebar_nav (modules.py:678) реален: при выключенном promotions якоря нет, а плитка «Marketing» → marketing-home (dashboard.py:287-292) остаётся. Единственная динамика в плитках — url_name первой (ov.entry_url_name, строка 277).
- **CONFIRMED** — «Website» — три входа с двумя разными целями под одним именем
  Сайдбар: modules.py:697-703 — {"url_name": "site", "nav_key": "site", "label": _("Website")} (в заявке 698-703, словарь начинается на 697). Шапка: _base_dashboard.html:143 — {% url 'site' %} с подписью «✏️ Website». Плитка главной: dashboard.py:305-311 — label «Website», url_name "site-home". Цели разные и подтверждены: templates/tenant/site.html — карточный хаб ровно из 6 карточек (site-preview, site-home, site-menu, site-sections, site-pages, site-seo; строки 22-47), а site-home — билдер главной. Чек-лист: apps/tenants/onboarding.py:490-495 — пункт «Add a banner or photo» с url_name "site".
- **CONFIRMED** — Режим Einfach/Experte почти ничего не делает, но занимает главное место в шапке
  Тумблер — _base_dashboard.html:124-128 (виден на каждой странице кабинета), подсказка на строке 124 буквально «Simple mode hides from the menu: …» из ui_simple_hidden (context.py:372 → modules.simple_hidden_labels). sidebar_nav (modules.py:653-712) не вызывает ни simple_hidden_modules, ни is_simple — прочитан целиком. Реальные потребители: grouped_active_modules (modules.py:785, только классик-ветка шаблона), home_widgets (dashboard.py:122, гейты finance/orders/stays/promotions/reviews), мёртвый dashboard_tiles (dashboard.py:25), templates/tenant/settings.html:57-60, templates/catalog/product_form.html:55-59 (ui_simple из catalog/views.py:52), информационный блок templates/tenant/modules.html:19-37. hub_tabs (cabinet.py:135-159) режим не читает вовсе. ARCHETYPE_SIMPLE_HIDDEN (modules.py:750-755, значение везде {"catalog"}) в дефолтном UI не влияет ни на что, кроме текста подсказки: home_widgets по catalog виджетов не строит.
- **CONFIRMED** — Мёртвый код навигации: dashboard_tiles
  apps/core/dashboard.py:12-86 (dashboard_tiles, 75 строк, бейджи «needs» и гейты по модулям). Grep по всему репо: вызовы только в apps/tenants/tests/test_onboarding_wizard.py:799, 812, 832 и упоминание в комментарии apps/core/views.py:141 («Прежние task-плитки AB7 заменены (dashboard_tiles остаётся для истории)»). Ни одна вьюха её не вызывает; главная получает "hubs": dash.hub_tiles(...) (views.py:143). Уточнение: код не полностью «мёртв» — он покрыт тремя тестами, которые продолжают его валидировать.
- **CONFIRMED** — Мёртвый гейт «Angebote» + дублирующая переменная has_sellables
  modules.py:668 — any(is_module_active(tenant, m) for m in ("catalog","booking","stays","events")); ModuleSpec catalog объявлен core=True (modules.py:98, блок 89-103), а is_module_active возвращает True сразу при spec.core (modules.py:539-540) → выражение тождественно истинно для любого тенанта, включая handwerker. Дубль: apps/core/context.py:288-290 считает has_sellables тем же выражением независимо от sidebar_nav, и шаблон использует его только в классик-ветке (_base_dashboard.html:69-75), тогда как компакт берёт свой пункт из nav_compact — два источника правды для одного пункта подтверждены.
- **CONFIRMED** — Хаб «Verkäufe» разорван: три поколения контролов на одной задаче
  Якорь → orders_view.entry_url_name (orders_view.py:85-99): не-classic всегда "verkaeufe". templates/core/verkaeufe.html: собственный переключатель видов POST-формами (строки 14-22) и собственные вкладки по kind (строки 25-30); ни hub_tabs, ни orders_view_switch в файле нет (подтверждено grep по всем шаблонам). Старые страницы несут оба других контрола: {% hub_tabs "board" %} + {% orders_view_switch %} — templates/core/board.html:6-7, templates/orders/order_list.html:6-7, templates/booking/calendar.html:6-7, templates/stays/calendar.html:6 (+ stays/today.html:6, events/event_list.html:6, jobs/list.html:6). Хаб-бар при этом урезан до Tickets/Aufträge через covered в cabinet.py:148-150, а плашка «Alte Ansicht · 🆕 Alles auf einer Seite →» — _orders_view_switch.html:17. Уточнение к списку синонимов: «Kanban»/«Feed» — внутренние ключи (orders_view.VIEWS), в UI подписи Board/Kalender/Liste (orders_view.py:16-20 и sales_page.VIEW_LABELS), а расхождение имён реально в паре h1 «Aufgaben-Board» (board.html:9) vs таб «Board» vs вкладки хаба «Bestellungen/Termine/Übernachtungen».
- **ADJUSTED** — Экраны управления событиями, заявками и доской достижимы только через легаси-петлю
  Подтверждено: events:list, jobs:list и board есть только в HUB_TABS["board"] (cabinet.py:64-71), который рендерится исключительно на самих легаси-страницах; ссылка «Full view →» — templates/tenant/dashboard.html:118 и при sales_is_calendar ведёт на sales_entry_url=/dashboard/verkaeufe/, где табов нет; строка dashboard.html:100 с {% url 'board' %} живёт внутри {% if classic_ui %} (строка 97). Неточности: (1) «единственный вход извне» неверно — виджеты главной дают ещё два входа в легаси-петлю: «Abholbereit» → orders:order-list (dashboard.py:158-176) и «Anreisen heute» → stays:today (dashboard.py:180-208, templates/stays/today.html:6 рендерит hub_tabs "board"), поэтому у отеля с активными events/jobs вкладки Tickets/Aufträge достижимы, а с order_list доска ещё и через сегмент ST-5b (kanban → board); (2) status-manager линкуется не только из board.html:40 — есть templates/tenant/_transition_rules_panel.html:29, включаемый в orders/order_list.html:49 и booking/resources.html:120. Верная формулировка: у архетипов без активных orders/stays (типичный Friseur: orders только suited_for, modules.py:204-206) входа в board/events:list/jobs:list из нового UI нет вовсе, а board-settings (board.html:22) остаётся доступен строго с самой доски.
- **CONFIRMED** — CTA «Belegungsplan» на главной показывается салонам и ресторанам
  templates/tenant/dashboard.html:108-114 — блок под {% if sales_is_calendar and not classic_ui %} с текстом «📅 Belegungsplan» / «Anreisen, Buchungen & Zimmer auf einen Blick» и href={{ sales_entry_url }}. views.py:126 sales_view = ov.resolve_view(tenant) → views.py:147 "sales_is_calendar": sales_view == "calendar"; resolve_view (orders_view.py:71-77) опирается на default_view (orders_view.py:58-68): любой primary в (booking, stays) → "calendar". У friseur/werkstatt/restaurant booking входит в recommended_for (modules.py:221), а в archetypes._PRIORITY booking стоит выше catalog/jobs → primary=booking → баннер с гостиничной лексикой показывается. Ссылка ведёт на sales_entry_url = ov.entry_url = /dashboard/verkaeufe/ (orders_view.py:80-91), а не на календарь. Единственное дополнение: блок гасится в classic_ui.
- **ADJUSTED** — Чек-лист готов
  Проверка невозможна: во входном JSON это заявление обрезано (title оборван на «Чек-лист готов», поля detail/files/severity отсутствуют). Пришлите полный текст — источники под рукой: чек-лист собирает apps/tenants/onboarding.completeness (пункты с url_name, в т.ч. "site" на строках 490-495), а рендерится он в templates/tenant/dashboard.html:78-92.
