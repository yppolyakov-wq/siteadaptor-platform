# AIS W4-6b — «Preis auf Anfrage» (2026-11-06)

Решение владельца (W4-6, «делай W4-6b с ЕСС по рекомендации»). Источник — находка стенда W4-6:
у Handwerker шаг «Angebot» пуст, потому что витрина печатает цену везде. Разведка (planner)
показала, что дефект уже ЖИВОЙ: импорт с сайта (`imports/site/apply.py`, `imports/cscart.py`)
создаёт `Product(primary_action="request", base_price=0)`, и такие позиции печатают «0,00 €»;
плюс быстрый «+» на карточке и `cart_add` не смотрят на `primary_action` — товар «nur auf
Anfrage» (MX-5) можно положить в корзину.

## Решение по модели — свойство, без миграции

`Product.price_on_request` = `primary_action == "request"` И нет положительной цены (база ≤ 0 и
ни одного активного варианта с ценой > 0). Nullable `base_price` отвергнут: ~180 мест арифметики.
Обычный товар за 0 € остаётся «0,00 €» (выбор владельца) — замок.

## Батчи

1. **Модель и машинные выходы.** Свойство; `sellable._product` → «Preis auf Anfrage»,
   `price_value=None` (JSON-LD без Offer, Finder, «Sortiment» кабинета, list-блоки). Замки:
   свойство, JSON-LD, фиды Merchant/local/legacy исключают, город — не листит (v1).
2. **Витрина.** Все формы карточки, прайс-лист, hero-товар категории, деталь + мобильный buybar,
   `_buybox` без jobs → ссылка «Kontakt»; Grundpreis не печатается; «+» скрыт у request.
3. **Корзина/фасеты/акции** (security). `cart_add`, `quick_add_form`, `create_order` отказывают
   request-товару (вкл. MX-5 с ценой); фасет цены исключает, сорт по цене — в конец; слой акций
   пропускает; пул свободной сборки исключает; PDF-меню — «auf Anfrage».
4. **Мастер.** `ENTITY_FOR["anfragen"]="product"`, создание `primary_action="request"`, подписи/
   подсказка, цена необязательна; стенд W4-6 — сценарий Handwerker с позициями.

Позже (roadmap): W4-6c — город с `new_price=None` и «Auf Bestellung»; колонка `primary_action` в
CSV; подсказка «übersprungen» в массовой цене помощника.

## ECC-прогоны

Скиллы: django-patterns, django-tdd, django-security, accessibility, e2e-testing. Агенты:
`django-reviewer` после батча 2 и перед мержем; `security-reviewer` + `silent-failure-hunter` на
батче 3; `a11y-architect` на подписи и фолбэк-CTA; Playwright-стенд 390/1440.
