# A5 Übernachtung/Hotel (Hotel/Pension/Ferienwohnung) — рынок ↔ функционал — 2026-06-30

> **Шаг 4** серии (индекс: `docs/market-gap-audit-2026-06-30-index.md`).
> Метод: воркфлоу 15 агентов → синтез → **адверсариальная проверка 12 гэпов**
> (3 CONFIRMED_MISSING, 8 PARTIAL, **1 ACTUALLY_EXISTS** — отвергнут ложный гэп).
> Бенчмарк: Booking.com, Airbnb, Expedia, HRS, Google Free Booking Links, Cloudbeds,
> Sirvoy, Smoobu, Lodgify, Little Hotelier, Beds24, apaleo, Mews, DIRS21/Hotel-Spider.
> Кит: `hotel`. Снапшот 2026-06-25 — `market-analysis/a5-hotel-uebernachtung.md`.

## 0. Вывод одной фразой

**Самый достроенный архетип** (H1–H9 + рост G1–G11a/b). Для прямого бронирования
объекта 1–20 номеров покрывает почти всё, что дают лидеры, **с правовыми
преимуществами DACH** (Kurtaxe, online-checkin + цифровой Meldeschein BMG, DOI,
cookieless, без dark-patterns, 0 % комиссии). Единственный стратегический гэп —
**реальный 2-way OTA channel manager** — сознательно отложен и partner-gated
(G11c–e). Остальное — **полировка** (чипы/рейтинг на карточках, верифиц. отзывы
гостя, богатые upsell, мультиязык контента).

## 1. Структура сайта (карта страниц)

| Страница | Статус | Заметка |
|---|:--:|---|
| Главная (секция номеров) | ✅ | карточки номеров; **без чипов отмены/предоплаты/рейтинга** |
| Листинг/поиск номеров | ✅ | поиск по датам; **bare native `<date>` инпуты** (нет визуального range-picker) |
| **Деталь номера + календарь наличия** | ✅ | 2 кол., галерея+лайтбокс, кликабельный календарь (C1–C4) с «N frei», тарифы-радио, extras, депозит |
| Бронь (даты→тариф→buchen) | ✅ | min-stay/LOS, multi-room (тот же тип), Kurtaxe, авто-скидки |
| Multi-room (один тип) | ✅ | G5; **нет cross-type/смешанной корзины** |
| Online-checkin + Meldeschein | ✅ | BMG §29-30, подпись+IP+время, retention 1 год |
| Geschenkgutschein | ✅ | Stripe Connect, погашение промокодом |
| Отмена брони | 🟡 | по signed-token на странице подтверждения; **не кнопкой в ЛК**; модификации/переноса нет |
| ЛК гостя | ✅ | список броней; **без кнопки отмены stay** |
| iCal импорт/экспорт | ✅ | one-way (занятость) |
| Метапоиск-фид | 🟡 | custom JSON «Free Booking Links»; не Google ARI/connectivity-спек |
| Отчёты Belegung/ADR/RevPAR | ✅ | G9 |
| iframe/embed-виджет | ✅ | G10 |
| Карта/локация | ✅ | Leaflet/OSM + geo schema.org |
| Hausordnung/Правовое | ✅ | + Hausordnung; AGB нет (сквозной гэп) |

## 2. Что уже есть (паритет с booking-engine/PMS-лидерами)

Типы номеров с фото+Ausstattung (16 amenities) · **визуальный календарь наличия**
с truthful «N frei» · сезонные/weekend цены · **тарифы** (Verpflegung/cancellation/
prepayment %) · min-stay/LOS · **multi-room** (один тип) · депозит/предоплата % ·
**Kurtaxe** (H9) · **авто-скидки** LOS/Frühbucher/Last-Minute (G4) · extras
(Frühstück/Parkplatz) · **Geschenkgutschein** (G1) · **online-checkin + Meldeschein**
(G6, BMG) · self-cancel по политике тарифа · **iCal импорт/экспорт** · идемпотентный
импорт броней (Channel-модель) · **метапоиск-фид** (G8) · **отчёты ADR/RevPAR** (G9) ·
**iframe-виджет** (G10) · карта · pre-arrival/post-stay письма (G2) · DOI-рассылки гостям (G3).

## 3. Матрица «рынок ↔ наш статус»

| Фича рынка | Важн. | Статус | Заметка |
|---|:--:|:--:|---|
| Типы номеров + фото + amenities | must | ✅ | |
| Календарь наличия (визуальный) | must | ✅ | на детали |
| Сезонные/динамические цены | must | ✅ | Season>weekend>base |
| Тарифы (Verpflegung/Storno/Vorkasse) | must | ✅ | radio-карточки |
| Min-stay/LOS | must | ✅ | |
| Multi-room (один тип) | should | ✅ | G5 |
| **Multi-room cross-type (смешанная корзина)** | should | ❌ | один Booking = один тип |
| Депозит/предоплата % | must | ✅ | |
| **Kurtaxe/Citytax** | must (DACH) | ✅ | H9 — VAT-free строка |
| Авто-скидки (Früh/Last/LOS) | should | ✅ | G4 |
| **Upsell extras (фото/кол-во/лимит)** | should | ❌ | плоские чекбоксы, без фото/qty/инвентаря |
| Geschenkgutschein | should | ✅ | G1 |
| **Online-checkin + Meldeschein** | must (DACH) | ✅ | G6 BMG |
| Self-cancel | must | 🟡 | по токену на подтверждении; **не в ЛК**; модификации нет |
| **iCal sync** | should | ✅ | one-way |
| **Real 2-way OTA channel manager** | should | 🟡 | фундамент + iCal; реальные API отложены (G11c–e, partner-gated) |
| **Google Free Booking Links** | should | 🟡 | custom JSON, не connectivity-спек |
| Отчёты ADR/RevPAR/Belegung | should | ✅ | G9 |
| iframe-виджет | should | ✅ | G10 |
| **Отзывы гостя (per-stay/room, верифиц.)** | must | ❌ | только бизнес-уровень (агрегатор); нет flow по StayBooking |
| Чипы отмены/предоплаты/рейтинга на карточках | should | 🟡 | есть на детали, **нет на карточках главной/листинга** |
| Карта/локация | should | ✅ | |
| Guest messaging/pre-arrival | should | ✅ | generic inbox (не per-booking) |
| Truthful «nur noch N frei» | should | ✅ | **есть** (calendar «N×»+tooltip) |
| **PayPal/SEPA/Klarna** | should | 🟡 | только Stripe-карты (без payment_method_types) |
| **Визуальный range-picker на поиске** | should | ❌ | деталь имеет календарь, поиск — bare native инпуты |
| **Мультиязык контента (name/desc/house_rules)** | should | ❌ | StayUnit не использует I18nMixin (в отличие от catalog!) |

## 4. Недостающий функционал — приоритизировано (верифицировано)

### 4a. Конверсия / доверие (дёшево, высокий ROI)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| H1 | **Чипы «Kostenlose Stornierung»/«keine Vorauszahlung» + рейтинг на КАРТОЧКАХ** номеров (главная+листинг); данные уже считаются на детали | PARTIAL | **S** |
| H2 | **Верифиц. отзыв гостя per-stay/room** (flow по fulfilled StayBooking; переиспользовать catalog-паттерн verified-purchaser) | CONFIRMED_MISSING | M |
| H3 | **Кнопка отмены stay в ЛК** (сейчас только токен-ссылка на подтверждении; refund-путь уже есть) | PARTIAL | S |
| H4 | **Визуальный range-picker на поиске** (на детали календарь уже есть → переиспользовать) | CONFIRMED_MISSING | S |
| H5 | **PayPal/SEPA/Klarna** (Stripe payment_method_types/Checkout config) — общий платёжный гэп | PARTIAL | S |

### 4b. Выручка / удержание
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| H6 | **Богатые upsell extras**: фото + количество + инвентарь-лимит (сейчас плоские чекбоксы) | CONFIRMED_MISSING | M |
| H7 | **Cross-type multi-room** (1 Doppel + 1 Familienzimmer в одной брони/корзине, один total) | CONFIRMED_MISSING | M |
| H8 | **Мультиязык контента** номеров/Hausordnung (применить I18nMixin к StayUnit/StaySettings + EN) — сходится с языковым модулем (D3/D4 общего аудита) | CONFIRMED_MISSING | M |

### 4c. Дистрибуция (стратегическое, partner-gated)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| H9 | **Real 2-way OTA channel manager** (ARI-push + reservations-pull Booking/Expedia/Airbnb) — **сознательно отложено G11c–e** (партнёрские аккаунты/сертификация = шаг владельца); фундамент построен | PARTIAL | L |
| H10 | **Google Free Booking Links** connectivity-адаптер (реальный ARI-фид в спеке Google, не custom JSON) — partner-gated | PARTIAL | L |

## 5. Сравнение с лидерами

- **vs Booking.com** — паритет booking-движка (карточки/тарифы/предоплата/мгновенное
  подтверждение/лайтбокс/календарь/PAngV/Kurtaxe/self-cancel). Гэп на уровне **карточек**
  (Booking показывает чипы отмены + рейтинг на каждой). Наш клин: 0 % комиссии,
  cookieless/DSGVO, без dark-patterns (Booking оштрафован €413 млн в Испании).
- **vs Smoobu** (ближайший DACH-аналог) — паритет немецких essentials (Kurtaxe,
  checkin+Meldeschein, DOI, Gutschein, депозит, ADR/RevPAR, embed-виджет). Их edge —
  зрелый 2-way channel manager + per-reservation messaging; у нас iCal one-way +
  фундамент импорта, реальные API отложены.
- **vs Cloudbeds** — закрываем SMB-срез (движок/тарифы/предоплата/отчёты/checkin/
  виджет); Cloudbeds — полный PMS с глубокой connectivity + Google Hotel Ads + богатые
  upsell. Мы не PMS; для 1–20 номеров перекрытие на пути прямого бронирования высокое.
- **vs Mews** — гостевые essentials совпадают; PMS-глубина/open API/revenue-management
  — вне таргета малого DACH-бизнеса (правильно).

**Net:** против OTA — паритет гостевых must + клин 0 %/DSGVO/без dark-patterns;
против booking-engine/PMS — держим SMB table-stakes, с честным исключением реального
2-way OTA-синка (фундамент есть, API отложены — шаг владельца) + мелкая полировка.

## 6. Что устарело в отчёте 2026-06-25

Отчёт занижал: 2026-06-22 coverage-аудит ставил A5 ~80–90 %; по факту H1–H9 + рост
G1–G11a/b, демо с тарифами/Kurtaxe/депозитом/авто-скидками/extras/Gutschein/Hausordnung/
порталом. **Подтверждено как гэп:** чипы на карточках, верифиц. отзыв гостя, cross-type
multi-room, мультиязык контента, богатые upsell, реальный 2-way OTA (отложен).
**Adversarial-нюанс:** truthful «N frei» — НЕ гэп (уже есть в календаре).

## 7. Связанные
`docs/archetype-completeness-audit-2026-06-30.md` · `docs/hotel-archetype-plan.md` /
`hotel-growth-plan.md` / `hotel-channel-manager-plan.md` ·
`docs/market-analysis/a5-hotel-uebernachtung.md` (снапшот) · `apps/stays`.
