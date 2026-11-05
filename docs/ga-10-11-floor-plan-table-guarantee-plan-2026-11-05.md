# GA-10 «Grundriss» + GA-11 «Tischgarantie» — план (2026-11-05)

Запрос владельца (2026-11-05): ресторан рисует простой план помещения и расставляет на нём
столы с числом мест для брони. Этажей может быть несколько. Бронь может быть условно
платной: при отмене позже срока — плата, либо обязательная предоплата; это настраиваемая
опция. Проверить рынок.

Статус: **план, кода нет** (часть решений принята, см. §6). Семейство — Gastro (`GA-*`, продолжение
GA-0…GA-9 волны 4 KA-12). Два трека, связанных только общими инкрементами витрины:

- **GA-10 «Grundriss»** — план зала с этажами: редактор, живой план, выбор зоны гостем.
- **GA-11 «Tischgarantie»** — правила отмены, предоплата и гарантия картой для брони стола.
- **GA-10.9 «Tisch sperren»** — быстро выключить стол, который уже занят или зарезервирован
  мимо системы (телефон, другая платформа, гость сел без брони). Добавлено 2026-11-05.
- **GA-12 «Kassenanbindung»** — интеграция с кассой ради реальной занятости столов.
  Добавлено 2026-11-05.

Решения владельца 2026-11-05: Р-2 ✅ · Р-3 ✅ · Р-5 ✅ (опция в правиле) · Р-7 ✅ · Р-9 ✅;
GA-10.9 и GA-12 — добавить в план, код не начинать.

---

## 1. Что уже есть (разведка кода 2026-11-05)

| Что | Где | Для плана |
|---|---|---|
| Стол = `booking.Resource(type=table)`: `seats`, `min_seats`, `zone` (строка), `sort_order`, `bookable_online` | `apps/booking/models.py` (GA-3) | Добавляем координаты и этаж. `zone` остаётся «Bereich» |
| Комбинации «Tisch 3+4» (`Resource.parts`), занятость области | `booking/occupancy.py` (GA-5) | Не трогаем, подсказываем по соседству |
| Автоподбор стола (наименьший подходящий), исходы INSTANT/REQUEST/CALL | `booking/table_rules.py`, `availability.table_slots`, `public_views.tisch_book` (GA-1/GA-4) | Фильтр по зоне/этажу добавляется перед подбором |
| Экран «Tischplan»: плитки по зонам на момент времени, walk-in, «Tisch zuweisen» | `booking/tischplan.py`, `templates/booking/tischplan.html` (GA-6) | Слой чтения переиспользуем 1:1, меняем только раскладку |
| Демо зала: 8 столов в двух зонах + «Tisch 3+4» | кит restaurant (GA-7) | Демо получит план и этаж |
| Депозит стола — **фиксированный, на стол** (`Resource.deposit_cents`) | `tisch_slots`/`tisch_book` | Не «за гостя», возврат без окна |
| **Правила отмены — только у услуги** (`Service.cancel_window_hours/late_cancel`), снимком в `Booking.cancel_policy` | `booking/cancel_policy.py` (B6) | **Бронь стола создаётся с `service=None` → снимок `{}` → «бесплатно до начала, всегда возврат».** У ресторана правил отмены сейчас нет вообще. Режимы снимка — только `keep\|refund` (удерживается вся Anzahlung, процентов нет, `:68-80`, `:176`) |
| Шкала Stornogebühr | `events/details.py::normalize_fee_steps` (T-4a, `:221`) | **В ДНЯХ**, пары `{days, percent}` «за ≤N дней — X %». Столам нужны часы → свой нормализатор (общий не трогаем, паритет T-4a) |
| Частичное удержание при отмене | `core/refunds.py::refund_cancel_fee` (`:399`), `refund_partial` (`:554`) | Механика удержания процента уже есть — переиспользуем |
| Депозит после N неявок | `booking/no_show_rule.py::amount_cents` (E6.4c, `:118`) | Сегодня **первое ненулевое** (депозит ресурса → сумма правила → цена), не максимум — формулу меняем явно (§4.6) |
| Сохранённая карта + списание без гостя | `billing.connect.installment_checkout_session` (`setup_future_usage=off_session`) + `mandate_from_payment_intent` + `charge_off_session` (R10) | Основа «Kartengarantie»; нужен Checkout `mode="setup"` и чтение мандата из **SetupIntent** |
| Вебхук connected-аккаунтов | `billing/webhooks.py::CONNECT_KINDS` (`:57`) | Новый вид не из списка молча отбрасывается как платформенный (`:112-121`) |
| Удержание места до оплаты | `core/payment_holds.py` (`expire_overdue`, `start_online_hold`, `STRIPE_MIN_SESSION` 30 мин + `SESSION_MARGIN` 15 мин) | Минимум удержания ≈ 45 мин; обработчик гарантии обязан обнулить `payment_due_at` |
| Фолио, онлайн-остаток, возвраты | `core/folio.py` (`record`/`record_online`), `core/balance_pay.py`, `core/refunds.py` | Плата пишется в фолио. **`balance_pay.rest_payable` для платы после неявки НЕ подходит** (требует `payment_state=deposit`, неотменённую сделку и `start > now`, `:60-75`) |
| Блокировка ресурса | `booking.ClosedDate` (`models.py:357`) — **только целый день**, без времени | Для «стол занят сейчас» нужен `TableHold` с интервалом (§3.7) |
| Занятость стола | считается в нескольких местах: `availability`, `services` (пересечение, `_would_overfill`), `tischplan`, `occupancy.scope_ids` для области | Блок/касса обязаны попасть во ВСЕ — одна функция `busy_intervals` (§3.7) |
| Исходящие вебхуки | `apps/integrations/webhooks` (`OutgoingWebhook`, `WebhookDelivery`), паттерн HMAC | Касса → нас — входящий HMAC-вход по тому же паттерну (§4b) |
| Ссылка гостя «Termin verwalten» | B6, `notifications.py:81-87` | Ставится только при снимке с `v` → у столов её сейчас нет; самоперенос требует `service_id` (`cancel_policy.py:103`) — у столов перенос гостем не делаем |
| Учёт денег брони стола | `Booking.price_cents=0` → `total_cents=0` (`models.py:621`), выручка при `fulfilled` не пишется (`state_machine.py:68`) | Плата без своей строки в контракте дала бы «переплату» (`refunds.overpaid_cents`, `:708`) — нужна явная строка (§4.5) |

Вывод: GA-10 — это в основном фронтенд и одна аддитивная миграция. Логика брони не меняется.
GA-11 серьёзнее: у столов нет правил отмены, а гарантии картой нет вообще (есть только
сохранение карты внутри оплаты рассрочки).

## 2. Рынок (проверено 2026-11-05)

**План зала у персонала — стандарт.** resmio продаёт онлайн-Tischplan с iPad-приложением,
drag & drop брони на стол и статусы «frei/reserviert/belegt» в реальном времени
([resmio](https://www.resmio.com/en/planning/visual-table-plan-software/)). В aleno сначала
создаётся помещение (Raum), затем графический план столов
([aleno](https://knowledge.aleno.me/en/kb/create-a-graphical-table-plan-in-aleno)). У Tablein
есть редактор плана зала ([Tablein](https://tablein.com/blog/restaurant-table-management-software)).
Графический план есть и в кассах (Melzer, [handbuch](https://handbuch.melzer-kassen.com/pdf/v18/seiten/handbuch/boniersystem/grafischen-tischplan-bearbeiten.pdf)).
Каталог SoftGuide описывает «Tischplanung» как графическое изображение зала с позициями
столов ([SoftGuide](https://www.softguide.de/funktion/tischplanung)). Явной поддержки
**нескольких этажей** в найденных материалах нет: у aleno многоуровневость достигается
несколькими помещениями (Räume). Значит, «этаж = лист плана» — разумная модель, соответствующая рынку.

**Гость выбирает ЗОНУ, а не стол.** Tablein: «select dining area», система сама ищет места
в зоне, зону можно сделать обязательной ([1](https://help.tablein.com/dining-area-selection),
[2](https://help.tablein.com/require-to-select-dining-room)). aleno — выбор помещения в
виджете ([aleno](https://knowledge.aleno.me/en/kb/raumauswahl-im-widget)), Zenchef — то же
([Zenchef](https://help.zenchef.com/hc/en-gb/articles/5277296302877-How-to-set-up-the-room-selection)).
Выбор конкретного стола гостем — нишевая функция (Tablz, Digital Diner:
[1](https://www.tablz.com/posts/the-future-of-dining-personalized-table-selection-for-unforgettable-experiences),
[2](https://hospitalitytech.com/guests-can-specify-exact-table-their-reservation)). У resos
стол выбирает персонал ([resos](https://resos.com/support/how-to-select-tables-on-a-booking/)).
У крупных систем (SevenRooms, TableCheck) план — инструмент персонала.

**Гарантия картой + плата за позднюю отмену — общепринятая практика.** Tablein: данные карты
как гарантия, списание только при неявке или поздней отмене
([Tablein](https://help.tablein.com/how-to-save-card-details-and-charge-in-case-of-no-show-or-last-minute-cancellation)).
Немецкие AGB ресторанов: бесплатная отмена за 24 ч ([Hugenpoet](https://hugenpoet.de/en/restaurants/book-a-table-terms-conditions))
или 48 ч ([Grill Royal](https://www.grillroyal.com/en/rechtliches/agb)); ступени 50 % за
48–24 ч и 100 % менее чем за 24 ч; фиксированная плата за гостя (Pfistermühle: 15–45 € и
оговорка «вы можете доказать меньший ущерб»; карта — только для компаний от 3 человек,
[AGB](https://www.pfistermuehle.de/fileadmin/user_upload/PDFs/Pfistermuehle/AGB_Pfistermuehle_EN_20.03.2026.pdf)).
По отчёту OpenTable, неявка пары стоит ресторану в Германии в среднем 87,60 €
([hogapage](https://www.hogapage.de/nachrichten/wirtschaft/gastronomie/wenn-der-leere-tisch-teuer-wird/)).

**Право (DE) — ориентиры, не заключение юриста.** Плата за неявку в принципе допустима, если
она согласована заранее (AGB, явное указание при бронировании) и соразмерна. Завышенная
плата — § 307/§ 138 BGB ([Verbraucherzentrale Niedersachsen](https://www.verbraucherzentrale-niedersachsen.de/themen/kaufen-reklamieren/ausfallgebuehr-no-show-gebuehr-was-ist-das-muessen-sie-sie-bezahlen),
[tageskarte](https://www.tageskarte.io/gastronomie/detail/no-show-gebuehren-in-der-gastronomie-worauf-wirte-achten-sollten.html),
[DEHOGA-Merkblatt](https://www.dehoga-bayern.de/fileadmin/USERFILES/Aktuelles/Merkblatt_No_Shows_in_der_Gastronomie_-_Stand_September_2019_final.pdf)).
Для паушальной суммы в AGB действует § 309 Nr. 5 BGB: сумма не выше обычного ущерба, и
гостю прямо оставлено право доказать меньший ущерб (так и сделано в образце Pfistermühle).
По Австрии — [WKO](https://www.wko.at/vlbg/tourismus-freizeitwirtschaft/gastronomie/noshow-gebuehren-in-der-gastronomie).

**Касса ↔ бронь.** resmio подключает orderbird, LINA POS / Amadeus 360, APRO и Duratec /
Vectron. У LINA и Amadeus 360 план столов в кассе обновляется сам, и детали брони видны
при расчёте; у Vectron брони можно печатать с кассы
([resmio](https://www.resmio.com/en/interfaces-partners/)). Лучше всего описана связка
Lightspeed K-Series ↔ aleno: брони появляются в кассе, гостей отмечают «пришёл/ушёл» в плане
столов кассы, после закрытия счёта касса возвращает в aleno данные гостя, заказа и суммы
([Lightspeed](https://k-series-support.lightspeedhq.com/hc/en-us/articles/18061152320411-Setting-up-and-using-the-Aleno-integration)).
Lightspeed также напрямую подключает OpenTable, Resy, SevenRooms и TheFork
([Lightspeed](https://k-series-support.lightspeedhq.com/hc/en-us/articles/39502756607131-About-reservations-integrations));
по обзору OpenTable↔Lightspeed, открытие брони за столом создаёт счёт в кассе, оплата счёта
переводит бронь в «Paid», а включается связка вручную
([Lightspeed partner](https://partner.lightspeedhq.com/pages/integration-page)). По
сторонним описаниям API K-Series вебхуки есть на заказы, оплаты и персонал, но **отдельного
события «стол занят» не нашлось** — занятость выводится из открытого заказа на столе
([Jentic](https://jentic.com/apis/lightspeed), [storekit](https://storekit.com/docs/guides/integrations/pos/lightspeed-k-series)).
Публичного API orderbird в поиске не нашлось. Вывод: интеграция с кассой — работа
«по одному адаптеру на кассу» с партнёрским доступом. Ручная блокировка стола нужна в
любом случае: касс много, и не у всех есть API.

**Вывод для продукта:**
1. Редактор и живой план — для персонала (так делает весь рынок).
2. Гостю — выбор зоны или этажа («Terrasse», «1. OG», «barrierefrei»); выбор конкретного
   стола — опция владельца, выключенная по умолчанию.
3. Три режима денег: без гарантии · предоплата · гарантия картой. Ступени отмены и правила
   для групп или особых дат — настраиваемые; шаблон текста условий содержит оговорку
   § 309 Nr. 5 b.

---

## 3. GA-10 «Grundriss» — дизайн

### 3.1 Модель (одна аддитивная миграция `booking/00xx`)

```
FloorPlan  («Ebene» — этаж или отдельное помещение)          TENANT
  name, name_i18n          «Erdgeschoss», «1. OG», «Terrasse», «Wintergarten»
  level  SmallInt          −1 Keller · 0 EG · 1 OG … (сортировка, подпись)
  width, height  SmallInt  размер листа в клетках сетки (по умолч. 40×24; кап 200×200)
  step_free  Bool          barrierefrei erreichbar (лифт/без ступеней)
  (is_outdoor — НЕ в 10.1: «закрыть террасу на день» массово создаёт ClosedDate и
   задевает брони → отдельный инкремент GA-10.8)
  elements  JSON           [{id, kind, x, y, w, h, rot, label}] — стены, двери, окна,
                           бар, лестница, растение, подпись, «Bereich»-прямоугольник; кап 300
  sort_order, is_active
  version  PositiveInt     оптимистичная блокировка редактора (409 при чужом сохранении)

Resource (+ только для type=table, все nullable → старые столы целы)
  floor  FK FloorPlan SET_NULL
  pos_x, pos_y, pos_w, pos_h  SmallInt   в клетках
  pos_rot  SmallInt        0…315, шаг 45
  shape  CharField         rect | round
```

- **`zone` остаётся «Bereich» (строка) — источником истины для подбора и витрины.**
  Прямоугольник `kind=area` на листе — только рисунок с подписью зоны. Это делает миграцию
  аддитивной и не трогает GA-1…GA-9.
- **Авто-раскладка без данных.** Стол без координат рисуется функцией
  `floorplan.auto_layout(tables)` (сетка по зонам в порядке `sort_order`) на листе
  «Erdgeschoss», который создаётся виртуально (в БД не пишется до первого Save). Существующий
  ресторан сразу видит план, бэкфилл не нужен.
- Этаж без активных столов на витрине не показывается. Удаление этажа не удаляет столы:
  `floor → NULL`, они попадают в «Nicht platziert».

### 3.2 Редактор `/dashboard/booking/grundriss/` (право — как у ресурсов)

- Вкладки этажей (`ui-tab`) + «＋ Etage». У каждого листа: имя, уровень, barrierefrei,
  Außenbereich, размер.
- SVG-холст с сеткой и привязкой к клетке. Палитра: «＋ Tisch rund/eckig» (открывает
  существующую шторку «Neue Ressource» с этажом и координатами), стена, дверь, окно, бар,
  лестница, растение, подпись, «Bereich».
- Колонка «Nicht platziert»: столы без этажа, перетаскиваются на лист.
- Действия: перетащить, потянуть за угол, повернуть (кнопка/R), отменить (Ctrl+Z, стек на
  сессию редактора), убрать с плана (Del — стол остаётся ресурсом).
- **Клавиатура (a11y):** Tab по объектам, стрелки — сдвиг на клетку, Shift — на 5,
  `aria-live` сообщает «Tisch 4 · Spalte 12, Reihe 3». Обычный список ресурсов остаётся
  полной альтернативой.
- **Телефон/планшет:** pointer events (мышь + палец), кнопки масштаба; полноценное
  редактирование — от планшета, на телефоне просмотр + сдвиг стрелками (Р-6).
- **На план ставятся только активные одиночные столы.** Комбинации (`Resource.parts` не
  пуст) и нестоловые ресурсы своей схемы не размещаются (схемы тенантов изолированы, так
  что реальный риск — именно они, а не чужой тенант); комбинация рисуется на живом плане
  обводкой своих столов.
- **Сохранение:** `POST` JSON целого листа `{version, tables:[…], elements:[…]}` →
  серверная валидация (только активные одиночные столы type=table, координаты в границах,
  уникальные id элементов, капы, длина подписей) → одна `atomic` с `select_for_update`
  листа → версия не совпала → 409 «Plan wurde inzwischen geändert». Без JS экран показывает
  read-only план + список.
- Реализация — vanilla JS `static/js/floorplan.js` (как `cabinet.js`), без библиотек.

### 3.3 Живой план (Tischplan по этажам)

- `tischplan.html` получает режим «Plan»: те же `Tile` из `tischplan.py`, разложенные по
  координатам; вкладки этажей; время — существующий выбор момента.
- Состояние — **цвет + текст** (не только цвет): frei bis 20:30 · reserviert ab 19:00 ·
  belegt (über 3+4) · Pool N/M Plätze.
- Клик по столу → шторка брони или walk-in, те же приёмники, что сейчас (`create_manual`,
  `services.move`). Перетаскивание брони на другой стол — v2 (Р-8).
- Переключатель «Plan | Liste» (persist как у видов продаж); «Liste» = нынешний экран.

### 3.4 Комбинации по соседству

- Столы одного этажа, чьи прямоугольники касаются или отстоят на ≤ 1 клетку, без готовой
  комбинации → подсказка «Tisch 3 + 4 zusammenstellen?» → существующая форма комбинации.
  Автосоздания нет.

### 3.5 Витрина: зона, этаж, barrierefrei

- В «Tisch reservieren» необязательный выбор «Bereich»: варианты = этажи и зоны, где есть
  `bookable_online`-столы, подходящие по числу гостей; «Egal» по умолчанию.
- Флажок «Barrierefrei» → только `step_free`-этажи.
- Подбор — прежний `table_slots`, но кандидаты сначала фильтруются по выбору гостя; занятый
  кандидат уступает следующему (GA-4) только **внутри** выбранной зоны.
- Выбранная зона пишется снимком в бронь (поле `Booking.requested_area`, Р-4) и видна на
  карточке брони и в Tischplan.

### 3.6 Выбор конкретного стола гостем (опция, выкл. по умолчанию)

- Тумблер владельца на этаже: «Gäste dürfen den Tisch wählen».
- Витрина показывает read-only SVG этажа: свободные подходящие столы — кнопки, прочие
  приглушены; мобильный и экранный ридер получают список тех же столов.
- Сервер перепроверяет всё (стол этого тенанта, онлайн, вместимость, свободен) — клиенту не
  верим. При гонке — честная ошибка с предложением соседнего стола, без молчаливой замены.

### 3.7 GA-10.9 «Tisch sperren» — быстрое выключение стола

Зачем: стол уже занят или обещан мимо системы (звонок, другая платформа, гость сел без
брони, стол сломан). Сейчас есть только блокировка **на весь день** (`ClosedDate`) и walk-in
(создаёт бронь с гостем, лишнее для «просто занят»).

**Модель `TableHold`** (TENANT, одна аддитивная миграция; общая с GA-12):

```
TableHold
  resource  FK Resource CASCADE      стол (комбинация блокирует свои столы — та же область)
  start, end  DateTime               end обязателен (нет «навсегда»: максимум до конца дня/смены)
  scope      online | all            «nur online» — стол не продаётся на сайте, персонал может
                                     посадить; «komplett» — занят для всех путей
  source     manual | pos            кто поставил (GA-12 пишет pos)
  reason     CharField(blank)        «Telefon», «Defekt», «Stammgast» …
  external_ref CharField(blank)      id открытого счёта в кассе (GA-12), unique per source
  created_by FK User NULL
  released_at DateTime NULL          «Freigeben» = released_at=now (история остаётся)
```

**Одна функция занятости.** Сейчас занятость стола считается в нескольких местах
(`availability`, `services` — проверка пересечения и `_would_overfill`, `tischplan`, слоты
витрины). Вводим `occupancy.busy_intervals(resource_ids, start, end, *, for_online)` —
брони ∪ активные `TableHold` той же области (`scope_ids`) — и переводим на неё все места;
замок «каждый путь брони видит блокировку» (витрина `tisch_book` и `/termin/`, ручная
запись, перенос, подбор GA-4, слоты, Tischplan). `scope=online` учитывается только при
`for_online=True`.

**Интерфейс — одно-два касания:**
- На плитке стола в Tischplan и на живом плане: кнопка «🔒 Sperren» → нижний лист с
  длительностью: «1 Std · 2 Std · 3 Std · bis Schichtende · bis …» и переключателем
  «Nur online / Komplett»; повторное касание — «Freigeben».
- Массово: «Alle Tische auf der Terrasse online sperren — heute» (этаж/зона × день).
- Быстрый доступ с телефона: тот же лист в Mini App «Mein Laden» (лёгкий кабинет) — v2.
- Если на стол уже есть бронь в этот промежуток — блок **ставится**, но показывается
  предупреждение «Tisch 4 hat um 19:30 eine Reservierung — umsetzen?» со ссылкой
  «Tisch zuweisen». Бронь молча не отменяется и не переносится.
- Право — как walk-in (персонал зала), без денег.
- Блок с `source=pos` вручную снимается только с подтверждением («Kasse meldet: Tisch
  offen»).

---

## 4. GA-11 «Tischgarantie» — дизайн

### 4.1 Три режима (правило владельца)

| Режим | Что платит гость при бронировании | Отмена до срока | Поздняя отмена / неявка |
|---|---|---|---|
| **Ohne** (по умолчанию) | ничего | бесплатно | ничего (можно включить только информирование и подсчёт неявок E6.4a) |
| **Vorauszahlung** | сумма сразу (Checkout) | возврат полностью | удержание по ступеням; опция «auf die Rechnung angerechnet» (Anzahlung) или нет (Reservierungsgebühr) |
| **Kartengarantie** | ничего, карта сохраняется (Checkout `mode="setup"`) | ничего, карта освобождается | списание по ступеням — **вручную** кнопкой владельца (Р-3) |

Сумма: «pro Person» или «pro Reservierung». Ступени — **в часах**, свой нормализатор
`booking/table_policy.py::normalize_hour_steps` (событийный `normalize_fee_steps` работает
в днях и с обратным смыслом — не обобщаем): «kostenlos bis 24 h vorher · 50 % bis 0 h ·
Nichterscheinen 100 %». Удержание процента — существующим `refunds.refund_cancel_fee`.

### 4.2 Где правило живёт

**Отдельный ключ `site_config["booking"]["table_policy"]`, рядом с `tables`, а не внутри.**
Причина (ревью): `normalize_booking` пересобирает `tables` только из `instant_max`/
`online_max` (`siteconfig.py:4194`) — вложенный ключ стёрся бы; а материализация `tables`
ради политики включила бы правило GA-1 с `instant_max=0` (`table_rules.decide`) → каждая
бронь стала бы Gruppenanfrage. Presence-minimal, golden-замок; нет ключа = прежнее
поведение байт-в-байт:

```
{ "mode": "none|prepay|guarantee",
  "amount_cents": 2500, "per": "person|booking", "credit": true,
  "steps": [{"h": 24, "pct": 0}, {"h": 0, "pct": 50}], "no_show_pct": 100,
  "rules": [  # особые правила; первое подходящее выигрывает, затем базовое
     {"label": "Silvester", "dates": [["2026-12-31","2026-12-31"]], "mode": "prepay", …},
     {"label": "Gruppen ab 8", "min_party": 8, "mode": "guarantee", …},
     {"label": "Terrasse", "floors": [<id>], …} ] }   # кап 10 правил
```

- Правило, депозит стола (`Resource.deposit_cents`) и E6.4c — см. §4.6 (явная формула).
- Экран — «Buchungsregeln» (D2.1), раздел «Tische»: режим, сумма, ступени, особые правила,
  живой предпросмотр текста условий для гостя. Право — `preise.edit` (как предоплата услуги).

### 4.3 Снимок и отмена

- При брони — снимок политики v2 в `Booking.cancel_policy`
  (`{"v": 2, "mode", "amount_cents", "steps", "no_show_pct", "credit", "text_hash"}`),
  `cancel_policy.py` учится читать v2 (v1 и `{}` — прежнее поведение, замки). Правка правила
  не меняет уже сделанные брони.
- Гость видит условия **до отправки**: блок «Stornobedingungen» с суммой и сроком,
  обязательный чекбокс «Ich akzeptiere die Stornobedingungen» (снимок текста + хэш в брони);
  письмо-подтверждение повторяет «Kostenlos stornierbar bis Fr, 19.12., 19:00».
- Ссылка гостя «Reservierung verwalten» — для столов **только отмена** с показом удержания
  «сейчас» (письмо получает `manage_url` при снимке v2; самоперенос стола — нет).
- Отмена из кабинета (`refunds.needs_choice`) предлагает удержание по снимку, а не по
  текущему правилу.
- Решение «вернуть / удержать» фиксируется в момент отмены (грабля B6), повтор решает по
  снимку.

### 4.4 Kartengarantie — механика

- Новый `connect.setup_checkout_session` (Checkout `mode="setup"`, `payment_method_types=["card"]`,
  metadata и в сессии, и в `setup_intent_data`, текст мандата о будущем списании) на connected
  account. **Customer создаётся заранее** на connected account (поддержка `customer_creation`
  в setup-режиме — проверить по документации Stripe в 11.3a; заранее созданный — надёжнее).
- Вебхук: новый вид `booking_guarantee` **в `CONNECT_KINDS`** (иначе событие отбрасывается).
  У setup-сессии `payment_intent` пуст, `payment_status=no_payment_required` → customer/PM
  читаются из **SetupIntent** (`mandate_from_setup_intent`, аналог `mandate_from_payment_intent`);
  сверка `event.account` (SEC-D1), дедуп по session id. Обработчик ставит
  `guarantee_state=ready` и **обнуляет `payment_due_at`** (как `mark_deposit_paid`), иначе
  `expire_overdue` снимет уже гарантированную бронь. Бронь подтверждается только после этого.
- Удержание стола до завершения гарантии/предоплаты — **не меньше ≈ 45 мин** (30 мин минимум
  сессии Stripe + 15 мин запаса, `payment_holds`); `start_online_hold` сейчас заточен на 24 ч —
  нужен параметр длительности (Р-7).
- Списание: карточка брони при `no_show` или поздней отмене → кнопка «Ausfallgebühr belasten»
  с суммой из снимка (можно уменьшить, нельзя увеличить) → `charge_off_session`
  (ключ идемпотентности = бронь + сумма) → фолио `folio.record_online` + выручка (§4.5).
  Право — как у возврата (owner или бухгалтер). Отказ карты / SCA → письмо гостю со
  **своей ссылкой оплаты платы** (новый вид `booking_fee` в `CONNECT_KINDS`; `balance_pay`
  не подходит — он требует депозит и будущую дату), состояние «Gebühr offen»; таймаут
  Stripe ≠ отказ (грабля B2-4a).
- «Gebühr erlassen» — закрывает без списания.
- **DSGVO/минимизация:** после посещения или отмены без платы — `guarantee_state=released`,
  через 14 дней beat отвязывает payment method в Stripe и чистит ссылки.
- Новые поля `Booking`: `guarantee_state`, `guarantee_customer_id`, `guarantee_pm_id`,
  `fee_charged_cents` (одна миграция в GA-11.3).

### 4.5 Деньги и налог

- Vorauszahlung «angerechnet» = Anzahlung: идёт существующим путём депозита (фолио, остаток,
  B2-8 Mindest-Ist/Anzahlungsrechnung).
- **У брони стола нет цены** (`total_cents=0`, выручка при `fulfilled` не пишется).
  Поэтому плата — **явная строка денежного контракта** (`fee_charged_cents` входит в
  total/due брони): иначе уплаченная плата выглядит «переплатой» (`overpaid_cents`) и кабинет
  предложит её вернуть. Выручка пишется в момент удержания/списания (поздняя отмена,
  неявка), а не при `fulfilled`. Reservierungsgebühr (не angerechnet) — выручка при визите.
- «Angerechnet» без чека в системе (ресторан пробивает счёт на своей кассе): предоплата
  остаётся обязательством к зачёту, в журнал как выручка не идёт — замок «нет двойного
  учёта» (Р-10).
- Удержанная плата и списание по гарантии — **вопрос Steuerberater'у (Р-5):** Entgelt
  (USt) или Schadensersatz (без USt); EuGH C-295/17 (MEO) сдвигает практику к «Entgelt».
  **Решение Р-5: опция в правиле** — «mit USt (Satz) / ohne USt», подсказка
  «mit Steuerberater klären»; по умолчанию как у B6-удержания.

### 4.6 Точки встраивания (из ревью кода)

- **Сумма к оплате:** `max(policy_amount, Resource.deposit_cents, E6.4c)` — меняем
  `no_show_rule.amount_cents` (сейчас «первое ненулевое»). Гостю с неявками режим
  guarantee повышается до prepay (карта уже не защищает от повторной неявки).
- **Автоподтверждение:** `auto_confirm` в `tisch_book` сейчас смотрит только
  `candidate.deposit_cents` — режимы prepay/guarantee тоже его блокируют. Сочетание с GA-1:
  REQUEST (Gruppenanfrage) + guarantee — гарантия собирается сразу, подтверждает владелец;
  INSTANT + guarantee — подтверждение после вебхука.
- **Обход политики:** `/termin/<pk>/` бронирует любой стол с `bookable_online`
  (`termin_book`). Политика и выбор зоны применяются в `_termin_book_core` при
  `resource.type == table`, а не только в `tisch_book` — замок «оба пути дают один снимок».
- **Ручные брони** (`create_manual`, стойка, Tischplan): согласия гостя нет → политика не
  применяется; опционально «Garantie-Link senden» гостю (v2).
- **Новые экраны** — в `view_perms` и `nav_registry` (чеклист `cabinet-screen-dod.md`).

---

## 4b. GA-12 «Kassenanbindung» — дизайн

Цель — **реальная занятость столов** без ручных действий: касса знает, где сидят гости
(открытый счёт на столе), система бронирования — кто придёт. Плюс отметка «гость пришёл»
и «счёт оплачен» у брони.

### 4b.1 Что синхронизируем

| Направление | Событие | Что делаем у нас |
|---|---|---|
| Касса → мы | счёт открыт на столе X | `TableHold(source=pos, scope=all, external_ref=<id счёта>, end=now+типичная длительность)`; если на стол есть бронь «скоро/сейчас» — бронь отмечается «Gast da» (check-in) |
| Касса → мы | позиции добавлены / счёт жив | продлеваем `end` блока (сердцебиение) |
| Касса → мы | счёт закрыт / оплачен | блок `released_at=now`; связанная бронь → `fulfilled` штатным FSM; предоплата «angerechnet» → отметка «verrechnet» (Р-10); сумма счёта — в карточку клиента CRM (LTV), **не в журнал выручки** (Р-12) |
| Касса → мы | стол перенесён в кассе | блок переезжает на другой стол |
| Мы → касса (v2) | новая/изменённая бронь | бронь видна в плане столов кассы (у кого касса это умеет) |

Если касса не присылает событие «стол занят» (как у Lightspeed K-Series по найденным
описаниям), занятость выводится из открытого заказа с номером стола.

### 4b.2 Архитектура

- Пакет `apps/integrations/pos/`: `PosConnection` (TENANT: провайдер, зашифрованные
  ключи — как SEC-волна 3, location id, статус, `last_event_at`) + `PosTableMap`
  (id стола в кассе ↔ `Resource`; экран сопоставления с подсказкой по номеру стола).
- **Адаптер на кассу** с общим интерфейсом `parse_event(request) → [PosEvent]`,
  `fetch_open_checks()` (сверка опросом), `push_reservation()` (v2). Первый адаптер —
  касса с публичным API и вебхуками (кандидат — Lightspeed K-Series; партнёрский доступ —
  шаг владельца). orderbird, Vectron и прочие — по наличию API/партнёрства.
- **Generic-вход для кассы без готового адаптера:** HMAC-подписанный вебхук
  (`docs/references/patterns/webhook-hmac-signing.md`) с простым форматом
  `{table, event: opened|closed|moved, check_id, at}` — чтобы кассовый интегратор или
  middleware мог подключиться без нашей разработки.
- Входящие события: отказ до БД при неверной подписи, обработка в Celery
  (`idempotent_task`, дедуп по `provider + event id`), порядок событий по времени кассы
  (позднее «opened» не воскрешает закрытый счёт).
- **Сверка опросом** (beat, раз в N минут в часы работы) — страховка от потерянных
  вебхуков: блок без подтверждения кассы снимается.

### 4b.3 Отказоустойчивость (главный риск)

- **Протухший блок не держит стол вечно:** у `source=pos` всегда есть `end`; нет
  сердцебиения/сверки → блок истекает сам.
- **Касса молчит** (нет событий X минут в часы работы) → плашка в Tischplan и на главной:
  «Kasse nicht verbunden — Belegung evtl. veraltet»; онлайн-бронь продолжает работать по
  броням и ручным блокам.
- Касса — не источник истины для денег и броней: мы не отменяем и не создаём брони по
  событиям кассы (только check-in, fulfilled, блок).

---

## 5. Инкременты и порядок

| # | Что | Миграция | Зависит |
|---|---|---|---|
| **GA-10.0 ∥ GA-11.0** | Замки ДО кода (параллельно): Tischplan (плитки/состояния), подбор GA-4, легаси-отмена стола «бесплатно до начала», снимок v1/`{}` неизменен, **нет `table_policy` → `decide()` GA-1 прежний**, golden `normalize_booking` | — | — |
| **GA-10.1** | `FloorPlan` + поля стола + `requested_area` + `auto_layout` + read-only рендер плана в Tischplan за переключателем | ⚠️ booking (аддитивная) | 10.0 |
| **GA-10.2a** | Серверное сохранение листа: JSON-приёмник, валидация (только активные одиночные столы), капы, версия → 409 | — | 10.1 |
| **GA-10.2b** | SVG-холст и JS: перетаскивание, размер, поворот, элементы, «Nicht platziert», Undo | — | 10.2a |
| **GA-10.2c** | Клавиатура, `aria-live`, палитра элементов, планшет | — | 10.2b |
| **GA-10.3** | Живой план: этажи, состояния текстом и цветом, клик → шторка, «Plan \| Liste» | — | 10.2 |
| **GA-11.1** | Правила отмены столов без денег: ступени в часах, ключ `table_policy`, снимок v2, условия + чекбокс на витрине (**за флагом юр-вычитки, Р-9**), письма, отмена по ссылке гостя, оба пути брони (`tisch_book` и `_termin_book_core`) | — | 11.0 |
| **GA-11.2** | Vorauszahlung pro Person/Reservierung, angerechnet/не, удержание по ступеням (`refund_cancel_fee`), строка платы в контракте, формула `max()` с E6.4c, блок автоподтверждения | — | 11.1 |
| **GA-10.5** | Витрина: Bereich/этаж/barrierefrei | — | 10.1 |
| **GA-10.4** | Подсказки комбинаций по соседству | — | 10.2 |
| **GA-11.3a** | Kartengarantie: setup-сессия, Customer на connected account, вебхук `booking_guarantee` (`CONNECT_KINDS`, SetupIntent), удержание ≥ 45 мин, обнуление `payment_due_at`, подтверждение | ⚠️ booking (поля гарантии) | 11.2 |
| **GA-11.3b** | Списание «Ausfallgebühr belasten»: off-session, ссылка оплаты платы (`booking_fee`), фолио, выручка, «Gebühr offen/erlassen», права | — | 11.3a |
| **GA-11.3c** | Освобождение карты после визита/отмены + beat отвязки через 14 дней | — | 11.3b |
| **GA-11.4** | Особые правила (даты/дни/группы/этажи) | — | 11.2, 10.1 |
| **GA-10.6** | Выбор стола гостем (опция) | — | 10.5 |
| **GA-10.8** | «Außenbereich heute geschlossen»: закрыть этаж-террасу на день с показом затронутых броней и письмом гостям | ⚠️ booking (`is_outdoor`) | 10.1 |
| **GA-10.9** | «Tisch sperren»: `TableHold` + единая `occupancy.busy_intervals` во всех путях + лист «Sperren/Freigeben» на плитке Tischplan + массово по зоне/этажу | ⚠️ booking (`TableHold`) | 10.0 |
| **GA-12.0** | Разведка API касс (Lightspeed K-Series, orderbird, Vectron, ready2order, SumUp) + выбор первого адаптера с владельцем + партнёрский доступ | — | — |
| **GA-12.1** | `PosConnection` + `PosTableMap` + экран сопоставления столов + generic HMAC-вебхук (opened/closed/moved → `TableHold`) + плашка «Kasse nicht verbunden» | ⚠️ integrations (новые таблицы) | 10.9 |
| **GA-12.2** | Связь с бронью: check-in по открытию счёта, `fulfilled` и «verrechnet» по оплате, сумма в CRM | — | 12.1, 11.2 |
| **GA-12.3** | Первый адаптер кассы + сверка опросом (beat) | — | 12.0, 12.1 |
| **GA-12.4** | (v2) Брони в план столов кассы | — | 12.3 |
| **GA-10.7 / 11.5** | Демо ресторана (2 этажа + терраса, правило гарантии для групп) + золотой путь GP-8 (бронь → поздняя отмена → удержание → выручка) + стенд + переводы ×5 | — | всё |

Рекомендуемый порядок: **10.0 ∥ 11.0 → 10.9 → 10.1 → 10.2a–c → 10.3 → 11.1 → 11.2 → 10.5 →
10.4 → 11.3a–c → 11.4 → 12.0 → 12.1 → 12.2 → 12.3 → 10.6 → 10.8 → 10.7/11.5**; GA-12.0
(разведка и партнёрский доступ — внешний шаг) можно начать параллельно в любой момент.
«Tisch sperren» идёт первым: работает на нынешнем Tischplan без плана зала, сразу полезен и
закладывает общую функцию занятости, на которую потом встанут касса и план. План зала даёт видимую ценность первым; правила
отмены без денег (11.1) дёшевы и уже снимают проблему «у ресторана нет правил отмены»;
гарантия картой (11.3) — самая рискованная часть, идёт после того, как правила и снимок
обкатаны.

## 6. Решения владельца

| # | Вопрос | Рекомендация |
|---|---|---|
| Р-1 | Лист плана = этаж **или** помещение? | Один уровень «Ebene» (этаж или помещение, `level` для порядка); зоны внутри — подписанные области. Двухуровневое «этаж → помещения» — только по спросу |
| Р-2 ✅ | Выбор конкретного стола гостем | **Принято:** опция на этаже, выкл. по умолчанию; по умолчанию гость выбирает зону |
| Р-3 ✅ | Списание по гарантии | **Принято:** вручную кнопкой (v1); авто-списание при `no_show` — позже опцией, после пилота |
| Р-4 | Где хранить выбранную гостем зону | Отдельное поле `Booking.requested_area` в миграции 10.1 (видно на карточке, ищется) |
| Р-5 ✅ | НДС удержанной платы | **Принято: опция в правиле** — «mit USt (Satz) / ohne USt» с подсказкой «mit Steuerberater klären»; по умолчанию как у B6-удержания |
| Р-6 | Редактирование с телефона | Полное — от планшета; телефон — просмотр + сдвиг стрелками |
| Р-7 ✅ | Сколько держать стол, пока гость не завершил гарантию/предоплату | 45 мин (меньше нельзя: минимум сессии Stripe 30 мин + 15 мин запаса) |
| Р-8 | Перетаскивание брони на другой стол в живом плане | v2 (сейчас — кнопка «Tisch zuweisen») |
| Р-9 ✅ | Текст условий | Шаблон с оговоркой § 309 Nr. 5 b («Ihnen bleibt der Nachweis eines geringeren Schadens unbenommen»); юр-вычитка до включения уже GA-11.1 в проде (флаг: чекбокс и текст условий появляются там) |
| Р-10 | Предоплата «angerechnet», если чек пробивается на кассе ресторана | Обязательство к зачёту, не выручка; отметка «verrechnet» на карточке брони |
| Р-11 | Длительность ручного блока по умолчанию и «bis Schichtende» | 2 ч по умолчанию; «Schichtende» = закрытие по часам работы дня |
| Р-12 | Суммы счетов кассы — в наш журнал выручки? | Нет: касса — учётная система (KassenSichV/TSE), у нас — только факт визита и сумма в CRM (LTV); иначе двойной учёт |
| Р-13 | Первая касса для адаптера | По данным пилота: какие кассы у ресторанов Solingen; кандидат с открытым API — Lightspeed K-Series |
| Р-14 | Блок поверх существующей брони | Ставится с предупреждением и ссылкой «Tisch zuweisen»; бронь не трогаем |

## 7. Риски

- **Деньги:** гонка «отмена гостем ↔ списание владельцем» — обе операции под блокировкой
  брони, решение по снимку; повтор вебхука setup — дедуп по session id; отказ карты ≠ таймаут.
- **Чужие данные в JSON редактора** (id столов другого тенанта, гигантские массивы) —
  серверная валидация + капы; замок «чужой стол = 400».
- **Конкурентная правка плана** двумя сотрудниками — версия листа, 409.
- **Доступность:** SVG без альтернативы недоступен — список и клавиатура обязательны, состояние
  не только цветом.
- **Производительность:** живой план — один запрос `tischplan` + столы с координатами (уже
  предзагружено); без опроса v1 (кнопка «Aktualisieren», опц. авто-обновление 60 с).
- **Право:** без явного согласия до брони плата не взыскивается — чекбокс обязателен, текст
  снимком.
- **Stripe:** Checkout `setup` — только карта (Klarna/PayPal не подходят для гарантии); у
  карты может истечь срок до визита — при отказе работает ссылка оплаты.

- **Блок, которого не видит один из путей брони** — главный риск GA-10.9: занятость
  считается в нескольких местах. Одна функция `busy_intervals` + замок по всем путям.
- **Касса:** потерянный или запоздавший вебхук, протухший блок, кража ключей кассы —
  дедуп, порядок по времени кассы, обязательный `end`, сверка опросом, шифрование ключей,
  отказ до БД при неверной подписи.

## 8. ECC-прогоны

Скиллы грузить **в начале** инкремента (`docs/pitfalls.md` §0).

| Инкремент | Скиллы до кода | Агенты и точка цикла |
|---|---|---|
| План (этот док) | `market-research` (сделано) | `planner` — ревью плана сразу после записи (§9); `architect` — модель Ebene/зон при Р-1 |
| GA-10.0 / 11.0 | `django-tdd`, `python-testing` | — (замки ДО кода, красные/зелёные по задумке) |
| GA-10.1 | `database-migrations`, `postgres-patterns`, `django-patterns` | `database-reviewer` (миграция, индексы `floor`), `django-reviewer` |
| GA-10.2a–c | `django-security`, `api-design` (JSON-сохранение), `accessibility`, `e2e-testing` | `security-reviewer` (валидация JSON, кросс-тенант), `django-reviewer`, `a11y-architect` (холст, клавиатура), `e2e-runner`/Playwright-стенд 1440/1024/390 |
| GA-10.3 | `accessibility`, `e2e-testing` | `django-reviewer`, `a11y-architect`, Playwright-стенд |
| GA-10.4 | `django-tdd` | `django-reviewer` |
| GA-10.5 / 10.6 | `django-security`, `accessibility`, `e2e-testing`, `seo` (витрина) | `security-reviewer` (недоверие к выбору гостя), `a11y-architect`, Playwright-стенд |
| GA-11.1 | `django-patterns`, `error-handling` | `django-reviewer`, `silent-failure-hunter` (снимок/повтор отмены) |
| GA-11.2 | `error-handling`, `django-security` | `django-reviewer` + `security-reviewer` + `silent-failure-hunter` |
| GA-11.3a–c | `error-handling`, `django-security`, `django-celery` (beat освобождения), `database-migrations` | `security-reviewer` (вебхук, `event.account`), `silent-failure-hunter` (SCA/таймаут), `database-reviewer`, `django-reviewer` |
| GA-11.4 | `django-tdd` | `django-reviewer` |
| GA-10.9 | `django-patterns`, `postgres-patterns`, `database-migrations`, `accessibility` | `database-reviewer` (запрос занятости, индекс `(resource, start, end)`), `django-reviewer`, `a11y-architect` (нижний лист), Playwright-стенд Tischplan 1440/390 |
| GA-12.0 | `market-research`, `api-design` | `planner` (выбор адаптера), `architect` (интерфейс адаптера) |
| GA-12.1–12.3 | `django-security`, `django-celery`, `error-handling`, `api-design`, `database-migrations` | `security-reviewer` (HMAC, ключи кассы), `silent-failure-hunter` (потерянные события, протухшие блоки), `database-reviewer`, `django-reviewer` |
| GA-10.7 / 11.5 | `e2e-testing` | `e2e-runner` (золотой путь GP-8), `doc-updater` (build-log, task-catalog, §3 CLAUDE.md) |

Гейт каждого батча: `ruff check .` + `ruff format --check .` + pytest затронутых модулей
(`--reuse-db`, при миграциях `--create-db`) + `scripts/i18n_quickcheck.py` +
`test_template_comments` + `npm run build:css` при новых классах → CI на git.

## 9. Ревью плана (planner, 2026-11-05)

Агент `planner` проверил план по коду; ключевые утверждения перепроверены вручную
(`siteconfig.py:4194`, `webhooks.py:57`, `balance_pay.py:60`, `no_show_rule.py:118`,
`events/details.py:221`, `payment_holds.py:84-112`). Внесено в план:

- ступени событий — в днях → свой нормализатор в часах (§1, §4.1);
- политика — отдельный ключ `booking.table_policy`: вложенный в `tables` стёрся бы и
  ломал GA-1 (§4.2);
- вебхук гарантии — новый вид в `CONNECT_KINDS`, мандат из SetupIntent, Customer заранее,
  обнуление `payment_due_at` (§4.4);
- удержание стола ≥ 45 мин вместо 30 (Р-7);
- ссылка оплаты платы — свой вид `booking_fee`, а не `balance_pay` (§4.4);
- у брони стола нет цены → плата явной строкой контракта, иначе «переплата» (§4.5);
- формула `max()` с E6.4c, блок автоподтверждения, политика и в `_termin_book_core`,
  ручные брони без политики (§4.6);
- в редакторе — только активные одиночные столы, без комбинаций (§3.2);
- `is_outdoor` вынесен в GA-10.8;
- GA-10.2 и GA-11.3 разбиты на a/b/c; GA-11.0 идёт параллельно с 10.0; флаг юр-вычитки —
  уже с GA-11.1.
