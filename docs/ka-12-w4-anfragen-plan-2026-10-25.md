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

### A-3 · E5.5b кейтеринг: дефолт формы + «pro Person» (без миграций)
Дефолт `anfrage` для catering при выборе типа (если ключа нет) + «Branchen-Vorlage laden» в панели.
Строка набора/услуги `per_person` при пустом количестве и заданных гостях → количество = гости;
при смене гостей — предупреждение, без автопересчёта. Опционально A-3b: вид «Kalender» у заявок (О-5).

### A-4 · E5.4b Termin из заявки (без миграций)
Форма «📅 Termin anlegen» в рейле карточки; ядро ручной записи вынести в
`booking.services.create_manual(...)` (часы, каникулы, ёмкость, навыки, буфер; паритет с
`booking_create`), бронь на `job.customer`, `job.booking` = новая запись. Гейт — модуль booking и ресурс,
иначе подсказка «Termine aktivieren» (О-1).

### A-5 · E5.4c фото мастера + Abnahmeprotokoll (⚠️ `jobs/0022`)
`JobPhoto.kind` (customer/before/after/intake/handover, default customer) + `uploaded_by`; модель
`JobProtocol` (kind intake|handover, date, notes, items JSON, mileage_km, signed_name/at,
confirmed_online_at, created_by). PDF «Abnahmeprotokoll»; онлайн-подтверждение клиентом на
`/auftrag/<token>/` (POST, один раз, под блокировкой, аудит); статус не меняет (О-3). DSGVO — в выгрузку/удаление.

### A-6 · E5.6 Werkstatt (⚠️ `jobs/0023` с data-шагом)
`jobs.Vehicle` (customer, plate, vin ISO 3779, hsn, tsn, make_model, first_registration, mileage_km,
hu_due, notes) + `Job.vehicle_ref`, `Job.mileage_km`; data-шаг plate → Vehicle (идемпотентно).
Пикер машины в карточке, протокол приёмки = `JobProtocol(intake)` + PDF «Fahrzeugannahme», карточка
машины из CRM (без нового якоря меню), поиск по Kennzeichen/FIN, напоминания по `hu_due`. Пресет статусов
`in_arbeit/teile_bestellt/abholbereit` кнопкой на «Abläufe» + в ките (О-8); письмо «abholbereit».

### A-7 · E7.5 ⚖️ Widerruf (⚠️ `jobs/0024`, за флагом `QUOTE_WITHDRAWAL_ENABLED`)
Для потребителя на `/angebot/<token>/`: Belehrung (текст тенанта), необязательный чекбокс «Beginn vor
Ablauf» (§ 356 Abs. 4, § 357a Abs. 2), снимок `withdrawal_info_at`/`early_start_requested_at`/
`withdrawal_text_hash`/`withdrawn_at`, письмо-подтверждение с PDF (§ 312f), функция отказа 14 дней
(§ 356a — подтвердить юристом) → `cancelled` через `apply_action` + полный возврат депозита (Wertersatz —
решает владелец). Исключения § 312g Abs. 2 — не в v1 (О-6).

## 3. Миграции (все аддитивные)

| Инкремент | Миграция | Что |
|---|---|---|
| A-5 | `jobs/0022` | `JobPhoto.kind` + `uploaded_by`; `JobProtocol` |
| A-6 | `jobs/0023` | `Vehicle`; `Job.vehicle_ref`, `Job.mileage_km`; data-шаг |
| A-7 | `jobs/0024` | поля Widerruf на `Job` |

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
