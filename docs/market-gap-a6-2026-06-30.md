# A6 Event/Retreat/Kurse (ретриты/воркшопы/курсы/билеты) — рынок ↔ функционал — 2026-06-30

> **Шаг 5** серии (индекс: `docs/market-gap-audit-2026-06-30-index.md`).
> Метод: воркфлоу 16 агентов → синтез → **адверсариальная проверка 12 гэпов**
> (4 CONFIRMED_MISSING, 8 PARTIAL, 0 ложных). Бенчмарк: Eventbrite, Eventim/Xing,
> BookRetreats, Retreat Guru, Tripaneer, Momence, Eversports, Mindbody, fitogram,
> regiondo, GetYourGuide, Zoom Events. Киты: `retreat`, `pranasy`.
> Снапшот 2026-06-25 — `market-analysis/a6-event-retreat.md`.

## 0. Вывод одной фразой

**Один из самых полных архетипов** — бэкенд/движок на уровне лидеров по всем трём
суб-архетипам (mass-ticketing / retreat / studio-course). Старые доки (~45–55 %)
**сильно занижали**. Честная дельта — не «движок», а 6 вещей: авто-early-bird,
верифиц. отзывы, per-attendee roster для групп, DE/EN-глубина, дистрибуция
(events в агрегаторе + embed-виджет), платёжный микс DACH (PayPal/SEPA).

## 1. Структура сайта (карта страниц)

| Страница | Статус | Заметка |
|---|:--:|---|
| Главная (секция событий) | ✅ | |
| Листинг событий + фасеты | ✅ | cat/level/lang/city/dur/month/teacher; countdown, sold-out |
| Календарь | 🟡 | месяц-сгруппированный **список**, не визуальный day-grid + iCal-subscribe |
| **Богатая деталь события/ретрита** | ✅ | program/agenda-таймлайн, hosts/Teacher, карта, галерея+лайтбокс, retreat-landing (for_whom/idea/includes/venue/food/bring/faq/before-after/certs), порядок секций настраивается |
| Выбор билета/тира + checkout | ✅ | тиры с пер-тир capacity, депозит, рассрочка, ваучер |
| Регистрация/анкета/Waiver | ✅ | structured fields (diet/emergency/experience/medical) + e-signature waiver |
| Подтверждение + QR-билет | ✅ | + Zoom-ссылка post-booking для online |
| Отмена + возврат | ✅ | signed-token, политика flexible/non_refundable, Stripe-refund |
| Блог | ✅ | RT4 BlogPost |
| Преподаватели/ведущие | ✅ | R3 Teacher + /lehrer/ |
| ЛК гостя (билеты) | ✅ | |
| Правовое | ✅ | AGB нет (сквозной гэп) |

## 2. Что уже есть (паритет с лидерами)

Листинг+фасеты+countdown · **тиры билетов** (Frühbucher/Standard/Kind) с пер-тир
capacity · **anti-oversell** (event + per-tier под row-lock) · multi-day · **серии**
(series_id + create_series) · **анкета + structured fields** · **Waiver/health-consent
с e-подписью** (snapshot+IP+время) · **депозит** · **рассрочка** (InstallmentPlan +
off-session beat) · **связка событие↔stays** с реальным anti-overbooking · **online/
Zoom** (ссылка post-booking) · **waitlist + авто-уведомление** · **QR-билет + check-in** ·
self-cancel+refund · промокоды · блог (RT4) · преподаватели (R3) · iCal download/subscribe ·
reminders + post-event письма · retreat-landing (богатый).

## 3. Матрица «рынок ↔ наш статус»

| Фича рынка | Важн. | Статус | Заметка |
|---|:--:|:--:|---|
| Листинг + календарь | must | ✅ | календарь — список (не grid) |
| Богатая деталь/landing (agenda/hosts/venue) | must | ✅ | сильная сторона |
| Тиры билетов (Frühbucher/Standard/Kind) | must | ✅ | |
| **Авто date-driven early-bird→Standard→Last-Minute** | should | ❌ | только ручные label-тиры; G4 у stays не подключён к events |
| Capacity + anti-oversell + per-tier | must | ✅ | row-lock |
| Multi-day / серии | should | ✅ | series_id |
| Анкета + structured fields | should | ✅ | |
| Waiver/consent e-signature | should (retreat) | ✅ | + snapshot/IP |
| Депозит | should | ✅ | |
| Рассрочка/payment-plan | should (retreat) | ✅ | InstallmentPlan |
| Связка событие↔проживание | should (retreat) | ✅ | real anti-overbooking |
| Online/Zoom | should | ✅ | ссылка post-booking |
| **Hybrid + запись/replay-библиотека** | should (course) | ❌ | только бинарный is_online, нет replay/hybrid |
| Waitlist + авто-уведомл. | should | ✅ | |
| QR-билет + check-in | must | ✅ | |
| **Per-attendee roster** (имена + QR на каждого + group-тир) | should | ❌ | multi-seat = 1 answers + 1 QR |
| Self-cancel + refund | must | ✅ | |
| Промокоды | should | ✅ | |
| **Sellable Geschenkgutschein для событий** | should | 🟡 | погашение на events работает; продажа привязана к stays-модулю |
| **Верифиц. отзывы attendee (event+host)** | must | 🟡 | только organizer-curated testimonials; нет EventReview по fulfilled ticket |
| Блог/контент | should | ✅ | |
| Преподаватели/ведущие | should | ✅ | |
| **.ics в письме + визуальный grid-календарь** | should | ❌ | .ics только download; календарь — список |
| **Event/Course JSON-LD** | should | ❌ | нет rich snippets / free event listings |
| **Дистрибуция: events в агрегаторе + embed-виджет** | should | 🟡 | агрегатор events **есть**; embed-виджет для events нет (есть у stays) |
| **PayPal/SEPA/Klarna** | should | 🟡 | только Stripe-карты |
| **DE/EN-глубина** (landing free-text/chrome/email/legal) | should | 🟡 | title/desc i18n; landing-блоки одноязычны; .po/.mo пусты |
| **Memberships/class-pass для курсов** | should (studio) | 🟡 | Pass есть для booking.Service, не подключён к events |
| **DSGVO retention для health/emergency-данных** | should (DACH) | ❌ | нет purge (в отличие от Meldeschein у stays) |

## 4. Недостающий функционал — приоритизировано (верифицировано)

### 4a. Конверсия / доверие / выручка
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| E1 | **Верифиц. отзывы attendee** на событие+ведущего (EventReview/TeacherReview по fulfilled ticket + post-event триггер) | PARTIAL | M |
| E2 | **Авто date-driven early-bird→Standard→Last-Minute** (переиспользовать G4 DiscountRule из stays, привязать к тирам по дате) | PARTIAL | M |
| E3 | **PayPal/SEPA/Klarna** (Stripe payment_method_types) — общий платёжный гэп | PARTIAL | M |
| E4 | **Per-attendee group booking**: именной roster + QR на каждого + group-тир | CONFIRMED_MISSING | M |
| E5 | **Sellable Geschenkgutschein для событий** (расширить stays G1 на events; погашение уже работает) | PARTIAL | S |

### 4b. Discovery / дистрибуция / SEO
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| E6 | **Event/Course JSON-LD** (rich snippets + Google free event listings) — переиспользовать паттерн A5 | CONFIRMED_MISSING | S |
| E7 | **Embed-виджет брони событий** (?embed=1 + iframe; у stays G10 есть) + events в агрегатор уже surface | PARTIAL | L |
| E8 | **.ics в письма** подтверждения/напоминания + визуальный **grid-календарь** (VEVENT-генератор уже есть) | CONFIRMED_MISSING | S |

### 4c. Право / контент / вертикали
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| E9 | **DSGVO retention/erasure** для health/emergency-данных билета (переиспользовать дисциплину Meldeschein-purge из stays) | CONFIRMED_MISSING | S |
| E10 | **DE/EN-глубина**: i18n на landing free-text + chrome/email/legal + runtime enabled_locales — сходится с языковым модулем (D3–D7 общего аудита) | PARTIAL | L |
| E11 | **Memberships/class-pass-credits** для курсов (Pass у booking есть → подключить к events.Event) | PARTIAL | L |
| E12 | **Hybrid-режим + replay/recording-библиотека** для online-событий (сейчас бинарный is_online + одна live-ссылка) | CONFIRMED_MISSING | M |

## 5. Сравнение с лидерами

- **vs Eventbrite** — паритет ядра ticketing (тиры+capacity, QR+check-in, waitlist+auto,
  промокоды, self-cancel, .ics, reminders). Eventbrite ведёт: авто-early-bird,
  Ads/marketplace + embed-виджет, per-attendee roster, Event JSON-LD, PayPal.
- **vs BookRetreats** — **наша сильнейшая зона**: богатый landing (agenda/hosts/venue/
  food/bring/faq/before-after/certs), депозит+рассрочка, **связка с проживанием с
  реальным anti-overbooking** — редкость. Их единственный решающий плюс: верифиц.
  отзывы attendee + best-price social proof + продажа gift-voucher.
- **vs Momence/Eversports/Mindbody** (studio/course) — паритет waitlist/online/серий/
  level/waiver/депозит/рассрочка/блог. Их плюс: memberships/class-pass, replay/on-demand,
  branded app/PWA+push, SEPA.
- **vs regiondo** — паритет тиров/capacity/QR/оплата/self-cancel; их плюс: channel-
  дистрибуция (GYG/Viator) + embed-виджет + gift cards.

**Net:** бэкенд на уровне лидеров; честная дельта — (1) авто-early-bird, (2) верифиц.
отзывы, (3) per-attendee roster, (4) DE/EN-глубина, (5) дистрибуция (events-в-агрегатор
есть, embed-виджет нет), (6) платёжный микс DACH. Кроме отзывов и wiring авто-скидок —
новых core-модулей не требуется.

## 6. Что устарело в отчёте 2026-06-25 / старых доках

Старые доки ставили A6 ~45–55 % — **сильно занижено**. По факту: тиры, per-tier
anti-oversell, waiver+e-подпись, рассрочка, связка с проживанием, online/Zoom,
серии, блог, преподаватели, waitlist+auto — всё есть. Подтверждено как гэп:
авто-early-bird, верифиц. отзывы, per-attendee roster, JSON-LD, embed-виджет,
.ics-в-письме, DSGVO-retention, replay/hybrid, memberships для курсов.

## 7. Связанные
`docs/archetype-completeness-audit-2026-06-30.md` (D9 тиры) · `docs/retreat-archetype-plan.md`
/ `retreat-installments-plan.md` / `retreat-waiver-plan.md` ·
`docs/market-analysis/a6-event-retreat.md` (снапшот) · `apps/events`, `apps/stays`.
