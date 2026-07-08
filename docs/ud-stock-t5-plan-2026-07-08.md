# U-D склад-леджер — срез T5 (миграционный пакет): Bestandswert + Bestellvorschlag

Дата: 2026-07-08. Ветка: `claude/unified-order-kanban-stock-af3pl7`.
Источник: план глубины T1–T5 (владелец выбрал T1+T2+T3 + «retail допиши что нужно»).
**Это ЕДИНСТВЕННЫЙ срез с миграцией каталога → требует деплоя владельцем.**

## 0. Зачем (рыночный контекст ретейла DACH)
Мелкий ретейл (Hofladen, Bioladen, Kiosk, Boutique) ведёт учёт не только «сколько
на полке», но и:
- **Einkaufspreis (закупочная цена)** → **Bestandswert** (стоимость склада, нужна для
  BWA/инвентаризации/страховки) и **Marge** (наценка — видно, что продавать выгодно).
- **Meldebestand + Sollbestand на артикул** → **Bestellvorschlag** (что и сколько
  дозаказать). Сейчас Meldebestand только глобальный (один порог на весь магазин),
  чего для реального ретейла мало.

## 1. Модель (миграция `catalog/0014`, чистый AddField, всё nullable)
На `Product` И `ProductVariant` (варианты держат свой остаток → свои поля):

| Поле | Тип | Семантика |
|------|-----|-----------|
| `cost_price` | `DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)` | Einkaufspreis netto. None = не задано (нет Bestandswert/Marge). Как `base_price`/`price`. |
| `reorder_point` | `IntegerField(null=True, blank=True)` | Meldebestand артикула. None → фолбэк на глобальный `low_stock_threshold`. |
| `reorder_target` | `IntegerField(null=True, blank=True)` | Sollbestand (до какого дозаказывать). None → без предложения количества. |

Свойства модели (в `Product`/`ProductVariant`):
- `stock_value` → `stock_quantity * cost_price` (Decimal) или None (untracked/нет cost).
- `margin_pct` → `(price − cost)/price * 100` (int %) или None. Для товара без
  вариантов — по `base_price`; вариант — по `price_value`.
- `effective_reorder_point(global_threshold)` → `reorder_point` или фолбэк.

## 2. Сервис (`apps/inventory/services.py`)
- `entity_stock_value(entity) -> Decimal|None` — остаток × cost (сущность = product|variant).
- `inventory_value() -> {total: Decimal, rows: [...]}` — суммарный Bestandswert по всем
  учитываемым сущностям + разбивка (переиспользуем `stock_entities()`).
- `reorder_suggestions(global_threshold) -> [{value,label,product,variant,counter,
  point,target,suggest}]` — сущности, где `counter <= effective_reorder_point`;
  `suggest = max(target−counter, 0)` если target задан, иначе None (просто «нужен дозаказ»).
  Сортировка: сначала counter==0 (Ausverkauft), затем по нехватке.

## 3. Кабинет (`apps/inventory/views.py` + `templates/inventory/stock.html`)
- **Bestandswert-плашка** сверху: «Warenwert: X €» (`inventory_value().total`) — только
  если есть хоть один cost. Каждая строка реконсиляции → колонка EK/Wert/Marge (при наличии).
- **Bestellvorschläge**-секция: таблица (Artikel / Bestand / Meldebestand / Vorschlag),
  из `reorder_suggestions(threshold)`. Пусто → скрыта. Ссылка строки → приёмка (prefill entity).
- Форма приёмки/корректировки не меняется (T2 entity picker).

## 4. Каталог (`apps/catalog/views.py` + шаблоны формы товара/варианта)
Добавить 3 поля в форму товара и в форму варианта (EK-Preis, Meldebestand, Sollbestand).
Секция «Lager & Einkauf» на форме товара. Валидация — необязательные, ≥0.
⚠️ Гейтить правки шаблонов: `test_template_comments`, при новых Tailwind-классах — `build:css`.

## 5. Тесты
- `test_stock_valuation.py`: `stock_value`/`margin_pct`/`inventory_value` (товар+вариант,
  untracked/нет cost → None; сумма по нескольким).
- `test_reorder.py`: `reorder_suggestions` — порог per-item перекрывает глобальный;
  target даёт suggest; counter==0 первым; товар без reorder_point с остатком>threshold не в списке.
- Каталог: форма сохраняет 3 новых поля (product + variant).
- Замок формы: рендер формы товара содержит поля EK/Meldebestand/Sollbestand.

## 6. Гейт/деплой
Локально: `ruff check . && ruff format --check .` + `pytest apps/inventory apps/catalog
apps/tenants --reuse-db --create-db` (миграция → `--create-db`). CSS при новых классах.
**Деплой:** `catalog/0014` едет вместе с уже ожидающей `inventory/0001` — один
`./scripts/deploy.sh single`. Миграция аддитивная (nullable) — совместима со старым кодом.

## 7. Границы (в T5 НЕ входит)
- Себестоимость проданного (COGS) в леджере/финансах — отдельный трек (нужен снапшот
  cost на момент продажи; сейчас cost — «текущий», для Bestandswert/Marge этого достаточно).
- Лоты/сроки годности (MHD), поставщики/закупочные заказы (M12) — Stage 3, не сюда.
- Мультивалютный cost — нет (cost в валюте товара).
