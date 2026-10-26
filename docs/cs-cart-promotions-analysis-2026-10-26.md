# CS-Cart «Promotions» vs наш движок акций — рыночный разбор (2026-10-26)

Зачем: понять, что из конструктора акций CS-Cart стоит взять в WR-9 и дальше, не превращая
форму акции в «Битрикс». Кода нет — только анализ и предложение инкрементов.

## 1. Как это устроено в CS-Cart

**Экран.** Marketing → Promotions → «+ Add promotion» → выбор **Add catalog promotion** или
**Add cart promotion**. У промо три вкладки: **General · Conditions · Bonuses** (в Multi-Vendor
ещё Storefronts/Vendors).

**General:** Name, Detailed/Short description, Image, «Use available period» (Available
from/till), **Priority** (0 — высший; при равном приоритете порядок — как вернула БД),
**Stop other rules** (после применения этой акции акции с меньшим приоритетом к заказу не
применяются), Status (Active/Hidden/Disabled).

**Два вида акций:**
- *Catalog promotion* — скидка на товары/категории, **видна в каталоге** (цена на карточке и
  странице товара). Условий мало: товары, категории, группа покупателей, (MV) продавцы.
- *Cart promotion* — скидки и бонусы, видны **только в корзине и на чекауте**; условий больше.
  В Free-режиме недоступна.

**Конструктор условий.** «Add condition» → тип из списка; над списком фраза
«If **all/any** of these conditions are **true/false**» — так задаётся И/ИЛИ и инверсия.
В интерфейсе админки есть и вложенные группы условий (группа со своим all/any); в
пользовательском руководстве они отдельно не описаны — помечаем как «по UI, не по докам».

Условия, подтверждённые руководством:
| Условие | Оператор / пример |
|---|---|
| Products | in — «два конкретных товара вместе» = два условия Products под «all» |
| Categories | in / not in |
| User group | equal / not equal |
| Order subtotal | equal or greater 90 (сумма товаров в корзине) |
| Total products in the cart | greater 5 / equal or less |
| Coupon code | equal (один код) / in (список через запятую) |
| Automatically generated coupon codes | коды, выданные бонусом «Give coupon» |
| Once per customer | совпадение 5 из 7 полей покупателя ИЛИ e-mail по заказам, списавшим склад |

Бонусы, подтверждённые руководством:
| Бонус | Параметры |
|---|---|
| Product discount (каталог) / Discount on products (корзина) | 4 режима: **by %**, **to %**, **by fixed**, **to fixed** |
| Order discount | те же 4 режима, доставку не меняет |
| Free products | выбор товаров-подарков, добавляются в корзину |
| Free shipping | выбор способа доставки |
| Give coupon | ссылка на другую промо-акцию; код выдаётся письмом после статуса Complete, на этот же заказ не действует |
| Gift certificate / reward points / give usergroup | выдача сертификата, баллов, членства в группе |

Типовые рецепты из документации: скидка на категорию, «N товаров в корзине → −X %»,
«сумма ≥ X → скидка/подарок», «два товара вместе», «бесплатная доставка за товар»,
«сертификат члену группы при сумме ≥ X», «скидка группе покупателей», авто-купоны.

**Вывод о UX.** Мощно, но это «язык правил»: владелец сам собирает И/ИЛИ-дерево, думает о
приоритетах и «стоп-правилах», а витрина при cart-акции цену заранее не показывает. Для
маленького бизнеса DACH это прямо противоречит нашему принципу «просто и без перегруза».

## 2. Что уже есть у нас

| Механика | Где |
|---|---|
| Цель акции: товар / услуга / номер / набор (FK) или свободная акция | `Promotion.product/service/stay_unit/combo` |
| Скидка: `discount_percent` (≈ by %), `price_override` (≈ to fixed), `compare_at_price` | `Promotion` |
| Срок `starts_at/ends_at`, `recurrence`, статус FSM, лимит кампании `available_quantity` (атомарный conditional UPDATE), `max_per_customer` | `models.py`, `price_layer.claim_units` |
| Окно действия: дни недели, часы (через полночь), мастер/ресурс; fail-closed | `target_rules` + `price_layer.rules_match` |
| Единый ценовой слой «показано = списано»: карточка, деталь, корзина, чекаут, фид | `price_layer.promo_line_price/attach_promos/product_promo_map`, `create_order` |
| Конфликт акций на один товар: **лучшая цена клиенту** (минимальная `new_price`), без суммирования (как G4/Lücken у номеров) | `promo_for_product` |
| §11 PAngV: снижение объявляется только от цены сравнения 30 дней (SF-7); mystery не раскрывает цену | `reference_price`, `has_discount`, SF-9 |
| Условие цены «2. Stück −50 %», «n für m», «ab n Stück −p %» — **только подпись**, цена штуки обычная, корзина не дешевеет | `metadata["price_condition"]`, `core/price_conditions.py` |
| Купоны/ваучеры: код, −% или −€, `min_order_cents`, срок, `max_uses`, привязка к клиенту/кампании/акции | `loyalty.Voucher` |
| Купон-кампании по сегментам CRM (тег, неактивные N дней, топ-LTV, день рождения, авто-win-back) поверх UWG-согласия | `CouponCampaign` |
| «Coupon holen» с акции (1 на человека, лимит штук) | T-8.3, `Voucher.promotion` |
| Подарочные сертификаты с балансом, штамп-карты лояльности | `GiftVoucher`, `LoyaltyProgram` |
| Бесплатная доставка от суммы (глобально на бизнес) | `Tenant.delivery_free_cents` |
| Наборы со своей ценой (замена «купи вместе») | `catalog.Combo` |
| В плане: скидка на категорию / весь магазин (WR-9, ⚠️ миграция) | `docs/ka-12-w4-waren-plan-2026-10-26.md` |

## 3. Таблица пробелов

Ценность — для DACH-микробизнеса (пекарня, мясная, бутик, салон); трудоёмкость — S/M/L.

| Механика | CS-Cart | Мы | Ценность | Трудоёмкость |
|---|---|---|---|---|
| Скидка на категорию / весь магазин (каталог) | Catalog promotion + Categories | нет (WR-9 в плане) | **высокая** («−20 % auf alle Sommerkleider», Sale-неделя) | M, миграция |
| Режимы скидки by %/to %/by €/to € | 4 режима | by % и to € (price_override) | средняя: «−2 € auf jedes Brot» — частый случай | S |
| Количественные скидки в корзине (nth, n für m, ab n Stück) | Total products in cart → Discount on products | **только подпись**, деньги не применяются | **высокая** (Bäckerei «3 Brötchen für 1 €», Mengenrabatt Metzgerei) — сейчас обещание без исполнения в корзине | M |
| Скидка на заказ от суммы | Order subtotal → Order discount | только через купон с `min_order_cents` | средняя | S–M |
| Подарок к заказу / к товару | Free products | нет | средняя («Gratis Kaffee ab 15 €») | M (строка 0 € + склад) |
| Бесплатная доставка | Free shipping по товару/условию | глобальный порог | низкая–средняя (порог покрывает 80 %) | S (порог на акции) |
| Купон как условие обычной акции | Coupon code | купон — отдельная сущность со своей скидкой | низкая: уже есть Voucher | — |
| «Первый заказ» / «1 раз на клиента» | Once per customer | `max_per_customer` у резервов, «1 купон на человека» | средняя («−10 % auf die erste Bestellung») | S–M |
| Группа покупателей | User group | теги CRM — только для кампаний | средняя (Stammkunden-Preis) но требует входа покупателя | M–L |
| Дни/часы действия | нет из коробки | **есть** (target_rules) | — (наше преимущество: Happy Hour, Mittagstisch) | — |
| Приоритеты + «Stop other rules» | есть | неявно: лучшая цена, без суммирования | низкая: явные приоритеты путают владельца | — (не брать) |
| Произвольное И/ИЛИ-дерево условий | есть | нет | **низкая/вредная** для нашей аудитории | L (не брать) |
| Выдать купон/группу/баллы как бонус | Give coupon / usergroup / points | купон-кампании, штамп-карты | низкая (покрыто проще) | — |
| Зоны / мультивитрина | Storefronts, Vendors | не нужно (тенант = бизнес) | нет | — |
| Показ cart-акций в каталоге | нет (только в корзине) | всё видно на карточке + §11 | — (наше преимущество) | — |

## 4. Рекомендуемые инкременты (по ценности/трудоёмкости)

Принцип: **не конструктор, а «рецепты»**. Владелец выбирает готовый тип выгоды и заполняет
2–3 поля; дерево условий, приоритеты и «stop rules» не показываем. Все расчёты — только в
`price_layer` / `create_order` («показано = списано»), §11 PAngV и UWG-формулировки — как сейчас.
Хранение — в `Promotion` (поля или `metadata`), без новой сущности «правило».

1. **PR-1 = WR-9 «Wofür gilt die Aktion?»** — радио «Ein Produkt · Eine Kategorie · Ganzer
   Shop · Leistung · Zimmer · Set». FK `category` + флаг `whole_shop`; резолв в
   `product_promo_map` (товар → своя акция → акция категории/родителя → магазин; правило
   конфликта прежнее — лучшая цена клиенту, без суммирования). §11 по вариантам со своей
   ценой. *M, миграция.* Наибольшая ценность.
2. **PR-2 «Art der Ersparnis»** — четыре режима CS-Cart, но словами: «−X %», «−X € pro Stück»,
   «Festpreis X €» (есть), «X % vom Preis» не берём (путает). Добавить «−X €» (`metadata` или
   поле). *S.* Нужен для PR-1: «−1 € auf alle Brote».
3. **PR-3 «Mengenaktion wirklich anwenden»** — превратить `price_condition` из подписи в
   расчёт корзины: nth / n für m / ab n Stück считаются в `totals`/`create_order` отдельной
   строкой «Aktion: 3 für 2 −2,50 €» (снимок в заказе, возврат лимита как сейчас). Цена штуки
   на витрине остаётся обычной (UWG/PAngV — уже так), бейдж уже есть. *M.* Закрывает
   «обещание без исполнения».
4. **PR-4 «Ab Bestellwert»** — минимальная сумма корзины у акции на магазин/категорию
   («−10 % ab 30 €») и бонус «Gratis-Artikel» (строка 0 € с позицией склада, выбор из
   ассортимента). Показ в корзине «Noch 4,20 € bis zum Geschenk». *M.*
5. **PR-5 «Nur für neue Kunden / einmal pro Kunde»** — флажок у онлайн-акции: проверка по
   e-mail/телефону в `create_order` (как «1 купон на человека», без 5-из-7 полей CS-Cart). *S–M.*
6. **PR-6 (по спросу)** — порог бесплатной доставки как бонус акции (на время Sale-недели);
   группы покупателей — только после личного кабинета покупателя, через теги CRM.

Не берём: произвольные И/ИЛИ-группы, приоритеты и «Stop other rules» (заменены правилом
«лучшая цена, не суммируем»), give usergroup/reward points, зоны.

Форма: один экран «Neue Aktion» с тремя вопросами — **Was?** (цель, PR-1) · **Wie viel?**
(вид выгоды, PR-2/PR-3) · **Wann/Für wen?** (срок, окно дней/часов, «ab Bestellwert»,
«nur Neukunden» — свёрнуто). Каждый ответ сразу показывает фразу-превью для клиента
(«Alle Brote −1 € · Mo–Fr bis 12 Uhr»), как подпись `rules_text`.

## Источники
- CS-Cart, How To: Set Up a Promotion — https://docs.cs-cart.com/latest/user_guide/manage_products/promotions/setting_promotion.html
- CS-Cart, Promotions (catalog vs cart) — https://docs.cs-cart.com/4.15.x/user_guide/manage_products/promotions/index.html ; список рецептов — https://docs.cs-cart.com/4.6.x/user_guide/manage_products/promotions/index.html
- Give Discounts to Specific User Groups (4 режима скидки) — https://docs.cs-cart.com/latest/user_guide/manage_products/promotions/user_group_discounts.html
- Create Bonus Coupon (Coupon code equal/in) — https://docs.cs-cart.com/4.6.x/user_guide/manage_products/promotions/creating_coupon.html
- Generate Bonus Coupon Codes Automatically (Give coupon, Once per customer) — https://docs.cs-cart.com/4.6.x/user_guide/manage_products/promotions/auto_coupons.html
- Discount When Cart Has Specific Number of Products — https://docs.cs-cart.com/4.6.x/user_guide/manage_products/promotions/discount_if_number_of_products_exceeds_value.html
- Discount for Buying Two Specific Products Together — https://docs.cs-cart.com/4.6.x/user_guide/manage_products/promotions/discount_two_products.html
- Free Product if Subtotal Exceeds Value — https://docs.cs-cart.com/4.7.x/user_guide/manage_products/promotions/free_product.html
- Free Shipping for a Certain Product — https://docs.cs-cart.com/4.6.x/user_guide/manage_products/promotions/free_shipping.html
- Discount on Products from Specific Categories — https://docs.cs-cart.com/4.6.x/user_guide/manage_products/promotions/category_discount.html
- Сторонние модули с количественными условиями (подтверждение, что в ядре их мало): https://cs-cart.pl/moduly/narzedzia/discount-groups-of-products-basing-on-categories-and-features/ , https://store.ecarter.co/extended-promotion-conditions-for-cs-cart

Оговорка: полный список типов условий/бонусов CS-Cart в руководстве не собран в одном месте;
таблица §1 составлена по страницам-рецептам. «Вложенные группы условий» и «Number of usages»
в руководстве не подтверждены — при необходимости проверить на демо-админке CS-Cart.
