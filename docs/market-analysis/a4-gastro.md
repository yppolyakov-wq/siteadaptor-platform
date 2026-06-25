# Архетип A4 «Gastro» — рыночный анализ и бэклог

> Статус: **аналитическая записка** (2026-06-25). Конвенция: docs до кода.
> Source of truth по вертикалям — `micro-business-verticals.md`; по покрытию китов —
> `kit-archetype-coverage.md`; по сделанному — `build-log.md`. Этот документ — срез
> рынка DACH-гастрономии + gap-анализ (визуальный / функциональный / блок-редактор)
> + приоритизированный бэклог. Кодим только после подтверждения порядка.

## 0. Контекст и позиционирование

Платформа — мультитенантный SaaS для микробизнеса DACH (один тенант = один сайт на
субдомене, ~39 €/мес, витрина без аккаунта, без трекинг-куки, Double-Opt-In по
UWG §7, анти-маркетплейс). Северная звезда — **«анти-Bitrix»**: запуск рабочего
сайта за ≤5–10 шагов, нативное лёгкое редактирование страниц, блочная структура
(«сайт может собрать ребёнок»).

Архетип A4 — **Restaurant, Café, Bistro, Imbiss, Eisdiele, Bar, Shisha-Bar,
Foodtruck, Bäckerei-Café**. Технически gastro = симбиоз готовых движков:
`catalog` (меню + варианты + модификаторы + комбо + аллергены LMIV) ⊕ `orders`
(Click&Collect + Lieferung с PLZ-зонами + KDS + QR-Bestellung за столом) ⊕
`booking` (бронь стола time-slot + депозит) ⊕ `events`/`jobs`/`loyalty`.

Демо-киты: **`restaurant`** (Bella Vista, итальянская кухня, 33 позиции) и
**`pranasy`** (Vegan Fastfood, многоуровневое меню, слайдер-герой, нижний таб-бар).

## Current coverage

Движок покрывает почти весь стандарт направления; основной разрыв — не в коде, а в
демо-showcase и в визуальной/UX-полировке витрины. Расхождение в доках
(`micro-business-verticals.md` §A4 пишет ~65 %, `kit-archetype-coverage.md` — ~95 %)
устарело: проверка кода показывает, что перечисленные в §A4 «до полноты» пункты уже
реализованы. **Фактическое покрытие движка ~90 %.**

**Что реализовано (проверено по коду):**

- **Меню = `catalog`.** Категории, товары с фото, описанием, ценой. `_p()` в
  `demo_kits.py` поддерживает `variants` (Pizza klein/groß, Cola 0,33/0,5),
  `allergens`, `modifiers`, `badge`.
- **Варианты + модификаторы/Extras** (`apps/catalog/modifiers.py`): группы с
  `min_select`/`max_select`, надбавки за опцию (Beilage, Garstufe, Toppings,
  Brötchen). Валидация выбора на витрине и при заказе, снимок (label+delta) в заказ.
  Демо: `PIZZA_MODIFIERS`, `VEGAN_BURGER_MODIFIERS`.
- **Комбо-наборы** (`apps/catalog/combos.py` + `templates/storefront/combos.html`,
  `combo_detail.html`): фикс-цена + надбавки опций, валидация по группам.
- **Аллергены/LMIV** (`apps/catalog/food.py`): 14 EU-аллергенов (Anhang II LMIV) с
  немецкими подписями + `origin`/`ingredients` (Herkunft). Рендер в
  `product_detail.html` (Lebensmittel-Kennzeichnung, только при наличии данных).
- **Онлайн-заказ Abholung** (Click&Collect) + **Lieferung** (`apps/orders`): зоны
  по PLZ, Liefergebühr, Mindestbestellwert, бесплатно от суммы (`delivery` в ките,
  с `zones`).
- **Онлайн-оплата заказа** (`apps/orders/payments.py`): Stripe Connect checkout на
  счёт бизнеса (предоплата C&C/доставки).
- **QR-Bestellung за столом / Dine-in** (`OrderItem.table_number` (T2a) +
  `orders/tisch-qr/`): заказ со стола без официанта.
- **KDS / кухонная очередь** (`orders/kitchen/board/` + `kitchen_action`):
  доска статусов на кухне.
- **Бронь стола** (`apps/booking`, time-slot): ресурс `Tisch` capacity=40,
  `counts_party_size`, слоты по часам; **депозит/no-show** (`Booking.deposit_cents`,
  `payment_state`, `apps/booking/payments.py`, Stripe).
- **Часы работы + live-статус** «Jetzt geöffnet/geschlossen» (`_open_badge.html`,
  `tenant.open_status`, структурные `opening_hours`).
- **Акции/промокоды** (`Voucher`), **лояльность** (Stempelkarte 10 штампов →
  Gratis-Pizza/Burger), **события** (Live-Musik, Brunch, Wein-Tasting, Backkurs),
  **кейтеринг-Anfrage** (`jobs`).
- **Многоуровневое меню** (`PRANASY_MENUS`): группы/подменю, sticky-шапка, нижний
  таб-бар (`bottom`) с иконками — мобильный нативный UX.
- **Единая витрина (M20U):** слайдер-герой (`heroes`), карточки категорий/событий,
  единая детальная `detail.html` (товар/событие/номер), per-page раскладки
  (`page_layouts`), мобильный buybar, лайтбокс-галерея.

**Пробелы в демо-showcase (не код, а наполнение):** в `restaurant` не засеяны
комбо-набор и лист QR-столов; в кабинет gastro `seed_records` льёт заказы/события,
но не брони стола; депозит за стол и no-show нигде в демо не показаны.

## Market benchmark

Конвенции и ожидания, выявленные по DACH-инструментам и трендам web-дизайна
ресторанов 2025/2026:

**Резервирование и no-show (resmio, OpenTable/Quandoo, Zenchef).** Стандарт —
онлайн-виджет брони стола с подтверждением по e-mail/SMS и **напоминанием** (резко
снижает no-show). resmio предлагает **Anzahlung / Kreditkartengarantie**:
залог списывается сразу или только при неявке, можно частично/полностью удержать,
конфигурируется по дням недели (только выходные), пауш./на гостя, порог по размеру
группы (от 6 гостей), дедлайн бесплатной отмены
([resmio Anzahlung](https://www.resmio.com/en/planning/deposit/),
[resmio No-Show Guide](https://www.resmio.com/spoon-bytes/no-shows-wie-du-das-problem-bekampfen-kannst/),
[Lightspeed](https://www.lightspeedhq.de/blog/online-reservierungssysteme-gastgewerbe/)).

**Доставка без провизии (Lieferando-Alternativen).** Сильнейший рыночный мотив:
прямой заказ через собственный сайт бережёт маржу. Конкуренты позиционируются
ровно нашей ценой — eCaupo «ab 39 €/Monat», order smart 119–229 €/мес. Обязательно:
управление **Liefergebiet (PLZ-зоны), Mindestbestellwert, Lieferzeit**, провизия 0 %
([jamezz](https://jamezz.com/blog/commission-free-online-ordering),
[order smart](https://ordersmart.de/lieferando-alternative/),
[eCaupo](https://www.ecaupo.com/ecaupo/lieferando_alternative.html)).

**Цифровая Speisekarte + QR-Dine-in (SIDES, resmio, Zenchef, Speisekarte.de).**
Меню — никогда не PDF, а живая, скроллируемая, **искомая** HTML-страница. У каждого
стола свой QR → гость заказывает и платит со смартфона (контактлесс, PayPal),
**отслеживает статус заказа**, может дать чаевые. Меню редактируется в реальном
времени; акции в меню повышают средний чек
([SIDES QR](https://www.get-sides.de/qr-code-bestellung/),
[resmio Table Ordering](https://www.resmio.com/en/ordering/table-ordering-system/),
[SO'USE](https://so-use.de/en/blog/qr-code-bestellsystem-qr-code-bestellungen-sind-mehr-als-eine-digitale-speisekarte)).
Speisekarte.de вмещает >5 млн гостей/мес — ключевые элементы карточки: фото,
отзывы, цены, часы, бронь ([speisekarte.de](https://www.speisekarte.de/)).

**Google-интеграция.** «Mit Google reservieren» и заказ еды прямо из
Unternehmensprofil — ожидаемая точка входа
([Google Business](https://business.google.com/de/business-profile/restaurants/)).

**Визуальные тренды 2025/2026.** Hero — крупный кадр лучшего блюда или зала;
**45 % гостей ищут фото меню онлайн**, фото повышают конверсию меню до +80 %.
Mobile-first: >60 % визитов — со смартфона, крупные tap-кнопки, быстрая загрузка,
визуальное меню с фото и иконками. Интерактив: наведение раскрывает ингредиенты,
тап — парные предложения. Нейтральная палитра под фото, крупная типографика,
full-screen hero, опц. dark-mode для премиум/ночных заведений
([nihstudio](https://nihstudio.com/restaurant-web-design-trends/),
[designhiro checklist](https://designhiro.com/the-2025-restaurant-website-checklist-what-youre-missing-thats-costing-you-customers/),
[richmenu](https://richmenu.io/top-restaurant-website-design/)).

## Visual gaps

| # | Заголовок | Почему (рынок) | Effort | Частично? |
|---|---|---|---|---|
| V1 | **Аппетитный food-hero + контраст под фото** | Hero = лучший кадр блюда/зала; нейтральная палитра под фото, full-screen ([nihstudio]) | S | Да — слайдер `heroes` есть, нет «food-first» пресета (overlay/затемнение/типографика под фуд-фото) |
| V2 | **Поиск/фильтр внутри меню** | Меню — живая, искомая HTML-страница, не PDF; быстрый поиск блюда ([SIDES], [richmenu]) | M | Частично — поиск меню есть в нативном кабинете (M20), на витрине каталога фильтры свёрнуты, но текстового поиска по блюдам нет |
| V3 | **Иконки/бейджи диеты на карточке** (vegan/vegetarisch/scharf/glutenfrei) | Визуальное меню с иконками, гость быстро находит своё ([nihstudio mobile]) | S | Частично — `badge` есть (neu/tagesgericht), но нет реестра диет-иконок и фильтра по ним |
| V4 | **Аллергены как раскрытие/тултип, не стена текста** | Интерактив: тап раскрывает ингредиенты/аллергены ([nihstudio]) | S | Частично — LMIV рендерится, но плоским списком в product_detail |
| V5 | **Mobile order/reserve: липкие крупные CTA «Bestellen»/«Tisch»** | >60 % мобайл, крупные tap-кнопки, заказ «effortless» ([instago], [reallygooddesigns]) | S | Частично — buybar + нижний таб-бар у pranasy; не дефолт для всех gastro-китов |
| V6 | **Видимость комбо и Tagesgericht/Mittagskarte на главной** | Акции в меню → выше средний чек; «блюдо дня» — DACH-конвенция ([SIDES], [SO'USE]) | S | Частично — комбо-движок есть, в showcase не виден; «Tagesgericht» только как badge |
| V7 | **Trust-блок: отзывы + рейтинг рядом с бронью/заказом** | Карточка ресторана = фото+отзывы+часы+бронь ([speisekarte.de]) | S | Частично — testimonials есть, рейтинг-звёзды и привязка к бронь-CTA нет |

## Technical gaps

| # | Заголовок | Почему (рынок) | Effort | Частично? |
|---|---|---|---|---|
| T1 | **Депозит/Kreditkartengarantie за стол с гибкими правилами** | resmio: залог сразу/при неявке, % или на гостя, только выходные, порог группы ([resmio Anzahlung]) | M | Частично — `Booking.deposit_cents`+Stripe есть, нет правил «по дням/размеру группы/частичного удержания» и no-show-fee flow |
| T2 | **Напоминание о брони (e-mail/SMS) + one-click отмена** | Reminder резко снижает no-show ([resmio reminder]) | S | Частично — письма брони есть; авто-reminder и публичная самоотмена под gastro-бронь не подтверждены |
| T3 | **Lieferzeit / время доставки и слоты** | Управление Lieferzeit — базовая функция Lieferando-альтернатив ([order smart]) | M | Нет — есть зоны/сбор/мин-сумма, нет оценки/выбора времени доставки и pickup-слотов |
| T4 | **Онлайн-оплата для QR-Dine-in (со стола) + чаевые** | Контактлесс-оплата за столом + Trinkgeld — ядро QR-систем ([resmio Table Ordering], [SIDES]) | M | Частично — оплата заказа через Stripe Connect есть для C&C; для table_number-сессии оплата/чаевые не показаны |
| T5 | **Live-статус заказа для гостя** | Гость отслеживает статус на смартфоне, знает когда готово ([SO'USE], [qrcode-tiger]) | M | Частично — KDS-статусы есть на кухне; публичная страница статуса заказа гостю не подтверждена |
| T6 | **Бронь стола как первоклассный виджет (party_size, дата+время, Anlass)** | Онлайн-виджет брони — стандарт (resmio/OpenTable/Quandoo) | S | Частично — booking time-slot работает, но gastro-копия/UX («Für wie viele Personen?», повод) не выделены; в `booking_index.html` нет party_size-поля |
| T7 | **JSON-LD Restaurant/Menu/OpeningHours + «Mit Google reservieren»/Order** | Точка входа из Google-профиля ([Google Business]) | M | Частично — open_status структурный; schema.org Menu/Restaurant и Google Reserve/Order не подтверждены |
| T8 | **Демо-наполнение showcase** (1 комбо + QR-стол-лист + брони стола + депозит в кабинет) | Готовые фичи невидимы в демо → не продают ([kit-archetype-coverage.md] §A4) | S | Нет — `seed_records` не льёт это для gastro |

## Anti-Bitrix block editor

Цель — собрать рабочий gastro-сайт за ≤10 шагов из переиспользуемых блоков с
live-preview, inline-правкой текста и панелью свойств секции (M20). Все блоки —
поверх JSON, без новых моделей, archetype-aware дефолты.

**Переиспользуемые блоки (секции) для gastro:**

1. **Speisekarte-блок** (меню): источник = категория/подкатегория; раскладки
   cols2/cols3/список; пер-секционный заголовок и «View all». Поверх существующего
   layout-движка секций M20U. Опции: показывать фото/аллерген-иконки/цены.
2. **Öffnungszeiten-блок**: структурные часы + live-бейдж «Jetzt geöffnet» (уже
   есть `_open_badge` + `open_status`) — вынести как самостоятельный блок.
3. **Tisch reservieren CTA-блок**: кнопка/мини-форма (party_size + дата) →
   `/termin/`; опц. бейдж «Sofortbestätigung».
4. **Lieferinfo-блок**: PLZ-зоны, Mindestbestellwert, Liefergebühr, Lieferzeit,
   «Wir liefern im Umkreis …» (данные из `delivery` кита) — авто-рендер.
5. **Galerie/Food-блок**: лайтбокс-галерея (есть `_media_gallery`) с food-пресетом
   (квадраты/сетка, акцент на фото).
6. **Kombo/Angebot-блок**: карточки комбо-наборов и акций (повышают средний чек).
7. **Tagesgericht/Mittagskarte-блок**: подборка «блюдо дня/обеденная карта»
   (фильтр по badge или ручной список).

**Smart defaults (archetype = restaurant):** главная по умолчанию = food-hero →
Speisekarte → Kombo/Angebot → Öffnungszeiten + Tisch-CTA → Galerie → Trust(отзывы).
`primary_item` = блюдо, `purchase_mode` = «In den Warenkorb», `purchase_label` =
«Bestellen». Нижний таб-бар (Menü/Korb/Tisch/Events) включён по умолчанию (как у
pranasy). Акцент-цвет тёплый (как `#b45309`), нейтральный фон под фото.

**Онбординг ≤10 шагов до рабочего gastro-сайта:**
1) тип «Gastro» → 2) название + логотип + акцент → 3) адрес + часы (→ live-бейдж)
→ 4) загрузить/выбрать hero-фото → 5) добавить 3–5 блюд (фото+цена+аллергены) или
импорт CSV → 6) включить Abholung (вкл/выкл) → 7) включить Lieferung + PLZ-зоны +
Mindestbestellwert (опц.) → 8) включить Tischreservierung (часы + вместимость, опц.
депозит) → 9) право (Impressum/Datenschutz автозаполнение) → 10) Veröffentlichen.
Заказ/бронь без аккаунта; Double-Opt-In для рассылок — отдельно, по UWG §7.

## Prioritized backlog table

| Приоритет | Код | Задача | Тип | Effort | Леверидж |
|---|---|---|---|---|---|
| 1 | A4-D1 | Демо-showcase: 1 комбо + лист QR-столов + брони стола + депозит в кабинет (restaurant/pranasy) | Демо | S | Делает готовые фичи видимыми/продающими |
| 2 | A4-V1 | Food-hero пресет (overlay/типографика под фуд-фото) + тёплый дефолт темы | Визуал | S | Первое впечатление, +конверсия меню |
| 3 | A4-V6 | Kombo/Angebot + Tagesgericht/Mittagskarte блоки на главной | Визуал/блок | S | +средний чек, DACH-конвенция |
| 4 | A4-T1 | Гибкий депозит/no-show за стол (правила: дни/группа/частичное удержание) | Функц. | M | Прямой аналог resmio, сильный мотив |
| 5 | A4-T6 | Бронь стола как gastro-виджет (party_size, повод, копия) | Функц./UX | S | Стандарт направления |
| 6 | A4-T2 | Авто-reminder брони + публичная самоотмена | Функц. | S | Снижает no-show, low-effort |
| 7 | A4-V3+V4 | Диет-иконки/фильтр (vegan/veg/scharf/glutenfrei) + аллергены как раскрытие | Визуал | S | Mobile-меню UX |
| 8 | A4-V2 | Поиск по меню на витрине каталога | Визуал | M | «Меню = искомая страница» |
| 9 | A4-T3 | Lieferzeit / слоты доставки и pickup | Функц. | M | Завершает Lieferando-альтернативу |
| 10 | A4-T4 | Оплата + Trinkgeld для QR-Dine-in (table session) | Функц. | M | Ядро QR-систем |
| 11 | A4-T5 | Публичная страница live-статуса заказа гостю | Функц. | M | Ожидание QR/доставки |
| 12 | A4-T7 | JSON-LD Restaurant/Menu/OpeningHours + Google Reserve/Order | SEO/интеграция | M | Точка входа из Google |
| 13 | A4-ABE | Gastro-блоки в M20 (Speisekarte/Öffnungszeiten/Tisch-CTA/Lieferinfo) + ≤10-step онбординг | Блок-редактор | M | «Анти-Bitrix», самообслуживание |

**Примечание по докам:** §A4 в `micro-business-verticals.md` (~65 %) устарел —
модификаторы, доставка-зоны, KDS, аллергены, депозит уже в коде. Привести в
соответствие с `kit-archetype-coverage.md` (фактически ~90 % движка; разрыв —
демо + визуал/UX + полировка брони/доставки).
