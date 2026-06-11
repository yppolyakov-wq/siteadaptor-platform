# Track D — Кирпичи Business OS (ТЗ на разработку)

> Источник: два концепт-документа владельца (2026-06-11) — «Универсальная цифровая
> экосистема / Business Operating System» (CRM + ERP + Marketplace + Dropshipping +
> Booking + Склад + Бухгалтерия + Биржа услуг + AI + интеграции + конструкторы).
> Полное видение — `docs/full-platform-vision.md` (Модули 1–24).
>
> Решение владельца по итогам разбора (2026-06-11): **гибрид/секвенсинг.** Остаёмся
> в нише оффлайн-SMB DACH (текущий продукт кормит и служит клином), но следующие
> модули строим осознанно как первые переиспользуемые кирпичи Business OS. Тяжёлый
> ERP/маркетплейс/дропшип — осознанно откладываем (см. §«Откладываем»).

## 0. Контекст: что уже есть (фундамент совпадает с Business OS)

Текущий продукт уже покрывает часть видения и даёт примитивы для Track D:

| Видение (Business OS) | Статус в коде | Что переиспользуем |
|---|---|---|
| Мультитенант, модульность, FSM, idempotent tasks | ✅ | ядро `apps/core` |
| Каталог + CSV/Excel импорт (Модуль 1, 22) | ✅ | `catalog.Product` (base_price/currency/images) |
| Акции + резерв с anti-oversell (Модуль 2) | ✅ | движок `reserve/redeem`, `ReservationSM`, QR, код `R-XXXX` |
| Publishing-каналы + GBP (Модуль 3, 21) | 🟡 | `apps/publishing` |
| Уведомления + БД-dedupe (Модуль 4) | ✅ | `send_notification`, `dedupe_key` |
| Агрегатор + порталы (Модуль 5) | ✅ | — |
| Онбординг/Auth/Branding (Модуль 6, 7) | ✅ | `Tenant` (реквизиты: name/address/vat_id/legal_responsible/contact_*) |
| Биллинг подписки платформы (Модуль 8) | ✅ | dj-stripe (подписка платформы, **не** выручка бизнеса) |
| Клиент `Customer` + история по email | 🟡 | `promotions.Customer` (FK из Reservation/LoyaltyCard), `account_services` |
| Local SEO, кастом-домены, DSGVO-инструменты | ✅ | — |

**Главный вывод разбора:** ТЗ-видение на 1–2 порядка больше текущего продукта, но
~30% его кирпичей уже стоят. D1–D4 ниже — **тонкие надстройки над готовыми
примитивами**, а не greenfield.

## 1. Принцип отбора модулей

В Track D берём только то, что **одновременно**:
1. нужно текущему клиенту (пекарня/мясная/кафе/ритейл DACH), и
2. переиспользует существующую архитектуру (schema-per-tenant, FSM, notifications).

Порядок (подтверждён владельцем): **D1 CRM-lite → D2 Click&Collect → D3 Booking-
календарь → D4 Light-Finance.** Финансы после заказов — Order/Reservation служат
источником выручки.

---

## D1 — CRM-lite «Kunden» (vision Модуль 9, срез 1)

**Заменяет** прежний пункт Track C / C3 «CRM-минимум» (расширен и поднят в приоритет).

**Цель.** Владелец видит и ведёт клиентов в кабинете; единая карточка 360°. База
под лояльность, повторные продажи и Light-Finance.

**Уже есть.** Модель `promotions.Customer` (TENANT): `name/email/phone/note`,
создаётся при первой брони, переиспользуется по email, `unsubscribe_token`, индекс
по email. FK: `Reservation.customer` (PROTECT), `LoyaltyCard.customer` (CASCADE).
Кросс-схемная история по email — `aggregator/account_services.reservations_for_email`
(но это кабинет конечного клиента, не владельца).

**Чего нет.** Кабинета владельца: ни маршрута, ни списка, ни карточки. Нет тегов,
согласия на маркетинг, ленты заметок, экспорта.

**Дельта.**
- Новое приложение `apps/crm` (TENANT; зарегистрировать в `base.py` TENANT_APPS):
  - `CustomerNote` (TENANT, `crm/0001`): `customer FK→promotions.Customer`, `author`
    (User), `text`, `created_at` — лента заметок (cross-app FK допустим).
- Миграция `promotions/0011`: добавить `Customer.tags` (`JSONField(default=list)`),
  `Customer.marketing_opt_in` (`bool`, default False; UWG §7 — Double-Opt-In, отписка
  уже есть), `Customer.created_source` (`reservation/manual/import`, default reservation).
  Теги через JSON-список строк (модель `CustomerTag` — позже при спросе).
- Маршруты в кабинете (новый `apps/crm/urls.py`, подключить в `urls_tenant.py`):
  - `/dashboard/customers/` — список: поиск по name/email/phone, фильтр по тегу,
    курсорная пагинация (как в каталоге/акциях).
  - `/dashboard/customers/<id>/` — карточка 360°: контакты, теги (inline-редакт,
    HTMX), `marketing_opt_in` toggle, лента заметок (добавить через HTMX), история
    броней (readonly: `Reservation.filter(customer)`), карты лояльности
    (`LoyaltyCard.filter(customer)`), ваучеры (по email/коду, если связь есть).
  - `/dashboard/customers/new/`, `/<id>/edit/` — ручное добавление/правка.
  - `/dashboard/customers/export.csv` — экспорт списка (DSGVO-aware; рядом уже есть
    команда `dsgvo_customer`).
- Гейтинг billing применяется (при `suspended` — read-only, как в остальном кабинете).

**Тесты.** Список/поиск/фильтр, карточка 360° (агрегация по одному tenant — дёшево),
добавление заметки, ручное создание, CSV-экспорт. Tenant + RequestFactory.

**Разбивка (подзадачи).** D1a модель+миграции+список → D1b карточка 360°+заметки+теги
→ D1c экспорт CSV. **Зависимости:** нет (данные уже есть).

---

## D2 — Click & Collect / Заказы-lite (vision Модуль 11, срез 1)

**Цель.** Клиент заказывает товар(ы) из витрины `/sortiment/` к самовывозу; владелец
видит заказы и отмечает выдачу. Мост к «Marketplace» без корзины-с-доставкой и без
обязательной онлайн-оплаты.

**Уже есть.** Весь движок «зарезервировал онлайн → забрал в магазине»: паттерн
`reserve()` (контакты→`Customer`), `ReservationSM` (pending→confirmed→fulfilled),
код `R-XXXX`, redeem-флоу + QR + авто-погашение по скану, список входящих,
TTL/expire, атрибуция `source_channel`, rate-limit, DSGVO-очистка PII. `catalog.Product`
с `base_price/currency/images`. Витрина товара `/sortiment/<slug>/` (C1).

**Чего нет.** Резерв привязан только к `Promotion` (FK `Reservation.promotion`). На
обычный товар каталога заказа нет (C1 — «без корзины, покупка офлайн»). Нет сущности
«заказ» (мультитовар), статуса оплаты, слота самовывоза.

**Дельта.**
- Новое приложение `apps/orders` (TENANT; в `base.py` TENANT_APPS):
  - `Order` (`orders/0001`): `customer FK`, `reference_code` (как `R-XXXX`),
    `status` (FSM), `pickup_slot` (nullable — мост к D3 позже), `note`,
    `source_channel`, `payment_state` (`unpaid/paid`, v1 — вручную/в магазине),
    `total` (снимок суммы).
  - `OrderItem`: `order FK`, `product FK→catalog.Product`, `qty`, `unit_price`
    (снимок), `title_snapshot`.
  - `OrderSM` (`apps/core/fsm`): `new → confirmed → ready → picked_up`
    (+ `cancelled`); внешние эффекты (письма) — через notifications dedupe.
- **Остаток.** `catalog.Product` сейчас без поля stock. v1 Click&Collect — без
  жёсткого лимита (предзаказ, как акция с `available_quantity=null`). Опц.
  `Product.stock` (nullable) + anti-oversell на заказе — отдельный инкремент и мост
  к Модулю 10 (Inventory). **Решение: v1 без stock.**
- **Оплата.** v1 — оплата в магазине (`payment_state` вручную). Онлайн-предоплата
  (Stripe-за-товар) — отдельный инкремент, переиспользует dj-stripe и **связан с
  P2.5** (платежи конечного клиента). **Решение: v1 без онлайн-оплаты.**
- Публичная витрина: на `/sortiment/<slug>/` кнопка «Zur Abholung bestellen» →
  корзина в сессии (Alpine, мультитовар) → форма оформления (контакты как в reserve,
  опц. желаемое время) → создаёт `Order` + `Customer`. Rate-limit как у брони.
- Кабинет: `/dashboard/orders/` — список входящих, карточка заказа, действия
  (confirm/ready/picked_up/cancel) с уведомлением клиенту на каждый статус. 360°
  из D1 показывает заказы клиента.

**Тесты.** Создание заказа из витрины (+Customer), FSM-переходы, письма-уведомления
(dedupe), rate-limit, корзина-сессия. Миграция `orders/0001`.

**Разбивка.** D2a модель+`OrderSM`+создание из витрины (корзина) → D2b кабинет
заказов + статусы + письма → D2c (опц./позже) `Product.stock`+anti-oversell и/или
онлайн-оплата. **Зависимости:** D1 (Customer/360°), `catalog.Product` (есть).

---

## D3 — Booking-календарь / запись по времени (vision Модуль 16, срез 1)

**Цель.** Запись по времени (столик / услуга / мастер / комната) — для кафе, салонов,
услуг. Самый «новый» домен из четырёх (больше всего кода).

**Уже есть.** `Reservation` — это **количественный** резерв (не слот). `Customer`,
notifications + beat-напоминания (паттерн), FSM-каркас.

**Чего нет.** Календаря, слотов времени, ресурсов/расписаний, анти-двойного-бронирования
по времени.

**Дельта.**
- Новое приложение `apps/booking` (TENANT; в `base.py` TENANT_APPS), `booking/0001`:
  - `Resource` — что бронируем: `name`, `type` (стол/мастер/комната/услуга),
    `capacity`.
  - `Schedule`/`Availability` — рабочие часы и слоты (recurring weekly) + исключения
    (выходные/праздники).
  - `Booking` — `resource FK`, `customer FK`, `start`, `end`, `party_size`,
    `status` (FSM: pending→confirmed→fulfilled→cancelled/no_show), `reference_code`.
  - `BookingSM` + **anti-double-book**: атомарная проверка пересечений по
    ресурсу/времени (аналог anti-oversell, но по интервалам; ключевой тест).
- Публичная витрина: `/termin/` — выбор ресурса/услуги → день → свободные слоты →
  форма контактов (как reserve). Rate-limit.
- Кабинет: календарь-вид (день/неделя), список записей, ручное добавление/перенос/
  отмена.
- Уведомления: подтверждение + напоминание (beat за N часов до начала) — через
  notifications dedupe. Сезонные цены / горящие слоты — позже.

**Тесты.** Пересечение слотов (нельзя забронировать занятый интервал) — критичный;
расписание/исключения; FSM; напоминание. Миграция `booking/0001`.

**Разбивка.** D3a ресурсы+расписание+`BookingSM`+anti-double-book → D3b публичная
запись из витрины → D3c кабинет-календарь + напоминания. **Зависимости:** D1
(Customer), notifications (есть).

---

## D4 — Light-Finance + DATEV (vision Модуль 13, срез 1)

**Цель.** Журнал выручки + счёт (Rechnung) PDF + экспорт DATEV/CSV. **Не** полный
бухучёт (SAP/1C уровень — Phase 3). DE-аргумент продажи.

**Уже есть.** `reportlab` (зависимость из B4 QR-постера) — генерация PDF. Источники
выручки: `Order` (D2), `Reservation`. Реквизиты в `Tenant`: `name/address/city/
vat_id (USt-IdNr)/legal_responsible/contact_email/phone` — для §14 UStG почти всё есть.

**Чего нет.** Финансовых движений бизнеса (есть только биллинг подписки платформы),
счетов, экспорта.

**Дельта.**
- Новое приложение `apps/finance` (TENANT; в `base.py` TENANT_APPS), `finance/0001`:
  - `RevenueEntry` (движение-lite): `source` (order/reservation/manual), `amount`,
    `currency`, `vat_rate`, `date`, `customer FK` (опц.), `note`, ссылка на документ.
    v1 — только доходы (расходы/себестоимость — позже; «любое действие → фин-событие»
    из ТЗ-2 закладываем хуком, но без полного контура).
  - `Invoice` (Rechnung): `number` (**последовательная per-tenant** — требование DE),
    `customer`, `lines` (снимок), `net/vat/gross`, `status` (draft/issued/paid/
    cancelled — `issued` иммутабелен), ссылка на PDF. Опц. флаг Kleinunternehmer §19
    (без НДС) — добавить в `Tenant` (миграция `tenants/000x`) + опц. `Steuernummer`,
    если решим, что `vat_id` недостаточно.
- Хуки: `Order.picked_up` / `Reservation.fulfilled` → `RevenueEntry` (idempotent).
- PDF Rechnung (reportlab, как постер) + скачивание; нумерация и иммутабельность
  `issued` (GoBD — оргчасть на владельце, код даёт последовательность).
- Экспорт: DATEV-CSV (формат полей) + обычный CSV за период.
- Кабинет: `/dashboard/finance/` — журнал выручки за период, счета, экспорт.

**Тесты.** Последовательность номеров (без дыр/гонок), расчёт VAT, §19-режим,
формат DATEV-экспорта, иммутабельность `issued`. Миграция `finance/0001`
(+ опц. `tenants/000x`).

**Разбивка.** D4a `RevenueEntry`+журнал+хуки → D4b `Invoice`+PDF Rechnung →
D4c экспорт DATEV/CSV. **Зависимости:** желательно D2 (Order как источник),
reportlab (есть).

---

## Откладываем (осознанно, с причинами)

- **Модуль 10 Inventory (полный склад), 12 Procurement, 14 Marketplace,
  15 Dropshipping, 17 Биржа услуг.** Другой класс сложности и **другие клиенты**.
  Дропшип/маркетплейс/биржа требуют **кросс-тенантного графа заказов на shared-
  таблицах** (родитель→дочерний заказ, цепочка поставки) — это **конфликтует со
  schema-per-tenant** (данные изолированы по схемам) и означает разворот ядра, а не
  модуль сверху. Делать только при сознательном пивоте.
- **Модуль 18 AI (полный), 19 Workflow-конструктор, 20 drag-and-drop сайт-билдер.**
  Phase 3–4.
- **POS/TSE (KassenSichV), собственный эквайринг, маркетплейс-корзина** — уже
  зафиксировано «не делать сейчас» (roadmap §Отложено, стратегия DE-рынка).

**Кандидат-исключение — AI-контент (узкий срез Модуля 18):** авто-описания товаров/
акций, SEO-тексты, посты в каналы поверх готового `apps/publishing` — дёшево, высокий
wow, кросс-модульно. Кандидат на D5 / параллельно (использовать актуальные модели
Claude). Зафиксировано как кандидат, вне основной очереди D1–D4.

## Связь с vision-модулями (для трассировки)

D1→Модуль 9 (CRM), D2→Модуль 11 (Orders), D3→Модуль 16 (Booking), D4→Модуль 13
(Финансы). Каждый — узкий **срез 1** соответствующего модуля; полные версии остаются
в Phase 2–4 по `docs/full-platform-vision.md`.

## Рабочий цикл (по общим конвенциям)

Один инкремент = одна подзадача: ветка `claude/<кратко>` → push → CI зелёный →
чекпоинт с владельцем → (опц. деплой `./scripts/deploy.sh single`) → следующая.
Новые TENANT-приложения — в `config/settings/base.py` TENANT_APPS (test.py
подхватит как SHARED). Смена статусов — только через FSM `.apply()`; внешние эффекты
— через Celery + idempotent_task / dedupe_key. Миграции последовательные.
