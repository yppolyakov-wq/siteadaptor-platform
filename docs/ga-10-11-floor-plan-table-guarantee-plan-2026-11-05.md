# GA-10 «Grundriss» + GA-11 «Tischgarantie» — план (2026-11-05)

Запрос владельца (2026-11-05): ресторан рисует простой план помещения и расставляет на нём
столы с числом мест для брони. Этажей может быть несколько. Бронь может быть условно
платной: при отмене позже срока — плата, либо обязательная предоплата; это настраиваемая
опция. Проверить рынок.

Статус: **план на решение владельца, кода нет.** Семейство — Gastro (`GA-*`, продолжение
GA-0…GA-9 волны 4 KA-12). Два трека, связанных только общими инкрементами витрины:

- **GA-10 «Grundriss»** — план зала с этажами: редактор, живой план, выбор зоны гостем.
- **GA-11 «Tischgarantie»** — правила отмены, предоплата и гарантия картой для брони стола.

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
| **Правила отмены — только у услуги** (`Service.cancel_window_hours/late_cancel`), снимком в `Booking.cancel_policy` | `booking/cancel_policy.py` (B6) | **Бронь стола создаётся с `service=None` → снимок `{}` → «бесплатно до начала, всегда возврат».** У ресторана правил отмены сейчас нет вообще |
| Шкала Stornogebühr «за N ч — X %» | `events.Event.cancel_fee_steps` + `normalize_fee_steps` (T-4a) | Переиспользуем нормализатор для столов |
| Депозит после N неявок | `booking/no_show_rule.py` (E6.4c) | Сочетается с GA-11 (берётся большее) |
| Сохранённая карта + списание без гостя | `billing.connect.installment_checkout_session` (`setup_future_usage=off_session`) + `charge_off_session` (R10) | Основа «Kartengarantie»; нужен вариант Checkout `mode="setup"` (без платежа) |
| Фолио платежей, онлайн-остаток, возвраты | `core/folio.py`, `core/balance_pay.py`, `core/refunds.py` | Списанная плата пишется в фолио, ссылка оплаты — тем же путём |
| Ссылка гостя «Termin verwalten» (отмена/перенос) | B6 | Распространяется на столы |

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
  is_outdoor Bool          терраса/сад — закрывается на день одной кнопкой (погода)
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
- **Сохранение:** `POST` JSON целого листа `{version, tables:[…], elements:[…]}` →
  серверная валидация (столы только этого тенанта и типа table, координаты в границах,
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

---

## 4. GA-11 «Tischgarantie» — дизайн

### 4.1 Три режима (правило владельца)

| Режим | Что платит гость при бронировании | Отмена до срока | Поздняя отмена / неявка |
|---|---|---|---|
| **Ohne** (по умолчанию) | ничего | бесплатно | ничего (можно включить только информирование и подсчёт неявок E6.4a) |
| **Vorauszahlung** | сумма сразу (Checkout) | возврат полностью | удержание по ступеням; опция «auf die Rechnung angerechnet» (Anzahlung) или нет (Reservierungsgebühr) |
| **Kartengarantie** | ничего, карта сохраняется (Checkout `mode="setup"`) | ничего, карта освобождается | списание по ступеням — **вручную** кнопкой владельца (Р-3) |

Сумма: «pro Person» или «pro Reservierung». Ступени — тот же формат, что у событий
(`normalize_fee_steps`): «kostenlos bis 24 h vorher · 50 % bis 0 h · Nichterscheinen 100 %».

### 4.2 Где правило живёт

`site_config["booking"]["tables"]["policy"]` (presence-minimal, через `normalize_booking`;
нет ключа = прежнее поведение байт-в-байт):

```
{ "mode": "none|prepay|guarantee",
  "amount_cents": 2500, "per": "person|booking", "credit": true,
  "steps": [{"h": 24, "pct": 0}, {"h": 0, "pct": 50}], "no_show_pct": 100,
  "rules": [  # особые правила; первое подходящее выигрывает, затем базовое
     {"label": "Silvester", "dates": [["2026-12-31","2026-12-31"]], "mode": "prepay", …},
     {"label": "Gruppen ab 8", "min_party": 8, "mode": "guarantee", …},
     {"label": "Terrasse", "floors": [<id>], …} ] }   # кап 10 правил
```

- Правило, депозит стола (`Resource.deposit_cents`) и E6.4c сочетаются **по максимуму**
  суммы — не суммируются (как G4 в отеле).
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
- Ссылка гостя «Reservierung verwalten» (B6) — для столов: отмена с показом удержания
  «сейчас».
- Решение «вернуть / удержать» фиксируется в момент отмены (грабля B6), повтор решает по
  снимку.

### 4.4 Kartengarantie — механика

- Новый `connect.setup_checkout_session` (Checkout `mode="setup"`, `payment_method_types=["card"]`,
  `customer_creation="always"`, текст мандата Stripe о будущем списании) на connected account.
- Вебхук `checkout.session.completed` (mode=setup, сверка `event.account` — SEC-D1) → бронь
  получает `guarantee_state=ready` + ссылки на customer/payment method; бронь подтверждается
  только после этого (как депозит). Незавершённая гарантия держит стол ограниченное время
  (как онлайн-оплата 24 ч → для стола 30 мин, Р-7) и снимается штатным FSM.
- Списание: карточка брони при `no_show` или поздней отмене → кнопка «Ausfallgebühr belasten»
  с суммой из снимка (можно уменьшить, нельзя увеличить) → `charge_off_session`
  (ключ идемпотентности = бронь + сумма) → фолио `DealPayment` + выручка тем же путём, что
  удержание B6. SCA-отказ / отказ карты → письмо гостю со ссылкой оплаты (`balance_pay`),
  состояние «Gebühr offen»; таймаут Stripe ≠ отказ (грабля B2-4a).
- «Gebühr erlassen» — закрывает без списания.
- **DSGVO/минимизация:** после посещения или отмены без платы — `guarantee_state=released`,
  через 14 дней beat отвязывает payment method в Stripe и чистит ссылки.
- Новые поля `Booking`: `guarantee_state`, `guarantee_customer_id`, `guarantee_pm_id`,
  `fee_charged_cents` (одна миграция в GA-11.3).

### 4.5 Деньги и налог

- Vorauszahlung «angerechnet» = Anzahlung: идёт существующим путём депозита (фолио, остаток,
  B2-8 Mindest-Ist/Anzahlungsrechnung).
- Удержанная плата и списание по гарантии — **вопрос Steuerberater'у (Р-5):** Entgelt
  (USt) или Schadensersatz (без USt); EuGH C-295/17 (MEO) сдвигает практику к «Entgelt».
  До ответа — ставка настраивается в правиле (по умолчанию как у B6-удержания).

---

## 5. Инкременты и порядок

| # | Что | Миграция | Зависит |
|---|---|---|---|
| **GA-10.0** | Замки ДО кода: характеристика Tischplan (плитки/состояния), подбор GA-4, легаси-отмена стола «бесплатно до начала» | — | — |
| **GA-10.1** | `FloorPlan` + поля стола + `auto_layout` + read-only рендер плана в Tischplan за переключателем | ⚠️ booking (аддитивная) | 10.0 |
| **GA-10.2** | Редактор (этажи, столы, элементы, Save с версией, клавиатура) | — | 10.1 |
| **GA-10.3** | Живой план: этажи, состояния, клик → шторка, «Plan \| Liste» | — | 10.2 |
| **GA-11.0** | Замки денег: снимок v1/`{}` неизменны, нет ключа policy = байт-в-байт | — | — |
| **GA-11.1** | Правила отмены столов без денег: ступени, снимок v2, условия на витрине + чекбокс, письма, «Reservierung verwalten» | — | 11.0 |
| **GA-11.2** | Vorauszahlung pro Person/Reservierung, angerechnet/не, удержание по ступеням | — | 11.1 |
| **GA-10.4** | Подсказки комбинаций по соседству | — | 10.2 |
| **GA-10.5** | Витрина: Bereich/этаж/barrierefrei | — | 10.1 |
| **GA-11.3** | Kartengarantie (setup, вебхук, ручное списание, SCA-фолбэк, освобождение) | ⚠️ booking (поля гарантии) | 11.2 |
| **GA-11.4** | Особые правила (даты/дни/группы/этажи) | — | 11.2, 10.1 |
| **GA-10.6** | Выбор стола гостем (опция) | — | 10.5 |
| **GA-10.7 / 11.5** | Демо ресторана (2 этажа + терраса, правило гарантии для групп) + золотой путь GP-8 (бронь → поздняя отмена → удержание → выручка) + стенд + переводы ×5 | — | всё |

Рекомендуемый порядок: **10.0 → 10.1 → 10.2 → 10.3 → 11.0 → 11.1 → 11.2 → 10.5 → 10.4 → 11.3
→ 11.4 → 10.6 → 10.7/11.5.** План зала даёт видимую ценность первым; правила отмены без
денег (11.1) дёшевы и уже снимают проблему «у ресторана нет правил отмены»; гарантия
картой (11.3) — самая рискованная часть, идёт после того, как правила и снимок обкатаны.

## 6. Решения владельца

| # | Вопрос | Рекомендация |
|---|---|---|
| Р-1 | Лист плана = этаж **или** помещение? | Один уровень «Ebene» (этаж или помещение, `level` для порядка); зоны внутри — подписанные области. Двухуровневое «этаж → помещения» — только по спросу |
| Р-2 | Выбор конкретного стола гостем | Опция на этаже, выкл. по умолчанию; по умолчанию гость выбирает зону |
| Р-3 | Списание по гарантии | Вручную кнопкой (v1); авто-списание при `no_show` — позже опцией, после пилота |
| Р-4 | Где хранить выбранную гостем зону | Отдельное поле `Booking.requested_area` в миграции 10.1 (видно на карточке, ищется) |
| Р-5 | НДС удержанной платы | Вопрос Steuerberater'у; до ответа — настраиваемая ставка |
| Р-6 | Редактирование с телефона | Полное — от планшета; телефон — просмотр + сдвиг стрелками |
| Р-7 | Сколько держать стол, пока гость не завершил гарантию/предоплату | 30 мин |
| Р-8 | Перетаскивание брони на другой стол в живом плане | v2 (сейчас — кнопка «Tisch zuweisen») |
| Р-9 | Текст условий | Шаблон с оговоркой § 309 Nr. 5 b («Ihnen bleibt der Nachweis eines geringeren Schadens unbenommen»); юр-вычитка до включения GA-11.2/11.3 в проде (флаг) |

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

## 8. ECC-прогоны

Скиллы грузить **в начале** инкремента (`docs/pitfalls.md` §0).

| Инкремент | Скиллы до кода | Агенты и точка цикла |
|---|---|---|
| План (этот док) | `market-research` (сделано) | `planner` — ревью плана сразу после записи (§9); `architect` — модель Ebene/зон при Р-1 |
| GA-10.0 / 11.0 | `django-tdd`, `python-testing` | — (замки ДО кода, красные/зелёные по задумке) |
| GA-10.1 | `database-migrations`, `postgres-patterns`, `django-patterns` | `database-reviewer` (миграция, индексы `floor`), `django-reviewer` |
| GA-10.2 | `django-security`, `api-design` (JSON-сохранение), `accessibility`, `e2e-testing` | `security-reviewer` (валидация JSON, кросс-тенант), `django-reviewer`, `a11y-architect` (холст, клавиатура), `e2e-runner`/Playwright-стенд 1440/1024/390 |
| GA-10.3 | `accessibility`, `e2e-testing` | `django-reviewer`, `a11y-architect`, Playwright-стенд |
| GA-10.4 | `django-tdd` | `django-reviewer` |
| GA-10.5 / 10.6 | `django-security`, `accessibility`, `e2e-testing`, `seo` (витрина) | `security-reviewer` (недоверие к выбору гостя), `a11y-architect`, Playwright-стенд |
| GA-11.1 | `django-patterns`, `error-handling` | `django-reviewer`, `silent-failure-hunter` (снимок/повтор отмены) |
| GA-11.2 | `error-handling`, `django-security` | `django-reviewer` + `security-reviewer` + `silent-failure-hunter` |
| GA-11.3 | `error-handling`, `django-security`, `django-celery` (beat освобождения), `database-migrations` | `security-reviewer` (вебхук, `event.account`), `silent-failure-hunter` (SCA/таймаут), `database-reviewer`, `django-reviewer` |
| GA-11.4 | `django-tdd` | `django-reviewer` |
| GA-10.7 / 11.5 | `e2e-testing` | `e2e-runner` (золотой путь GP-8), `doc-updater` (build-log, task-catalog, §3 CLAUDE.md) |

Гейт каждого батча: `ruff check .` + `ruff format --check .` + pytest затронутых модулей
(`--reuse-db`, при миграциях `--create-db`) + `scripts/i18n_quickcheck.py` +
`test_template_comments` + `npm run build:css` при новых классах → CI на git.

## 9. Ревью плана (planner)

_Заполняется по итогам прогона агента `planner`._
