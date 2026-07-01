# A7 Handwerker (Maler/Elektriker/SHK/Tischler/Garten) — рынок ↔ функционал — 2026-06-30

> **Шаг 6** серии (индекс: `docs/market-gap-audit-2026-06-30-index.md`).
> Метод: воркфлоу 16 агентов → синтез → **адверсариальная проверка 12 гэпов**
> (10 CONFIRMED_MISSING, 2 PARTIAL, 0 ложных). ⚠️ Разведчик старого отчёта упал
> (StructuredOutput retry-cap) → синтез построен на код-инвентаре + рыночном
> бенчмарке; раздел «что устарело» тоньше обычного. Бенчмарк: MyHammer, Check24
> Profis, Blauarbeit, Houzz Pro, Jobber, Housecall Pro, ServiceTitan, Plancraft,
> Meisterwerk, ToolTime, ProvenExpert. Кит: `handwerker`. Снапшот — `market-analysis/a7-handwerker.md`.

## 0. Вывод одной фразой

A7 **отлично делает DACH-специфичную петлю Anfrage→Angebot→Auftrag→Rechnung** (с
фото, депозитом, материалами из каталога и списанием склада) — то, что маркетплейсы
и SEO-билдеры НЕ дают. Но это **самый слабый архетип по витрине/контенту и
комплаенсу**: нет детали услуги и каталога Leistungen (SEO), нет **E-Rechnung**
(юр. шлюз B2B 2025), нет service-area/PLZ, верифиц. отзывов, структурных trust-бейджей,
портфолио проектов, онлайн-оплаты счёта, e-подписи.

## 1. Структура сайта (карта страниц)

| Страница | Статус | Заметка |
|---|:--:|---|
| Главная (секция Leistungen-тизер + before/after) | ✅ | |
| **Каталог Leistungen (контент/SEO)** | ❌ | только home-тизер + воронка `/termin/`; нет standalone-страницы |
| **Деталь услуги** | ❌ | только `/termin/leistung/<pk>/` = слот-пикер; `booking.Service`/`jobs` **не в `DETAIL_ENTITIES`** |
| Anfrage (заявка) + фото | ✅ | `/anfrage/`, до 5 фото, honeypot+rate-limit; **нет PLZ, нет urgency/Notdienst** |
| Публичный Angebot/Kostenvoranschlag | ✅ | `/angebot/<token>/` — line items, нетто/НДС/брутто, accept/decline; **без e-подписи** |
| Auftrag→Rechnung | ✅ | `quote_to_invoice` → finance.Invoice + PDF; **нет E-Rechnung XRechnung/ZUGFeRD** |
| Онлайн-оплата счёта | ❌ | оплачивается только депозит на Angebot (Stripe Connect); финальный счёт — нет |
| Депозит/Anzahlung | ✅ | на акцепте Angebot, Stripe Connect |
| Before/after Referenzen | 🟡 | слайдер пар (один caption); **нет портфолио проектов** (multi-image/per-project/Gewerk) |
| Termin booking + связка с Job | ✅ | A7d; связывает существующую бронь |
| Материалы из каталога + списание склада | ✅ | G11 идемпотентно |
| Reviews | 🟡 | только агрегатор (бизнес-уровень); нет отзыва по завершённому Auftrag |
| Trust/Meister | 🟡 | free-text chips; нет типизир./верифиц. бейджей + загрузки документов |
| Правовое (Impressum/Datenschutz/Widerruf) | ✅ | **AGB нет**; правовое не засеяно (placeholder) |

## 2. Что уже есть (сильная сторона — back-office петля)

**Anfrage с фото** (до 5) · **публичный Angebot/Kostenvoranschlag** с line items +
accept/decline · **депозит онлайн** (Stripe Connect) · **Auftrag→Rechnung** + PDF ·
**материалы/Teile из каталога** на строках сметы · **идемпотентное списание склада**
при завершении (G11) · before/after слайдер · Termin-бронь + связка с Job (A7d) ·
Fahrzeug-поля (общее с A9) · vehicle/HSN/TSN.

## 3. Матрица «рынок ↔ наш статус»

| Фича рынка | Важн. | Статус | Заметка |
|---|:--:|:--:|---|
| Anfrage-форма с фото/описанием/адресом | must | ✅ | |
| **Каталог Leistungen (контент/SEO)** | must | ❌ | только тизер + воронка брони |
| **Деталь услуги (scope/Ablauf/FAQ/CTA/SEO-URL)** | must | ❌ | только слот-пикер; не в DETAIL_ENTITIES |
| Публичный Angebot + accept/decline | must | ✅ | |
| **E-подпись на акцепте** | should | ❌ | только accepted_at (e-подпись есть у stays/events, не у jobs) |
| Auftrag→Rechnung | must | ✅ | + PDF |
| **E-Rechnung (XRechnung/ZUGFeRD)** | must (B2B 2025) | ❌ | **юр. шлюз**; только визуальный PDF; нет XML-библиотек |
| **Онлайн-оплата счёта** | should | 🟡 | только депозит на Angebot, не финальный счёт |
| Депозит/Anzahlung онлайн | should | ✅ | Stripe Connect |
| Before/after | must (визуал доверия) | 🟡 | пары; нет портфолио |
| **Портфолио проектов (multi-image/per-project/Gewerk)** | should | ❌ | |
| Termin booking + связка с Job | should | ✅ | A7d |
| Материалы из каталога + списание склада | should | ✅ | G11 |
| **Notdienst/urgency-флаг на заявке** | should | ❌ | только статичный маркетинг-текст |
| **Service area/Einzugsgebiet (PLZ)** | must (local-SEO) | ❌ | только free-text адрес; PLZ-зоны есть у orders, не у jobs |
| **Trust-бейджи (Meister/Innung/HWK-Nr./Versicherung/Zert.)** | must (DACH) | 🟡 | free-text chips, без типов/верификации/загрузки |
| **Верифиц. отзыв по завершённому Auftrag** | must | ❌ | ProductReview только catalog; нет review-FK на Job |
| **Response-time SLA / auto-ack на Anfrage** | should | ❌ | письмо клиенту только на этапе «quoted», нет авто-ответа на «new» |
| **AGB** + засев правового в демо | must (DACH) | ❌ | нет AGB; placeholder Datenschutz |
| Multi-step Anfrage-визард | should | ❌ | одна длинная форма |
| **Единый customer-portal** (заявка+смета+Termin+счёт) | should | 🟡 | пер-документ токен-ссылки (лёгкая версия) |
| Sticky click-to-call / WhatsApp (mobile) | must | ❌ | не выявлено |
| Good-better-best тиры сметы | nice | ❌ | JobLine — один плоский список |
| Financing/Ratenzahlung | nice | ❌ | нет |

## 4. Недостающий функционал — приоритизировано (верифицировано)

### 4a. Витрина / SEO (самый большой контентный дефицит A7)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| W1 | **Деталь услуги** + регистрация `booking.Service`/jobs в `DETAIL_ENTITIES` (scope/Ablauf/галерея/FAQ/CTA/SEO-URL) — D1 общего аудита, общий гэп с A3/A9 | CONFIRMED_MISSING | **L** |
| W2 | **Каталог Leistungen** (контент/SEO-страница, отвязанная от воронки `/termin/`) — D8 общего аудита | CONFIRMED_MISSING | M |
| W3 | **Описание услуги как FAQ/Ablauf** per-service (D2 общего аудита) | (в matrix) | S |
| W4 | **Портфолио проектов** (multi-image case-studies + per-project page + Gewerk-категории) поверх before/after | CONFIRMED_MISSING | M |

### 4b. Право / комплаенс DACH (жёсткие шлюзы)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| W5 | **E-Rechnung (XRechnung/ZUGFeRD)** на Auftrag→Rechnung — **обязательна для B2B в DE с 2025**; сейчас только визуальный PDF | CONFIRMED_MISSING | **L** |
| W6 | **AGB** + засев реального Impressum/Datenschutz/AGB в демо (сквозной гэп) | CONFIRMED_MISSING | S |
| W7 | **Структурные/верифиц. trust-бейджи** (Meister/Innung/HWK-Nr./Betriebshaftpflicht/Zert./Garantie) + загрузка документа | PARTIAL | M |

### 4c. Конверсия / лиды / доверие
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| W8 | **Service area/Einzugsgebiet (PLZ)** для бизнеса + PLZ на Anfrage (переиспользовать PLZ-зоны из orders) | CONFIRMED_MISSING | M |
| W9 | **Верифиц. отзыв по завершённому Auftrag** (расширить review за пределы catalog.Product) + активный post-job запрос | CONFIRMED_MISSING | M |
| W10 | **Notdienst/urgency-флаг** на заявке + поле Job (sofort/heute/Notfall) | CONFIRMED_MISSING | S |
| W11 | **Response-time SLA / auto-ack** на Anfrage (авто-ответ клиенту + «Antwort in X Std.») | CONFIRMED_MISSING | S |
| W12 | **E-подпись** на акцепте Angebot (паттерн уже есть у stays/events) | CONFIRMED_MISSING | S |
| W13 | **Онлайн-оплата финального счёта** (card/SEPA по ссылке; Stripe-сеам уже есть для депозита) | PARTIAL | M |
| W14 | Multi-step Anfrage-визард + единый customer-portal + sticky call/WhatsApp | (в matrix) | M |

## 5. Сравнение с лидерами

- **vs Plancraft** (DACH back-office) — паритет петли Angebot→Auftrag→Rechnung + наш
  плюс (материалы+труд со списанием склада G11); проигрываем решающе на **E-Rechnung**
  (их хедлайн, обязателен с 2025) + GAEB/Abschlags-/Schlussrechnung.
- **vs MyHammer** — **мы владеем тем, что они монетизируют**: Anfrage с фото прямо
  мастеру, без платы за лид и без shared-leads + полная петля Angebot. Их плюс:
  guided multi-step intake, PLZ-routing, urgency-триаж, enforced response-time.
- **vs Houzz Pro** — у нас before/after, но только пары; их категоризир. multi-image
  портфолио + good-better-best сметы + client-dashboard + financing впереди.
- **vs Jobber** — паритет онлайн-брони + депозит онлайн; проигрываем на branded
  Client-Hub, оплате счёта онлайн, e-подписи, авто-напоминаниях (у jobs нет beat-задач).

**Net:** A7 уверенно держит DACH-специфичную quote-first петлю (фото/депозиты/материалы),
но ниже лидеров из-за (1) SEO-поверхности (нет детали услуги/каталога Leistungen),
(2) комплаенса (E-Rechnung, AGB), (3) глубины доверия (free-text бейджи, нет верифиц.
отзывов, мелкое портфолио), (4) US-полировки конверсии (оплата счёта, e-sign, portal).

## 6. Сквозные подтверждения

- «Деталь услуги» — **подтверждена снова** (общий гэп A3+A7+A9 = D1).
- AGB + засев правового — снова подтверждено (сквозной гэп).
- Верифиц. отзывы per-item — снова подтверждено (A3/A4/A5/A6/A7).
- Переиспользование движков: PLZ-зоны orders→jobs, e-подпись stays/events→jobs,
  Stripe-оплата (депозит→финальный счёт). Дешёвые победы.

## 7. Связанные
`docs/archetype-completeness-audit-2026-06-30.md` (D1/D2/D8) · `docs/market-gap-a3-2026-06-30.md`
(общая деталь услуги) · `docs/market-analysis/a7-handwerker.md` (снапшот) ·
`apps/jobs`, `apps/booking`, `apps/catalog`, `apps/finance`.
