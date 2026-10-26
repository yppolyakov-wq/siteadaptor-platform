# KA-12 · Волна 4 · Anfragen/Handwerk — план (2026-10-25)

Источники:
- `ka-12-master-plan-2026-10-23.md` — строка направления: E5.4, E5.5, E5.6, E7.5 ⚖️, E7.7. Перед
  направлением — золотой путь E11.1.
- Аудиты: `ka-5fg-handwerk-lite-2026-10-23.md` (HW-2/3/4, H5), `ka-5b-gastro-2026-10-23.md` (G-4),
  `ka-5c-termine-2026-10-23.md` (Werkstatt §2, T-5/T-6).
- Разведка кода 2026-10-25 (агент planner). Образец структуры — `ka-12-w4-tickets-plan-2026-10-25.md`.
  Юридические пункты — за флагом до подтверждения юристом.

## 0. Что значит каждый пункт

| ID | Что владелец получает | Аудит |
|---|---|---|
| A-0 (E11.1) | Сквозной путь «/anfrage/ → заявка → смета → /angebot/ принять → done → счёт → выручка» проверен стендом и серверным двойником | — |
| A-1 (E7.7) | Ссылка на Datenschutz на всех публичных формах с персональными данными или фото | HW-4 |
| A-2 (E5.4a+E5.5a) | Ручная заявка («по телефону») принимает всё, что и `/anfrage/`; эти поля правятся в карточке | HW-2, G-4 |
| A-3 (E5.5b) | Кейтеринг: форма заявки с датой/гостями/поводом у нового бизнеса сразу; количество «pro Person» от гостей | G-4, G6 |
| A-4 (E5.4b) | «📅 Termin anlegen» прямо из заявки (выезд/приёмка) | HW-2 |
| A-5 (E5.4c) | Фото мастера (до/после) и акт сдачи-приёмки (Abnahmeprotokoll) с PDF и онлайн-подтверждением клиента | HW-3 |
| A-6 (E5.6) | Мастерская: машина как сущность (Kennzeichen/FIN/HSN/TSN/пробег/HU), протокол приёмки, статусы работ | T-5/T-6 |
| A-7 (E7.5 ⚖️) | Widerrufsbelehrung, запрос «Beginn vor Ablauf», Widerruf-функция при онлайн-принятии сметы потребителем | H5 |

## 1. Что уже есть (разведка, file:line)

**Модель `Job`** (`apps/jobs/models.py`): `site_plz` :54; `vehicle` :56, `vehicle_plate/hsn/tsn` :59-61;
AF-1 `event_date/guest_count/event_type` :65-67; `source_channel` :79, `public_token` :81, `valid_until`
:82, `service_due_date` :89; `voucher_paid_cents` :107, `deposit_cents/payment_state` :126-127; SH-23
`customer_type/billing_*` :132-141; FK `booking` :145; `lines_locked` :171; `plan_calc` :208.
`JobLine.vat_rate` :256. `JobPhoto` :310 — без `kind` и автора. `services.create_job` (:43) уже
принимает `site_plz`, поля авто, событийные поля и `fulfillment`.

**Публичная часть** (`public_views.py`): `anfrage` :79 (фото, PLZ, событийные поля по конфигу, авто при
`jobs_vehicle`, honeypot + rate-limit); `rueckruf` :170; `auftrag_status` :219 (знает только встроенные
статусы `_STATUS_FLOW`); `angebot` :249.

**Кабинет** (`views.py`): `job_new` :47 принимает только name/email/phone/title/description/
site_address/vehicle — PLZ, фото, источника, событийных полей и HSN/TSN нет (**HW-2/G-4 подтверждено**);
`_request_form.html` без `enctype`. В карточке `event_*`, `site_plz`, `vehicle_plate/hsn/tsn` только
показываются. `_link_booking` :315 — только привязка СУЩЕСТВУЮЩЕЙ брони; создать Termin нельзя.

**Уже закрыто прежними волнами:** KA-H10 (H1–H4), KA-H5 (счёт кейтеринга), B2-8b/c (Anzahlungsrechnung),
E1.9 (депозит/гонка accept), VF-13 (резерв склада), DC (общая карточка), пилот-батч B (выручка при счёте),
VAT-1 (ставка у строки).

**Кейтеринг:** конфиг `site_config["anfrage"]` пишет только демо-кит и панель «Anfrage-Formular»; при
выборе типа бизнеса — нет (**G6**). Смета не связывает количество с гостями. Вида «Kalender» у заявок нет.

**Werkstatt:** модели машины нет. Напоминание о TÜV — по `Job.service_due_date`. Статусов работ —
только вручную (SM-3), пресета нет.

**Datenschutz:** ссылка есть только в подвале и у newsletter; на `_anfrage_form.html`,
`_message_form.html`, Rückruf — нет (**HW-4**).

**Widerruf:** на `storefront/angebot.html` только «Accept»/«Decline»; тексты Widerruf тенанта есть в
`core/legal.py`.

**Золотые пути:** `scripts/golden_paths.py` gp1…gp5; `/anfrage/` код клиенту не показывает → для GP-6
поиск по метке в теме.

## 2. Инкременты

### A-0 · золотой путь GP-6 (без миграций)
Стенд `gp6_anfragen` на демо handwerker: `/anfrage/` с меткой `GP <tag>`, PLZ, фото → «Thank you» →
заявка в БД по метке темы → `/auftrag/<token>/`. Серверный двойник `apps/jobs/tests/test_golden_path_anfragen.py`:
POST `/anfrage/` → `new`; `set_lines` (19 % и 7 %) → `quoted`; `/angebot/<token>/` показывает разбивку;
accept → `accepted`; `done` → счёт с получателем и Leistungsdatum; выручка = сумма счёта одной строкой;
ветка с депозитом → Offene Posten = счёт − депозит.

**A-0 ✅ сделано (2026-10-25, без миграций).** Двойник `apps/jobs/tests/test_golden_path_anfragen.py`
(2 теста: путь до выручки по ставкам + ветка Anzahlung) и стенд GP-6 (10/10 на демо handwerker).
Дефектов не найдено; подозрение «счёт без Leistungsdatum» снято — дата ставится при выпуске (KA-H10).

### A-1 · E7.7 Datenschutz на формах (без миграций)
Партиал `storefront/_privacy_note.html` (информация по Art. 13, НЕ чекбокс — основание Art. 6(1)(b)),
в `_anfrage_form.html` (+ строка про фото), Rückruf, `_message_form.html`. Замок: каждый публичный
шаблон с `type="file"`/`name="email"`/`name="phone"` содержит `storefront-privacy`; исключения списком.

**A-1 ✅ сделано (2026-10-25, без миграций).** Шире плана: заметка нужна на ВСЕХ формах витрины с
e-mail/телефоном/файлом (Art. 13), а не на трёх — партиал `storefront/_privacy_note.html` в конце 18 форм
(+ `_buybox_contact_fields`), подпись про фото у `/anfrage/`; замок `apps/core/tests/test_privacy_note.py`
сканирует все шаблоны витрины; исключение — блок newsletter (своя ссылка).

### A-2 · E5.4a + E5.5a ручная заявка = публичная, правка в карточке (без миграций)
`job_new` + `_request_form.html` (multipart): PLZ, фото, источник (белый список «Telefon · E-Mail ·
Vor Ort · Empfehlung · Sonstiges» → `source_channel`), событийные поля по конфигу, авто при
`jobs_vehicle`/werkstatt. Карточка: `action=request` — тема, описание, PLZ, событие, авто; presence-guard
на каждом поле (W0); после `lines_locked` тема/событие правимы (О-4). Фото в карточке — отдельной формой.

**A-2 ✅ сделано (2026-10-25, без миграций).** `jobs:new` принимает PLZ, фото, источник (белый список
`MANUAL_SOURCES`, «manual» = Telefon), событийные поля по конфигу формы (вид мероприятия — и свой текст),
структурные поля авто у мастерской; поле «Fahrzeug» у прочих типов не показывается (G-4). Карточка:
«✏️ Anfrage bearbeiten» (`action=request`, presence-guard; нечитаемое число/дата не стирает прежнее;
правка даты/гостей после принятия сметы — в аудит `job.request_edit`) и «📷 Fotos hinzufügen»
(`action=photos`, лимит под блокировкой заявки). Ревью Django + безопасность: HIGH нет, LOW/MEDIUM закрыты.

### A-3 · E5.5b кейтеринг: дефолт формы + «pro Person» (без миграций)
Дефолт `anfrage` для catering при выборе типа (если ключа нет) + «Branchen-Vorlage laden» в панели.
Строка набора/услуги `per_person` при пустом количестве и заданных гостях → количество = гости;
при смене гостей — предупреждение, без автопересчёта. Опционально A-3b: вид «Kalender» у заявок (О-5).

**A-3 ✅ сделано (2026-10-25, без миграций).** `apps/jobs/anfrage_presets.py` — пресет по типу (пока
только catering); кладётся в `_new_tenant` и `apply_business_type` ТОЛЬКО при отсутствии ключа
(выбор владельца, вкл. «всё снято», не перетирается). Кнопка «Branchen-Vorlage laden» на «Abläufe» —
явное действие, перезаписывает. Пикер помечает `data-per-person` (Combo.price_per_person,
Service.pricing_mode); JS ставит кол-во = гости поверх значения по умолчанию (введённое не трогает); подсказка
«Preise „pro Person“ … N Gästen»; смена гостей при строках → предупреждение, без автопересчёта.
Быстрый старт (`start_quick_provisioning`) перезаписывает site_config профилем «aktionen» — у лёгкого
пакета заявок нет, пресет там не нужен. A-3b (Kalender заявок) — отложено.

### A-4 · E5.4b Termin из заявки (без миграций)
Форма «📅 Termin anlegen» в рейле карточки; ядро ручной записи вынести в
`booking.services.create_manual(...)` (часы, каникулы, ёмкость, навыки, буфер; паритет с
`booking_create`), бронь на `job.customer`, `job.booking` = новая запись. Гейт — модуль booking и ресурс,
иначе подсказка «Termine aktivieren» (О-1).

**A-4 ✅ сделано (2026-10-25, без миграций).** Ядро ручной записи вынесено в
`booking.services.create_manual` (длительность/цена из услуги и варианта, per_person, часы с
«Trotzdem eintragen», места пула, навык — предупреждением, занятость/закрыто → `ManualBookingRefused`);
`booking_create` переведён на него без изменения поведения (456 тестов booking зелёные). `book()` принимает
`customer=` — запись из заявки идёт на клиента заявки, а не на «Walk-in» по контактам. Карточка заявки:
«📅 Termin anlegen» (ресурс, начало, услуга, минуты), гости заявки = места, заметка = номер и тема заявки;
созданная запись сразу в `job.booking`. Без модуля записи формы нет и POST ничего не создаёт; без ресурса —
подсказка со ссылкой на «Öffnungszeiten & Ressourcen».

### A-5 · E5.4c фото мастера + Abnahmeprotokoll (⚠️ `jobs/0022`)
`JobPhoto.kind` (customer/before/after/intake/handover, default customer) + `uploaded_by`; модель
`JobProtocol` (kind intake|handover, date, notes, items JSON, mileage_km, signed_name/at,
confirmed_online_at, created_by). PDF «Abnahmeprotokoll»; онлайн-подтверждение клиентом на
`/auftrag/<token>/` (POST, один раз, под блокировкой, аудит); статус не меняет (О-3). DSGVO — в выгрузку/удаление.

#### A-5 · детальный план (2026-10-26)
**Модель (`jobs/0022`, аддитивная):**
- `JobPhoto.kind` CharField(16, choices customer/before/after/intake/handover, default "customer",
  db_default) — существующие фото = фото клиента; `uploaded_by` FK User SET_NULL null (как
  `crm.CustomerNote.author`). Индекс не нужен (выборка всегда по job_id, ≤ 25 строк).
- `JobProtocol` (TimestampedModel): job FK CASCADE related_name="protocols", kind (intake|handover),
  date DateField, notes Text blank, items JSON list[{"label": str, "ok": bool}] default list,
  mileage_km PositiveInteger null, signed_name Char(120) blank, signed_at DateTime null,
  confirmed_online_at DateTime null, confirmed_name Char(120) blank, created_by FK User SET_NULL null.
  UniqueConstraint(job, kind) — один акт каждого вида на заявку.
**Лимиты:** клиентский лимит 5 считает только kind=customer (публичная форма); мастер — до 20 фото
своих видов (`MAX_MASTER_PHOTOS`), счёт под `select_for_update` заявки (как сейчас).
**Кабинет (jobs:detail):** выбор вида при загрузке (whitelist, мусор → customer запрещён для
мастера → before), фото группами «Kunde / Vorher / Nachher / Annahme / Übergabe»; блок
«📝 Abnahmeprotokoll» (date, пункты — строка на пункт, «✗ » в начале = Mangel, пробег, заметки,
имя подписавшего на месте) → action `protocol` (kind из whitelist), правка запрещена после
онлайн-подтверждения; PDF `jobs:protocol-pdf <pk> <kind>` (тот же documents-слой, язык заявки).
**Витрина `/auftrag/<token>/`:** при наличии handover-акта — пункты/заметки/фото «Nachher» и форма
«Abnahme bestätigen» (имя обязательно, чекбокс «Ich habe die Leistung geprüft»): POST, под
`select_for_update` акта, повтор → «bereits bestätigt», `audit_event(strict=False)` с IP-хэшем не
пишем (только факт), ratelimit по IP. Статус заявки НЕ меняется (О-3); владельцу — flash-уведомление
нет, письмо через `notify` с dedupe (owner-ветка, «Abnahme bestätigt»).
**DSGVO:** выгрузка — CHILDREN jobs.Job += photos, protocols; удаление — фото вида customer
удаляются (файл on_commit), акты и фото мастера остаются по основанию «abnahme» (Abnahme
запускает срок Gewährleistung § 634a BGB — доказательство), из актов стираются signed_name/
confirmed_name. ⚖️ Основание — на вычитку юриста (как waiver).
**ECC:** до кода — django-patterns, django-tdd, django-security, database-migrations; агенты —
database-reviewer (дизайн миграции до кода), django-reviewer + security-reviewer (после кода:
публичный POST, загрузка файлов, IDOR по kind/pk); стенд — серверный тест витрины (JS нет).
**Замки до кода:** клиентский лимит не съедается фото мастера; мастер не может загрузить
customer; акт подтверждается ровно один раз и не меняет статус; правка после подтверждения
запрещена; чужой токен → 404; PDF отдаётся; DSGVO: фото клиента удалены, акт без имён остался.

### A-6 · E5.6 Werkstatt (⚠️ `jobs/0023` с data-шагом)
`jobs.Vehicle` (customer, plate, vin ISO 3779, hsn, tsn, make_model, first_registration, mileage_km,
hu_due, notes) + `Job.vehicle_ref`, `Job.mileage_km`; data-шаг plate → Vehicle (идемпотентно).
Пикер машины в карточке, протокол приёмки = `JobProtocol(intake)` + PDF «Fahrzeugannahme», карточка
машины из CRM (без нового якоря меню), поиск по Kennzeichen/FIN, напоминания по `hu_due`. Пресет статусов
`in_arbeit/teile_bestellt/abholbereit` кнопкой на «Abläufe» + в ките (О-8); письмо «abholbereit».

#### A-6 · детальный план (2026-10-26)
Делим на **A-6a** (модель, перенос, привязка, карточка, поиск) и **A-6b** (напоминания HU, пресет
статусов, письмо «abholbereit», PDF «Fahrzeugannahme»); одна миграция `jobs/0023` на оба.
**Модель (`jobs/0023`, аддитивная + data-шаг отдельной операцией):**
- `Vehicle` (TimestampedModel): customer FK CASCADE related_name="vehicles" (клиент не
  удаляется — анонимизируется), plate Char(15) blank (норма: верхний регистр, одиночные пробелы),
  vin Char(17) blank (ISO 3779: 17 знаков, без I/O/Q — проверка в сервисе, не в БД), hsn Char(4),
  tsn Char(3), make_model Char(120), first_registration Date null, mileage_km PositiveInteger null,
  hu_due Date null, hu_reminder_sent_for Date null (дедуп A-6b: одно письмо на дату HU), notes Text.
  UniqueConstraint(customer, plate, condition plate≠"") — одна машина клиента на номер;
  Index(plate) для поиска по Kennzeichen.
- `Job.vehicle_ref` FK Vehicle SET_NULL null related_name="jobs"; `Job.mileage_km` PositiveInteger null.
- data-шаг: для заявок с непустым `vehicle_plate` — get_or_create Vehicle(customer, норм. plate),
  hsn/tsn/make из заявки только в пустые поля, `vehicle_ref` = машина; идемпотентно, батчами,
  reverse = noop. Плоские поля заявки остаются (снимок: смета/PDF/письма читают их).
**Привязка (`jobs/vehicles.py`):** `ensure_vehicle(job)` — после create_job и правки заявки:
есть номер → найти/создать машину клиента, связать, дописать пустые поля машины; номер
очищен → связь снять. Пробег из акта приёмки (A-5 intake) → `Job.mileage_km` и машина
(только вверх — одометр не убывает; меньшее значение → предупреждение).
**Кабинет:** блок «🚗 Fahrzeug» в карточке заявки (данные машины + правка VIN/EZ/HU/пробег/
заметки, прошлые заявки этой машины); раздел «Fahrzeuge» в карточке клиента CRM (customer360);
поиск сделок по Kennzeichen и FIN (`_TITLE_SEARCH`). Новых экранов/якорей нет.
**A-6b:** beat по `Vehicle.hu_due` (окно как у service_due, дедуп `hu_reminder_sent_for`,
письмо `vehicle_hu_reminder`, отписка/unsubscribed уважаются); «Status-Vorlage Werkstatt»
кнопкой на «Abläufe» (свои статусы `in_arbeit/teile_bestellt/abholbereit` через тот же
редактор FB-3 B, идемпотентно) + в ките werkstatt + новым тенантам werkstatt; письмо клиенту
при входе в статус «abholbereit» (по коду, dedupe); PDF акта intake у werkstatt озаглавлен
«Fahrzeugannahme» и печатает Kennzeichen/FIN/пробег.
**DSGVO:** `jobs.Vehicle` в ERASURE_POLICY = delete (номер/FIN — ПДн; заявки остаются, связь
SET_NULL, плоские поля заявки уже чистятся политикой `jobs.Job`); в выгрузку — как связанная
с клиентом модель (автоматически через related_objects).
**ECC:** скиллы django-patterns, django-tdd, database-migrations, django-security; агенты —
database-reviewer (дизайн до кода + data-шаг), django-reviewer + security-reviewer после кода
(IDOR: машина чужого клиента, правка через POST заявки), silent-failure-hunter — beat A-6b.
**Замки до кода:** перенос идемпотентен и не дублирует машину; номер в разном регистре/пробелах
= одна машина; очищенный номер снимает связь; пробег не убывает; поиск по номеру и FIN находит
заявку; CRM показывает машины; DSGVO удаляет машину и не трогает заявку; HU-письмо одно на дату.

#### A-6b · детальный план (2026-10-26, без миграций)
1. **HU-напоминание.** `jobs.tasks.send_due_hu_reminders(today, tenant)` — машины с
   `hu_due` в окне [сегодня, +SERVICE_REMINDER_LEAD_DAYS], `hu_reminder_sent_for ≠ hu_due`;
   клиент с e-mail и не отписан; канал — тот же переключатель «Service-Erinnerung» (UD4-2).
   Если у живой заявки этой машины `service_due_date == hu_due` — письмо уже шлёт A9,
   машину помечаем без второго письма. Письмо `vehicle_hu_reminder`, дедуп
   `vehicle:<pk>:hu:<дата>:customer` + отметка `hu_reminder_sent_for`; правка HU в
   карточке сбрасывает отметку (сделано в A-6a). Бег — внутри существующего ежедневного
   `send_service_reminders` (новой записи beat нет); сбой одного бизнеса логируется и не
   останавливает остальные.
2. **Status-Vorlage Werkstatt** (`apps/jobs/status_presets.py`): свои статусы заявки
   `in_arbeit` · `teile_bestellt` · `abholbereit` (роль active) + рёбра accepted→in_arbeit,
   in_arbeit↔teile_bestellt, in_arbeit→abholbereit, abholbereit→done, отмена из
   in_arbeit/teile_bestellt. Кнопка «Werkstatt-Vorlage laden» в редакторе своих статусов на
   «Abläufe» (kind job, тип werkstatt) — `status_manager_save` с `load_preset`, СЛИЯНИЕ:
   недостающие коды/рёбра добавляются, правки владельца целы, повтор ничего не меняет.
   Новым бизнесам werkstatt и при смене типа — только если своих статусов заявки нет.
   Демо-кит werkstatt получает те же статусы.
3. **Письмо «abholbereit»**: вход в статус с кодом `abholbereit` (любой путь FSM) →
   клиенту `job_ready` (со ссылкой на страницу статуса), событие матрицы «Abholbereit».
   Переход abholbereit→done письмо «Auftrag fertig» не шлёт — клиент уже знает.
4. **PDF**: акт приёмки заявки с номером машины — заголовок «Fahrzeugannahme»; в шапке
   любого акта с машиной — Kennzeichen, FIN, марка.
**ECC:** django-patterns/django-tdd/django-celery; django-reviewer после кода,
silent-failure-hunter — бег HU. **Замки:** одно письмо на дату HU; дубль с A9 гасится;
отписанному не шлём; выключенный канал не помечает; сбой бизнеса не валит бег; пресет
идемпотентен и не трёт правки; дефолт только без своих статусов; вход в abholbereit шлёт
письмо один раз, done после него — нет; заголовок PDF.

### A-7 · E7.5 ⚖️ Widerruf (⚠️ `jobs/0025`, за флагом `QUOTE_WITHDRAWAL_ENABLED`)
Для потребителя на `/angebot/<token>/`: Belehrung (текст тенанта), необязательный чекбокс «Beginn vor
Ablauf» (§ 356 Abs. 4, § 357a Abs. 2), снимок `withdrawal_info_at`/`early_start_requested_at`/
`withdrawal_text_hash`/`withdrawn_at`, письмо-подтверждение с PDF (§ 312f), функция отказа 14 дней
(§ 356a — подтвердить юристом) → `cancelled` через `apply_action` + полный возврат депозита (Wertersatz —
решает владелец). Исключения § 312g Abs. 2 — не в v1 (О-6).

#### A-7 · детальный план (2026-10-26, ⚠️ `jobs/0025`)
Всё видимое клиенту — за флагом `QUOTE_WITHDRAWAL_ENABLED` (default False; включает владелец
платформы после юриста, О-7). Применяется только к потребителю (`customer_type = private`):
фирме (`company`) право отказа не положено.
- **Модель (`jobs/0025`, аддитивная, nullable):** `Job.withdrawal_info_at`,
  `withdrawal_text_hash` (sha256 показанного текста — доказательство, ЧТО показали),
  `early_start_requested_at` (§ 356 Abs. 4 / § 357a Abs. 2: клиент сам попросил начать до
  конца срока), `withdrawn_at`.
- **Belehrung на `/angebot/<token>/`** (статус quoted): текст бизнеса (`withdrawal_policy`)
  или заготовка для работ/услуг (`apps/jobs/withdrawal.py`, помечена ⚖️ на вычитку) — НЕ
  товарный текст C.1. Необязательный чекбокс «Ausführung vor Ablauf der Widerrufsfrist
  beginnen» (молчание = не просил). Снимок пишется при нажатии «Annehmen» (и в пути с
  депозитом — до ухода в Stripe), один раз.
- **Подтверждение (§ 312f):** при принятии потребителем — письмо клиенту `job_contract` с
  составом, суммой, текстом Belehrung и отметкой о раннем начале + PDF сметы вложением.
- **Функция отказа (§ 356a, кнопка):** на той же странице, пока заявка `accepted`, до
  `accepted_at + 14 дней` и пока не `done`: «Vertrag widerrufen» → шаг подтверждения
  (имя, отметка) → `withdrawn_at` + переход в `cancelled` через `transactions.apply_action`
  (возврат депозита — общим путём `refunds`, actor=None = системный путь; Wertersatz при раннем
  начале решает владелец вручную) → письмо клиенту «Widerruf eingegangen» (подтверждение
  получения на носителе) + владельцу. Под блокировкой строки, повтор — «уже получено».
  Лимит частоты как у публичных форм. Форма `/widerruf-formular/` остаётся.
- **Кабинет:** в карточке заявки — отметки «Belehrung angezeigt», «früher Beginn verlangt»,
  «widerrufen am».
- **DSGVO:** отметки — не ПДн, остаются (доказательство); выгрузка — с заявкой.
**ECC:** django-patterns, django-tdd, django-security, database-migrations, accessibility;
агенты — database-reviewer (миграция), django-reviewer + security-reviewer (публичный POST без
входа, деньги), silent-failure-hunter (возврат/письма), a11y-architect (новые элементы формы).
**Замки:** флаг выключен — страница байт-в-байт прежняя; фирме Belehrung нет; снимок пишется
один раз и хранит хеш показанного текста; чекбокс не отмечен — `early_start` пуст; письмо с
PDF при принятии потребителем; кнопка отказа только в окне 14 дней и до `done`; отказ
отменяет заявку и возвращает депозит одним путём; повтор отказа ничего не делает;
чужой токен — 404.

## 3. Миграции (все аддитивные)

| Инкремент | Миграция | Что |
|---|---|---|
| A-5 | `jobs/0022` | `JobPhoto.kind` + `uploaded_by`; `JobProtocol` |
| A-6 | `jobs/0023` + `0024` | `Vehicle`; `Job.vehicle_ref`, `Job.mileage_km`; data-шаг отдельной миграцией |
| A-7 | `jobs/0025` | поля Widerruf на `Job` |

## 4. Решения (с рекомендацией)
- **О-1** Termin только через модуль booking — да.
- **О-2** Источник ручной заявки — белый список — да.
- **О-3** Онлайн-Abnahme клиента не переводит в `done` — да.
- **О-4** После принятия событийные поля и тема правимы, позиции — нет — да.
- **О-5** Вид «Kalender» у заявок — да.
- **О-6** ⚖️ Исключения § 312g Abs. 2 — не в v1.
- **О-7** ⚖️ Widerruf: информация + запрос раннего начала + снимок + письмо — сразу; функция отказа и
  тексты — после юриста (флаг).
- **О-8** Пресет статусов мастерской — кнопкой + в ките + новым тенантам werkstatt.

## ECC-прогоны
- Скиллы до кода: `django-patterns`, `django-tdd` (все); `django-security` (A-1, A-4, A-5, A-7);
  `database-migrations` (A-5/A-6/A-7); `e2e-testing` (A-0, A-5, A-7); `accessibility` (A-2, A-7).
- Агенты: `django-reviewer` — каждый; `security-reviewer` — A-2, A-4, A-5, A-7; `database-reviewer` —
  A-5/A-6; `silent-failure-hunter` — A-4, A-7; `a11y-architect` — A-7; Playwright-стенд — A-0, A-2, A-5, A-7.
- Грабли: presence-guard (W0); хелпер не между `@login_required` и вьюхой; i18n_quickcheck +
  `i18n_gap`; `npm run build:css`; многострочный `{# #}`; новый экран — `cabinet-screen-dod.md`.
