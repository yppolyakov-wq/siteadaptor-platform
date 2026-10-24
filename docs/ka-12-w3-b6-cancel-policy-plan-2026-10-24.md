# KA-12 W3 B6 = E4.4b «Правила отмены и самоперенос записи» — план, 2026-10-24

План — агент `planner` по коду HEAD. Миграция **`booking/0038`** (в плане ресурсов был номер 0036 —
устарел, 0036/0037 заняты E4.4a/E4.4b).

## Решения владельца
Поздняя отмена v1 — «удержать Anzahlung» или «всегда возвращать»; процентного сбора с карты нет
(§ 309 Nr. 5 BGB). Окно бесплатной отмены по умолчанию 24 ч. Самоперенос гостем — в том же окне,
≤ 2 раз, только на свободное время мастера с навыком. Политику правят owner+admin; staff —
длительность/варианты/навыки. Политика СНИМКОМ на записи (правка услуги не меняет старые записи).
**По рекомендации (автономно, 2026-10-24):** В-1 Mehrfachkarte — в окне кредит возвращается,
поздняя отмена сжигает визит; В-2 дефолт поздней отмены новых услуг — `keep_deposit`.

## 0. Опора в коде
- Образец — самоотмена отеля H4b (`apps/stays/public_views.py:872-927`, `services.cancellation_state`).
  Не копировать дыры: у отеля нет лимита частоты, блокировки строки и `retain_on_cancel`
  (удержанное не попадает в выручку — класс KA-MC X6).
- **Обход через ЛК:** `apps/account/views.py::cancel_booking` отменяет когда угодно и всегда
  возвращает деньги → перевести на общий сервис.
- FSM-хуки `cancelled` уже возвращают лимит акции, промокод, опции, сторно Anzahlungsrechnung.
- Деньги: `refunds.refund_payment` (идемпотентный, откат, письмо владельцу при сбое) +
  `money_contract.retain_on_cancel` (удержанное → выручка `{id}:retained`).
- `availability.free_slots_with_spots` не умеет исключить саму переносимую запись → нужен `exclude`.
- Группа HF-6c: депозит/Extras/промокод — на первой брони группы.

## 1. Модель (`booking/0038`, аддитивная)
- `Service.cancel_window_hours` (default 24, ≤ 720 валидатор + CheckConstraint), `Service.late_cancel`
  (`keep_deposit` | `refund`, CheckConstraint).
- `Booking.cancel_policy` JSON-снимок `{"v":1,"window_h","late","resched_max"}` (пусто = легаси:
  бесплатно до начала, refund, без самопереноса — поведение как сегодня), `Booking.reschedule_count`
  (CheckConstraint ≤ 10). Снимок пишет `services.book()` из СВЕЖЕЙ строки услуги под блокировкой.

## 2. `apps/booking/cancel_policy.py` — одна точка правил
`snapshot(service)` · `state(booking, now)` → `can_cancel/free/deadline/late_mode/kept_cents/
can_reschedule/reschedules_left/reason` · `guest_cancel` (atomic, `select_for_update` строки и
группы по pk, перепроверка под блокировкой, `BookingSM.apply(cancelled)`, деньги после коммита:
в окне или `refund` → `refund_payment`; иначе нет; всегда `retain_on_cancel`; повторный POST по
отменённой записи ДОВОДИТ возврат) · отказы v1: выставленный счёт; поздно + `keep_deposit` при
оплате больше депозита → «Bitte kontaktieren Sie uns» (прямая линия LS-6).

## 3. Гостевой флоу
- Токен `signing.dumps(pk, salt="termin-manage")` (группа — по первой брони); код `T-XXXXXX` для
  изменений не годится (перебор). Роуты `termin/verwalten/<token>/` (+ `stornieren/`, `verschieben/`).
- GET — без побочных эффектов, лимит частоты, `Referrer-Policy: no-referrer`, noindex, no-store.
- POST — CSRF, honeypot, лимит, PRG.
- `services.guest_reschedule` (отдельно от кабинетного `move`): блокировка строки → ресурсы по pk;
  текущий мастер, иначе любой с навыком; без override часов; длина = снимок `end − start`;
  счётчик условным UPDATE; акция — новый старт обязан проходить её правила; другая сезонная цена →
  отказ v1 (цену не пересчитываем); pool-опции — перенос на другой день запрещён v1.
- Ссылка manage — в письмах (created/confirmed/reminder/moved); на `/t/<code>/` НЕ показываем.
- Условия ДО брони: строка в buy-box услуги при депозите.

## 4. Кабинет
Блок «Stornierung & Umbuchung» в форме услуги только owner/admin (`roles`), сентинел
`cancel_policy_present`, сервер молча игнорирует поля от staff (W0); карточка записи —
дедлайн и «Umbuchungen durch Gast: N von 2». Письма владельцу `guest_cancelled` / `guest_moved`.

## 5. Замки (red-first)
Снимок и CheckConstraint · `state()` границы/легаси/кастом-статус · отмена: в окне → возврат один
раз, поздно + keep → нет возврата + `RevenueEntry :retained`, поздно + refund → возврат, двойной
POST → один возврат, сбой Stripe → «wird geprüft» · **ЛК после дедлайна не возвращает депозит** ·
хуки FSM ровно раз · группа · перенос: окно/лимит/`exclude`/навык/буфер/закрытие/акция/цена/гонка ·
HTTP: подделка токена 404, GET без эффектов, CSRF 403, 429, Referrer-Policy, токена нет на `/t/` ·
кабинет: staff не меняет политику, W0.

## 6. ECC-прогоны
| Когда | Что |
|---|---|
| До кода | `django-patterns`, `django-tdd`, `python-testing`, `database-migrations`, `postgres-patterns`, `django-security`, `error-handling`, `accessibility`, `e2e-testing`; `pitfalls.md` §1–§3 |
| После миграции | `database-reviewer` (`sqlmigrate booking 0038`, порядок блокировок против `book`/`move`/`resync_occupancy`) |
| После кода | `security-reviewer` (токен, Referer, лимит, IDOR групп, гейт политики), `silent-failure-hunter` (деньги: сбой Stripe, доведение возврата), `django-reviewer` (`test_orphan_decorators`, W0) |
| UI | `a11y-architect` (страница manage, подтверждение) + Playwright-стенд 390/1440, de/ru |
| Перед мержем | ruff целиком, pytest `--create-db`, `test_template_comments`, `i18n_quickcheck` + сверка `.txt` писем |

## 7. Порядок батча
1 миграция + snapshot/state · 2 guest_cancel + ЛК · 3 `exclude` + guest_reschedule · 4 публичные
вьюхи + buy-box · 5 кабинет · 6 письма + `.po` · 7 стенд, ревью, CI, мерж.
