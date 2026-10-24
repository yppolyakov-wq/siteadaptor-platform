# KA-12 Волна 4 · Termine — E11.1 (золотой путь) + E6.4 «Неявки и история услуги» — план, 2026-10-24

План — агент `planner` по коду HEAD (`7eacc366`). Источник: `ka-12-master-plan-2026-10-23.md` §E6 (E6.4 🗄),
§E11 (E11.1), §Волна 4 («Termine: E4.2, E4.4, E6.2 (external), E6.4; перед направлением — золотой путь
E11.1»); `ka-5c-termine-2026-10-23.md` (строка 6 «нет счётчика неявок», §4 п.5 «Карточка окрашивания»).
Выбор направления — по рекомендации (открытый вопрос плана §5.1): Termine, т.к. E4.2/E4.4 уже сделаны.

## 1. Цель
1. **E11.1 (первым):** золотой путь Termine — витрина → услуга → время → форма → `/t/<code>/` →
   `Booking` в БД (Playwright GP-3) + серверный двойник: confirm → fulfilled → выручка → счёт из записи;
   confirm → no_show → депозит удержан.
2. **E6.4a — счётчик неявок**: сотрудник ДО визита видит «N× nicht erschienen» (карточка записи,
   Tagesplan, карточка клиента).
3. **E6.4b — история услуги («карточка окрашивания»)**: внутренняя заметка мастера к визиту, видна на
   следующем визите этого клиента на ту же услугу.
4. **E6.4c — «после N неявок — только с депозитом»**: ⏸ решение владельца, по умолчанию выкл.

Не делаем: SMS/WhatsApp и «пора на стрижку» (E6.2 external), кассу, машину как сущность (T-5).

## 2. Что уже есть
- `no_show`: `booking/models.py` `STATUS_NO_SHOW`; переход `confirmed → no_show` в
  `booking/state_machine.py`; ставится экшеном карточки, доской (`transactions.apply_action`), Tagesplan.
  Роль в реестре — `cancelled` (`core/status_registry.py`) → неявку от отмены по роли не отличить,
  считать буквальный код. Депозит не возвращается (`core/refunds.py` `NO_REFUND_TARGETS`); отзывы
  исключают no_show. **Счётчика нет нигде.**
- `Booking.note` — ЗАМЕТКА КЛИЕНТА (уходит в письмо владельцу, видна в Tagesplan) → заметки мастера туда
  нельзя. `Meta.ordering=["start"]` → в агрегатах `.order_by()` (грабля VS-2c).
- Клиент: `promotions.Customer`; поиск при записи по e-mail (по телефону — только из кабинета, KA-H7).
- `crm.CustomerNote` (customer CASCADE, text, `-created_at`), вывод в `crm/views.py::customer_detail`,
  `templates/crm/customer_detail.html`; KPI/разделы — `crm/customer360.py` (`kpis`, `sections`; раздел
  Appointments печатает статус сырым кодом — поправить).
- Карточка записи: `booking/views.py::booking_detail` (скелет DC-1), шаблон `booking/booking_detail.html`.
- Tagesplan: `booking/views.py::calendar_context` (брони дня одним запросом), `booking/tagesplan.py`.
- DSGVO: `crm/dsgvo.py` `ERASURE_POLICY` (`crm.CustomerNote: delete`), выгрузка сериализует все поля.
- `scripts/golden_paths.py`: GP-1 (klingenbrot), GP-2 (shop), хелперы `Run`, `_page_health`, `_db_has`.

## 3. Модель данных — решение
**Счётчик — ВЫЧИСЛЯЕМЫЙ** (`apps/booking/no_shows.py`): один источник истины — статус записи; хранимый
счётчик пришлось бы держать в FSM/кастом-статусах/переносе/DSGVO (класс расхождений MX-2e). API:
`summary(customer) → {n, last, visits}`, `counts_for(ids) → {pk: n}` одним агрегатом
(`values("customer_id").annotate(Count).order_by()`), `NO_SHOW_STATUSES = ("no_show",)`.

**История услуги — расширить `crm.CustomerNote` (вариант C)**, миграция `crm/0003` (аддитивная):
`kind` (`note` | `service`, default `note`), `booking` FK SET_NULL, `service` FK SET_NULL,
`author` FK user SET_NULL (проверить, что User — TENANT; иначе снимок `author_name`), индекс
`(customer, kind, -created_at)`.

| Вариант | Плюс | Минус |
|---|---|---|
| A. поле `Booking.service_notes` | без таблицы | нет заметки без записи, нет автора, история = скан броней |
| B. `booking.ServiceNote` | чистая семантика | дубль CustomerNote: две ленты, две DSGVO-политики |
| **C. расширить CustomerNote** | одна лента, DSGVO `delete` уже есть, UI есть | crm ссылается на booking (строковые FK) |

DSGVO: рецептура — не деньги, хранить по GoBD не нужно → `delete`; `author` — в `SKIPPED` выгрузки.

## 4. UI
- **Карточка записи:** бейдж `⚠ N× nicht erschienen` (title «zuletzt am …»); блок «Behandlung &
  Rezeptur»: «Beim letzten Besuch» (до 3 service-заметок по этой услуге, иначе по любой с пометкой) +
  форма «＋ Notiz zu diesem Termin» с подсказкой «Keine Gesundheitsdaten … ohne ausdrückliche
  Einwilligung». Приёмник — `action=service_note` в `booking:booking-action` (уже под логином).
  Удаление — автор или owner/admin; правка — v2.
- **Tagesplan:** один `counts_for` на клиентов дня; бейдж в списке и в блоке сетки; 🎨 при наличии
  service-заметки (второй агрегат одним запросом).
- **Карточка клиента:** KPI «Nicht erschienen» (n>0, модуль booking); раздел «Behandlungshistorie».
- Кто: видеть и добавлять — любой участник кабинета; удалять — автор / owner / admin.

## 5. E6.4c (⏸ решение владельца, по умолчанию ВЫКЛ)
`site_config["booking"]["no_show_deposit"] = {"after": N, "days": 365}` (presence-minimal). На витрине:
клиент по e-mail, `n ≥ after` → обязательная предоплата `min(deposit, price)` (Stripe подключён) или
«Bitte rufen Sie uns an». Нейтральный текст без причины (оракул «этот e-mail не приходил»).
Вопросы: В-1 включаем? · В-2 N (рек. 2) · В-3 без Stripe — закрыть онлайн-запись или пропускать?

## 6. E11.1
**GP-3 «Termin»** в `scripts/golden_paths.py` (Playwright 390 px, демо friseur): `/termin/` → услуга →
свободное время → форма → `/t/<code>/` → `_db_has("booking.Booking", code, …)`. Нет слота — `✗` с
причиной, не тихий пропуск. **Серверный двойник** `apps/booking/tests/test_golden_termine.py`:
(а) book → confirm → fulfilled → `RevenueEntry` = total → `invoice_from_booking` с той же суммой;
(б) confirm → no_show → депозит не возвращён, `summary().n == 1`; (в) повторная запись того же e-mail →
тот же Customer.

## 7. Тесты (красные до кода)
`test_no_shows.py`: счёт (no_show×2, cancelled×1, fulfilled×3 → n=2, visits=3, last); `counts_for` —
1 запрос и верно при `Meta.ordering`; кастом-статус роли cancelled не считается; бейдж на карточке
есть/нет; Tagesplan без N+1. `crm/tests/test_service_notes.py`: создание через `action=service_note`,
аноним → логин, чужой pk → 404, показ на следующем визите, удаление (автор да, чужой staff 403, owner
да), пустой/длинный текст, XSS экранирован, заметка мастера не в письмах/ЛК. DSGVO: выгрузка без
`author`, удаление клиента удаляет заметки, замок покрытия. customer360: KPI и раздел. i18n — текстовым
дописыванием в 5 .po (не `polib.save()`).

## 8. Порядок
| # | Инкремент | Миграция |
|---|---|---|
| 0 | E11.1 GP-3 + `test_golden_termine` | нет |
| 1 | E6.4a `no_shows.py` + бейджи + KPI | нет |
| 2 | E6.4b `crm/0003` + заметки + «Behandlungshistorie» + DSGVO | ⚠️ `crm/0003` |
| 3 | Демо friseur/werkstatt (неявки, рецептура), `SEEDER_VERSION`, переводы | нет |
| 4 | E6.4c правило депозита | ⏸ владелец |

## 9. Риски
R1 Art. 9 DSGVO (аллергии/PPD-тест) — подсказка, без отдельного поля в v1 (В-4 поле с согласием,
В-5 шифрование) · R2 дубли клиентов без e-mail дробят счётчик (честно «по этой карточке»; слияние —
roadmap) · R3 свой статус «Nicht gekommen» не считается (v2: флаг `counts_as_no_show`) · R4 N+1 в
Tagesplan/Verkäufe — замок · R5 смешение заметок клиента и мастера — разные блоки, тест на письма/ЛК ·
R6 бейдж только в кабинете · R7 хелперы между декоратором и вьюхой · R8 GP-3 зависит от свободных слотов
демо.

## 10. ECC-прогоны
| Когда | Что |
|---|---|
| До кода | скиллы `django-patterns`, `django-tdd`, `postgres-patterns`, `database-migrations`, `django-security`, `e2e-testing`, `accessibility`; `pitfalls.md` §2–§5 |
| После плана | `architect` — коротко C против B и E6.4c |
| Инкр. 0 | Playwright GP-3 на `config.settings.stand` (Chromium `/opt/pw-browsers`, без `playwright install`) |
| Инкр. 1 | `django-reviewer`; `database-reviewer` на `counts_for` и запросы Tagesplan |
| Инкр. 2 | `database-reviewer` (`crm/0003`), `security-reviewer` (перс. данные, Art. 9, удаление, XSS, утечки), `django-reviewer`, `a11y-architect` (бейдж текстом, label формы), стенд 390/1440 + ru |
| Инкр. 3 | `django-reviewer` (сидер), `test_demo_*` |
| Инкр. 4 | `security-reviewer` (оракул e-mail), `silent-failure-hunter` (депозит) |
| Перед мержем | build-log, task-catalog, §3 CLAUDE.md, очередь миграций |

## 11. Вопросы владельцу
В-1…В-3 (§5) · В-4 поле аллергий с согласием · В-5 шифрование текста заметок · В-6 правка чужой
заметки — только owner/admin (рекомендация) или все.
