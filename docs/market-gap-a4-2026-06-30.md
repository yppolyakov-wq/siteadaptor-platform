# A4 Gastro (Restaurant/Café/Bäckerei/Imbiss) — рынок ↔ функционал — 2026-06-30

> **Шаг 3** серии (индекс: `docs/market-gap-audit-2026-06-30-index.md`).
> Метод: воркфлоу 16 агентов → синтез → **адверсариальная проверка 12 гэпов**
> (6 CONFIRMED_MISSING, 6 PARTIAL, 0 ложных). Бенчмарк: Lieferando, Wolt, Uber Eats,
> OpenTable, Quandoo, TheFork, resmio, SevenRooms, orderbird, Gastronovi, Lightspeed.
> Киты: `restaurant`, `pranasy`. Снапшот 2026-06-25 — `market-analysis/a4-gastro.md`.

## 0. Вывод одной фразой

Движок Gastro ~**90 %** для ниши «свой канал SMB DACH». **Ближе всего к resmio**
(почти паритет), конкурентен против Lieferando/OpenTable на питче «свой сайт, 0 %
комиссии», **сознательно уже** orderbird по фискальному POS (нет TSE/KassenSichV —
правильный прагматичный срез). Самые ценные закрытия: платёжный микс (PayPal/cash
selector), слоты предзаказа, QR pay-at-table + чаевые, Mittagstisch-расписание.

## 1. Структура сайта (карта страниц)

| Страница | Статус | Заметка |
|---|:--:|---|
| Главная (food-hero, меню/категории/комбо/события/часы/отзывы) | ✅ | live open/closed badge; нет отдельного «food-first» hero-пресета |
| Speisekarte/меню | ✅ | категории+подкатегории+диет-фасет+комбо-тизер; **нет поиска по меню** |
| Деталь блюда | ✅ | фото/цена/Grundpreis, LMIV-аллергены+Herkunft+Zutaten, модификаторы, отзывы |
| Combo/Menü-конфигуратор | ✅ | `/kombi/` выбор напитка/гарнира, фикс-цена + доплаты |
| Корзина/онлайн-заказ (Abholung+Lieferung) | ✅ | зоны/мин/сбор/free-from/промокод/апселл; **нет выбора способа оплаты, нет слота времени** |
| **Бронь стола** | 🟡 | generic `/termin/` (party_size+депозит), не gastro-виджет; нет Anlass/гибкого депозита |
| **QR dine-in заказ за столом** | 🟡 | `?tisch=N` → заказ к столу; **нет pay-at-table и чаевых**, нет live-статуса гостю |
| Подтверждение заказа | ✅ | статичное (без live-статуса) |
| Подтверждение брони | ✅ | `/t/<code>/` |
| ЛК клиента | ✅ | magic-link, заказы/брони, GDPR |
| Gastro-события/билеты | ✅ | Live-Musik/Brunch/Tasting, capacity, тиры, QR, iCal, waitlist |
| Catering-Anfrage + Angebot | ✅ | generic jobs-движок (не gastro-копия/форма) |
| Geschenkgutschein | ✅ | через stays-движок (не gastro-tailored) |
| Лояльность/Newsletter(DOI)/Правовое | ✅ | AGB нет (сквозной гэп) |

## 2. Что уже есть (паритет/выше рынка)

Цифровое меню с категориями/фото/ценами + **Grundpreis** · **14 LMIV-аллергенов** +
Herkunft/Zutaten · модификаторы/Extras · **Combos/Menüs** · онлайн-заказ Abholung +
**Lieferung с PLZ-зонами**/Mindestbestellwert/сбор/free-from · бронь стола (party_size
+ Stripe-депозит) · **QR dine-in заказ** + печать QR-листа столов · **KDS** (кухонный
дисплей) · live open/closed статус · gastro-события (билеты) · Geschenkgutschein ·
лояльность · multi-language меню (i18n) · Newsletter DOI · отзывы о блюде (верифиц.).

## 3. Матрица «рынок ↔ наш статус»

| Фича рынка | Важн. | Статус | Заметка |
|---|:--:|:--:|---|
| Цифровое меню (категории/фото/цены) | must | ✅ | + Grundpreis |
| **LMIV-аллергены (14) + Herkunft/Zutaten** | must | ✅ | плоский список (не tooltip) |
| **Zusatzstoffe/E-номера (footnotes)** | must | ❌ | **юр. пробел** — Kennzeichnungspflicht, поля нет |
| Модификаторы/Extras/Combos | must | ✅ | |
| Онлайн-заказ Abholung+Lieferung | must | ✅ | зоны/мин/сбор/free-from |
| **Слот предзаказа (Vorbestellung) + ETA** | should | ❌ | `pickup_slot` есть в модели, но checkout его не ставит |
| **Выбор способа оплаты (PayPal/Karte/Bar)** | must | ❌ | оплата задана конфигом, не гостем; PayPal нет |
| Бронь стола (party_size/время/депозит) | must | 🟡 | generic-виджет; без Anlass/гибкого депозита |
| **No-show fee (захват депозита)** | should | ❌ | статус no_show есть, но депозит не списывается |
| **QR dine-in заказ** | should | ✅ | + печать QR-столов |
| **QR pay-at-table + Trinkgeld** | should | ❌ | заказ есть, оплаты за столом и чаевых нет |
| KDS (кухонный дисплей) | should | ✅ | staff-only |
| **Live-статус заказа гостю** | should | 🟡 | FSM+KDS+push есть; нет публичной live-страницы |
| Mittagstisch/Tageskarte (расписание) | should | ❌ | только статичный badge «tagesgericht» |
| Geschenkgutschein | should | ✅ | через stays-движок |
| Лояльность/Stempelkarte | should | ✅ | |
| **Reminder брони + post-visit отзыв-реквест** | should | 🟡 | ready/shipped push есть; reminder заказа и review-request нет |
| **SMS/WhatsApp** | should | ❌ | WhatsApp — заглушка-enum без sender; SMS нет |
| Часы + live open/closed | must | ✅ | |
| **JSON-LD Restaurant (openingHours/hasMenu/acceptsReservations)** | should | ❌ | только base Restaurant; нет расширений + Reserve-with-Google |
| **Поиск по меню** | should | ❌ | только категория+диета (поиск есть в кабинете) |
| Catering-Anfrage | should | 🟡 | generic jobs, нет структурной формы (гости/дата/диета/меню) |
| Multi-language меню | nice | ✅ | i18n JSONField |
| Nährwerte/kcal | nice | ❌ | поля нет |
| Отзывы о блюде | should | ✅ | верифиц. покупатель |

## 4. Недостающий функционал — приоритизировано (верифицировано)

### 4a. Заказ / оплата (конверсия + право)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| O1 | **Выбор способа оплаты**: PayPal + Karte + Bar(+Apple/Google Pay); поле `Order.payment_method` (общий гэп с A1/A2) | CONFIRMED_MISSING | **L** |
| O2 | **Слот предзаказа** (Vorbestellung) + ASAP-тоггл + prep-time/ETA (`pickup_slot` уже в модели → дотянуть checkout+UI) | CONFIRMED_MISSING | M |
| O3 | **Zusatzstoffe/E-номера** footnotes per dish (DE Kennzeichnungspflicht; зеркало паттерна allergens) | CONFIRMED_MISSING | **S** |
| O4 | **Live-статус заказа гостю** (eingegangen→Zubereitung→fertig/unterwegs; FSM+push уже есть → публичная polling-страница) | PARTIAL | M |
| O5 | **Поиск по меню** на витрине (есть в кабинете → перенести) | CONFIRMED_MISSING | S |

### 4b. Dine-in / стол
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| T1 | **QR pay-at-table + Trinkgeld** для столовой сессии (сейчас стоп на заказе) | PARTIAL | L |
| T2 | **Gastro-виджет брони**: Anlass/occasion + спец-пожелания + гибкий депозит (per-day/group/partial-hold) + **no-show fee** | PARTIAL | L |

### 4c. Контент / маркетинг / discovery
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| M1 | **Mittagstisch/Tageskarte**: дате/время-скоупленные секции меню (авто show/hide) + недельный редактор | CONFIRMED_MISSING | M |
| M2 | **JSON-LD Restaurant** (openingHours/hasMenu/acceptsReservations) + **Reserve/Order-with-Google** (`opening_hours_structured` уже есть → дотянуть) | CONFIRMED_MISSING | M |
| M3 | **Reminder заказа + post-visit review-request** + опц. SMS/WhatsApp (ready/shipped push уже есть) | PARTIAL | M |
| M4 | **Catering intake-форма** (гости/дата/диета/on-site-vs-Lieferung/меню) поверх jobs | CONFIRMED_MISSING | S |
| M5 | **Демо-данные**: засеять combos, депозит на стол, **diets-теги на pranasy** (all-vegan → 0 тегов!) и по блюдам restaurant | PARTIAL | S |
| M6 | Nährwerte/kcal (опц., для healthy/vegan/пекарни-prepack) | (из матрицы) | S |

## 5. Сравнение с лидерами

- **vs Lieferando** — паритет/выше по меню/модификаторам/комбо/доставке+зоны/LMIV/KDS;
  наш клин — **0 % комиссии на своём субдомене**. Отстаём: слот предзаказа, live-трекинг, платёжный микс (PayPal).
- **vs OpenTable** — есть бронь без аккаунта + Stripe-депозит + waitlist (через events); отстаём: gastro-tailored виджет (Anlass/гибкий депозит/гость-CRM), Reserve-with-Google.
- **vs resmio** — ближайший функциональный peer, почти паритет (бронь/заказ/Gutschein/DOI-newsletter/часы/лояльность/multi-lang); отстаём: Mittagstisch-расписание, embed-виджеты, глубина GBP-синка.
- **vs orderbird** — есть KDS + QR dine-in, но **не POS-замена** и **сознательно без TSE/KassenSichV/RKSV**; отстаём жёстко: pay-at-table+Trinkgeld, split-bill, TSE-чеки (правильный SMB-срез, но это потолок для заведений с настоящей кассой).

**Net:** сильнее всего против resmio, конкурентен против Lieferando/OpenTable на «своём канале», уже orderbird по фискалу. Топ-рычаги: платёжный микс, слоты предзаказа, QR pay-at-table+чаевые, Mittagstisch-расписание.

## 6. Что устарело в отчёте 2026-06-25

Доехало: combos, QR dine-in + KDS, диет-фасет, multi-language меню (pranasy),
gastro-события, отзывы о блюде. Осталось/подтвердилось как гэп: платёжный микс,
слоты предзаказа, pay-at-table+чаевые, Mittagstisch-расписание, Zusatzstoffe,
live-статус гостю, gastro-виджет брони, JSON-LD Restaurant. **Демо-факт:** pranasy
(«100 % vegan») сеет **0 diet-тегов** → его live диет-фильтр пуст; combos и депозит
на стол не засеяны.

## 7. Связанные
`docs/archetype-completeness-audit-2026-06-30.md` · `docs/market-gap-a1a2-retail-2026-06-30.md`
(общий платёжный гэп) · `docs/market-analysis/a4-gastro.md` (снапшот) ·
`apps/catalog`, `apps/orders`, `apps/booking`, `apps/events`, `apps/promotions`.
