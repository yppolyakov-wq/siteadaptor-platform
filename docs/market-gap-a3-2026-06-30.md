# A3 Termin-Dienstleister (Friseur/Massage/Kosmetik/Physio/Coaching) — рынок ↔ функционал — 2026-06-30

> **Шаг 2** серии (индекс: `docs/market-gap-audit-2026-06-30-index.md`).
> Метод: воркфлоу 16 агентов (код + бенчмарк рынка + сверка отчёта 2026-06-25/демо)
> → синтез → **адверсариальная проверка 12 гэпов** (9 CONFIRMED_MISSING, 3 PARTIAL,
> 0 ложных). Бенчмарк: Treatwell, Planity, Fresha, Shore, Booksy, Phorest, Salonized,
> Timify, Calendly. Кит: `friseur`. Снапшот 2026-06-25 — `market-analysis/a3-termin-dienstleister.md`.

## 0. Вывод одной фразой

**Движок записи на уровне Fresha/Shore или выше** (atomic anti-double-book, депозит/
no-show через Stripe Connect, Mehrfachkarte с онлайн-покупкой, выбор мастера с
фото/био, extras, лояльность, гостевая запись). Дифференциатор — **flat 39 €/мес,
0 % комиссии, свой список клиентов** (vs Treatwell ~35 % за первую запись / Fresha
~20 % на новых). Отставание — **не движковое, а презентация + 4 hygiene-фичи**:
нет детальной страницы услуги, нет клиентского переноса записи, нет SMS-напоминаний,
нет отзывов у CTA брони, плоский список слотов вместо визуального календаря.

## 1. Структура сайта (карта страниц)

| Страница | Статус | Маршрут / шаблон | Заметка |
|---|:--:|---|---|
| Главная (+ секция «Leistungen & Preise») | ✅ | `storefront-home` · `sections/_services.html` | секция services в реестре M20 (старый отчёт «нет секции» — устарел) |
| Листинг услуг | ✅ | `/termin/` `termin_index` · `service_index.html` | богатые карточки (фото/описание/длит./цена); ведут сразу в форму брони |
| **Деталь услуги (standalone)** | ❌ | — | **ключевой гэп:** нет `service_detail` маршрута/шаблона; контент инлайн на странице слотов; нельзя deep-link/SEO-страницу услуги без виджета брони |
| Форма слотов+брони (услуга) | ✅ | `/termin/leistung/<pk>/` `service_slots` | совмещает «деталь+бронь»: фото/описание/цена, выбор мастера, дни ±1, **плоский список слотов** (нет визуал. календаря/AM-PM), контакт, extras, депозит |
| Форма слотов (ресурс/группа) | ✅ | `/termin/<pk>/` `termin_slots` | для столов/залов/групп (capacity>1), есть `party_size` |
| Выбор мастера (?resource=) | ✅ | `service_slots.html:23-48` | чипы + био; **но нет skill-matrix** (assign_resource берёт любого свободного) |
| Подтверждение брони | 🟡 | `/t/<code>/` `termin_confirmation` | детали + код; **нет .ics/add-to-calendar, карты/Anfahrt, ссылки отмены/переноса** |
| Отмена (self-service) | ✅ | `/konto/termin/<code>/stornieren/` | под логином; возврат депозита; нет отмены по токену для гостя (в отличие от stays) |
| **Перенос/Umbuchung (self-service)** | ❌ | — | `services.move()` есть, но только в кабинете владельца; клиент должен отменить+перезаписаться |
| ЛК клиента (история записей) | ✅ | `/konto/` | Termine (10) + Mehrfachkarten + отмена; нет «rebook wie letztes Mal» |
| Покупка Mehrfachkarte | ✅ | `/karten/` `karte_kaufen` | Stripe Connect |
| **Подарочный сертификат услуги** | 🟡 | (только `/gutschein/` у stays) | gift-voucher-flow привязан к отелю; для A3 нет страницы покупки/погашения на бронь |
| Правовое (Impressum/Datenschutz/Widerruf) | ✅ | общие маршруты | AGB нет (сквозной гэп) |

## 2. Что УЖЕ есть (паритет/выше рынка)

Онлайн-запись по слотам 24/7 (atomic anti-double-book) · богатая карточка услуги
(описание/фото/длит./цена) · **выбор мастера** с фото/био + пер-мастер расписание ·
модель Resource (staff/room/table) · **депозит/предоплата/no-show** (Stripe Connect) ·
**self-service отмена** + возврат депозита · **Mehrfachkarte/PassPlan** + онлайн-покупка ·
extras/доп-услуги · лояльность · ЛК с историей записей · **гостевая запись** (без
аккаунта) · часы работы/ClosedDate · real-time доступность (движок) · кабинет-календарь
владельца · email+Telegram-напоминания (beat).

## 3. Матрица «рынок ↔ наш статус»

| Фича рынка | Важн. | Статус | Заметка по гэпу |
|---|:--:|:--:|---|
| Онлайн-запись по слотам 24/7 | must | ✅ | ядро на месте |
| Богатая карточка услуги | must | ✅ | гэп старого отчёта «нет карточки» — устарел |
| **Standalone деталь услуги (SEO/deep-link)** | must | ❌ | каждый URL услуги = виджет брони; нет `service_detail.html` |
| Выбор мастера («Termin bei Lena») | must | ✅ | опционально; есть фото/био |
| **Skill-matrix (мастер↔услуга)** | should | ❌ | берётся любой свободный → барбер может попасть на окрашивание |
| **Визуальный календарь слотов (AM/PM)** | must | 🟡 | доступность считается верно, но UI — плоский список пилюль |
| Депозит/предоплата/no-show | must | ✅ | Stripe Connect |
| **Self-service перенос/Umbuchung** | must | ❌ | только отмена; `move()` лишь в кабинете |
| **SMS-напоминания** | must | ❌ | только email+Telegram; SMS-канала нет в модели |
| Email/Telegram-напоминания | must | ✅ | beat hourly |
| **Отзывы услуги/бизнеса у CTA брони** | should | 🟡 | инфра BusinessReview есть (на отеле выводится), но на A3-флоу не выводится; пер-услуга отзывов нет |
| Mehrfachkarte/Abo/пакеты | should | ✅ | PassPlan + онлайн-покупка |
| Abo/авто-продление членства | should | ❌ | PassPlan — разовая карта, не renewing |
| **Подарочные сертификаты услуги** | should | 🟡 | gift-flow только у отеля; не подключён к booking |
| Лояльность | should | ✅ | штамп-карта |
| ЛК с историей записей + rebook | should | ✅ | без one-tap rebook |
| Гостевая запись | must | ✅ | honeypot+ratelimit |
| **Buffer/Pufferzeit** | should | ❌ | back-to-back возможны (нет уборки/подготовки) |
| **Intake/Consent/Patch-Test/Alter** | should | 🟡 | только free-text note; паттерн вопросов есть в events, не в booking |
| **Waitlist на занятый слот/день** | should | ❌ | waitlist есть только у акций/событий |
| **Серийные/повторяющиеся записи** | should | ❌ | каждая бронь — один интервал |
| Группа (party_size) | should | 🟡 | только в generic-resource флоу, не в service |
| Мультилокация/филиалы | should | ❌ | один тенант = одна точка |
| **Календарь-синк (Google/Outlook/iCal)** | should | ❌ | iCal есть только у stays/events |
| **.ics/add-to-calendar + карта на подтверждении** | nice | ❌ | подтверждение без календаря/карты/ссылки отмены |
| Часы работы/праздники | must | ✅ | AvailabilityRule + ClosedDate |
| Кабинет-календарь владельца | must | ✅ | move/confirm/fulfill/no_show |

## 4. Недостающий функционал — приоритизировано (верифицировано)

### 4a. Презентация / конверсия (самый дешёвый и заметный слой)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| S1 | **Standalone деталь услуги** `/leistung/<pk>/` (info-страница, SEO/deep-link, кнопка → слоты) — общий гэп с A7/A9, см. D1 общего аудита | CONFIRMED_MISSING | **S** |
| S2 | **Визуальный календарь слотов** + группировка Vormittag/Nachmittag (заменить плоский список) | CONFIRMED_MISSING | M |
| S3 | **Отзывы услуги/бизнеса** у CTA брони (вывести BusinessReview на A3-флоу + пер-услуга) | PARTIAL | M |
| S4 | Полировка подтверждения: **.ics/add-to-calendar + карта/Anfahrt + ссылка отмены/переноса** | CONFIRMED_MISSING | S |

### 4b. Сервисные «table stakes» (есть у всех 4 лидеров)
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| B1 | **Клиентский перенос/Umbuchung** по self-service ссылке в рамках Frist (`move()` уже есть → нужен клиентский маршрут+UI+guard) | CONFIRMED_MISSING | M |
| B2 | **SMS-напоминания** (добавить SMS-канал за `notify()`-сеамом; email/TG уже есть) | CONFIRMED_MISSING | M |
| B3 | **Skill-matrix**: M2M Service↔Resource + фильтрация в availability/assign | CONFIRMED_MISSING | M |
| B4 | **Buffer/Pufferzeit** до/после услуги (поле + расширить блокируемый интервал) | CONFIRMED_MISSING | S |

### 4c. Удержание / выручка / вертикали
| # | Что | Вердикт | Размер |
|---|---|:--:|:--:|
| C1 | **Подарочный сертификат услуги** (адаптировать stays gift-flow к booking: покупка+погашение на бронь) | PARTIAL | M |
| C2 | **Waitlist** на занятый слот/день + авто-уведомление при отмене | CONFIRMED_MISSING | M |
| C3 | **Серийные/standing записи** (coaching/physio/Pilates) — модель серии + дочерние брони | CONFIRMED_MISSING | L |
| C4 | **Intake/Consent/Patch-Test/Altersnachweis** (Kosmetik/Tattoo) — схема формы per-Service, в рамках DSGVO Art.9/Heilberuf | PARTIAL | L |
| C5 | **Календарь-синк** мастера (Google/Outlook/iCal, two-way) — для коучей/физио | (не верифиц., 13-й) | L |
| C6 | Мультилокация/филиалы | (из матрицы) | L |

## 5. Сравнение с лидерами

- **vs Fresha** — паритет движка (anti-double-book, депозиты/no-show, Mehrfachkarte,
  extras, выбор мастера). Fresha берёт ~20 % с новых клиентов; мы — flat 39 €/мес,
  0 % комиссии, полное владение клиентской базой → **наш устойчивый клин**.
- **vs Treatwell** — это маркетплейс на ~35 % за первую запись на общем профиле; мы
  даём бизнесу свой сайт + свой список клиентов + гостевую бронь (анти-маркетплейс).
- **vs Planity** — у них SMS-напоминания + мульти-услуга-за-визит + отзывы у CTA;
  у нас **нет SMS, нет нескольких услуг в одной брони (Booking = 1 Service), нет
  отзывов на витрине** — три чистых паритет-гэпа к Planity.
- **vs Shore** — та же flat-модель (~49,90 €/мес), мы дешевле; Shore даёт buffer,
  calendar-sync и клиентский перенос, которых у нас нет.

**Net:** движок конкурирует head-to-head; разрыв — (1) клиентский перенос, (2) SMS,
(3) отзывы у брони, (4) визуальный календарь + .ics/карта + деталь услуги. Всё —
storefront/UX или тонкий notification-канал, не глубина движка.

## 6. Что устарело в отчёте 2026-06-25

**Доехало** (отчёт занижал): секция «services» в реестре главной + богатая карточка
услуги (фото/описание/длит./цена), выбор мастера с фото/био, PassPlan + онлайн-покупка,
extras, демо friseur с Lea/Jonas. **Осталось как было:** нет детали услуги, нет
переноса, нет SMS, нет skill-matrix, нет buffer, нет waitlist/серий, отзывы не на флоу.

## 7. Связанные
`docs/archetype-completeness-audit-2026-06-30.md` (D1 деталь услуги) ·
`docs/market-analysis/a3-termin-dienstleister.md` (снапшот) ·
`apps/booking`, `apps/account`, `apps/loyalty`, `apps/promotions`.
