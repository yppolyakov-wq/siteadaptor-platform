# KA-12 PR-1 (= WR-9, E3.5) · Aktion auf Kategorie / ganzen Shop (2026-10-26)

Из разбора CS-Cart (`cs-cart-promotions-analysis-2026-10-26.md` §4 п.1): «−20 % auf alle
Brote», «Sale −10 % auf alles» — сегодня акция живёт только на ОДНОМ товаре.

## Решение
- `Promotion.category` (FK catalog.Category, SET_NULL) + `Promotion.whole_shop` — ⚠️
  `promotions/0032`, аддитивная. `scope_kind` = «category»/«shop»/''.
- Область — **только процент**: «новая/старая цена», условие цены и mystery — свойства
  одного товара (форма отклоняет, резолвер отфильтровывает).
- Резолвер — единственный (`price_layer.product_promo_map`; `promo_for_product` делегирует
  ему): своя акция товара · акция категории товара или её предков · весь магазин; правило
  прежнее — лучшая цена клиенту, без суммирования. Акции области — тем же запросом (число
  запросов фида/каталога прежнее, замок `test_promo_feed_constant_queries`).
- Цена считается свойствами модели от ЭТОГО товара: резолвер подставляет виртуальную копию
  акции (`scope_copy`: свой `_state` и кэш связей, `save()` запрещён). Поэтому §11 PAngV,
  бейдж, «Sie sparen», Merchant-фид, корзина, `create_order` (снимок, лимит, маркер возврата)
  работают без правок.
- Вариант со своей ценой — без скидки (прежнее правило `promo_line_price`).
- Страница акции: отклик «Nur zeigen» (или Coupon/Anfrage по выбору), карточка «Gilt für» →
  страница категории / весь каталог.

## Не делаем (v1)
«−X €» на всю область (PR-2), «ab Bestellwert» (PR-4), исключения товаров из области.

## ECC-прогоны
Скиллы: database-migrations, django-patterns, django-tdd. Агенты после кода: django-reviewer,
database-reviewer (запрос/цепочка категорий), security-reviewer + silent-failure-hunter (деньги).

## Ревью (django-reviewer, 2026-10-26) — исправлено
- POST `/p/<uuid>/kaufen/` и резерв принимали акцию области (цена None → 500 в create_order):
  гард во вьюхах и в сервисах `purchase()`/`reserve()` (будущие каналы — бот/MCP).
- §11 PAngV: прошлая акция категории/магазина входит в 30-дневный минимум товара (тем же
  запросом, что прошлые акции товара — число запросов прежнее).
- Виртуальная копия помнит область (`scope_kind` = область оригинала, `target_kind` = product).
