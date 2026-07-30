# M4 Boutique: lookbook, wishlist, цвет×размер, порог доставки (2026-07-30)

Волна M4 плана `mode-boutique-plan-2026-07-30.md §3`. Разведка (агент, 73 tool-uses)
дала карту точек и рисков; порядок исполнения — по возрастанию риска: **D → B → C → A**.

## D. «Noch X € bis kostenlosem Versand» (S, 0 миграций) — ПЕРВЫЙ
`delivery_quote` (orders/services.py:89-118) уже знает `free_cents`; корзина уже
несёт `data-grand-cents/-free-cents` и JS `apply()`. Нужно: `delivery_free_gap_cents`
в контекст корзины + строка с прогресс-баром над `#order-summary` + 3 строки в JS.
Гейты: только при `delivery_enabled` И выбранной доставке (при самовывозе строка
вводит в заблуждение); при PLZ-зонах порог может отличаться → оговорка
«(Standardversand)». Замки delivery не трогаются.

## B. Lookbook (S→M, 2 миграции) — ВТОРОЙ
`Collection` есть (booking/stays M2M), у `Product` связи нет, галереи у коллекции нет.
- `catalog`: `Product.collections` M2M (join-таблица).
- `collections`: `Collection.images` (FileRef-конверт как Product.images) — фото образа.
- Кабинет: снять 404-гейт (сейчас только booking/stays), ветка products.
- Листинг: `kollektion` в CatalogFacets + чипы СТРОГО между h1 и фасет-формой
  (замок test_listing_parity пинит порядок блоков).
- Публичная страница образа `/lookbook/<slug>/` (галерея + грид товаров).
- Риск: `core/finder.py` начнёт матчить Product по коллекции — проверить выдачу.

## C. Wishlist/Merkzettel (S/M, 0 миграций в v1) — ТРЕТИЙ
В tenant-схеме нет ничего (FavoriteListing — портал агрегатора, другая схема).
v1 — сессия по образцу корзины (`WISH_SESSION_KEY`), 0 миграций, без аккаунта,
DSGVO-чисто; v2 (по спросу) — персист на `promotions.Customer` + merge при
magic-link входе. Точки: сердечко во ВСЕХ ТРЁХ раскладках `_product_card.html`
(compact/overlay/default — конфликт позиционирования с контролами канвы),
деталь, счётчик в шапке, страница `/merkzettel/`, тумблер в siteconfig
(не показывать у гастро/услуг).

## A. Цвет × размер + фото варианта (M, 1 миграция) — ЧЕТВЁРТЫЙ
Решение: **вариант (1)+(3)** — поля `size`/`color` + `images` на ProductVariant,
`label` ОСТАЁТСЯ денормализованным ключом («S · Blau») → склад/заказы/PDF/фид/
импорт не трогаются (они уже работают по FK).
Обязательно вместе с полями: фасет Größe переключить на `variants__size`
(иначе чипы станут декартовым произведением «M · Blau»); в форме корзины
остаётся ОДИН `select name="variant"` (замок test_buybox_parity пинит набор
полей) — оси через data-атрибуты + JS-фильтрация; импорт CSV матчит по
(product,size,color) c фолбэком на label; генерация label в `save()`.
Фото варианта v1 — подмена главного фото при выборе (галерея товара цела).

Каждый инкремент: локальные гейты + адверсариальное ревью-workflow, стенд, CI, merge.
