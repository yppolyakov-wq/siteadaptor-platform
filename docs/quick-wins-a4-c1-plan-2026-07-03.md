# Быстрые победы A4 + C1 (план, 2026-07-03)

Остаток п.3 одобренного стека ТЗ (A3/C2/B3 ✅). Разведка агентом, факты
сверены (file:line в транскрипте).

## A4 — Share-ссылка на черновик витрины (read-only, без логина)

Механика превью уже готова: витрина читает `session["site_preview_draft"]`
при `?preview=1` (главная `public_views.py:~91`, хром `context.py:~119`);
page-кэш обходится сам (`pagecache.py`: непустая сессия/GET-параметры).

- **Выпуск (owner):** POST `/dashboard/site/share-preview/` — снапшот =
  `session["site_preview_draft"]` | `Tenant.site_config["_draft"]` |
  `normalize(site_config)`; `cache.set("share_preview:<token>", draft, 7 дней)`,
  `secrets.token_urlsafe(32)` (паттерн magic-link `aggregator/auth.py`).
  Ответ JSON `{url}` → кнопка «Share-Vorschau» в топ-баре билдера (рядом с
  Save): fetch + clipboard + статус.
- **Просмотр (аноним):** GET `/vorschau/<token>/` — `cache.get` (БЕЗ delete,
  многоразово до TTL) → снапшот в сессию посетителя под `site_preview_draft`
  → redirect `/?preview=1`. Нет/истёк → страница «Link abgelaufen» (410).
  Read-only по построению (нет логина; data-edit-атрибуты инертны вне
  iframe редактора).
- **Снапшот фиксируется в момент выпуска** (cache), дальнейшие правки
  владельца на ссылку не влияют (риск #4 разведки).
- Замки: roundtrip (аноним видит draft-заголовок на главной), 410 по
  истечении, фиксация снапшота, выпуск требует логина.

## C1 — Утренний дайджест владельцу (MVP: email)

- **Сбор** `apps/core/digest.py`: выручка вчера (`RevenueEntry.date`, Sum);
  сегодня — брони (`Booking.start__date`, ACTIVE), заезды
  (`StayBooking.arrival`), события (`Event.starts_at__date`, published);
  «требует действия» — pending-брони/-заезды/-билеты, заказы `new`,
  Anfragen `jobs.new`, `inbox.unread_for_staff`. Только активные модули
  (`is_module_active`), fail-safe по блокам.
- **Задача** `apps/core/tasks.py::send_owner_digests` — tenant-loop
  (паттерн `booking/tasks.py`), в `CELERY_BEAT_SCHEDULE` раз в час;
  внутри гейт «локальный час тенанта == 7» (`tenant.timezone`; без
  crontab-новшества). Дедуп — `notify(dedupe_key=f"digest:{schema}:{date}")`
  (unique в БД) → повторные прогоны безвредны.
- **Письмо** — `notify()` на `tenant.owner_email`; шаблон
  `emails/owner_digest*.txt` (owner-письма — DE, без trans, как остальные).
  Пустой день (нет ни выручки, ни событий, ни действий) — НЕ слать.
- **Opt-out:** `Tenant.owner_digest_enabled` (bool, default True; SHARED
  миграция tenants/0021) + чекбокс в настройках.
- **Telegram владельцу — ВТОРЫМ шагом** (гэп: chat_id владельца нигде не
  хранится, `TelegramLink` только у клиентов; нужен /start-биндинг —
  в roadmap §Отложено).
- Замки: агрегаты по фикстурам, «пустой день не шлёт», дедуп второго
  прогона, opt-out, гейт часа.
