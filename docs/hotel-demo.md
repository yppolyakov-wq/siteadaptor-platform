# Демо-сайт отеля «Pension Seeblick» — полный обзор функционала (A5)

Документ описывает **готовый демо-сайт отеля** на платформе и **что/как работает** по
всему функционалу архетипа A5 (Übernachtung). Соответствует реализованным подзадачам
**H1–H6, H9** (см. `docs/hotel-archetype-plan.md`, история — `docs/build-log.md`).

## 1. Как поднять демо

На сервере (схема-на-тенанта, ~1 мин на миграции):

```bash
python manage.py seed_demo_tenants --kit hotel        # → https://hotel.<base>/
python manage.py seed_demo_tenants --kit hotel --recreate   # пересоздать
python manage.py seed_demo_tenants --kit hotel --delete     # удалить
```

- Витрина публична: `https://hotel.<base>/`.
- Кабинет владельца: логин из вывода команды; пароль демо — `demo-12345678`.
- Весь контент создаётся `apps/tenants/demo_kits.py::apply_kit(tenant, "hotel")`
  (кит `HOTEL`). Проверяется тестом
  `apps/tenants/tests/test_demo_kits.py::test_apply_hotel_kit_builds_stays_site`.

## 2. Что внутри демо (данные «Pension Seeblick»)

- **4 типа номеров** (`StayUnit`), у каждого фото, описание, площадь, тип кровати,
  удобства:
  - Doppelzimmer Seeblick — 89 €/ночь, ×4, 2 гостя, 24 м², Queensize, WLAN/TV/Bad/
    Balkon/Kaffee, депозит 30 €, **Hochsaison 119 €** (01.07–31.08);
  - Einzelzimmer Komfort — 69 €, ×3, 1 гость, 16 м², Boxspring, Schreibtisch;
  - Familienzimmer — 129 €, ×2, 4 гостя, min 2 ночи, 32 м², Doppel+2 Einzel, Haustiere;
  - Ferienwohnung am Garten — 149 €, ×1, 4 гостя, min 3 ночи, 55 м², Küche/Terrasse.
- **4 тарифа** (`RatePlan`, H1): Basistarif (flex, бесплатная отмена до 7 дней),
  Mit Frühstück (+12 €/ночь), Halbpension (+28 €/ночь), Sparpreis nicht erstattbar (−12 %).
- **Extras** (`core.Extra`): Frühstücksbuffet 12 €/ночь, Parkplatz 8 €/ночь, später
  Check-out 20 €, Haustier 15 €.
- **Kurtaxe** 2,50 €/взрослый/ночь (H9). **Промокод** `SOMMER10` −10 % (H4a).
- **Hausordnung** (H6): check-in/out, Ruhezeiten, Haustiere, Rauchen, Kaution, Kinder, Storno.
- Отзывы (3, рейтинг), FAQ, галерея, команда, «Über uns», CTA, секция поиска на главной.
- 2 демо-брони (подтверждённые) — видны в кабинете в календаре загрузки.

## 3. Витрина (гость) — пошагово

### 3.1. Главная — `/`
- Hero «Pension Seeblick» + **секция быстрого поиска** (H2): Anreise / Abreise /
  Erwachsene / Kinder → кнопка «Suchen». Тизеры разделов, отзывы, FAQ, галерея,
  карта/контакты, переключатель **DE/EN** и тёмная тема. Полностью адаптивно (ТЗ §12).
- В `<head>` — **JSON-LD `Hotel`** (H6): имя, адрес, гео, `priceRange` («ab 69 €»),
  фото, `aggregateRating` (из отзывов). Open Graph/мета — базовые платформенные.

### 3.2. Поиск и список номеров — `/unterkunft/?von=…&bis=…&erw=2&kinder=0`
- Показывает **все номера** с доступностью на даты и ценой «ab … € total» за период
  (берётся дешёвый тариф). Недоступные — серым, с причиной (мин. ночей / вместимость /
  занято). Доступные — выше, дешевле — сверху. Карточка ведёт на номер с прокинутыми
  датами (H2).

### 3.3. Страница номера — `/unterkunft/<id>/`
- Галерея, описание; **блок фактов** (гости/площадь/кровать) и **сетка Ausstattung**
  с иконками (H3). Форма дат (Anreise/Abreise/Erwachsene/Kinder).
- После выбора дат — **выбор тарифа** (H1): по каждому тарифу видны цена за период,
  питание (Frühstück/Halbpension), **условия отмены ДО оплаты** (ТЗ §20). Чек-боксы
  **Extras**, поле **промокода**, строка «inkl. X € Kurtaxe».
- Блок **«Ähnliche Zimmer»** (H3). Кнопка «Jetzt buchen» (или «Weiter zur Zahlung»,
  если у номера задан депозит и подключён Stripe).

### 3.4. Бронирование → подтверждение — `POST /unterkunft/<id>/buchen/` → `/s/<code>/`
- Анти-овербукинг по ночам (атомарно), honeypot + rate-limit. Снимок в брони:
  тариф, питание/отмена, Extras, **скидка по промокоду** (на проживание+услуги, не на
  Kurtaxe), **Kurtaxe** (взрослые×ночи), **adults/children** (H5).
- Если задан депозит и есть Stripe Connect — оплата на счёт бизнеса (Checkout), иначе
  обычная бронь. Подтверждение `/s/<code>/`: разбивка гостей, тариф+условия отмены,
  Extras, «−X € Rabatt (SOMMER10)», «inkl. Kurtaxe», итог, реф-код, **ссылка «Stornieren»**.
- Письма гостю (created/confirmed) и владельцу; в письмах — ссылка на отмену и one-click
  отписку. То же дублируется в Telegram, если гость привязал бота.

### 3.5. Самоотмена — `/stornieren/<token>/` (H4b)
- Подписанная ссылка (из письма/подтверждения) → страница с **политикой отмены тарифа**:
  flexible до дедлайна = бесплатно (+возврат депозита через Stripe), nicht erstattbar =
  без возврата. Кнопка «Stornieren» → бронь отменяется (FSM), ночи освобождаются.

### 3.6. Hausordnung — `/hausordnung/` (H6)
- Правила проживания (свободный текст) + строка Kurtaxe. Ссылка — в футере витрины.
- Юр-страницы платформы: `/impressum`, `/datenschutz`, `/widerruf` (DSGVO).

## 4. Кабинет (владелец) — управление

- **`/dashboard/stays/`** — календарь загрузки (номера × ночи: свободно/занято/блок),
  список броней, действия по FSM (bestätigen/erledigt/no-show/stornieren), перенос дат,
  ручная бронь (телефон/стойка → сразу confirmed), «Rechnung erstellen».
- **`/dashboard/stays/units/`** — номера и настройки:
  - карточка **«Kurtaxe & house rules»** (H9/H6): ставка Kurtaxe, метка, текст Hausordnung;
  - **«Rate plans»** (H1): CRUD тарифов (процент/надбавка, питание, условия отмены, порядок);
  - по каждому номеру: цена/выходные/кол-во/min ночей/max гостей/депозит/ручное
    подтверждение, **площадь/кровать/чек-лист удобств** (H3), фото, блокировки дат,
    **сезонные тарифы**, **iCal** (экспорт занятости + импорт Booking.com/Airbnb).
- Счёт из брони → `apps.finance` (7 % Beherbergung; **Kurtaxe отдельной строкой без НДС**, H9).
- Промокоды — общий механизм `apps.loyalty.Voucher` (переиспользуется витриной брони).

## 5. Карта ТЗ → реализация

| Потребность ТЗ | Где в демо |
|---|---|
| Поиск по датам, доступность в реальном времени | Главная + `/unterkunft/` (H2), анти-овербукинг |
| Номера: фото/площадь/кровати/удобства/цена/отмена | Карточка номера (H3 + H1) |
| Тарифы (Basis/Frühstück/Halbpension/Sparpreis…) | RatePlan (H1) |
| Питание (Verpflegung) | meal_plan тарифа (H1) |
| Допуслуги в бронировании | core.Extra (#7) |
| Спецпредложения/скидки/промокоды | RatePlan + Voucher SOMMER10 (H1/H4a) |
| Взрослые + дети | adults/children (H5) |
| Онлайн-оплата/депозит | Stripe Connect (E4) |
| Условия отмены до оплаты + самоотмена | H1 (показ) + H4b (ссылка) |
| Kurtaxe / Tourismusabgabe | StaySettings (H9) |
| Правила проживания (Hausordnung) | `/hausordnung/` (H6) |
| SEO (Hotel-разметка, цена, рейтинг) | JSON-LD `Hotel` (H6/B5/G8) |
| Языки DE/EN, мобильная версия | базовые витрины |
| Каналы Booking.com/Airbnb (занятость) | iCal импорт/экспорт (A5b) |
| Юр-страницы (Impressum/Datenschutz/AGB) | базовые витрины |

## 6. Вне демо (сознательно, ТЗ §5.2/§6)

Метапоиск/Google Hotel Ads, полный двусторонний Channel Manager, большой PMS/замки/
касса, роли персонала, online-чекин/Meldeschein, revenue management. Двусторонний
агрегатор отелей (вертикальный портал-поиск) — следующий шаг **H8a/H8b**
(`docs/hotel-archetype-plan.md`).
