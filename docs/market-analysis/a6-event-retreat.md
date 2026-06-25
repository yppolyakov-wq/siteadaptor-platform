# A6 — Событие / Ретрит (Seminarhaus, Yoga-Retreat, Kurs, Stadtführung, Tour, Konzert)

> Рыночный анализ архетипа A6 (2026-06-25). Конвенция: docs до кода. Source of
> truth по сделанному — `build-log.md`; план наполнения — `retreat-archetype-plan.md`
> (R1–R13 закрыты, кроме рассрочки R10 — она сделана, но dormant до Stripe-теста).
> Этот документ сверяет нашу реализацию с лидерами рынка ретрит/событийного
> софта и выделяет **визуальные**, **технические** и **анти-Битрикс** пробелы.
> Позиционирование неизменно: один сайт одного бизнеса (~39 €/мес), витрина без
> аккаунта/трекинг-куки, Double-Opt-In (UWG §7), «own-your-audience», анти-маркетплейс.

---

## Current coverage

Архетип A6 — **один из самых зрелых в платформе**. Движок `apps.events` +
кит `retreat` покрывают практически всё ядро event/retreat-софта. Подтверждено
чтением кода (`models.py`, `services.py`, `public_views.py`, `details.py`,
`registration.py`, `installments.py`, `ical.py`, `state_machine.py`,
`templates/storefront/event_*.html`, `demo_kits.py`).

**Продажа места и ценообразование**
- Событие на дату с вместимостью; **атомарный анти-овердрафт** под блокировкой
  строки Event (`services.book_ticket`, `select_for_update`), `capacity=0` =
  безлимит (фестиваль). `seats_left` / `is_sold_out`.
- **Ценовые тиры билета** (`tiers`: Frühbucher / Standard / Mehrbett …) с
  **per-tier вместимостью** (R11): «Mehrbett 2 frei», «Einzel ausgebucht»,
  анти-овердрафт тира под той же блокировкой, предвыбор первого доступного тира,
  «ab X €» на витрине. Это уровень 3–5 тиров, который рынок считает оптимальным
  (Eventbrite/SimpleTix).
- **Extras к билету** (`core.Extra`, scope events): Bio-Mittagessen,
  Einzelzimmer-Zuschlag, Yogamatte-Verleih.
- **Депозит / частичная предоплата** (R4, `deposit_percent`): 30 % онлайн, остаток
  на месте; снимок `deposit_cents` / `balance_cents`.
- **План рассрочки** (R10, `InstallmentPlan`/`InstallmentCharge` + `installments.py`):
  первая доля on-session (мандат Stripe), остальные off-session по графику (beat),
  режимы `until_event` / `fixed`. Готово, но dormant до боевого Stripe-теста.
- **Подарочный/промо-код** (R4, `Voucher`): скидка на билет, атомарное гашение.
- **Онлайн-оплата** — Stripe Connect на счёт бизнеса; выручка в `finance` (НДС 19 %,
  идемпотентно через FSM `TicketSM`).

**Проживание (ретрит с ночёвкой)**
- **Связка event ⊕ stays** (R5): `offers_accommodation` + M2M `accommodation_units`;
  выбор типа номера на даты ретрита с реальным анти-овербукингом stays, цена входит
  в `total_cents` (одна оплата), привязанная `StayBooking` (`Ticket.stay_booking`);
  отмена билета освобождает номер. Это редкость даже у лидеров (room-inventory ⊕
  ticket — фишка Retreat Guru).

**Регистрация, право, доверие**
- **Структурированная анкета** (R1, `registration.py`): пресет-поля
  (Land, Geburtsdatum, Notfallkontakt, Ernährung, Erfahrung, Allergien,
  Gesundheitliche Hinweise) + свободные `questions`. Ответы в стабильных ключах для
  ростера/CSV.
- **Waiver + Gesundheits-Selbstauskunft с e-подписью** (R8, `TicketWaiver`):
  печатное Ф.И.О. + время + IP, снимок текста условий (юр-след). Дефолтный шаблон
  для Yoga/Meditation.
- **Гибкая политика отмены** (R12): flexible (бесплатно до N дней, возврат через
  Stripe Connect) / non_refundable; самоотмена гостем по подписанной ссылке
  (`/e/storno/<token>/`), освобождение номера + уведомление листа ожидания.
- **Trust-блоки** (R13): отзывы `name|city|text|photo|rating` (фото-аватар + звёзды),
  истории «Vorher/Nachher» (transformation), значки сертификации (RYT-500 и т. п.).

**Богатый ретрит-лендинг** (`details.py`, рендер `event_detail.html`)
- Блоки: promise, for_whom, idea/Atmosphäre, includes, Programm/Ablauf (`program`),
  venue + Galerie + **карта OSM** (R6, cookieless), accommodation, food, hosts,
  price_includes/excludes/note, bring, FAQ, testimonials, before_after, certifications.
- **Преподаватели как сущность** (R3, `Teacher`): фото/био/website/Instagram,
  страницы `/lehrer/`, фильтр каталога.

**Каталог, навигация, воронка**
- **Каталог-фильтры** (R2): таксономия city/category/level/language/duration +
  фасеты по факту наличия; на маленькой витрине фильтры скрыты (анти-Битрикс),
  на агрегаторе — включены. `from X €`, свободные места, бейджи.
- **Годовой календарь** по месяцам + **iCal**: один `.ics` на событие
  («Zum Kalender hinzufügen») и фид-подписка `retreats.ics` (`ical.py`).
- **Waitlist** (R1, `EventWaitlistEntry`) на sold-out, одно DSGVO-уведомление при
  освобождении места.
- **Drip-письма** (R9): подтверждение → напоминание за N дней → post-event (отзыв),
  идемпотентно + БД-дедуп.
- **Памятка-PDF** (R6, `memo.py`): «Teilnehmer-Memo» (что взять, как добраться).
- **Корп/групповой запрос** (R6): кнопка на лендинге → движок Angebote (`jobs`).
- **Уведомления** Email + **Telegram** клиенту; **ЛК клиента** (`customer_account`).
- **Site Builder M20U**: унифицированные главная/каталог/детальная, layout-движок,
  per-page раскладки, archetype-aware дефолты, мобильный buybar, sticky-цена.
- **Агрегатор**: события листятся с фильтром по направлению/городу/месяцу.

**Кабинет организатора** (`views.py`): CRUD событий, ростер участников + действия
FSM (confirm / **attended** / cancel + mark paid), **CSV-экспорт** ростера
(utf-8-sig, Excel-friendly).

**Демо-кит `retreat`** («Waldlicht Retreat»): несколько событий, тиры, проживание
(3 типа номеров), преподаватели, waiver, депозит, отзывы с фото/Vorher-Nachher,
extras, карта Freiburg.

**Оценка готовности backend: ~85–90 %** ядра event/retreat-софта для DACH-микробизнеса
(одиночный сайт). Дыры — почти исключительно UX-витрина, контент-SEO и пара точечных
функций; модель и сервисы зрелые.

---

## Market benchmark

Сверка с лидерами (что они продают как ценность):

- **Retreat Guru** — комната ⊕ программа ⊕ платёж в одной системе; pre-arrival /
  post-departure email-кампании; meal-reports по диетам для кухни; fixed- и
  flexible-date программы ([software.retreat.guru/features](https://software.retreat.guru/features)).
- **WeTravel** — «больше чем booking page»: сбор анкеты (диета, room preference),
  **payment plans с авто-напоминаниями**, room-assignment/inventory, отчётность по
  выручке/перформансу ([academy.wetravel.com](https://academy.wetravel.com/wetravel-vs-retreat-guru-which-platform-is-better-for-retreat-organizers)).
- **BookRetreats** — продаёт **доверием и трансформацией**: 4.7/5 на Trustpilot,
  модерация качества, проверка credentials фасилитаторов, **free cancellation**,
  72-часовое «окно раздумий», **pre-retreat Zoom-звонок за 2 недели**, корпоративные
  ретриты ([bookretreats.com](https://bookretreats.com/), [trustpilot](https://www.trustpilot.com/review/bookretreats.com)).
- **Eventbrite / SimpleTix** — **3–5 тиров** оптимальны (≥20–25 % разница), early-bird/
  time-based pricing «волнами», VIP/add-ons, Apple/Google Pay, **FTC all-in pricing**
  (полная цена с комиссиями upfront) ([eventbrite tiered pricing](https://www.eventbrite.com/blog/make-money-tiered-pricing-ds00/), [simpletix](https://www.simpletix.com/event-ticketing-software-tiered-pricing-guide/)).
- **pretix / Regiondo / GetYourGuide** — **timeslot-визит-менеджмент** (выбор слота +
  лимит), **embed-виджет** ticketshop на чужом сайте, OTA-каналы, time-point vs
  time-period ([pretix timeslots](https://pretix.eu/about/en/timeslots), [pretix widget](https://docs.pretix.eu/guides/widget/), [regiondo](https://pro.regiondo.com/booking-system/)).
- **Momoyoga / Arketa** — **recurring class series**, class pass (кредиты) и
  recurring membership, attendance/waitlist для студийного формата
  ([momoyoga class pass](https://support.momoyoga.com/en/support/solutions/articles/201000116521-what-s-the-difference-between-a-membership-and-a-class-pass-)).
- **Конвенции витрины** (landing best-practices 2025/26): минимальная форма на
  конверсии (имя+email, остальное потом), proof с именем+фото+конкретным результатом,
  **83 % трафика мобильный** при худшей мобильной конверсии → mobile-first и низкий
  friction, явный одиночный CTA ([shopify](https://www.shopify.com/blog/high-converting-landing-pages), [landingi](https://landingi.com/landing-page/41-best-practices/)).
- **Ticketing-стандарт**: **QR-билет + check-in сканом** (анти-дубль, offline,
  лог входа), PDF-билет, **Add to Apple/Google Wallet** ([qrcodechimp guide](https://www.qrcodechimp.com/event-ticket-qr-code-guide/), [eventregist wallet](https://support.eventregist.com/en/knowledge/add-tickets-to-apple-wallet-or-google-wallet)).

Вывод: наша **модель/сервисы — на уровне лидеров** (тиры с per-tier capacity,
депозит, рассрочка, room-inventory, waiver, отмена). Отставание — в **витрине-storytelling**,
**check-in/доступе к билету**, **онлайн-формате** и **контент-SEO**.

---

## Visual gaps

(A) Визуальные / UX-пробелы витрины и лендинга.

| # | Пробел | Почему (рынок) | Effort | Частично есть? |
|---|--------|----------------|--------|----------------|
| V1 | **Hero ретрита со сроком, датой, «ab X €» и Countdown/«noch N Plätze»** | Landing-конвенция: один сильный экран с обещанием+датой+ценой+дефицитом; «only N left» уже двигает конверсию (Eventbrite urgency, landing best-practices) | S | Частично: hero-галерея + sticky-цена + «Only N spots left» есть; нет таймера/обратного отсчёта и единого «над сгибом» CTA-экрана |
| V2 | **Программа/Agenda как визуальный day-by-day timeline** | Retreat Guru/WeTravel показывают Ablauf по дням блоками, не плоским списком; это ключевой блок «что я получу» | S–M | Да, `program` — но это плоский `<ul>` строк, без группировки по дням/таймлайна |
| V3 | **Tier-pricing как карточки-сравнение** (а не радиокнопки в форме) | Eventbrite/SimpleTix: 3–5 тиров читаются как pricing-таблица «что входит»; влияет на выбор и upsell | M | Частично: тиры есть, но рендерятся радиокнопками внутри формы брони; нет витринной сравнительной карточки тиров до формы |
| V4 | **Двухшаговый чекаут** (тариф/номер/extras → контакты/waiver/оплата) | Длинная одностраничная форма с waiver+анкетой+проживанием = высокий friction на мобильном (83 % трафика); minimal-form best-practice | M | Нет (решено в `m20-retreat-pages-plan` M20R-4, не реализовано): сейчас всё одним длинным POST на детальной |
| V5 | **Карточка ретрита для грида каталога** (обложка+бейджи+«ab»+места) | Обзорная страница «каталог ретритов» как у BookRetreats/Retreat Guru — визуальные карточки, не строки-list | S–M | Частично: `event_index` есть, но карточка — горизонтальная строка с маленькой 96px-картинкой; нет крупной обложки-grid карточки |
| V6 | **Галерея-storytelling / лайтбокс на лендинге** | Wellness-ретриты продаются атмосферой (фото места/природы/практик); рынок ставит фото в центр | S | Частично: `_media_gallery` (большое+миниатюры) есть в hero; venue-галерея — простой 3-кол грид без лайтбокса |
| V7 | **Профиль преподавателя богаче** (соцсети-иконки, видео-интро, «ведёт N ретритов») | Trust строится на фасилитаторе (BookRetreats проверяет credentials); страница `/lehrer/` есть, но скромная | S | Да, `Teacher` + страница; не хватает визуальной подачи (badge сертификаций, видео, отзывы о ведущем) |
| V8 | **Sticky/прогресс-бар вместимости** («12 von 18 belegt») | Дефицит + социальное доказательство; рынок активно использует «fast filling» | S | Частично: «Only N left» текст есть; нет визуального прогресса/«заполняется» |

---

## Technical gaps

(B) Технические / функциональные пробелы (учитывая, насколько зрел backend).

| # | Пробел | Почему (рынок) | Effort | Частично есть? |
|---|--------|----------------|--------|----------------|
| T1 | **QR-билет + check-in сканом** | Ticketing-стандарт: уникальный QR, скан на входе (анти-дубль, лог, offline); сейчас «attended» ставится вручную в ростере | M | Частично: статус `attended` + ростер/CSV есть; нет QR на билете/в PDF и сканер-экрана check-in в кабинете |
| T2 | **Онлайн-/Zoom-ретрит** (ссылка-доступ после оплаты) | BookRetreats/студии: гибрид и pre-retreat Zoom-звонки; растущий формат | S–M | Нет (отложено в плане): нет поля access_url/онлайн-флага, выдачи ссылки в письме/подтверждении |
| T3 | **Блог / контент-SEO модуль** | Лидеры держат SEO-трафик статьями; для одиночного DACH-сайта органика — главный недорогой канал | M | Нет (R7 отложен отдельным треком) |
| T4 | **PDF-билет с брендом (а не только памятка)** | Стандарт: attendee получает PDF-билет с QR; у нас есть memo-PDF, но не «билет» | S | Частично: `memo.py` (Teilnehmer-Memo) есть; нет билета-PDF с QR/штрих-кодом |
| T5 | **Recurring/серии событий** (еженедельный курс, абонемент) | Momoyoga: class series + class pass/membership; Kochkurs/Yoga-Studio формата «курс из 8 занятий» | M–L | Частично: `Pass`/Mehrfachkarte есть (G9, см. verticals); нет UX генерации серии дат и серийной брони на стороне events |
| T6 | **Timeslot для Stadtführung/Tour** (несколько слотов одного дня) | pretix/Regiondo/GetYourGuide: один продукт — много time-point слотов; туры/экскурсии так и продаются | M | Частично: можно завести отдельное Event на каждый слот; нет «product → слоты дня» как у tour-софта |
| T7 | **Все-включено цена (PAngV/FTC)** на витрине везде | FTC all-in pricing с мая 2025; PAngV в DE. Депозит/extras/номер считаются, но «итог к оплате» виден только при выборе | S | Частично: `payable/amount_due_now` считаются; нет живого пересчёта итога на форме (JS) до сабмита |
| T8 | **WhatsApp-уведомления** | DACH-клиенты ждут WhatsApp; рынок туров активно использует | M | Нет (P12, нужен Business-API аккаунт владельца) |
| T9 | **Apple/Google Wallet-pass** | Ticketing-стандарт «add to wallet» | M | Нет; iCal-«в календарь» есть (близкий, но не Wallet-pass) |
| T10 | **Meal-/diet-report для кухни** | Retreat Guru фича: сводка по `diet` для кухни | S | Частично: `diet` собирается в анкете → CSV-ростер; нет агрегированного meal-report одной кнопкой |

---

## Anti-Bitrix block editor

(C) Рекомендации для блочного редактора M20 и «ретрит-шаблона». Принцип:
пресеты вперёд, настройки спрятаны, детальная — управляемый скелет (не холст),
публикация ретрита ≤10 шагов. Бэкенд уже даёт все данные — это работа над
переиспользуемыми секциями и онбордингом.

**Переиспользуемые блоки ретрит-лендинга** (все данные уже в `details`/модели):
1. **Hero + Countdown / «noch N Plätze»** — full-bleed фото, обещание (`promise`),
   дата, «ab X €», CTA «Platz sichern», опц. таймер до старта/раннего тарифа. (V1)
2. **Programm/Agenda-Block** — day-by-day таймлайн из `program` (группировка по дням
   через парсинг префикса «Fr/Sa/So» или новая структура день→пункты). (V2)
3. **What's-included-Block** — грид иконка+заголовок+текст из `includes`
   (+ price_includes/excludes как «✓ / –»). Уже есть как секция, нужен пресет-стиль.
4. **Teacher-Block** — карточки ведущих (`Teacher`/`hosts`) с фото, ролью, соц-иконками,
   ссылкой на профиль. (V7)
5. **Tier-Pricing-Block** — сравнительные карточки тиров «Label · ab € · was frei»
   до формы (а не только радио в форме). (V3)
6. **FAQ-Block** — аккордеон из `faq` (есть, оформить как пресет).
7. **Gallery-Block** — лайтбокс-галерея фото места/практик (V6); переиспользовать
   `_media_gallery` + grid-движок.
8. **Reviews / Before-After-Block** — отзывы с фото+звёздами + «Vorher/Nachher» +
   значки сертификации (R13 уже отрендерены — обернуть в блок с layout-пресетом).
9. **Map + Anreise-Block** — OSM-карта (R6) + текст venue + «Route planen».
10. **Buchungs-Block** — виджет покупки (тиры/номер/extras/waiver/депозит/рассрочка),
    в идеале 2-шаговый (V4).

**Smart defaults / «Retreat-Landing-Template»**
- При выборе архетипа «Ретрит» в онбординге — авто-раскладка главной и детальной
  из `primary_item=events` (M20U-4 уже даёт archetype-aware дефолт): hero →
  ближайшее событие → программа → ведущие → отзывы → FAQ → буч.
- Демо-контент (как кит `retreat`) предзаполняет блоки реалистичным текстом, чтобы
  владелец **редактировал, а не создавал с нуля** («a child could edit»).
- Один большой CTA-стиль, мобильный buybar (есть), минимальная форма на первом шаге.

**≤10-шаговый онбординг «опубликовать ретрит»**
1. Название + 1 фраза-обещание → 2. Даты (старт/конец) → 3. Вместимость →
4. Цена / тиры (пресет «Frühbucher/Standard») → 5. Программа (день-за-днём) →
6. Фото (галерея) → 7. Ведущий (выбрать/создать) → 8. Что входит / взять (опц.) →
9. Waiver/анкета вкл-выкл переключателями (опц.) → 10. «Veröffentlichen».
Депозит/рассрочка/проживание/отмена — в свёрнутом «Erweitert» (smart defaults:
flexible-отмена, без депозита), чтобы не пугать на первом проходе.

**Дисциплина (держим):** не плодить модели (всё поверх JSON `details`/site_config),
детальная — скелет с тогглами, фильтры/поиск off на одиночном сайте, пресет +
свёрнутое «Дополнительно» вместо десятков контролов на блок.

---

## Prioritized backlog table

Порядок: сперва дёшево поднять конверсию витрины и закрыть ticketing-стандарт,
затем форматные расширения, затем контент-SEO и каналы.

| Приоритет | ID | Что | Тип | Effort | Обоснование |
|-----------|----|-----|-----|--------|-------------|
| 1 | V4 | 2-шаговый чекаут (тариф/номер/extras → контакты/waiver/оплата) | UX | M | Главный friction на мобильном; уже спланировано (M20R-4) |
| 2 | V2 | Programm/Agenda day-by-day timeline-блок | Визуал | S–M | Ключевой блок «что я получу», дёшево |
| 3 | V5 | Карточка ретрита для грида каталога (крупная обложка) | Визуал | S–M | Обзор-страница «как у лидеров», основа агрегатора |
| 4 | V1 | Hero + Countdown / дефицит мест | Визуал | S | Конверсия, дёшево |
| 5 | T1 | QR-билет + check-in сканом в кабинете | Тех | M | Ticketing-стандарт; «attended» уже есть, не хватает скана |
| 6 | V3 | Tier-pricing как сравнительные карточки | Визуал | M | Выбор тира + upsell |
| 7 | T7 | Живой пересчёт «итог к оплате» (PAngV/FTC) | Тех | S | Право DE/all-in pricing, доверие |
| 8 | T4 | PDF-билет с QR (рядом с memo) | Тех | S | Стандарт выдачи билета |
| 9 | V6/V7 | Лайтбокс-галерея + богаче профиль ведущего | Визуал | S | Atmosphere + trust |
| 10 | T2 | Онлайн-/Zoom-ретрит (access_url после оплаты) | Тех | S–M | Растущий формат, дёшево |
| 11 | T5 | Recurring/серии событий (курс из N занятий) | Тех | M–L | Kochkurs/Yoga-Studio; есть `Pass`, нет UX серий |
| 12 | T6 | Timeslot для туров/экскурсий (слоты дня) | Тех | M | Stadtführung/Tour-Operator |
| 13 | T3 | Блог / контент-SEO модуль | Тех | M | Органика — главный недорогой канал (R7) |
| 14 | T10 | Meal-/diet-report для кухни (1 кнопка) | Тех | S | Retreat Guru фича; данные уже собираются |
| 15 | T8/T9 | WhatsApp-уведомления / Wallet-pass | Тех | M | Зависят от аккаунтов владельца; отложено |

---

### Sources
- WeTravel vs Retreat Guru — https://academy.wetravel.com/wetravel-vs-retreat-guru-which-platform-is-better-for-retreat-organizers
- Retreat Guru features — https://software.retreat.guru/features
- BookRetreats — https://bookretreats.com/ ; Trustpilot — https://www.trustpilot.com/review/bookretreats.com
- Eventbrite tiered pricing — https://www.eventbrite.com/blog/make-money-tiered-pricing-ds00/ ; SimpleTix — https://www.simpletix.com/event-ticketing-software-tiered-pricing-guide/
- pretix timeslots — https://pretix.eu/about/en/timeslots ; pretix widget — https://docs.pretix.eu/guides/widget/ ; Regiondo — https://pro.regiondo.com/booking-system/
- Momoyoga class pass/series — https://support.momoyoga.com/en/support/solutions/articles/201000116521-what-s-the-difference-between-a-membership-and-a-class-pass-
- Landing best practices — https://www.shopify.com/blog/high-converting-landing-pages ; https://landingi.com/landing-page/41-best-practices/
- QR/Wallet ticketing — https://www.qrcodechimp.com/event-ticket-qr-code-guide/ ; https://support.eventregist.com/en/knowledge/add-tickets-to-apple-wallet-or-google-wallet
