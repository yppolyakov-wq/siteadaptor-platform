# Рынок ↔ функционал по архетипам A1–A9 — СВОДКА сквозных тем + единый бэклог — 2026-06-30

> Капстоун серии «детальная проверка архетипов» (индекс: `docs/market-gap-audit-2026-06-30-index.md`).
> Сводит 8 пошаговых разборов (A1/A2, A3, A4, A5, A6, A7, A8, A9), каждый —
> воркфлоу (код-инвентарь + бенчмарк рынка DACH + сверка) → синтез → адверсариальная
> проверка гэпов против кода. Здесь — что повторяется в ≥3 архетипах и в каком порядке
> закрывать. **Ничего не разрабатывалось — только анализ.**

## 1. Сводная готовность по архетипам

| Архетип | Движок | Витрина/конверсия | Верифиц. гэпы (CM/PARTIAL) | Док |
|---|---|---|:--:|---|
| A1/A2 Retail | сильный (PAngV/anti-oversell/feed/Widerruf) | средняя | 9 / 3 | `market-gap-a1a2-retail` |
| A3 Termin-Dienstleister | на уровне Fresha/Shore | презентация отстаёт | 9 / 3 | `market-gap-a3` |
| A4 Gastro | ~90% (≈resmio) | средняя (нет fiscal POS — сознательно) | 6 / 6 | `market-gap-a4` |
| A5 Übernachtung/Hotel | **самый полный** (H1–H9+G1–G11a/b) | высокая | 3 / 8 (+1 EXISTS) | `market-gap-a5` |
| A6 Event/Retreat | на уровне лидеров (богатый) | высокая | 4 / 8 | `market-gap-a6` |
| A7 Handwerker | сильная back-office петля | **слабейшая витрина/комплаенс** | 10 / 2 | `market-gap-a7` |
| A8 Aggregator/Portal | зрелый скелет (метапоиск+SEO) | средняя | 6 / 5 | `market-gap-a8` |
| A9 Kfz-Werkstatt | паритет дневного цикла | авто-retention отстаёт | 8 / 2 | `market-gap-a9` |

**Общий вывод:** бэкенд-движки почти везде на уровне лидеров. Реальный фронт работ —
**(1) сквозные дешёвые победы** (деталь услуги, JSON-LD, отзывы, reuse движков),
**(2) правовой/платёжный долг DACH** (AGB, E-Rechnung, PayPal/Kauf-auf-Rechnung,
§312j, PAngV), **(3) языковой модуль**, **(4) точечные вертикальные retention-фичи**.

## 2. Сквозные темы (повторяются в ≥3 архетипах) — самые ценные работы

### T1. Деталь услуги + каталог Leistungen — A3, A7, A9
`booking.Service` несёт `description/image/price/duration`, но **не зарегистрирован в
`DETAIL_ENTITIES`** (`apps/core/archetypes.py:100-107`) → URL услуги = слот-пикер, нет
SEO-страницы. A7/A9 вдобавок без публичного каталога Leistungen. = D1/D8 общего аудита.
**Одна сборка закрывает 3 архетипа.**

### T2. Платёжный микс DACH — A1/A2, A4, A5, A6, A7, A9
Storefront-оплата = только Stripe-карты или pay-on-pickup; **нет PayPal, нет Klarna
«Kauf auf Rechnung», нет SEPA/Vorkasse**; у `Order` нет `payment_method`. Stripe Checkout
везде создаётся **без `payment_method_types`** → SEPA/PayPal частично включаются конфигом
коннектед-аккаунта, но платформа их не предоставляет. PayPal + Kauf-auf-Rechnung —
жёсткий конверсионный блокер DACH.

### T3. Верифицированные отзывы per-item на витрине бизнеса — A3, A4, A5, A6, A7, A9
Верифиц. отзыв есть только у **товара** (`catalog.ProductReview`, verified-buyer). Бизнес-
уровень (`aggregator.BusinessReview`) — не purchase-gated, портал-only. Нет отзыва по
услуге/номеру/событию/завершённому Auftrag. **Расширить паттерн ProductReview** на
Service/StayBooking/Event/Job + post-event/visit запрос.

### T4. Правовое DACH: AGB + засев правового + §312j + PAngV — A1/A2, A4, A5, A6, A7, A9
**AGB отсутствует полностью** (нет маршрута/поля/шаблона). Правовое **не засеяно в демо**
→ Datenschutz всегда placeholder. A1/A2/A4: кнопка `Zahlungspflichtig bestellen` (§312j)
сейчас «Place order»; ноты PAngV «inkl. MwSt./Lieferzeit» не на товаре/в корзине;
Zusatzstoffe/E-номера (A4). = D5/D6 общего аудита.

### T5. Языковой модуль — A5, A6 (landing) + сквозное (chrome/emails/legal)
Фундамент на витрине тенанта есть (DE/EN-переключатель + оверлей), но: `enabled_locales`/
`default_locale` **не читаются в рантайме**, `.po/.mo` пусты, chrome/письма/правовое —
DE-only, контент-модели частично i18n (**catalog да; `StayUnit`/`Event`-landing нет** →
применить `I18nMixin`). = D3/D4/D7 / план L1–L6.

### T6. JSON-LD по архетипу (rich snippets / local-SEO) — A1/A2, A4, A6, A8, A9
Product JSON-LD нет (A1/A2); Restaurant без openingHours/hasMenu/acceptsReservations
(A4); Event/Course нет (A6); openingHours/Review/Breadcrumb/sameAs нет (A8); AutoRepair
только на `/anfrage/` (A9). Дешёвый органик-ROI, паттерн A5 переиспользуем.

### T7. Переиспользование готовых движков между архетипами — самые дешёвые победы
Гэп одного архетипа = уже работающий движок соседнего, не подключённый сюда:
| Движок (где есть) | Подключить к | Закрывает |
|---|---|---|
| G4 авто-скидки (stays) | events | авто-early-bird (A6 E2) |
| Pass/Mehrfachkarte (booking) | events | memberships/class-pass (A6 E11) |
| gift-voucher (stays) | events, A3 booking | продажа сертификата (A6 E5, A3 C1) |
| embed-виджет (stays) | events | embed брони событий (A6 E7) |
| Meldeschein-retention (stays) | events | DSGVO health-данных (A6 E9) |
| PLZ-зоны (orders) | jobs | service-area/Einzugsgebiet (A7 W8) |
| e-подпись (stays/events) | jobs | подпись на акцепте (A7 W12) |
| Stripe-депозит-сеам | финальный счёт | онлайн-оплата счёта (A7 W13, A9 K10) |
| core.Extra | werkstatt/A9 | Zusatzleistungen/Ersatzwagen (A9 K3/K4) |
| ProductReview verified-buyer | Service/Stay/Event/Job | T3 отзывы |
| календарь/деталь | поиск stays, слоты A3/A6 | range-picker (A5 H4), визуал-календарь (A3 S2) |

### T8. SMS/WhatsApp-канал — A3, A4 (+reminders повсюду)
SMS-канала нет вообще; WhatsApp — заглушка-enum без sender. `notify()`-сеам готов →
добавить SMS-провайдера за ним. SMS-напоминания — топ no-show-рычаг DACH.

### T9. Поиск/discovery на витрине — A1/A2, A4, A8
Поиска на витрине нет вообще (A1/A2, A4 — есть только в кабинете); A8 full-text = icontains
по 3 полям без autosuggest/typo. Фасеты тонкие.

### T10. Богатые upsell/extras — A5, A9 (+A4)
`core.Extra` — плоские чекбоксы без фото/кол-ва/инвентаря (A5); не засеяны для werkstatt (A9).

## 3. Единый приоритизированный бэклог (эпики)

Оценка = импакт × переиспользование ÷ стоимость. **Tier 1** — сквозные дешёвые
победы (один эпик закрывает несколько архетипов).

### Tier 1 — сквозные, высокий ROI
| # | Эпик | Архетипы | Размер |
|---|---|---|:--:|
| **E-1** | **Деталь услуги + каталог Leistungen** (зарегистрировать `Service` в `DETAIL_ENTITIES` + route/template + FAQ/Ablauf) | A3, A7, A9 | M |
| **E-2** | **Правовой пакет DACH**: AGB (поле+route+автошаблон+футер) + засев правового в демо + §312j-кнопка + PAngV-ноты (inkl.MwSt./Lieferzeit) + Zusatzstoffe(A4) | A1/A2, A4, A5, A6, A7, A9 | M |
| **E-3** | **JSON-LD по архетипу** (Product/Restaurant-openingHours-hasMenu/Event-Course/Breadcrumb/AutoRepair-sitewide) | A1/A2, A4, A6, A8, A9 | S×неск. |
| **E-4** | **Верифиц. отзывы per-item** на витрине (расширить ProductReview-паттерн + post-visit запрос) | A3, A4, A5, A6, A7, A9 | M |
| **E-5** | **Reuse-пачка** (G4→events, Pass→events, gift→events/A3, embed→events, PLZ→jobs, e-подпись→jobs, Extra→werkstatt, депозит→счёт) | сквозное | M (пачкой) |

### Tier 2 — языковой модуль + платежи (стратегические, крупнее)
| # | Эпик | Архетипы | Размер |
|---|---|---|:--:|
| **E-6** | **Языковой модуль L1–L4**: `enabled_locales`/`default_locale` в рантайм + кабинет «Sprachen» + EN-контент во все киты + `I18nMixin` на stays/events + `.po/.mo` chrome/emails | сквозное | L |
| **E-7** | **Платёжный микс DACH**: PayPal + Klarna «Kauf auf Rechnung» + SEPA + Vorkasse + `Order.payment_method` (Stripe `payment_method_types`) | A1/A2, A4, A5, A6, A7, A9 | L |
| **E-8** | **SMS/WhatsApp-канал** за `notify()`-сеамом + reminder/review-триггеры | A3, A4, A6, A9 | M |

### Tier 3 — вертикальные retention/конверсия
| # | Эпик | Архетип | Размер |
|---|---|---|:--:|
| **E-9** | A9 retention: repair-статус+«fertig»-письмо → **HU/AU-reminder (serviced-vehicle)** → Reifeneinlagerung | A9 | M→L→L |
| **E-10** | A4 gastro: слот предзаказа, QR pay-at-table+Trinkgeld, Mittagstisch-расписание | A4 | M |
| **E-11** | A8 монетизация: **claim-your-business** + вынос бизнес-страницы/отзывов на `/entdecken` + owner-аналитика + «Anzeige»-лейбл | A8 | L |
| **E-12** | A5: чипы отмены/рейтинг на карточках + cross-type multi-room + богатые upsell | A5 | M |
| **E-13** | A6: per-attendee roster + авто-early-bird (reuse G4) + .ics-в-письме | A6 | M |
| **E-14** | A1/A2: поиск+фасеты + multi-axis варианты + полный CSV-импорт + DHL carrier + wishlist | A1/A2 | M→L |
| **E-15** | A3: визуальный календарь слотов + клиентский перенос/Umbuchung + skill-matrix + buffer | A3 | M |

### Tier 4 — сознательно отложено (partner-gated / вне SMB-тира)
- **Real 2-way OTA channel manager** (A5 G11c–e) — партнёрские аккаунты/сертификация.
- **Google Free Booking Links connectivity-фид** (A5/A8) — partner-gated.
- **DAT SilverDAT 3 / GT-Motive** estimation (A9) — partner-gated; ручная смета — SMB-субститут.
- **Фискальный POS / TSE/KassenSichV** (A4) — сознательно вне скоупа (order-routing, не касса).
- **E-Rechnung XML (ZUGFeRD/XRechnung)** (A7/A9) — юридически важно (B2B 2025), но
  интеграционно тяжело; вынести в отдельный трек E-Invoice.

## 4. Рекомендованный порядок волн

1. **Волна 1 (Tier 1):** E-1 деталь услуги → E-2 правовой пакет → E-3 JSON-LD →
   E-4 отзывы → E-5 reuse-пачка. Максимум закрытых архетипов за минимум кода;
   снимает большинство «дешёвых» CONFIRMED_MISSING разом.
2. **Волна 2 (Tier 2):** E-6 языковой модуль (L1–L4) → E-7 платёжный микс → E-8 SMS.
   Стратегический долг DACH + «время языкового модуля пришло».
3. **Волна 3 (Tier 3):** вертикальные retention-фичи по приоритету владельца
   (рекомендация: E-9 A9-retention и E-11 A8-монетизация — наибольший бизнес-эффект).
4. **Tier 4** — по мере партнёрств/спроса; E-Invoice — отдельным треком при первом B2B-клиенте.

## 5. Связанные
Per-archetype: `market-gap-a1a2-retail` / `-a3` / `-a4` / `-a5` / `-a6` / `-a7` / `-a8` /
`-a9` (`-2026-06-30.md`) · общий аудит `archetype-completeness-audit-2026-06-30.md`
(D1–D10) · индекс `market-gap-audit-2026-06-30-index.md` · снапшот рынка 2026-06-25
`archetype-market-analysis.md` + `market-analysis/*`.
