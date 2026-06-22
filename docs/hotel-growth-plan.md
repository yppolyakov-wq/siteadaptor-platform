# Hotel / Pension (A5) — план роста по рынку (G1–G11)

Статус: 🟡 в работе (2026-06-22). Продолжение `docs/hotel-archetype-plan.md` (H1–H9
закрыты). Анализ рынка прямого бронирования для **малого отеля DACH** (1–20 номеров):
TravelLine, Sirvoy, Beds24, eviivo, Little Hotelier/Cloudbeds, SiteMinder, локальные
«сайт+движок». Принцип прежний: **надстройка над нашими модулями** (`apps.stays`,
`apps.loyalty`, `apps.finance`, `apps.notifications`, `apps.aggregator`, Stripe Connect),
docs до кода, по подзадачам с CI-чекпоинтом.

## Где мы уже на уровне рынка (H1–H9)
Тарифы+питание, условия отмены до оплаты, Extras, депозит (Stripe), Kurtaxe, дети,
промокоды, самоотмена, богатые карточки+похожие, SEO `Hotel`+Hausordnung, iCal-каналы
(односторонне), собственный агрегатор с поиском по датам, счета (DATEV/GoBD).

## Бэклог G1–G11 (ранжирован по левериджу/усилию)

| # | Фича | Зачем (рынок) | Опора | Усилие |
|---|---|---|---|---|
| **G1** | **Geschenkgutscheine** — продажа подарочных сертификатов онлайн | топ-ревенью малых отелей DACH, особенно к праздникам | `loyalty.Voucher` (погашение уже есть, H4a) + Stripe Connect + `notifications` | низкое 🔥 |
| **G2 ✅** | **Pre-/post-stay письма + запрос отзыва** | стандарт движков; upsell + отзывы → SEO `aggregateRating` | `notifications` + beat (как stay-reminder) | низкое 🔥 |
| **G3** | **Рассылки гостям (Newsletter-кампании)** | ТЗ §4/§10; прямой канал без OTA | DOI-opt-in, `Customer`, `notifications` | среднее |
| **G4** | **LOS-скидки + авто Frühbucher/Last-Minute** | ТЗ §7 (12–13); ключевой ценовой инструмент | надстройка над `RatePlan`/`pricing` | среднее |
| **G5** | **Мультикомнатное бронирование** | ТЗ §3.4; семьи/группы | `book_stay` → родитель-бронь | среднее |
| **G6** | **Online-Checkin + digitaler Meldeschein** | Bundesmeldegesetz (Meldepflicht) — юр-must DE | новый мини-поток + подпись/хранение | средне-высокое |
| **G7** | **Гибкая предоплата по тарифу** (0/частично/100 %) + PayPal/Klarna | сейчас только депозит | Stripe (методы) + поля `RatePlan` | среднее |
| **G8** | **Google Free Booking Links / Hotel Ads-фид** | метапоиск ТЗ §10; бесплатный спрос в прямое | цены/наличие, агрегатор | средне-высокое |
| **G9 ✅** | **Отчёты: Belegung %, ADR, RevPAR, выручка** | базовая аналитика PMS | брони + `finance` | низко-среднее |
| **G10 ✅** | **Booking-виджет/iframe** для сайтов отелей | многие уже имеют сайт | `/unterkunft/` + deeplink | низкое |
| **G11** | **2-way Channel Manager** (Booking/Expedia/Airbnb) | «грааль», но тяжёлая интеграция | пока односторонний iCal | высокое ⛔ |

**Вне scope (enterprise, ТЗ §6):** Revenue Management/динамика цен, Housekeeping-модуль,
замки/карты доступа, мультиобъектные сети, агентские/корп-контракты.

## Порядок реализации
Сначала «деньги и удержание» (низкое усилие): **G1 → G2 → G9 → G10**; затем
«конверсия/право»: **G4 → G7 → G5 → G6**; дистрибуция: **G8**; **G11** — отдельный
крупный модуль позже.

## G1 — Geschenkgutscheine — ✅ сделано (`loyalty/0002`)
**Идея:** гость покупает подарочный сертификат на сумму онлайн → оплата Stripe Connect
(на счёт отеля) → выпускается код `loyalty.Voucher` (фикс-сумма, 1 использование) →
письмо покупателю/получателю. **Погашение уже работает** (H4a: поле промокода в брони
вычитает `Voucher.discount_for`). G1 = только флоу продажи.
**Модель:** `loyalty.GiftVoucher` (buyer/recipient/сумма/сообщение/payment_state/
stripe_payment_intent/выпущенный `voucher`). После оплаты → создать `Voucher`
(`discount_cents=сумма`, `max_uses=1`, label «Geschenkgutschein») + письма.
**Где:** витрина `/gutschein/` (форма → Stripe Checkout → подтверждение), подтверждение
оплаты через тот же механизм, что депозит брони (`apps.stays.payments`/billing webhook),
письма (`notifications`), кабинет — список проданных сертификатов. Demo-кит: включить.
**Гейт:** показываем, если у бизнеса включён `stays` и подключён Stripe Connect.
