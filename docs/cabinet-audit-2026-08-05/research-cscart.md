# RESEARCH: cscart

## SUMMARY
CS-Cart (включая Multi-Vendor) — «коробочная» ecommerce-платформа с двумя поколениями админки. Классическая (до 4.18): два горизонтальных уровня меню — операционный ряд (Orders, Products, Customers, Marketing, Website, Vendors) и системный ряд (Add-ons, Administration, Settings, Design), из-за чего настройки были размазаны между «Settings» и «Administration». В 4.18.1 — редизайн: левый сайдбар в стиле SaaS, все системные вещи слиты в «Settings» в нижнем левом углу, «Design» растворён в «Website»; позже добавлены тёмная тема (4.18.2), сворачиваемый slim-сайдбар и PWA-админка (4.20.1). «Настройки» устроены как разделы (16 шт.: General, Company, Appearance, Checkout, Emails, Security и т.д.) → внутри разделов вкладки (структура SECTION/TAB закреплена даже на уровне схемы БД), плюс Settings Wizard для первичной настройки и per-storefront переключатели «глобально/индивидуально». Отдельного поиска по настройкам в базе нет — это заметная боль. Функциональность сильно модульная: страница «Downloaded add-ons» со статусами Active/Disabled, gear-меню (Settings/Disable/Uninstall/Open), поиском, фильтрами, «Недавно установленные»/«Избранное» и массовыми диагностическими операциями (Disable all third-party / Re-enable). Мерчанты хвалят интуитивность и мощность («можно всё сам, без программиста»), ругают кривую обучения блочного редактора, «тысячи функций, но много ручной работы для их включения», одинаковые иконки блоков и редизайн без отката.

## IA STRUCTURE
CS-CART / MULTI-VENDOR — АДМИН-ПАНЕЛЬ

═══ A. АКТУАЛЬНАЯ (4.18–4.21): левый сайдбар ═══
├── 🏠 Home / Dashboard (дашборд: продажи, графики; валюта отчётов переключается)
├── 📦 Orders (Заказы)
│   ├── Список заказов (расширенные фильтры)
│   ├── Shipments (отгрузки)
│   ├── Return requests (возвраты, RMA — аддон)
│   ├── Call requests (обратный звонок / купить в 1 клик)
│   └── Sales reports (отчёты по продажам)
├── 🛍 Products (Товары)
│   ├── Products (список, advanced-фильтры)
│   ├── Categories (категории)
│   ├── Features (характеристики)
│   ├── Filters (фильтры витрины)
│   └── Options (опции/варианты)
├── 👥 Customers / Users (Покупатели)
│   ├── Customers (покупатели)
│   ├── Administrators (администраторы)
│   ├── User groups (группы с привилегиями)
│   └── Vendor's administrators (MV: админы продавцов)
├── 🏪 Vendors (только Multi-Vendor)
│   ├── Vendors (список, статусы: Active/Pending/Suspended…)
│   ├── Vendor plans (тарифные планы продавцов: комиссии, периодические платежи, доступные категории)
│   ├── Applications for vendor account (заявки/онбординг)
│   ├── Accounting / Payouts (балансы, выплаты вендорам)
│   ├── Vendor-to-Admin Payments (сбор долгов: лимит долга + grace period, авто-скрытие товаров должника)
│   └── Product approval (модерация товаров вендоров)
├── 📣 Marketing (Маркетинг)
│   ├── Promotions (акции: catalog/cart rules)
│   ├── Abandoned / Live carts (брошенные корзины)
│   └── через аддоны: Gift certificates, Newsletters, Banners, Reward points, Affiliate
├── 🌐 Website (Сайт)
│   ├── Pages (страницы, блог, формы, ссылки, опросы)
│   ├── Themes (темы — переехало из бывшего «Design»)
│   ├── Layouts (блочный редактор раскладок каждой страницы)
│   ├── Menus (меню витрины)
│   └── SEO: robots.txt, Sitemap, llms.txt (с 4.20.1, per-storefront)
├── 🧩 Add-ons (Модули)
│   ├── Downloaded add-ons («Manage add-ons»: поиск, фильтры, секции Recently installed / Favorites, статусы Active/Disabled, gear-меню per-addon: Settings · Disable · Uninstall · Open; gear страницы: Manual installation (zip/сервер/URL), Disable all / Disable third-party / Re-enable)
│   └── Browse all available add-ons (витрина Marketplace)
└── ⚙️ Settings (внизу слева; сюда слито и бывшее «Administration»)
    ├── Разделы настроек (форма с вкладками внутри раздела):
    │   General · Company · Appearance · Stores/Storefronts · Checkout ·
    │   Emails · Thumbnails · Sitemap · Vendors (MV) · Security settings ·
    │   Logging · Reports · CDN · Licensing mode
    ├── Settings Wizard (мастер первичной настройки)
    ├── Payment methods (способы оплаты, 20+ шлюзов)
    ├── Shipping & taxes (методы доставки, зоны, налоги)
    ├── Currencies / Languages (валюты, языки, переводы)
    ├── Import / Export (CSV/XML), Backup/Restore (Database), Files
    ├── Logs (журналы)
    └── Upgrade center (обновления ядра и аддонов)
    [+ toggle у части настроек General/Appearance/Checkout: «глобально» ↔ «per-storefront»]

Верхняя полоса: универсальный поиск (товары/заказы/пользователи; в 4.20.1 ускорен в 2–3×) · уведомления · Growth Center (контекстная справка: доки/видео/рекомендации аддонов под текущую страницу) · профиль (тёмная тема) · переход на витрину · переключатель storefront'а.

═══ B. КЛАССИЧЕСКАЯ (до 4.18): два горизонтальных ряда ═══
Ряд 1 (системный): Add-ons · Administration (платежи, доставка/налоги, валюты, магазины, импорт/экспорт, бэкапы, логи, upgrade) · Settings (16 разделов) · Design (темы, layouts, меню, email-шаблоны, документы) + селекторы языка/валюты + корзина-ссылка на витрину
Ряд 2 (операционный): 🏠 · Orders · Products · Customers · Marketing · Website · Vendors (MV)
+ Quick Start menu: Branding · Legal documents · Vendor onboarding (MV) · Checkout

## PATTERNS
- Жёсткое разделение «операционное сверху — системное внизу»: Settings прижат к нижнему левому углу сайдбара, повседневные разделы (заказы/товары/маркетинг) — наверху; редизайн 4.18 слил разбросанные Settings+Administration в одну точку входа
- Двухуровневые настройки «раздел → вкладки»: 16 понятных разделов (General, Company, Checkout, Emails, Security…), внутри каждого — вкладки; структура закреплена на уровне платформы (SECTION/TAB), и аддоны обязаны встраивать свои настройки в ту же схему
- Settings Wizard — мастер, проводящий по ключевым настройкам при запуске, отдельно от полного дерева; плюс Quick Start menu (Branding, Legal documents, Vendor onboarding, Checkout) для стартового наполнения
- Переключатель «глобально ↔ per-storefront» прямо у отдельной настройки (иконка-toggle) — мультивитринность без дублирования всего дерева настроек
- Страница модулей как каталог: поиск + фильтры + секции «Recently installed» и «Favorites» + статус Active/Disabled бейджем; у каждого аддона gear-меню Settings/Disable/Uninstall и «Open» — прямой прыжок к страницам, которые модуль добавил в админку
- Массовая диагностика конфликтов модулей одной кнопкой: «Disable all add-ons» / «Disable third-party add-ons» + «Re-enable» — стандартный приём поиска сбойного аддона без ручного перебора
- Growth Center — контекстная помощь в правом верхнем углу: документация, видео и рекомендации аддонов подбираются под страницу, на которой находится админ
- Сворачиваемый сайдбар (slim bar, 4.20.1) + тёмная тема, наследующая системную (4.18.2), + мобильная адаптация с автогруппировкой пунктов в dropdown — ответ на жалобы «меню съедает экран»
- Vendors как отдельный корневой раздел в Multi-Vendor: список со статусами, тарифные планы (комиссии/периодика/доступные категории), заявки-онбординг, балансы/выплаты и работа с должниками (лимит долга + grace period + авто-санкции) — весь жизненный цикл продавца в одном месте
- Пункты меню подписаны языком задач: у каждого раздела короткое описание что здесь делают («promote your products, offer bonuses, and view the carts that the customers didn't take to checkout»)

## ANTIPATTERNS
- Размазывание системных функций по двум меню (историческое «Settings» vs «Administration»: платежи и валюты — в одном, email и юниты — в другом) — годами путало мерчантов, в 4.18 пришлось сливать принудительно
- Отсутствие поиска по настройкам в базовой поставке: при 16 разделах × вкладки нужный тумблер ищется вручную; универсальный поиск админки ищет товары/заказы/пользователей, но не настройки
- «Тысячи функций, но много ручной работы, чтобы их включить»: возможности спрятаны за десятками выключателей аддонов — фича формально есть, но до неё нужно догадаться дойти через Add-ons → Manage add-ons → gear → Settings
- Настройки функциональности живут у аддона, а не у предметной области: например, настройки поиска витрины — в Add-ons → Searchanise → Settings, а не в разделе «Поиск» — ломается ментальная модель «настраиваю там, где вижу»
- Одинаковые иконки блоков в layout-редакторе («icons of the blocks which are often all the same») — визуально неразличимые элементы заставляют учиться методом тыка; блочный редактор в целом называют «far from the ease of Shopify»
- Принудительный редизайн без отката: на релиз 4.18.1 мерчанты спрашивали «can we change back to old theme design?» — ответа нет; часть аудитории воспринимает вынужденную смену привычной навигации как регресс
- Редизайн «только UI»: сообщество встретило новый сайдбар вопросом «is this only a UI change?» — ожидались функциональные улучшения (автоматизация выплат вендорам), а не перекраска; косметика без workflow-улучшений раздражает
- Сайдбар, съедающий ширину экрана (особенно на ноутбуках/split-screen) — жалобы копились с 4.18 и были закрыты только collapse-режимом в 4.20.1
- Онбординг предполагает техническую уверенность: «not as beginner-friendly as Shopify or Wix», «not plug-and-play — читайте доки или нанимайте разработчика»; крутая кривая обучения для нетехнических владельцев
- Быстрые релизы с багами: мерчанты на форуме жалуются, что «тратят больше времени на репорты и трекинг багов, чем на управление магазином» — доверие к обновлениям подорвано

## SOURCES
- https://docs.cs-cart.com/latest/user_guide/admin_panel.html
- https://docs.cs-cart.com/4.13.x/user_guide/admin_panel.html
- https://docs.cs-cart.com/4.17.x/user_guide/admin_panel.html
- https://docs.cs-cart.com/latest/user_guide/index.html
- https://docs.cs-cart.com/latest/user_guide/settings/index.html
- https://docs.cs-cart.com/latest/developer_guide/core/settings/index.html
- https://docs.cs-cart.com/latest/user_guide/addons/1manage_addons.html
- https://docs.cs-cart.com/latest/user_guide/users/vendors/index.html
- https://docs.cs-cart.com/latest/user_guide/users/vendors/manage_vendor_plans.html
- https://docs.cs-cart.com/latest/user_guide/addons/vendor_debt_payout/index.html
- https://www.cs-cart.com/blog/its-now-easier-to-manage-your-cs-cart-store-admin-panel-updates-overview/
- https://www.cs-cart.com/blog/meet-cs-cart-4-18-1-with-a-revamped-admin-panel-and-an-upgraded-paypal-checkout-experience/
- https://www.cs-cart.com/blog/cs-cart-4-20-1/
- https://forum.cs-cart.com/t/meet-cs-cart-4-18-1-with-a-revamped-admin-panel-and-an-upgraded-paypal-checkout-experience/98684
- https://www.capterra.com/p/172642/CS-Cart-Multi-Vendor/reviews/
- https://www.selecthub.com/p/shopping-cart-software/cs-cart/
- https://www.trustradius.com/products/cs-cart-multi-vendor/reviews?qs=pros-and-cons