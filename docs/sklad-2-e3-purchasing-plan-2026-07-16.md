# Склад-2 E3 — Закупки (M12): Lieferant + Bestellung — план-разбивка

> **Статус: DRAFT (2026-07-16).** Волна одобрена владельцем («все 3 эпика», порядок
> E1→E3→E2). E1 (Chargen/MHD+FEFO) закрыт (E1.1-E1.5). Этот док — план E3 ДО кода.
> ID семейства — **U-D2W-E3** (`task-catalog.md`), поверх T5 (Bestellvorschläge) + E1
> (приёмка по партиям). Источник спеца — `sklad-2-plan-2026-07-16.md §2` (строка E3).

## 1. Что уже есть (фундамент — переиспользуем, не переписываем)

- **T5 (`catalog/0014`):** `cost_price`/`reorder_point`/`reorder_target` на Product+Variant;
  `inventory_value()` (Warenwert), `reorder_suggestions(threshold)` (Bestellvorschlag =
  Soll−Bestand, Ausverkauft первыми) — `apps/inventory/services.py:172`.
- **E1 (`inventory/0002`):** `receive_lot` (приёмка партии: счётчик+леджер+Lot одной atomic);
  `apply_manual_movement` (ЕДИНСТВЕННЫЙ путь «счётчик+леджер», `select_for_update`).
- **Кабинет `/dashboard/stock/`** (хаб «Sortiment»): Bestellvorschläge, приёмки, Warenwert.
- **Пикер сущностей** `stock_entities()` (`v<pk>`/`p<pk>`), `find_entity_by_code` (SKU/EAN).
- **Чего НЕТ:** поставщик (Lieferant), закупочный заказ (Bestellung), связь приёмки с
  заказом, история закупочных цен, авто-обновление `cost_price` из реальных закупок.

## 2. Целевой флоу (Bestellwesen)

```
Bestellvorschläge (T5)  →  Bestellung-Entwurf (draft)  →  bestellt (ordered)
   [дозаказ по Soll]        [строки: Artikel/Menge/EK]     [отправлен поставщику]
        │                                                        │
        └──────────────── выбрать поставщика ────────────────────┘
                                                                 ▼
                              Wareneingang (empfangen, полный/частичный)
                              → книжит receipt (E1 receive_lot при lots_enabled,
                                иначе apply_manual_movement) → qty_received++ на строке
                              → опц. обновляет cost_price товара из EK строки
                              → статус received когда всё принято
```

## 3. Модели (⚠️ миграция `inventory/0003`, TENANT, аддитив)

- **`Lieferant`** (поставщик): `name`, `contact_person`, `email`, `phone`, `address`
  (Textfield), `customer_number` (наш № у поставщика), `note`, `is_active`,
  Timestamped. Опц. `default_lead_days` (срок поставки — для будущих алертов).
- **`Bestellung`** (закупочный заказ): `supplier` FK→Lieferant (SET_NULL, nullable —
  «разный/разовый»), `status` (draft/ordered/received/cancelled), `reference` (авто-код
  `BE-XXXX`, как reference_code заказа), `note`, `ordered_at`/`received_at` (nullable),
  `actor`, Timestamped. Свойство `total_cost` (Σ строк) для отображения.
- **`BestellPosition`** (строка заказа): `bestellung` FK (CASCADE, related_name=`positions`),
  `product` FK / `variant` FK (nullable — сущность как в остальном складе), `qty`
  (PositiveInt), `unit_cost` (Decimal — EK снимок), `qty_received` (default 0), `note`.
  Свойство `is_fully_received` (qty_received >= qty), `line_total`.

**Инвариант:** Bestellung НЕ трогает счётчик до приёмки; приёмка = существующий путь
(`receive_lot`/`apply_manual_movement`) → счётчик/леджер двигаются ТОЛЬКО там (D1 цел).
Идемпотентность приёмки — по `source="purchase"`,`source_ref=str(position.pk)+":"+seq`
(частичные приёмки — разные seq; UniqueConstraint леджера уже есть).

## 4. Фазовая разбивка (по инкременту; каждая = ветка→CI→чекпоинт→FF-мерж)

- **E3.1 (⚠️ миграция `inventory/0003`)** — модели Lieferant/Bestellung/BestellPosition +
  сервисы `create_po`, `add_po_line`, `set_po_status`, `receive_po_line` (книжит receipt
  через E1-путь + qty_received++ + опц. cost_price). Замки: создание/приёмка двигает
  счётчик один раз; частичная приёмка; идемпотентность.
- **E3.2** — кабинет `/dashboard/purchasing/` (список Bestellungen + CRUD-Entwurф):
  выбрать поставщика, добавить строки (пикер сущности + Menge + EK), статусы
  (draft→ordered→received/cancelled). Под хабом «Sortiment» (вкладка «Einkauf»).
- **E3.3** — «Bestellvorschlag → Entwurf»: кнопка на Bestellvorschläge (T5) собирает
  черновик заказа из предложений (сгруппировать по поставщику, если у Artikel задан
  Standard-Lieferant — опц. поле `Product.default_supplier`?). v1: один черновик из всех
  предложений, поставщик выбирается вручную.
- **E3.4** — приёмка в кабинете: экран Wareneingang по Bestellung (ввести принятое кол-во
  на строку → книжит; при lots_enabled — Charge/MHD как в E1). Закрытие заказа.
- **E3.5 (опц.)** — Lieferanten-Verwaltung (CRUD поставщиков отдельным экраном), история
  закупочных цен (EK-Historie на товаре), связь `cost_price` авто-обновление (тумблер).
- **Демо/тесты:** демо-поставщик + пара Bestellungen для еда/ритейл-китов; замки на
  приёмку/идемпотентность/статусы.

## 5. Развилки на согласование владельцем (перед E3.1)

1. **`Product.default_supplier`** (Standard-Lieferant на товаре, для группировки
   Bestellvorschlag→Entwurf по поставщику) — добавляем в E3.1 (ещё поле миграции) или
   откладываем (v1 — один черновик, поставщик вручную)? Рекомендую **отложить** (v1
   проще; поле добавим в E3.3, если понадобится группировка).
2. **Авто-обновление `cost_price`** при приёмке (EK из строки → cost_price товара):
   всегда / по тумблеру / никогда? Рекомендую **по тумблеру** (не перетирать вручную
   выставленный EK без спроса) — в E3.4/E3.5.
3. **Частичные приёмки** нужны в v1 или достаточно «принять весь заказ»? Рекомендую
   **частичные** (реалистично: поставки приходят дробно) — заложено в модель (qty_received).
4. **Немецкий UI:** «Einkauf»/«Bestellungen»/«Lieferanten»/«Wareneingang» — подтвердить
   терминологию.

## 6. Риски

- **Инвариант D1:** Bestellung — планирование; счётчик двигает ТОЛЬКО приёмка через
  существующий путь (receive_lot/apply_manual_movement). Ни одной прямой записи счётчика.
- **Идемпотентность приёмки:** partial-receipts → уникальный `source_ref` per receipt-событие
  (позиция+seq), леджерный UniqueConstraint ловит дубль.
- **Миграция** `inventory/0003` — аддитивная, nullable FK (совместимость). ⚠️ деплой.
- **E1-совместимость:** приёмка по заказу при `lots_enabled` создаёт Charge/MHD (реюз
  `receive_lot`); без тумблера — `apply_manual_movement(receipt)`.
- **Не захламлять:** «Einkauf» показываем при активном catalog + (еда/ритейл); Простой
  режим — по `ARCHETYPE_SIMPLE_HIDDEN`-логике.

## 6b. Точки интеграции (разведка 2026-07-16, верифицировано по коду)

- **Хаб-вкладка «Einkauf»:** `HUB_TABS["catalog"]` в `apps/core/templatetags/cabinet.py:53`
  (5-кортеж `url, label, nav_key, module_key, advanced`). E3.2 добавляет кортеж
  `("purchasing", _("Einkauf"), "purchasing", None, False)` (или `advanced=True` для
  не-еды/ритейла). Тег `{% hub_tabs "catalog" %}` + `_hub_tabs.html` — переиспользуем.
- **Генератор кода `BE-XXXXXX`:** зеркалим `orders/services.py:125 _unique_order_code`
  (`secrets.choice(_ALPHABET)`, retry-until-unique). Свой `_unique_po_code()`.
- **Приёмка → счётчик:** ТОЛЬКО через `inventory/services.py`: `receive_lot` (при
  `lots_enabled`) или `apply_manual_movement(kind=receipt)`. Сервисы E3 — в новом
  `apps/inventory/purchasing.py` (модели туда же в `models.py`; app inventory уже TENANT).
- **Модуль/сайдбар:** «Einkauf» под хабом «Sortiment» (catalog core) — гейт видимости
  по еде/ритейлу (`ARCHETYPE_SIMPLE_HIDDEN`-паттерн) в E3.2.

## 7. Что НЕ входит в v1 E3

Мультисклад-приёмка (E2), EDI/API поставщиков (external-backlog), мульти-валютные закупки,
автоматический дозаказ по расписанию (beat), приёмка по штрихкоду поставщика, кредит-ноты/
возвраты поставщику, COGS-снапшот по партии.
