# RESEARCH: bestinclass

## SUMMARY
Исследованы админки Shopify, Wix, Squarespace и Shopware 6. Канонический паттерн верхнего уровня совпадает у всех: (1) объекты бизнеса (Заказы/Товары/Клиенты) — первыми и всегда видимы; (2) инструменты роста (Маркетинг/Скидки/Аналитика/Контент) — вторым блоком; (3) каналы продаж и приложения — как ОПЦИОНАЛЬНЫЕ расширения, появляющиеся в меню по мере установки; (4) Settings — единый хаб внизу/в оверлее с 15–30 разделами, куда вынесено всё «настроил один раз и забыл». Wix в редизайне 2024 явно сформулировал принцип: группировать «по действию и интенту, а не по бизнес-приложению». Progressive disclosure везде трёхслойный: setup-guide-карточки на Home с прогрессом и адаптацией под тип бизнеса; plan-гейты (фичи видны, но заблокированы с апгрейд-промптом); кастомизация меню (скрыть неиспользуемое — Squarespace Edit Menu, Shopify pin, Wix favorites). Глобальный поиск — обязательный элемент: Shopify Ctrl/Cmd+K ищет и данные, и разделы, и приложения; Squarespace «/» ищет панели меню; Shopware ищет сущности из любого экрана. Для siteadaptor это подтверждает верность курса S1–S6/ST-4b (хабы, Простой/Эксперт, единый Settings) и подсказывает недостающее: глобальный поиск-палитру кабинета и маппинг «старое→новое» при переездах навигации.

## IA STRUCTURE
═══ SHOPIFY ADMIN ═══
Сайдбар (сверху вниз):
├─ Home (setup guide с прогрессом + контекстные карточки-подсказки)
├─ Orders (Drafts · Abandoned checkouts)
├─ Products (Collections · Inventory · Purchase orders · Transfers · Gift cards · Price lists)
├─ Customers (Segments · Companies [B2B])
├─ Content (Metaobjects · Files · Menus)
├─ Finances (Billing · Payouts)
├─ Analytics (Reports · Live View)
├─ Marketing (Campaigns · Automations · Attribution)
├─ Discounts
├─ ── Sales channels ── (секция-расширение, пункты появляются при установке)
│   ├─ Online Store (Themes · Blog posts · Pages · Navigation · Preferences ← настройки внутри канала!)
│   ├─ Point of Sale · Shop · Inbox · …(+ Add channel)
├─ ── Apps ── (установленные приложения; можно «pin» избранные)
└─ Settings (ОТДЕЛЬНЫЙ ОВЕРЛЕЙ поверх админки, ~21 раздел):
    General · Plan · Billing · Users and permissions · Payments · Checkout ·
    Customer accounts · Shipping and delivery · Taxes and duties · Locations ·
    Gift cards · Markets · Apps and sales channels · Domains · Customer events ·
    Brand · Notifications · Custom data (metafields) · Languages · Customer privacy · Policies
Поиск: Ctrl/Cmd+K — единая палитра: товары, заказы, клиенты, страницы, приложения, разделы админки, с фильтрами по типу.
Гейты: Plus-only фичи (unlimited B2B catalogs, deposits) видны, но заблокированы; ядро B2B спущено на все тарифы (04.2026).

═══ WIX DASHBOARD ═══
Сайдбар (группировка «по действию и интенту, а не по бизнес-приложению» — редизайн 2024):
├─ Home (обзор: план/домен/почта + setup-чеклист под тип бизнеса: «Set up payment methods», «Get found on Google»…)
├─ Getting Paid (способы оплаты · транзакции · Invoices · Pay Links · Price Quotes)
├─ Sales (ВСЕ продажи вместе: заказы + подписки + gift cards)
├─ Catalog (товары/услуги — появляется при установке Stores/Bookings)
├─ [Пер-app вкладки: Blog · Bookings · Events · Restaurants — ТОЛЬКО если приложение установлено]
├─ Inbox
├─ Customers & Leads (Contacts · Segments · Forms · Reviews · Loyalty · Tasks)
├─ Marketing (Overview · Email · соцсети · Google Ads · Coupons · SEO)
├─ Analytics (Reports · Insights)
├─ Automations
├─ Site & Mobile App (Website & SEO · Site Speed · Uptime & Security · Mobile App · Logo & Brand · Hopp)
├─ CMS · Developer Tools (Velo)
├─ Apps (App Market · Manage apps)
└─ Settings (единый хаб: Business Info · Website settings · Language & region · Roles & Permissions ·
    Domains · Storage · Site members + настройки ВСЕХ бизнес-приложений: eCommerce, Bookings, Subscriptions)
Поиск: глобальный — по инструментам, приложениям И статьям справки. Favorite Pages (закрепление страниц) + Quick Add.

═══ SQUARESPACE (меню 2025) ═══
Главное меню (после редизайна; плоские панели вместо глубокого Home Menu):
├─ Home (dashboard: setup-чеклисты ПО ТИПУ бизнеса, домен, аналитика, видеотуториалы, Customize Home — вкл/выкл виджеты)
├─ Website (Pages + System Pages/Utilities · Styles [кисть] · Assets · SEO/AI Visibility)
├─ Products & Services (физтовары · услуги · digital · gift cards)
├─ Content & Memberships (курсы · видео · членства · блоги)
├─ Donations · Invoicing · Scheduling (Acuity)
├─ Email Campaigns · Contacts
├─ Analytics
├─ Finance (все заказы + пожертвования + payments/payouts)
└─ Settings (иконка-шестерёнка внизу; хаб с подгруппами):
    Website (favicon, соцсети, cookie banner) · Selling (Payments · Shipping · Taxes — только если продаёшь) ·
    Permissions & Ownership · Marketing/SEO · Billing · Domains · Connected Accounts
Сервис-иконки внизу: Search (поиск панелей, клавиша «/» или «?») · Edit Menu (СКРЫТЬ неиспользуемые пункты) · Help.

═══ SHOPWARE 6 ADMIN ═══
Сайдбар:
├─ Dashboard (обороты, заказы, статистика)
├─ Orders (Overview · создание заказа в админке)
├─ Customers (Overview · создание)
├─ Catalogues (Products · Categories · Dynamic product groups · Properties · Manufacturers · Reviews)
├─ Content (Shopping Experiences [CMS-страницы] · Themes · Media)
├─ Marketing (Promotions · Newsletter recipients)
├─ Extensions (Store · My extensions)
├─ ── Sales Channels ── (первоклассные объекты в сайдбаре: Storefront · Headless API · сравнение цен; «+» добавить)
├─ Settings — 3 группы:
│   ├─ Shop (~30 плиток!): Basic information · Cart · Countries · Currencies · Customer groups ·
│   │   Delivery times · Documents · Email templates · Import/Export · Languages · Log-in & sign-up ·
│   │   Number ranges · Payment methods · Product units · Rule Builder · Flow Builder · SEO · Search ·
│   │   Shipping · Sitemap · Snippets · Tags · Taxes · Salutations · Newsletter · Warehouses · …
│   ├─ System: Users & Permissions · Integrations · Caches & Indexes · Event logs · Custom fields ·
│   │   Mailer · Privacy · Shopware Account/Updates/Plans · Storefront
│   └─ Extensions (настройки плагинов)
└─ Profile (внизу: язык админки, выход)
Поиск: центральный сверху — товары, категории, клиенты, заказы, медиа из любого экрана.

## PATTERNS
- Канонический порядок верхнего уровня: сначала объекты бизнеса (Заказы → Товары → Клиенты), затем инструменты роста (Контент/Маркетинг/Скидки/Аналитика), затем расширения (Каналы/Apps), Settings — в самом низу или отдельным оверлеем. Все 4 платформы сходятся на этом.
- Единый Settings-хаб: всё «настроил один раз» (реквизиты, оплата, доставка, налоги, домены, юзеры, уведомления, право) — в ОДНОМ месте с 15–30 разделами; в рабочих разделах остаётся только оперативное. Shopify рендерит Settings отдельным оверлеем — визуально отделяя «конфигурацию» от «работы».
- Внутри Settings — вторичная группировка, когда разделов много: Shopware делит на Shop/System/Extensions, Squarespace — на Website/Selling/Permissions/Billing. Плоский список из 20+ пунктов уже требует подгрупп.
- Каналы продаж и приложения — опциональные расширения меню: пункт появляется ТОЛЬКО после установки (Wix per-app вкладки, Shopify Sales channels с «+ Add», Shopware Sales Channels как объекты). База не загромождена тем, что не куплено/не включено.
- Группировка по действию и интенту, а не по модулю (явный принцип редизайна Wix 2024): Sales объединяет заказы+подписки+gift cards из разных приложений; Getting Paid собирает все способы получить деньги. Это прямой аналог хабов Verkäufe/Sortiment в siteadaptor.
- Setup guide = карточки на Home с прогресс-баром, автоотметкой выполненного, адаптацией под тип бизнеса (Squarespace варьирует чеклист для e-commerce/услуг/курсов; Wix — под установленные приложения) и возможностью отложить/скрыть. Shopify оформил это как переиспользуемый UI-паттерн (setup guide composition).
- Plan-гейты вместо скрытия: заблокированная фича видна с замком/апгрейд-промптом (Shopify Plus-only), а ядро фич со временем спускают вниз по тарифам (B2B → все тарифы, 04.2026). Пользователь знает, что существует, — это и есть воронка апселла.
- Кастомизация навигации самим пользователем: Squarespace Edit Menu (скрыть неиспользуемые панели), Customize Home (вкл/выкл виджеты дашборда), Wix Favorite Pages, Shopify pin apps. Дешёвая альтернатива умным пресетам — дать спрятать лишнее вручную.
- Глобальный поиск как страховка от ЛЮБОЙ навигационной ошибки: Shopify Ctrl/Cmd+K ищет одновременно данные (заказы/товары/клиентов), разделы админки и приложения с фильтрами; Squarespace «/» ищет панели меню; Wix ищет инструменты + статьи справки; Shopware — сущности из любого экрана. Это самый дешёвый ответ на «не могу найти» (класс проблем FB-1/FB-2 у siteadaptor).
- Экспертные механизмы вынесены в отдельные именованные инструменты, а не размазаны по формам: Shopware Rule Builder / Flow Builder, Shopify Custom data (metafields) / Customer events — базовые формы остаются простыми, сложное живёт в своём разделе.
- Home отвечает на «что сегодня», а не дублирует отчёты: карточки задач + 2–4 ключевые метрики + контекстные подсказки; полная аналитика — отдельным разделом (совпадает с ST-4a siteadaptor).
- Редактор сайта отделён от админки данных: у Shopify Online Store — лишь один из каналов, у Wix «Edit Site» — отдельная кнопка из дашборда, у Squarespace Website-панель отделена от Commerce/Finance. Дизайн — не соседний пункт меню с заказами.

## ANTIPATTERNS
- Россыпь настроек по продукту: даже у Shopify часть конфигурации живёт внутри канала (Online Store → Preferences, темы) отдельно от Settings — источник вечных «где это настраивается?». Правило: если параметр меняют реже раза в неделю — ему место в Settings-хабе, не в рабочем разделе.
- Группировка меню по внутренним модулям/приложениям, а не по задачам пользователя — Wix жил так до 2024 и публично отказался («grouped by action and intent, not by business app»). Меню, повторяющее архитектуру кода, — антипаттерн.
- Плоская стена из 30+ плиток настроек без иерархии (Shopware Settings → Shop): технически «единый хаб», но без подгрупп и поиска по настройкам превращается в игру «угадай плитку» с названиями по внутренним модулям (Number ranges, Snippets, Salutations).
- Переезд навигации без маппинга «старое → новое»: редизайн меню Squarespace породил целый жанр статей «Where did everything go» — при перестройке нужны алиасы старых путей, подсказки на прежних местах и редиректы, иначе теряются даже лояльные пользователи.
- Полное скрытие функции вместо показа с гейтом: спрятанная фича не продаёт апгрейд и порождает тикеты «а у вас есть X?». Показать с замком — лучше, чем убрать (обратная сторона: НЕ загромождать base-план десятками замков).
- Дублирование одной сущности в нескольких местах меню без единого источника — пользователь не понимает, «настоящий» ли это тот же список (у Shopify «Apps and sales channels» есть и в сайдбаре, и в Settings — оправдано лишь потому, что в Settings это управление доступом, а в сайдбаре — вход в работу; без такого разделения ролей дубль вреден.
- Смешение оперативной работы и конфигурации на одном экране: список заказов + правила статусов + шаблоны писем рядом перегружают форму; лидеры разводят это по слоям (работа в разделе, конфигурация в Settings/отдельной панели).
- Глубокая вложенность 3+ уровней drill-down (старое Home Menu Squarespace: Home → Commerce → Inventory → …): новый дизайн намеренно уплощён до панелей 1–2 уровней; глубже двух уровней клика меню не масштабируется.
- Онбординг-чеклист, который нельзя отложить или скрыть: гайдлайны Shopify прямо требуют opt-out и «завершить позже» — принудительный мастер, блокирующий работу, хуже отсутствия мастера.

## SOURCES
- https://help.shopify.com/en/manual/shopify-admin/shopify-admin-overview
- https://firebearstudio.com/blog/shopify-admin.html
- https://shopthemedetector.com/blog/shopify-store-settings-pages-and-admin-set-up/
- https://shopify.dev/docs/api/app-home/patterns/compositions/setup-guide
- https://shopify.dev/docs/apps/design/user-experience/onboarding
- https://changelog.shopify.com/posts/key-b2b-features-now-available-on-non-plus-plans
- https://support.wix.com/en/article/about-your-wix-dashboard
- https://www.wixcreate.com/post/mastering-wix-dashboard
- https://support.wix.com/en/article/step-by-step-guide-to-creating-your-wix-site-and-online-business
- https://support.squarespace.com/hc/en-us/articles/212260078-Your-site-s-main-menu
- https://mdc-designs.com/blog/where-did-everything-go-squarespace-menu
- https://bycrawford.com/blog/squarespaces-new-home-dashboard-explained
- https://docs.shopware.com/en/shopware-6-en/first-steps/administration-overview
- https://docs.shopware.com/en/shopware-6-en/settings
- https://docs.shopware.com/en/shopware-6-en/settings/shop
- https://docs.shopware.com/en/shopware-6-en/settings/system
- https://firebearstudio.com/blog/exploring-shopware-admin-overview.html