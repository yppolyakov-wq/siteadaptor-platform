# Концепция платформы для малого бизнеса: полное описание

> Документ описывает полную концепцию SaaS-платформы для малых офлайн-бизнесов, начиная с MVP (Phase 1) и до долгосрочного видения универсальной бизнес-операционной системы. Включает архитектурные решения, технологический стек, фазы развития, монетизацию, точки расширения и миграции.

---

## 1. Краткое описание (executive summary)

**Что строится:** Multi-tenant SaaS-платформа для малых офлайн-бизнесов в Германии/DACH. Каждый бизнес получает собственный мини-сайт, базу клиентов, инструмент создания акций с бронированием и автоматической публикацией в локальный агрегатор и внешние каналы (email, Telegram, Google Business Profile, Instagram, WhatsApp).

**Кто целевой клиент:** мини-маркеты — собирательное название для малых офлайн-бизнесов: пекарни, мясные/колбасные лавки, продуктовые магазины, Bioläden, Hofläden, специалитет-магазины, малые рестораны и кафе. Все они объединены тем, что у них уже есть постоянная клиентская база и они нуждаются в простом инструменте для её активации.

**Главная ценность:** позволить малому бизнесу делать с собственной базой клиентов то, что делают сети (push-уведомления об акциях, бронирование уценённых остатков, локальный discovery) — за €39/мес фиксированно, без сложности корпоративных инструментов типа Mailchimp/Klaviyo.

**Стратегическая идея:** начать с одного простого модуля (акции для мини-маркетов), доказать product-market fit, и постепенно наращивать функционал до полноценной бизнес-операционной системы — CRM, ERP, склад, бухгалтерия, маркетплейс, дропшипинг, биржа услуг — оставаясь на том же ядре.

**Параллельный продукт:** на том же ядре планируется агрегатор туров (по подобию Tripster) с продажей реальных туров и комиссионной моделью. Разрабатывается после стабилизации первого продукта, не параллельно.

---

## 2. Долгосрочное видение

Платформа задумана как **универсальная цифровая бизнес-операционная система (Business OS) для малого и среднего бизнеса**. В полном виде она должна объединять:

- CRM (управление клиентами, лиды, воронки)
- ERP (склад, закупки, отгрузки)
- Маркетплейс (внешний каталог, продажи через агрегатор)
- Dropshipping-платформа (наследование заказов между бизнесами в системе)
- Система бронирования (для гостиниц, ресторанов, услуг, туров)
- Управление заказами
- Складской учёт
- Бухгалтерия и финансовые движения
- Канбан и workflow-движок
- AI-автоматизация (анализ, генерация контента, прогнозирование)
- Многоканальные продажи (онлайн + офлайн + внешние каналы)
- Интеграции с внешними сервисами
- Конструктор сайтов и витрин
- B2B и B2C инструменты

**Главная философия:** одна система — много бизнесов, мультиарендность (multi-tenant), модульная архитектура, единое ядро данных, региональное хранение, мультиязычность.

Каждый бизнес в системе получает собственное пространство, собственный сайт/витрину, собственную базу клиентов, собственные процессы, собственные роли и права, собственный бренд и интерфейс.

**Принцип роста клиента:** малый бизнес может начать с CRM, потом добавить сайт, потом магазин, потом склад, потом бухгалтерию, потом сотрудников, потом маркетплейс, потом AI — не меняя платформу.

---

## 3. Целевая аудитория

### Phase 1 (узкий фокус)

**Мини-маркеты в Германии:**
- Пекарни (Bäckereien) — ~11,300 в DE
- Мясные/колбасные (Metzgereien/Fleischereien) — ~7,700
- Кондитерские (Konditoreien) — ~3,000
- Bioläden, Hofläden, специалитет-магазины — ~10,000+
- Малые рестораны, кафе — ~50,000+
- Малые магазины розницы (одежда, специалитет) — ~20,000+

**Total Addressable Market в Германии: ~100,000 предприятий.**

**SAM (Serviceable Addressable Market):** ~30,000–50,000 — бизнесы с физической точкой, в городах от 30,000 жителей, с минимальной готовностью использовать digital tools.

**Профиль идеального клиента:**
- Уже есть постоянная клиентская база (300–800 регулярных)
- Хочет коммуницировать с этой базой об акциях/новостях/остатках
- Не использует или плохо использует Mailchimp/Brevo (слишком сложно)
- Оборот €300k–2M/год
- Готов платить €30–50/мес за инструмент с очевидным ROI

### Phase 2+ (расширение)

- Гостиницы, ретриты, кафе с бронированием
- Туроператоры
- B2B сервисные компании
- Образовательные проекты
- Малые производители

### Долгосрочно

Любые малые и средние бизнесы, которым нужна цифровая операционная система.

---

## 4. Главное ценностное предложение Phase 1

### Проблема, которую решаем

Малый офлайн-бизнес имеет постоянных клиентов, но не имеет инструмента для системной коммуникации с ними. Сегодня владелец малой пекарни:
- Не знает контактов своих регулярных клиентов
- Не может сообщить им об акции/остатках/специалитет
- Платит за рекламу Facebook/Google, чтобы привлечь новых, теряя при этом существующих
- Не имеет собственного сайта или имеет устаревшую страницу-визитку
- Не имеет способа бронирования уценённых остатков (которые завтра выкинет)

### Что даёт платформа

Связку из четырёх элементов, которая отсутствует у конкурентов:

1. **Собственный мини-сайт** на subdomain `{slug}.platform.com` или своём домене, с витриной товаров и текущими акциями
2. **База клиентов** — клиенты подписываются через QR-код в магазине, форму на сайте, или регистрацию в агрегаторе
3. **Создание акций с опциональным бронированием** — например, "круассаны со скидкой 30% после 16:00, забронируй до 15:00, забрать с pickup-кодом"
4. **Автоматическая публикация** во все включённые каналы одним кликом — собственный сайт, локальный агрегатор платформы, email подписчикам, Telegram-канал бизнеса, Google Business Profile, Instagram, WhatsApp Business

### Дополнительный канал: локальный агрегатор

На стороне потребителя — публичный агрегатор `aggregator.platform.com`, где люди выбирают город и категорию, подписываются на конкретные бизнесы или категории, получают уведомления о новых акциях.

**Ключевой момент:** агрегатор это не основной продукт, а **бесплатный бонус-канал** для бизнеса поверх собственного сайта. Бизнес платит за свой сайт и инструмент акций — агрегатор даёт дополнительный охват без дополнительной оплаты.

### Уникальная позиция на рынке

Ни один конкурент (Mailchimp, Brevo, Klaviyo, Mailerlite, WhatsApp Business, Square, Shopify) не предлагает связку "собственный сайт + база клиентов + акции с бронированием + локальный агрегатор + DACH-нативность". Это уникальный wedge на немецком рынке.

---

## 5. Модули и их логика

### Модуль 1: Catalog (Phase 1)

**Что:** управление каталогом товаров/позиций бизнеса.

**Сущности:**
- Product (товар или позиция меню) — name (i18n), description (i18n), price, currency, category, images, stock_quantity (опционально), metadata (отраслевая специфика)
- Category — иерархическая структура категорий с i18n названиями

**Логика:**
- CRUD товаров через HTMX-dashboard
- CSV-импорт каталога
- Категоризация
- Загрузка изображений
- Опциональное отслеживание остатков (для будущей интеграции с inventory)

**Расширения в будущем:**
- Полноценный inventory management (склад, остатки, серии, партии)
- Связь с поставщиками
- Себестоимость

### Модуль 2: Promotions & Reservations (Phase 1)

**Что:** создание акций с опциональным бронированием.

**Сущности:**
- Promotion — title (i18n), description (i18n), discount_type (percent / fixed amount / fixed final price), discount_value, starts_at, ends_at, is_bookable, total_quantity, available_quantity, pickup_window, pickup_location, связь с products и categories, targeting (city, district, tags), status (draft → scheduled → active → ended → cancelled)
- Reservation — клиент резервирует количество единиц акции, получает pickup_code, статус (pending → confirmed → collected → cancelled → expired)

**Логика:**
- Создание акции через wizard в dashboard
- Опциональное включение бронирования (с указанием total_quantity и pickup window)
- Атомарное уменьшение available_quantity при создании резервации (PostgreSQL select_for_update)
- Автоматический переход в ended по истечении ends_at (Celery beat)
- Автоматическое expiration pending reservation через 30 минут

**Расширения в будущем:**
- Loyalty-программа (баллы за активность)
- Купоны и промокоды
- Recurring promotions (еженедельные/ежедневные)
- Бронирование услуг (не только товаров) — пересекается с booking-модулем

### Модуль 3: Publishing Engine (Phase 1)

**Что:** автоматическая публикация акции в выбранные каналы одним кликом.

**Сущности:**
- Channel — тип канала (subdomain / custom_domain / aggregator / email / telegram_channel / whatsapp_broadcast / google_business / instagram / meta_business / sms), конфигурация, статус включения
- Publication — факт публикации Promotion в Channel, статус (pending / publishing / published / failed / unpublished), external_id, external_url

**Логика:**
- Абстрактный `BasePublisher` интерфейс
- Реализации на канал (SubdomainPublisher, AggregatorPublisher, EmailPublisher, TelegramPublisher и далее)
- При активации Promotion — signal `promotion_activated` → автоматическая публикация во все включённые default channels
- При окончании Promotion — автоматический unpublish
- Retry-логика для failed publications
- Tracking external_id для возможности удаления из внешнего канала

**Каналы Phase 1:** subdomain, aggregator, email, telegram channel.

**Каналы Phase 2:** WhatsApp Business API, Google Business Profile, Instagram, SMS.

**Каналы Phase 3+:** Facebook, TikTok, Twitter/X, локальные DACH-агрегаторы (mydealz API если откроют), внешние маркетплейсы.

### Модуль 4: Notification Engine (Phase 1)

**Что:** уведомление потребителей о новых акциях по их подпискам.

**Сущности:**
- Customer — потребитель, контакты (email, phone, telegram), consents (согласия на каждый канал), locale, metadata
- Subscription — подписка customer на конкретный tenant, категорию, локацию, с выбранными каналами уведомлений
- Notification — факт отправки уведомления, статус (queued / sent / delivered / opened / clicked / failed / bounced)

**Логика:**
- Абстрактный `BaseNotificationChannel` интерфейс
- Реализации: EmailChannel, TelegramChannel, далее WhatsApp/SMS/Push
- При публикации Promotion в канал aggregator — signal `promotion_published` → Celery task ищет matching subscriptions → отправка уведомлений с rate limiting
- Каждый Notification логируется с трекингом доставки/открытия/клика
- One-click unsubscribe через signed token

**Phase 1 каналы уведомлений:** Email (через Resend), Telegram (через bot).

**Phase 2+ каналы:** WhatsApp Business API, SMS (Twilio), Push (когда будет мобильное приложение).

### Модуль 5: Aggregator (Phase 1)

**Что:** публичная витрина для потребителей со всеми акциями всех бизнесов платформы.

**Сущности:**
- GlobalCategory — унифицированные категории для cross-tenant навигации (Bäckerei, Restaurant, Bekleidung и т.д.)
- AggregatorListing — денормализованный индекс активных акций для быстрого чтения (обновляется через signals)

**Логика:**
- Главная страница: выбор города
- `/{city}/` — все активные акции города, сортировка по ending soon
- `/{city}/{category}/` — фильтр по глобальной категории
- `/biz/{slug}/` — страница конкретного бизнеса с его активными акциями
- `/promotion/{id}/` — детальная страница акции с формой резервации
- Личный кабинет потребителя — управление подписками и каналами уведомлений
- Cache-слой (Redis) для list views

**Расширения:**
- Геолокация: показывать ближайший город автоматически
- Фильтры по типу скидки, времени окончания
- Поиск
- Карта с локациями бизнесов
- Hyperlocal real-time акции (с push по геолокации) — Phase 2

### Модуль 6: Tenant Onboarding & Auth (Phase 1)

**Что:** регистрация нового бизнеса и аутентификация.

**Логика:**
- Внешняя форма onboarding на главной — создание Tenant + Domain + первого User в схеме tenant'а
- Email-based auth через django-allauth
- Magic link для customer (опт-ин на агрегаторе)
- Multi-user поддержка в tenant (owner / admin / staff роли в Phase 1, расширяемая система прав в будущем)

### Модуль 7: Branding & Settings (Phase 1)

**Что:** настройки бизнеса и кастомизация витрины.

**Логика:**
- Логотип, primary color, шрифты (Phase 1: ограниченный выбор)
- Custom domain с CNAME verification и автоматическим SSL (Caddy on-demand TLS)
- Контакты, описание, фото
- Выбор включённых каналов публикации
- Email шаблоны для уведомлений (с placeholder'ами)

**Расширения:**
- Drag-and-drop конструктор страниц (Phase 3+)
- Полноценный конструктор лендингов
- A/B testing страниц
- SEO-настройки

### Модуль 8: Billing (Phase 1)

**Что:** платежи и подписки через Stripe.

**Логика:**
- 14-дневный free trial при регистрации
- Один тариф €39/мес в Phase 1, без tier'ов
- Stripe Checkout для оплаты
- dj-stripe webhook handler для обновления subscription_status
- Customer Portal для управления подпиской
- Trial reminder за 3 дня до окончания
- Grace period 7 дней при cancelled subscription

**Phase 2+ модель:** тарифы Starter/Standard/Pro, add-ons (WhatsApp, кастомный домен, дополнительные локации), annual subscriptions с 15% скидкой.

### Модуль 9: CRM (Phase 2)

**Что:** управление клиентами как отдельный бизнес-процесс.

**Сущности и логика:**
- Lead — потенциальный клиент, источник, статус, контактная история
- Deal/Opportunity — сделка, воронка, этапы
- Customer (расширение существующей сущности) — сегментация, теги, lifetime value, RFM-анализ
- Activity — звонки, встречи, заметки
- Task — задачи сотрудникам
- Pipeline — настраиваемые воронки продаж
- Workflow — автоматические переходы и триггеры

**Логика:**
- Канбан-вид воронок
- Workflow-движок: при событии X → выполнить действие Y
- AI-анализ клиентов (для будущих сегментаций и предсказаний)
- Интеграция с notification engine для автоматических напоминаний

### Модуль 10: Inventory / Склад (Phase 2-3)

**Что:** полноценный складской учёт.

**Сущности и логика:**
- Warehouse — склад, локация
- StockMovement — приход, расход, перемещение, инвентаризация
- StockLevel — текущий остаток с различением: физический, доступный, зарезервированный, в пути, у поставщика
- Lot/Series — партии и серийные номера
- Supplier — поставщик, прайсы, условия

**Логика:**
- Резервирование при создании заказа
- Автоматическое списание при отгрузке
- Поддержка multiple warehouses
- Inventory snapshots для аудита

### Модуль 11: Orders / Заказы (Phase 2-3)

**Что:** управление заказами — отдельная сущность над Reservation.

**Сущности:**
- Order — заказ, items, total, customer, status (created → paid → fulfilling → shipped → delivered → cancelled), payment_status, fulfillment_status, parent_order (для наследования), supplier_tenant_id (для dropshipping)

**Логика:**
- Создание заказа из reservation или прямой покупки на сайте
- Workflow заказа с настраиваемыми статусами
- Связь с inventory (резерв при создании, списание при отгрузке)
- Связь с финансовыми движениями
- **Архитектурно заложено в Phase 1:** поля `parent_order` и `supplier_tenant_id` будут в миграции с первой версии модели Order, реализация логики наследования — в Phase 3+

### Модуль 12: Procurement / Закупки (Phase 3)

**Что:** полноценный процесс закупок у поставщиков.

**Workflow:**
- Потребность → запрос поставщику → коммерческое предложение → подтверждение закупки → заказ поставщику → ожидание поставки → приёмка → поступление на склад → обновление остатков → финансовая операция

### Модуль 13: Финансы и бухгалтерия (Phase 3)

**Что:** финансовый контур каждого бизнеса.

**Сущности и логика:**
- FinancialMovement — каждое действие в системе создаёт финансовое событие (продажа = доход, закупка = расход, возврат = корректировка, комиссия маркетплейса = удержание)
- Document — счета, инвойсы, акты, накладные, возвраты, чеки, договоры
- Account — счета и кассы
- Tax — налоги (для DACH: 19% MwSt, 7% reduced rate, etc.)

**Логика:**
- Любое действие создаёт финансовое движение автоматически
- Документы с PDF-генерацией и подписью
- Экспорт в DATEV (немецкий стандарт) — критичный для DACH рынка
- GoBD-совместимое хранение (требование немецкого Finanzamt)
- Финансовая аналитика

### Модуль 14: Marketplace (Phase 3-4)

**Что:** превращение агрегатора в полноценный маркетплейс с продажами через платформу.

**Логика:**
- Продавцы (tenants) с собственными витринами
- Комиссионная модель платформы
- Корзина потребителя через платформу (cross-tenant)
- Единое checkout
- Выплаты продавцам
- Escrow для гарантии сделок
- Рейтинги и отзывы

### Модуль 15: Dropshipping (Phase 3-4)

**Что:** система наследования заказов между бизнесами в системе.

**Сущности и логика:**
- Один товар может существовать у производителя, поставщика, посредника, магазина, на маркетплейсе
- При продаже на конце цепочки — автоматическое создание дочерних заказов
- Цепочка поставок: Клиент → магазин → дропшипер → поставщик → производство
- Каждый участник видит свою часть заказа
- Автоматическое распределение комиссий
- Синхронизация статусов через event bus

**Архитектурная заготовка в Phase 1:** поля `parent_order_id` и `supplier_tenant_id` в Order модели будут заложены с первой миграции. Реализация логики — позже.

### Модуль 16: Booking system (Phase 2-3)

**Что:** система бронирования для гостиниц, кафе, салонов, ретритов, услуг.

**Сущности и логика:**
- BookableResource — номер, столик, место, слот времени
- Booking — бронь конкретного ресурса на временной интервал
- Calendar — доступность ресурсов
- PricingRule — сезонные цены, акции, горящие предложения

**Связь с Promotion:** акция "горящая путёвка" — это специальный вид бронирования с скидкой, last-minute столик — то же самое.

### Модуль 17: Биржа услуг (Phase 4)

**Что:** платформа типа Upwork/Fiverr для подрядчиков и заказчиков.

**Логика:**
- Заявки и тендеры
- Подрядчики с рейтингами
- Безопасные сделки через escrow
- Этапы работ
- Арбитраж споров
- AI-подбор исполнителей

### Модуль 18: AI-помощник (Phase 4+)

**Что:** AI-ассистент внутри платформы.

**Возможности:**
- Анализ клиентской базы (сегментация, churn risk, lifetime value)
- Генерация писем и текстов акций
- Создание описаний товаров по фото
- SEO-оптимизация
- Прогнозирование продаж
- Рекомендации действий
- Автоматические ответы клиентам

### Модуль 19: Конструктор процессов / Workflow (Phase 3-4)

**Что:** позволяет каждому бизнесу настраивать собственные процессы.

**Логика:**
- Визуальный конструктор этапов
- Триггеры и условия
- Автоматические действия
- Обязательные поля на этапах
- Уведомления и эскалации
- Интеграция с CRM, заказами, финансами

### Модуль 20: Конструктор сайтов (Phase 3+)

**Что:** drag-and-drop конструктор страниц для tenant'ов.

**Возможности:**
- Шаблоны
- Drag-and-drop редактор
- SEO-настройки
- Мультиязычность
- Мобильная версия
- AI-генерация страниц по описанию
- Конструктор форм
- Конструктор карточек товаров

### Модуль 21: Интеграции (Phase 2-4)

**Что:** интеграции с внешними системами.

**Список:**
- Amazon, eBay (Phase 3+)
- Shopify, WooCommerce (импорт каталога — Phase 2)
- Google Merchant Center (Phase 2)
- Meta Business, TikTok (Phase 2-3)
- ERP-системы (1С, SAP — Phase 4)
- Службы доставки (DHL, Hermes, GLS — Phase 2-3)
- Платёжные системы (помимо Stripe — Phase 3+)
- Банки (Phase 3+)
- API поставщиков (Phase 3+)
- Bookkeeping/DATEV (Phase 3 — критично для DACH)

### Модуль 22: Импорт и экспорт (Phase 1 базовый, Phase 2+ расширенный)

**Phase 1:**
- CSV/Excel импорт каталога
- CSV/Excel экспорт акций, клиентов, броней
- JSON REST API на чтение

**Phase 2+:**
- XML/JSON импорт из ERP
- API двусторонней синхронизации
- Webhooks (outbound и inbound)
- Sopostavlenie полей через визуальный редактор
- Rollback и история изменений
- Массовое обновление

### Модуль 23: Аналитика и KPI (Phase 2+)

**Что:** дашборды и аналитика.

**Метрики:**
- Продажи, прибыль, маржа
- KPI сотрудников
- Эффективность каналов рекламы
- Воронки CRM, конверсии
- Загрузка ресурсов
- Эффективность поставщиков
- Customer Lifetime Value
- Churn analysis

### Модуль 24: Роли и права (Phase 2+)

**Что:** гибкая система прав доступа внутри tenant'а.

**Роли:**
- Owner — полный доступ
- Manager — управление операциями
- Staff — выполнение задач
- Accountant — финансы и документы
- Warehouse — складские операции
- Contractor — подрядчик
- Supplier — поставщик
- Customer — клиент
- Partner — партнёр

**Логика:** настраиваемые permission'ы, ролевая модель + объектные права.

---

## 6. Параллельный продукт: тур-агрегатор

### Концепция

Второй продукт на том же ядре платформы — агрегатор реальных туров (по аналогии с Tripster). Туроператоры публикуют туры, потребители бронируют через систему, платформа берёт комиссию.

### Сущности (расширения над core)

- Tour (extends Product) — длительность, языки, точка сбора, максимум участников
- TourDeparture — конкретный заезд с датой
- TourBooking (extends Reservation) — бронирование тура с участниками
- Commission — модель распределения комиссии оператору
- Payout — выплаты операторам
- Escrow — удержание средств до оказания услуги

### Стратегия запуска

**Последовательно, не параллельно с первым продуктом:**
1. Месяцы 1–6: первый продукт (акции для мини-маркетов) → 30–50 платящих клиентов
2. Месяц 7: рефакторинг — вынос общих частей в shared core, audit extension points
3. Месяцы 8–11: второй продукт (туры) на готовом core
4. Месяц 12+: параллельное развитие

**Причины последовательной разработки:**
- Параллельная разработка двух SaaS одним человеком гарантированно валит оба
- К Phase 2 будет понятно, что реально общее, а что нет — рефакторинг будет осмысленным
- Первый продукт даёт cash flow для второго

---

## 7. Архитектура платформы

### Принципы

1. **Build minimal, architect for extension.** Реализуем минимум сейчас, но архитектурные точки расширения закладываем сразу. Это бесплатно сейчас, дорого потом.

2. **Modular monolith.** Не микросервисы. Один Django-проект с чётко выделенными модулями (Django apps), которые могут быть выключены/включены через `INSTALLED_APPS` и `Tenant.enabled_modules`.

3. **Event-driven internal architecture.** Модули общаются через signals (event bus), а не через прямые вызовы. Это позволяет добавлять новые модули без переписывания существующих.

4. **Multi-tenancy first.** Изоляция данных каждого клиента через schema-per-tenant (PostgreSQL schemas) с django-tenants.

5. **Single source of truth для данных.** Единая БД (с разделением на схемы), единая модель данных в каждой схеме.

### Multi-tenancy

**Подход:** schema-per-tenant через django-tenants.

- Public schema — Tenant, Domain, глобальные категории, агрегатор
- Tenant schema (по одной на каждого клиента, имя `tenant_{slug}`) — каталог, акции, клиенты, заказы, всё специфичное

**Преимущества:**
- Физическая изоляция данных каждого клиента
- Сильный argument для GoBD/GDPR compliance (немецкий рынок)
- Возможность использовать стандартные Django queries без ручного фильтра по tenant_id
- Возможность мигрировать enterprise-клиентов в отдельные БД без перестройки кода

**Routing:** middleware определяет tenant по subdomain/custom domain и автоматически переключает PostgreSQL schema.

### Multi-region

**Архитектурно заложено в Phase 1:**
- Поле `Tenant.data_region` (EU / US / IN / UK / UAE)
- Router определяет регион по subdomain/domain

**Фактически в Phase 1:** один EU-сервер (Hetzner Falkenstein/Nürnberg), все tenants с `data_region='EU'`.

**Расширение в будущем:**
- Когда появятся US/Asia клиенты — поднимается второй стек в этом регионе
- US tenants переводятся туда, EU остаются в EU
- Нет cross-region репликации — это другой класс сложности

### Multi-language

**Контент tenant'ов (i18n JSONField):**
- Product.name, Product.description, Category.name, Promotion.title, Promotion.description, GlobalCategory.name — все хранятся как JSONField со словарём по локалям
- Tenant выбирает свой `default_locale` и `enabled_locales[]`

**UI:**
- Django i18n с gettext и .po файлами
- Phase 1: de + en
- Phase 2+: ru, uk, tr, fr и далее

**Расширение:** при необходимости JSONField мигрирует на django-modeltranslation (отдельные колонки `name_de`, `name_en`).

### Domain handling

Три режима, работают одновременно:
- Aggregator listing: `aggregator.platform.com/biz/{slug}`
- Subdomain: `{slug}.platform.com`
- Custom domain: `shop.client-domain.de`

Custom domain настраивается через CNAME, Caddy с on-demand TLS автоматически выпускает Let's Encrypt сертификат при первом запросе.

### Event bus (Django signals + Celery)

Архитектурный паттерн для коммуникации между модулями.

**Пример:**
```
PromotionService.create()
    ↓
signal `promotion_created` отправляется
    ↓
publishing receiver: автоматически публикует во все default channels
notifications receiver: queue notification tasks
crm receiver (Phase 2): обновить сегментацию клиентов
inventory receiver (Phase 3): зарезервировать stock
```

Это даёт чистую точку расширения: новый модуль подписывается на нужные signals, не трогая существующий код.

### Layers / абстракции

**Publishing Engine:**
- `BasePublisher` интерфейс
- Реализации на канал (Subdomain, Aggregator, Email, Telegram, WhatsApp, Google Business, Instagram, etc.)
- Registry: `get_publisher(channel_type)`
- Универсальная логика retry, статусы, error handling

**Notification Engine:**
- `BaseNotificationChannel` интерфейс
- Реализации: Email, Telegram, WhatsApp, SMS, Push
- Rate limiting через Celery
- Consent management
- Tracking доставки/открытий/кликов

**Этот же паттерн применяется к будущим модулям:**
- PaymentEngine (Stripe, PayPal, Klarna, банковские переводы)
- ShippingEngine (DHL, Hermes, GLS, Deutsche Post)
- IntegrationEngine (Shopify, WooCommerce, Amazon, eBay)

### Структура кода (monorepo)

```
platform/
├── config/                    # Django project
│   ├── settings/
│   ├── urls_public.py         # SHARED schema urls
│   ├── urls_tenant.py         # TENANT schema urls
│   ├── celery.py
│   └── wsgi.py
├── apps/
│   ├── tenants/               # SHARED: Tenant, Domain
│   ├── core/                  # TENANT: базовые модели, event bus
│   ├── catalog/               # TENANT: товары и категории
│   ├── promotions/            # TENANT: акции и резервации
│   ├── subscriptions/         # TENANT: клиенты и подписки
│   ├── publishing/            # TENANT: каналы и публикации
│   ├── notifications/         # TENANT: уведомления
│   ├── billing/               # TENANT: подписки tenant'а на Stripe
│   ├── aggregator/            # SHARED: публичная витрина
│   ├── global_categories/     # SHARED: глобальные категории
│   └── (future modules)
│       ├── crm/
│       ├── inventory/
│       ├── orders/
│       ├── dropshipping/
│       ├── procurement/
│       ├── finance/
│       ├── marketplace/
│       ├── booking/
│       ├── tours/
│       ├── workflows/
│       ├── ai_assistant/
│       └── integrations/
├── templates/
├── static/
└── docs/
```

---

## 8. Точки расширения и миграции

Это ключевой раздел — он описывает, **что в Phase 1 будет заложено архитектурно, но не реализовано**, чтобы будущая разработка не требовала переписывания ядра.

### Точки, заложенные в схеме данных Phase 1

**В модели Tenant:**
- `data_region` — для multi-region
- `enabled_locales[]` — для языковых расширений
- `enabled_modules[]` — для tier-based billing и постепенной выкатки модулей
- `business_type` — для отраслевой специфики (туры, отели, рестораны)

**В модели Product:**
- `metadata` (JSONField) — для отраслевой специфики:
  - Bakery: `{perishable, baked_at, allergens}`
  - Hotel: `{room_type, max_guests}`
  - Tour: `{duration_days, languages_offered, meeting_point, max_participants}`
  - Restaurant: `{table_size, dietary_tags}`
- `stock_quantity` — заготовка под inventory module

**В модели Customer:**
- `metadata` (JSONField) — для будущей CRM-сегментации
- Несколько каналов контакта (email, phone, telegram) — для multi-channel notifications

**В модели Promotion:**
- `metadata` (JSONField) — расширение под специфику
- `tags` (JSONField list) — для будущей сегментации и фильтрации
- `target_city`, `target_district` — для будущей гиперлокальной механики

### Точки, требующие миграций при добавлении новых модулей

**При добавлении CRM (Phase 2):**
- Расширение Customer: tags, segments, lifetime_value, churn_risk_score
- Новые модели: Lead, Deal, Activity, Task, Pipeline, Stage
- Миграция данных: existing customers получают пустой LTV и сегментацию

**При добавлении Orders (Phase 2-3):**
- Новая модель Order с полями:
  - `parent_order_id` (FK на self, для dropshipping наследования)
  - `supplier_tenant_id` (UUID, для cross-tenant orders)
  - `origin_type` (own_site / aggregator / channel_import)
- Связь Order ↔ Reservation: каждая Reservation может стать полноценным Order
- Миграция: существующие reservations не трогаются, новые orders создаются с обоих flows

**При добавлении Inventory (Phase 2-3):**
- Расширение Product: переход с `stock_quantity` на отдельную модель StockLevel
- Новые модели: Warehouse, StockMovement, StockLevel, Lot
- Миграция данных: `Product.stock_quantity` мигрирует в `StockLevel` для default warehouse

**При добавлении Finance (Phase 3):**
- Новые модели: FinancialMovement, Document, Account, Tax
- Связь FinancialMovement с existing entities (Order, Reservation, Subscription)
- Миграция: backfill финансовых движений из истории заказов и подписок

**При добавлении Marketplace (Phase 3-4):**
- Cart модель в shared schema (cross-tenant корзина потребителя)
- Commission модель на уровне платформы
- Payout модель для выплат tenant'ам
- Расширение Order: `marketplace_order=True`, связь с платформенной комиссией

**При добавлении Dropshipping (Phase 3-4):**
- Логика наследования заказов через `parent_order_id` (поле уже есть)
- Логика cross-tenant orders через `supplier_tenant_id` (поле уже есть)
- Новые модели: SupplierRelation, DropshippingAgreement
- Sync статусов между связанными orders через signals

### Миграция со стороны клиентов (импорт из существующих систем)

В Phase 2+ потребуется поддержка миграции данных бизнесов из других систем:

**Импорт каталога:**
- CSV/Excel (Phase 1 базовая поддержка)
- Shopify (через REST API)
- WooCommerce (через REST API)
- Lightspeed (через API)
- Square (через API)

**Импорт клиентской базы:**
- CSV с email/phone
- Mailchimp (через API)
- Brevo (через API)
- Excel-файлы (типичный формат для немецких пекарен)

**Импорт заказов / истории продаж:**
- POS системы (Square, Lightspeed)
- Существующие e-commerce платформы
- CSV-выгрузки

### Migration strategy между фазами

**Правило:** ни одна миграция не должна требовать downtime больше 10 минут на tenant.

**Подходы:**
- Использовать Django migrations с реверсируемой логикой
- Большие data migrations — через Celery tasks с прогрессивным обновлением
- Новые модели добавляются без удаления старых полей сразу (deprecate first, drop after 2 версии)
- Feature flags для постепенной активации новых модулей

---

## 9. Технологический стек

### Backend
- **Python 3.12+**
- **Django 5.1+** — основной фреймворк
- **django-tenants** — schema-per-tenant multi-tenancy
- **PostgreSQL 16+** — primary database
- **Redis 7+** — cache, sessions, Celery broker
- **Celery 5+** — async tasks, scheduled jobs (django-celery-beat)
- **Django REST Framework** — API (для интеграций и будущего мобильного приложения)

### Frontend
- **HTMX** — interactivity без SPA-сложности
- **Alpine.js** — клиентские компоненты
- **Tailwind CSS** — стилизация
- **django-htmx** — helper для интеграции

**Альтернатива (Phase 3+):** если понадобится drag-and-drop конструктор страниц или real-time дашборды — Next.js фронтенд поверх Django API.

### Auth
- **django-allauth** — email-based auth, social auth (Google/Apple для Phase 2+)
- **Magic links** для customer auth на агрегаторе

### Admin
- **Django Admin** (встроенный) — backoffice бесплатно
- **django-unfold** — современный UI для admin

### Payments
- **dj-stripe** — Stripe integration (subscriptions, webhooks, customer portal)

### Storage
- **django-storages** + Hetzner Object Storage (S3-compatible)
- В development — local FileSystemStorage

### Email
- **django-anymail** + Resend (или Postmark) provider

### Telegram
- **python-telegram-bot** для bot integration

### Internationalization
- Django i18n (gettext, .po файлы)
- Custom i18n JSONField widgets
- django-modeltranslation для будущего перехода

### Monitoring
- **Sentry** — error tracking
- **django-prometheus** — metrics
- **Plausible** или **PostHog** — product analytics (privacy-first, GDPR-friendly)

### Reverse proxy & SSL
- **Caddy 2** — automatic HTTPS, on-demand TLS для custom domains

### CI/CD
- **GitHub Actions** — build, test, deploy
- **Docker** + **Docker Compose** — контейнеризация

### Hosting
- **Hetzner Cloud** (Falkenstein/Nürnberg)
- Phase 1: 1× CPX21 (app) + 1× CCX13 (PostgreSQL + Redis), ~€25/мес
- Phase 2+: масштабирование

### Backup
- **Hetzner Snapshots** ежедневно
- **pg_dump** в Hetzner Object Storage с rotation (7 дней)

---

## 10. Фазы развития

### Phase 1: MVP (12 недель)

**Цель:** работающий продукт для мини-маркетов с end-to-end flow от регистрации до получения резервации.

**Состав:**
- Tenant onboarding & auth
- Catalog management
- Promotions с бронированием
- Publishing в subdomain + aggregator + email + Telegram
- Aggregator (публичная витрина)
- Customer subscriptions с уведомлениями
- Notification engine (email + Telegram)
- Billing (Stripe, €39/мес, 14-дневный trial)
- Branding & basic settings
- de + en UI

**Цель в клиентах:** 10–30 платящих к концу Phase 1.

**Спринты:**
1. Foundation & multi-tenancy
2. Catalog & dashboard
3. Promotions & reservations
4. Publishing engine & landing pages
5. Aggregator & customer experience
6. Notifications, billing & launch

### Phase 2: Расширение каналов и базовая CRM (3-6 месяцев после Phase 1)

**Цель:** 30 → 100 платящих, расширение функционала на основе обратной связи.

**Состав:**
- WhatsApp Business API integration
- Google Business Profile integration
- Instagram Business integration
- SMS notifications (Twilio)
- CRM-light: customer segmentation, tags, lifetime value
- Loyalty-программа (баллы)
- Купоны и промокоды
- Базовая аналитика дашборд
- Annual subscriptions
- Multi-location (для сетей точек)
- Расширение языков: ru, uk, tr

### Phase 3: Бизнес-операционная система (6-12 месяцев)

**Цель:** 100 → 300 платящих, превращение в полноценную Business OS.

**Состав:**
- Orders module (полноценные заказы поверх reservations)
- Inventory management (склад с warehouse/stock movement)
- Finance & accounting (financial movements, документы, DATEV экспорт)
- Procurement (закупки у поставщиков)
- Booking system (для гостиниц, ресторанов, услуг)
- Workflow engine (настраиваемые процессы)
- Расширенная аналитика и KPI
- Полноценная ролевая модель
- Mobile app (iOS + Android) для tenant'ов

### Phase 4: Маркетплейс и AI (12-24 месяца)

**Цель:** 300 → 1000+ платящих, превращение в платформу.

**Состав:**
- Marketplace (cross-tenant продажи через платформу)
- Dropshipping (наследование заказов)
- Биржа услуг
- Tour aggregator product (второй продукт)
- AI-помощник (анализ, генерация, рекомендации)
- Конструктор сайтов (drag-and-drop)
- Расширенные интеграции (Amazon, eBay, ERP)
- Multi-region (US, Asia)

### Phase 5+: Экосистема (24+ месяца)

**Долгосрочно:**
- B2B cloud infrastructure
- Платформа франшиз
- White-label решения для крупных партнёров (Bäcker-Innungen, retail chains)
- Международное расширение

---

## 11. Монетизация

### Phase 1: один тариф €39/мес

Обоснование:
- Психологически ниже €40
- Ниже Brevo Business (€44), выше Brevo Starter (€17)
- Покрывает связку "сайт + база + акции + бронирование + агрегатор", которой нет у конкурентов
- ROI очевиден владельцу с первой акции

### Phase 2+: tier-модель

- **Starter €19/мес** — пекарня без email, только сайт + агрегатор + Telegram
- **Standard €39/мес** — полный пакет
- **Pro €89/мес** — + WhatsApp + кастомный домен + расширенная аналитика + 2 точки
- **Multi-location €149/мес** — до 5 точек

### Add-ons

- Дополнительные локации: €15/мес каждая
- WhatsApp Business: €19/мес (1000 сообщений включено)
- Кастомный домен: €5/мес
- SMS: €0.10 за сообщение pay-as-you-go
- Премиум-поддержка: €49/мес

### Annual

- 15% скидка за годовую подписку
- Цель: 30-40% клиентов на annual

### Юнит-экономика

- Среднее CAC: €150 (Phase 1, личные продажи) → €250 (Phase 2+, mixed channels)
- LTV: €731 (при churn 4%/мес и gross margin 75%)
- LTV:CAC ratio: 3-5x (цель >3x)
- Break-even при solo: ~150 платящих клиентов

### Параметры успеха

| Метрика | Год 1 | Год 2 | Год 3 |
|---------|-------|-------|-------|
| Customers | 100 | 250 | 500 |
| MRR | €3,900 | €9,750 | €19,500 |
| ARR | €47k | €117k | €234k |
| Monthly churn | <5% | <4% | <3% |
| LTV:CAC | >3x | >4x | >5x |

---

## 12. Рынок и конкурентная позиция

### Конкуренты по функциям

| Решение | Цена/мес | Email | Сайт | База | Бронирование | Лок. агрегатор | Pickup |
|---------|----------|-------|------|------|--------------|----------------|--------|
| Mailchimp | $13-20+ | ✓ | базовый | до 500 | ✗ | ✗ | ✗ |
| Brevo | €17-44 | ✓ | extra | unlim | ✗ | ✗ | ✗ |
| Klaviyo | $20+ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ |
| WhatsApp Bus | free | ✗ | ✗ | базовая | ✗ | ✗ | вручную |
| Mailerlite | $9+ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Square Mktg | $15+POS | ✓ | требует POS | ✓ | ✓ | ✗ | ✓ |
| Shopify Starter | €5+ | extra | ✓ | базовая | ✗ | ✗ | ✗ |
| Lieferando | 13% комисс | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ |
| **Наша платформа** | **€39** | ✓ | ✓ | unlim | ✓ | ✓ | ✓ |

### Уникальная позиция

Единственная связка "собственный сайт + база клиентов + акции с бронированием + локальный агрегатор" на немецком рынке с DACH-нативной поддержкой и фиксированной ценой (не зависящей от размера базы клиентов, в отличие от Mailchimp).

### Главные ценностные аргументы для продажи

1. **"Заработай больше с существующих клиентов"** — push об остатках = +€60/день в средней пекарне → ROI 46x
2. **"Будь как сети"** — у Kamps/Bäcker Görtz есть приложения, у вас нет → стратегический страх отставания
3. **"Не завись от Facebook и Google"** — собственная база клиентов принадлежит вам, не платформам

---

## 13. Что уже архитектурно решено

### Зафиксированные решения

- **Python + Django 5 + django-tenants** как backend
- **PostgreSQL** как primary database
- **HTMX + Alpine + Tailwind** как frontend (без SPA в Phase 1)
- **Schema-per-tenant** multi-tenancy
- **Stripe + dj-stripe** для billing
- **Hetzner Cloud (EU)** как hosting
- **Resend** для email
- **Modular monolith** архитектура (не микросервисы)
- **Event bus через Django signals + Celery** для inter-module communication
- **i18n через JSONField** в Phase 1, миграция на django-modeltranslation позже
- **Один тариф €39/мес** в Phase 1, tier-модель в Phase 2+
- **Последовательная разработка двух продуктов** (мини-маркеты → потом туры)
- **Старт с одной EU-локации** (Falkenstein/Nürnberg), multi-region архитектурно заложен но не построен
- **6 спринтов по 2 недели** в Phase 1

### Открытые вопросы

- Конкретный городской фокус для старта (Hilden / Düsseldorf / Köln регион — кандидат, нужны interviews)
- WhatsApp Business — Phase 2 или раньше (зависит от спроса)
- Mobile app — Phase 3 (Native vs PWA — отложено)
- Конкретная модель монетизации tour-агрегатора (комиссия %, fixed fee, hybrid)
- Когда нанимать первых людей (зависит от cash flow и темпа роста)
- Когда (и нужно ли) поднимать инвестиции
- Конкретные partner channels (Bäcker-Innungen, IHK, Fachzeitschriften) — нужна валидация

---

## 14. Риски и митигация

### Главные риски

1. **High churn (>5%/мес)** — типичная боль SMB SaaS
   - Митигация: серьёзный onboarding (live demo, помощь с настройкой первой акции, проверка использования через 2 недели), engagement tracking

2. **Высокий CAC** — если холодный аутрич не работает
   - Митигация: фокус на одном канале до 100 клиентов прежде чем масштабировать, referral program, партнёрства с Bäcker-Innungen

3. **Аггрегатор не наберёт пользователей** — chicken-and-egg
   - Митигация: аггрегатор позиционируется как бонус, основная ценность в собственном сайте бизнеса. Не зависим от агрегатора в первый год.

4. **Цена окажется неверной** — €39 слишком дорого или слишком дёшево
   - Митигация: A/B testing в первых 30 интервью (€19/€39/€59), price grandfathering для существующих

5. **Технический долг от parallel разработки**
   - Митигация: строго последовательная разработка двух продуктов, не параллельная

6. **Cumulative loss до break-even ~€67,000**
   - Митигация: параллельный consulting бизнес (BOLTCAD) генерирует cash flow и снимает давление сроков

### Что НЕ риск (но кажется)

- Конкуренция с Mailchimp/Brevo — они в другой нише (email-only), не делают связку
- Конкуренция с локальными платформами (mydealz) — они user-driven aggregator, мы business-driven с собственным сайтом
- Технический скейл — на Phase 1 объёмах это вообще не проблема, Django + PostgreSQL держит миллионы записей

---

## 15. Ключевые принципы

### Продуктовые

- **Глубина в одной нише сначала, ширина потом.** Не "all-in-one для всех бизнесов", а "идеально для мини-маркетов в Германии".
- **Простота важнее функциональности.** Владелец пекарни не должен учиться. Создать акцию = 2 минуты.
- **Очевидный ROI.** За €39/мес клиент должен зарабатывать минимум €100/мес. Лучше €500.
- **No surprises.** Фиксированная цена, никакого pay-as-you-go или роста цены при росте базы.

### Технические

- **Build minimal, architect for extension.** Реализуем только нужное, но точки расширения закладываем сразу.
- **Один модуль за один спринт.** Не пытаемся делать пять модулей параллельно.
- **Tests параллельно с кодом, не "потом".** Минимум 70% coverage.
- **Modular monolith, не микросервисы.** Микросервисы — только когда команда >10 человек.
- **Event-driven internal architecture.** Модули общаются через signals, не через прямые вызовы.

### Бизнес

- **Bootstrap, не VC, до product-market fit.** Венчурные деньги привлекают плохие решения и неправильные KPI.
- **Параллельный consulting бизнес (BOLTCAD) даёт runway** — это критическое стратегическое преимущество перед типичными стартаперами.
- **30-50 платящих клиентов = signal для следующего шага.** До этого не нанимать, не масштабировать, не запускать второй продукт.
- **Customer interviews до кода, всегда.** Гипотеза не подтверждена — продукт не строим.

---

## 16. Что нужно сделать прежде чем писать код

### Customer development (2-3 недели)

1. Собрать список 50 пекарен/мини-маркетов в радиусе 30 км от Hilden
2. Провести 15 интервью с владельцами (НЕ продавать, слушать)
3. Валидировать ключевые гипотезы:
   - "У вас есть постоянные клиенты, чьи контакты вы знаете" — должно быть "да" в 70%+
   - "Вы бы хотели иметь способ сообщать им об акциях/остатках" — должно быть "да" в 80%+
   - "Вы готовы платить €30-50/мес за такой инструмент с гарантией нескольких дополнительных клиентов в день" — должно быть "да" в 50%+
4. Решение go/no-go: если 8+ из 15 говорят "да заплатил бы за это" → go

### После go-решения

5. Начало Sprint 1 разработки
6. Параллельно — построение списка warm pipeline из тех 15 интервью

---

## 17. Итог: что отличает эту платформу

1. **Узкий вертикальный фокус на старте** — мини-маркеты в Германии, не "все бизнесы во всех странах"
2. **Связка функций, которой нет у конкурентов** — сайт + база + акции + бронирование + локальный агрегатор
3. **DACH-нативная архитектура** — schema-per-tenant для GoBD/GDPR, локальный хостинг (Hetzner), немецкий язык первым, DATEV-экспорт в Phase 3
4. **Модульная архитектура с заложенными точками расширения** — от MVP до Business OS без переписывания
5. **Фиксированная цена €39/мес без сюрпризов** — в отличие от Mailchimp/Klaviyo с растущими ценами
6. **Параллельный продукт (туры) на том же ядре** — последовательно, не параллельно
7. **Bootstrap-стратегия с consulting backup** — устойчивая финансовая модель без венчурных денег
8. **Долгосрочное видение универсальной Business OS** — но шаг за шагом, не пытаясь построить всё сразу

---

## Метаданные документа

- **Версия:** 1.0
- **Дата:** ноябрь 2026
- **Контекст создания:** документ создан как результат серии стратегических обсуждений между основателем и AI-ассистентом
- **Назначение:** загрузка в другой чат для независимого анализа и валидации концепции, выявления слепых зон и предложений по улучшению
- **Что хотелось бы получить от анализа:**
  - Слепые зоны в концепции
  - Риски, которые не были учтены
  - Альтернативные углы взгляда на ту же проблему
  - Конкретные тактические улучшения Phase 1
  - Сравнение с похожими успешными/проваленными SaaS-проектами
  - Реалистичность сроков и финансовых проекций
