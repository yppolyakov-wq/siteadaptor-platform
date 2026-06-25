# A3 — Termin / Dienstleister (Anschauen-Analyse)

Анализ архетипа **A3 «Termin / Dienstleister»** (запись по времени): Friseur,
Barber, Kosmetik/Nagel/Wimpern/Waxing, Massage, Fußpflege/Podologie, Hundesalon,
Tattoo/Piercing, Fotograf, Fahrschule, Nachhilfe/Musikschule, Yoga/Pilates,
Coach/Berater. Цель документа — сверить текущую витрину siteadaptor с тем, что
ожидают клиенты DACH-салонов и что предлагают рыночные системы (Treatwell, Shore,
Fresha, Salonkee, Planity, Calendly, Acuity, SimplyBook), и зафиксировать гэпы +
бэклог под анти-Битрикс-конструктор. **Юридический предел:** Heilberuf
(Massage-Therapie/Physio/Heilpraktiker) — только запись, без Patientenakte /
медкарт (DSGVO Art. 9 + Heilmittelwerbegesetz).

Источник по коду: `apps/booking/` (models, availability, public_views,
notifications, tasks), `apps/tenants/demo_kits.py` (кит `FRISEUR`,
`Salon Schöngut`), `templates/storefront/service_*.html` /
`booking_*.html`, `apps/tenants/siteconfig.py` (реестр секций M20).

---

## Current coverage

Движок записи (`apps.booking`) уже довольно зрелый — по нашей собственной оценке
~90–95 % (`docs/kit-archetype-coverage.md` §A3, `micro-business-verticals.md` §A3).
Что реально есть:

**Модель и движок (`apps/booking/models.py`, `availability.py`, `services.py`):**
- **Услуга с ценой и длительностью** — `Service` (G10): `duration_minutes` +
  `price_cents` + `deposit_cents` («Haarschnitt Damen — 45 Min., 39 €»).
- **Ресурсы/мастера** — `Resource` (типы `staff`/`table`/`room`/`service`),
  `capacity`, `counts_party_size` (групповой курс с видимыми местами),
  `deposit_cents`, `require_manual_confirm` (анти-фрод).
- **Доступность** — недельные правила `AvailabilityRule` (окно + шаг слота) минус
  `ClosedDate` (выходные/праздники) минус занятые интервалы. Анти-двойное-
  бронирование атомарно в `services.book` (зеркало anti-oversell).
- **Слоты по услуге** — `service_slots()` собирает свободные старты по всем
  ресурсам под длительность услуги; `assign_resource()` назначает ресурс.
- **Опциональный выбор мастера** на витрине (#4): `?resource=<pk>` — пилюли
  «Anyone / Lea / Jonas» в `service_slots.html`.
- **Депозит / Vorkasse (анти-no-show, P2.5b)** — Stripe Connect Checkout на счёт
  бизнеса; `payment_state` (none/pending/paid/refunded), refund-готовность.
- **Mehrfachkarte / 10er-Karte** — `Pass` + `PassPlan` (G9b): покупка онлайн через
  Stripe (`/karten/`, `karte_kaufen`), гашение визита кодом `K-XXXXXX` при записи,
  привязка карты к конкретной услуге.
- **Групповой курс** — `capacity>1` + `counts_party_size` показывает «N Plätze frei»
  (Yoga/Pilates/Fahrschule-Theorie).
- **Напоминания** — beat-задача `send_booking_reminders` (за `BOOKING_REMINDER_HOURS`,
  по умолч. 24 ч), ровно одно (`reminder_sent_at` + БД-дедуп).
- **Письма** — created/confirmed/cancelled/reminder клиенту + Telegram-дубль (TG3)
  + письмо владельцу при новой заявке; List-Unsubscribe (one-click).
- **Extras к термину** (#7) — `apps.core.Extra` («Haarkur Intensiv», «Kopfmassage»),
  снимок в `Booking.extras`, входят в `total_cents`.
- **FSM статусов** — `BookingSM` (pending→confirmed→fulfilled/cancelled/no_show);
  смена только через `.apply()`.
- **Лояльность** — Stempelkarte (`apps.loyalty`), в ките `Treuekarte` 10 штампов.

**Витрина (templates/storefront):**
- `/termin/` → `service_index.html` (карточки услуг: имя + «45 min · 39 €»),
  иначе `booking_index.html` (выбор ресурса). Ссылка на Mehrfachkarte.
- `service_slots.html` — пилюли мастеров, ±день навигация, слоты-пилюли по H:i,
  раскрытие формы по `?slot=`, поля Name*/Email/Phone/Note, Pass-Code, Extras,
  баннер депозита.
- `booking_confirmation.html` (`/t/<code>/`) — благодарность, дата, reference-code,
  статус депозита/подтверждения, Telegram-CTA.
- Без аккаунта, honeypot + rate-limit по IP, без трекинг-куки (UX-принцип владельца).

**Демо-кит `FRISEUR` (`Salon Schöngut`):** 6 услуг, 2 ресурса типа `staff`
(Lea/Jonas), 2 PassPlan (10er/5er-Karte), Treuekarte, отзывы (`reviews_seed`),
team/FAQ/testimonials/trust, каталог Pflegeprodukte (4), 2 Extras, меню (`menus`).

**Вывод по покрытию:** функциональное ядро записи — одно из самых сильных в
платформе. Слабое место — НЕ в backend-движке, а в **витринной/UX-подаче** и в
том, что многие сильные фичи (мастер, депозит, карты) визуально подаются как
generic-форма без отраслевого «салонного» лица. Плюс отсутствуют несколько
функций, которые в DACH уже стали гигиеническим стандартом (SMS-Erinnerung,
Multi-Service-Buchung, Gutscheine, intake/consent-формы).

**Оценка готовности витрины A3: ~70 %** (движок ~90 %, но потребительский
опыт/подача ниже рыночной планки).

---

## Market benchmark

Что используют DACH-салоны и что ждут их клиенты (по рыночным источникам):

- **Трёхшаговый флоу** «Leistung → Zeit → Bestätigung» — канон. Каждое лишнее
  поле/шаг повышает abandonment ~на 7 %; умные дефолты и условные поля сокращают
  клики (Salon Booking System, Booknetic).
- **Визуальный календарь вместо списков** — цветной календарь свободных слотов
  воспринимается мгновенно, лучше текстовых dropdown'ов (Booknetic best-practices).
- **Выбор мастера со специализацией** — продвинутые системы знают, что не все
  стилисты делают все услуги, и матчат навык↔услуга; у каждого свои часы/перерывы
  (Salon Booking System, Mindbody). Клиент часто хочет «zu Lena».
- **Профили/фото мастеров и услуг** — при онбординге заливают services, prices,
  staff info **и фото** (Fresha setup-гайд).
- **Multi-Service-Buchung** — клиент бронит несколько услуг подряд, календарь
  пересчитывает суммарную длительность в реальном времени (Planity).
- **SMS-Erinnerung за 24 ч** — у Planity/Salonkee/Acuity/SimplyBook стандарт против
  no-show; e-mail-Bestätigung сразу после брони (Planity, Salonkee).
- **Депозит / Anzahlung** — анти-no-show, особенно для дорогих услуг (Färben,
  Tattoo) (Fresha/Treatwell).
- **Bewertungen на странице бизнеса** — verified reviews повышают доверие и число
  записей (Planity).
- **Gutscheine / Gift certificates** — продажа и дарение сертификатов на услуги
  (Acuity, SimplyBook) — в DACH сильный сезонный канал (Weihnachten, Muttertag).
- **Intake / Consent / Patch-Test** — кастомные формы и согласия до визита; Fresha
  трекает patch-test для Beauty (Acuity, SimplyBook, Fresha). Для Kosmetik/Tattoo/
  Wimpern — почти обязательно (Einverständnis, Allergie-Check).
- **Waitlist** — клиент встаёт в лист ожидания на занятое время; держит календарь
  полным (Acuity, SimplyBook).
- **Recurring / Serientermine** — еженедельный Nachhilfe/Massage/Pilates (Acuity,
  Setmore, SimplyBook).
- **Klassen-/Gruppenmanagement** — лимит мест, waitlist на курс (SimplyBook).
- **Mehrfachkarte / Pakete / Memberships** — карты на N визитов (есть у нас).

**Коммерческий контекст:** Treatwell — 39 €/мес + **35 %** комиссия с первой брони
нового клиента + 2 % за онлайн-предоплату; Fresha — 20 %; Shore — от 49,90 €/мес
без комиссии, но это чистый management-tool без маркетплейса (KundenLoop-Vergleich
2026, timetailor). Это прямой аргумент позиционирования siteadaptor: **39 €/мес,
own-your-audience, без комиссии с брони и без маркетплейс-захвата клиента** —
ровно то, чего салоны боятся у Treatwell.

Источники: [KundenLoop Vergleich 2026](https://www.kundenloop.de/blog/buchungssoftware-kosmetikstudio-vergleich-2026),
[Treatwell.de](https://www.treatwell.de/),
[Fresha best salon software](https://www.fresha.com/for-business/salon/best-salon-software),
[Planity Friseur](https://info.planity.com/de-de/deine-branche/friseur),
[Salonkee online bookings](https://salonkee.com/pro/en/online-bookings/),
[Salon Booking System — customer booking guide](https://www.salonbookingsystem.com/salon-booking-system-blog/customer-booking-system/),
[Booknetic — scheduling best practices](https://www.booknetic.com/blog/appointment-scheduling-process),
[Acuity Scheduling](https://acuityscheduling.com/),
[SimplyBook.me vs Calendly vs Acuity](https://www.booknetic.com/blog/calendly-vs-simplybookme-vs-acuity-scheduling),
[timetailor Fresha/Treatwell](https://www.timetailor.com/timetailor-alternatives/fresha-treatwell-comparison).

---

## Visual gaps

(A) VISUAL / UX — ощущение флоу, подача меню услуг, мобайл, доверие, мастера,
ясность календаря, подтверждение.

1. **Нет блока «Leistungen / Preisliste» на главной** — S. Сейчас услуги живут
   только на `/termin/`; на главной (`home`) нет секции «services». Клиент салона
   ждёт прайс-лист на лендинге («Schnitt 39 €, Färben 69 €») как витрину доверия.
   *Рынок:* прайс — первый контент салонной страницы. _Частично:_ есть
   `service_index`, но не как секция конструктора.

2. **Слоты — плоский список пилюль, нет визуального календаря/группировки** — M.
   `service_slots.html` показывает H:i-пилюли без группировки «Vormittag/
   Nachmittag/Abend», без визуального day-picker'а (только ←/→ по одному дню), без
   индикации «следующий свободный день». *Рынок:* цветной календарь интуитивнее
   списка (Booknetic). _Частично:_ ±день есть, календаря нет.

3. **Профили мастеров без лица** — M. Выбор мастера — это текстовые пилюли
   «Lea / Jonas / Anyone». Нет фото, специализации, мини-био («Lea — Coloristin,
   seit 2012»). `team`-секция на главной и `Resource` НЕ связаны — фото команды
   есть в `team`, но в записи их нет. *Рынок:* фото+специализация мастера — норма
   онбординга (Fresha). _Частично:_ team-секция существует отдельно.

4. **Слабая «салонная» эстетика флоу записи** — S. `service_slots.html` —
   generic-форма (booking_slots.html ещё несёт hardcoded `🍽`-emoji из ресторанного
   контекста). Нет фото услуги, нет hero под услугу, шаги не пронумерованы
   визуально (1 Leistung · 2 Zeit · 3 Daten). *Рынок:* трёхшаговый визуальный
   progress снижает abandonment.

5. **Подтверждение без «add to calendar» и без карты/маршрута** — S. На
   `booking_confirmation.html` нет кнопки «In Kalender speichern» (.ics/Google),
   нет ссылки на карту/Anfahrt, нет явной кнопки самоотмены/переноса. *Рынок:* ics
   и самоотмена — гигиена. _Частично:_ есть reference-code, Telegram-CTA, адрес
   строкой.

6. **Нет отображения отзывов на самом флоу/услуге** — S. `reviews` есть как
   секция главной (G8/#6), но в `/termin/` и на карточке услуги доверие не
   подсвечено (звёзды, «347 zufriedene Kund:innen»). *Рынок:* verified reviews →
   больше записей (Planity). _Частично:_ блок reviews есть на home.

---

## Technical gaps

(B) TECHNICAL / FUNCTIONAL — функции, которых движку не хватает до рыночного
паритета.

1. **Multi-Service-Buchung (несколько услуг за один визит)** — L. Сейчас одна
   `Booking` = одна `Service`. Клиент салона часто бронит «Waschen + Schnitt +
   Föhnen» подряд; длительность и слот должны сложиться. *Рынок:* у Planity это
   базовая фича. _Нет._

2. **Привязка услуга↔мастер (skill matrix)** — M. `assign_resource` берёт ЛЮБОЙ
   свободный ресурс; нет модели «эту услугу делают только Lea и Mia». Для салона с
   разнопрофильными мастерами это реальная дыра (запишут «Färben» к барберу).
   *Рынок:* skill-based matching — стандарт (Salon Booking System). _Нет (есть
   только ручной выбор ресурса клиентом)._

3. **SMS-Erinnerung** — M. Напоминания только email/Telegram. В DACH SMS за 24 ч —
   де-факто стандарт против no-show (Planity, Salonkee, Acuity). Нужен SMS-провайдер
   + согласие. _Нет (email/TG есть)._

4. **Gutscheine / Geschenkgutscheine на услуги** — M. У отеля уже есть
   Geschenkgutscheine (G1), у A3 — нет продажи/гашения сертификата на услугу
   (≠ Mehrfachkarte). Сильный сезонный канал DACH. *Рынок:* Acuity/SimplyBook. _Нет
   для booking (есть `vouchers` на заказы и Pass)._

5. **Intake / Consent / Patch-Test-Formular** — M. Для Kosmetik/Wimpern/Tattoo
   нужны Einverständnis + Allergie-/Gesundheits-Fragen до визита; для Tattoo —
   Altersnachweis. Сейчас только свободное `note`. *Рынок:* кастомные intake-формы
   и patch-test-трекинг (Acuity, SimplyBook, Fresha). **Heilberuf-предел:** формы
   допустимы как согласие/анкета, но без хранения медкарт. _Частично:_ есть `note`
   и `events.questions` (для событий, не для booking). Можно переиспользовать
   паттерн вопросов.

6. **Serientermine / Recurring** — M. Нет повторяющихся записей (еженедельный
   Nachhilfe/Pilates/Massage). *Рынок:* Acuity/Setmore/SimplyBook. _Нет._

7. **Waitlist на занятый слот** — M. Для акций/событий waitlist в платформе есть
   (`/p/<uuid>/waitlist/`), но для `booking`-слотов нет. *Рынок:* Acuity/SimplyBook.
   _Нет для booking._

8. **Stornierung/Umbuchung клиентом по ссылке** — S–M. FSM есть, но
   публичной кнопки «termin stornieren/verschieben» на confirmation нет; депозитные
   правила отмены (Frist) не выражены. *Рынок:* самоотмена в окне — норма.
   _Частично:_ статусы и письмо cancelled есть, публичного действия нет.

9. **Buffer-Zeiten между записями** — S. Нет настройки «15 мин уборки/подготовки
   после услуги». Длительность = ровно `duration_minutes`. *Рынок:* buffer — частая
   настройка. _Нет._

10. **Anzahlung-Politik по услуге + «Stripe нет → нет депозита»** — S. Депозит
    есть, но нет дифференцированной политики (процент vs фикс, кому требовать).
    _Частично:_ фикс `deposit_cents` есть.

---

## Anti-Bitrix block editor

(C) Какие переиспользуемые блоки нужны архетипу, ≤10-шаговый онбординг и дефолты.

**Реестр секций M20 сейчас** (`siteconfig.SECTIONS`) содержит: hero, stay_search,
stay_rooms, promotions, categories, products, events, archetypes, about, process,
team, cta, testimonials, trust, reviews, faq, gallery, contact. **Секции `services`
для A3 НЕТ** — это ключевой пробел конструктора для этого архетипа.

**Рекомендуемые блоки (анти-Битрикс, drag-drop, live-preview):**

1. **Block «Leistungen & Preise» (services)** — НОВЫЙ. Сетка/список услуг с
   длительностью+ценой+опц. фото, layout-пресеты (list/cols2/cols3) как у прочих
   grid-секций, кнопка «Termin buchen» на каждой карточке. Источник — `Service`.
   Это №1 must-have. Effort: M.

2. **Block «Team / Unsere Stylisten» с записью** — расширить существующий `team`:
   связать карточку мастера с `Resource` → «Termin bei Lea», фото+специализация.
   Effort: M (модель-связка team↔resource).

3. **Block «Termin-CTA / Jetzt buchen»** — переиспользовать `cta` с дефолтом на
   `/termin/`; sticky mobile buybar «Termin buchen» (M20U buybar уже есть для
   purchase_mode — настроить `purchase_mode=booking`, `purchase_label=Termin buchen`).
   Effort: S (конфигурация существующего).

4. **Block «Bewertungen» (reviews)** — уже есть (G8/#6); включить в дефолт A3-кита и
   показать звёзды рядом с CTA записи. Effort: S.

5. **Block «So läuft's» (process) + FAQ** — есть; в ките FRISEUR заполнены. Оставить
   в дефолтном пресете A3. Effort: 0 (готово).

6. **Block «Gutschein verschenken»** — после реализации Gutscheine (Technical #4) —
   карточка-CTA на покупку сертификата. Effort: зависит от #4.

**Archetype-aware дефолт главной для A3** (`archetypes.primary_item=service`,
`purchase_mode=booking`, `purchase_label="Termin buchen"`): hero →
**services (прайс)** → team(с записью) → reviews → process → faq → gallery →
contact. Сейчас A3-кит не показывает services-секцию на главной — это первый
дефолт, который надо ввести.

**≤10-шаговый онбординг до рабочей записи** (анти-Битрикс):
1. Тип бизнеса = «Friseur/Beauty/Dienstleister» → авто-пресет (модули booking +
   loyalty, дефолтная раскладка главной с прайсом).
2. Название + адрес + Öffnungszeiten (структурные часы → расписание ресурса
   авто-заполняется из `opening_hours`).
3. Добавить 1–6 услуг (имя · Dauer · Preis) — авто-дефолты из шаблона отрасли
   (Haarschnitt 30 Min · 25 €).
4. Добавить мастеров (имя + фото) — каждый = `Resource` типа `staff`, часы
   наследуют Öffnungszeiten.
5. (опц.) Депозит/Anzahlung — один тумблер + сумма.
6. (опц.) Mehrfachkarte/Gutschein — пресет.
7. Логотип + акцентный цвет (1 клик из палитры).
8. Готово → витрина с прайсом, командой и рабочим `/termin/`.

**Sensible auto-fill:** Öffnungszeiten → AvailabilityRule всех мастеров; шаг слота
= минимальная длительность услуги; дефолтные FAQ/process из шаблона FRISEUR;
дефолтный текст hero/CTA («Termin in 30 Sekunden online buchen»).

---

## Prioritized backlog table

| # | Гэп | Тип | Почему важно (рынок) | Effort | Статус |
|---|-----|-----|----------------------|--------|--------|
| 1 | Блок **«Leistungen & Preise» (services)** на главной | Visual/Editor | Прайс — первый контент салонной страницы; нет в реестре SECTIONS | M | Нет |
| 2 | **SMS-Erinnerung** за 24 ч | Tech | Де-факто стандарт DACH против no-show (Planity/Salonkee) | M | Нет (email/TG есть) |
| 3 | **Multi-Service-Buchung** (несколько услуг подряд) | Tech | Базовая фича Planity; «Waschen+Schnitt+Föhnen» | L | Нет |
| 4 | **Профили мастеров с фото+специализацией**, связь team↔Resource, «Termin bei Lea» | Visual/Editor | Фото+специализация мастера — норма онбординга (Fresha) | M | Частично (team отдельно) |
| 5 | **Gutscheine / Geschenkgutscheine** на услуги | Tech | Сильный сезонный канал DACH (Weihnachten/Muttertag) | M | Нет (есть у hotel G1) |
| 6 | **Intake / Consent / Patch-Test-Formular** (в рамках Heilberuf-предела) | Tech | Обязательно для Kosmetik/Wimpern/Tattoo (Acuity/SimplyBook/Fresha) | M | Частично (note; events.questions) |
| 7 | **Skill-Matrix услуга↔мастер** | Tech | Иначе «Färben» уйдёт к барберу (Salon Booking System) | M | Нет |
| 8 | **Визуальный календарь/группировка слотов** (Vormittag/Nachmittag) + day-picker | Visual | Цветной календарь интуитивнее списка (Booknetic) | M | Частично (±день) |
| 9 | **Самоотмена/Umbuchung клиентом** + правила отмены депозита | Tech/UX | Самоотмена в окне — гигиена | S–M | Частично (FSM/письмо) |
| 10 | **«In Kalender (.ics)» + карта/Anfahrt** на confirmation | Visual | Гигиена подтверждения | S | Нет |
| 11 | **Serientermine / Recurring** | Tech | Nachhilfe/Pilates/Massage (Acuity/Setmore) | M | Нет |
| 12 | **Waitlist на занятый слот** | Tech | Держит календарь полным (Acuity/SimplyBook) | M | Нет (есть для акций) |
| 13 | **Buffer-Zeiten** между записями | Tech | Уборка/подготовка после услуги | S | Нет |
| 14 | **Termin-CTA/buybar пресет** + reviews-звёзды у CTA | Editor | Снижение трения, доверие | S | Частично (buybar есть) |
| 15 | **Archetype-aware дефолт главной A3** (hero→services→team→reviews) | Editor | ≤10-шаговый онбординг до рабочей записи | S | Нет |

**Чистый вывод:** движок A3 — один из сильнейших, но витрина отстаёт от рынка.
Самый высокий ROI: блок **services на главной (#1)**, **SMS-Erinnerung (#2)** и
**профили мастеров с записью (#4)** — это закрывает разрыв между «мощным backend»
и «салонным ощущением», которое ждут DACH-клиенты, при этом сохраняя
анти-маркетплейс-позиционирование (39 €/мес, без 35 %-комиссии Treatwell).
