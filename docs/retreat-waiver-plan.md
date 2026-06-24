# R8 — Waiver + Gesundheits-Selbstauskunft с e-подписью (план)

> ✅ **РЕАЛИЗОВАНО** (2026-06-24). Первый пункт рыночного бэклога R7+ (см.
> `retreat-archetype-plan.md` §4.1). Хронология — `build-log.md`. Ниже — исходный план.

## Зачем (рынок)
Почти все ретрит-софты (Retreat Guru, WeTravel, Arketa) требуют **подписанный
отказ от ответственности** (Haftungsausschluss/Waiver) + **самоаускунфт о здоровье/
пригодности** перед участием — юридическая защита организатора (йога/детокс/
пост/физнагрузка). У нас есть свободная анкета (R1: diet/medical), но **нет
подписи и снимка согласия**. Дёшево: переиспользуем паттерн `stays.GuestRegistration`
(простая e-подпись: печатное Ф.И.О. + отметка времени + IP, eIDAS «einfache»).

## Объём (что делаем)
Подпись waiver — **на билет** при онлайн-брони. Конфигурация — на событие
(организатор включает и задаёт текст). Снимок текста на момент подписи — для
юридического следа (переживает правку шаблона).

## Подзадачи (по пунктам)

**R8.1 — Модель + миграция.**
- `Event.waiver_required: bool` (default False) — требовать подпись.
- `Event.waiver_text: TextField` — текст отказа/условий (задаёт организатор; пусто = дефолтный шаблон).
- `events.TicketWaiver` (OneToOne→Ticket): `waiver_text_snapshot`, `health_confirmed: bool`
  (подтверждение «здоров/раскрыл противопоказания»), `signed_name`, `signed_at`, `signed_ip`.
- Миграция `events/0012`. Удержание: waiver не авто-чистим (срок исковой давности) —
  в отличие от BMG-Meldeschein; отметка в доке.

**R8.2 — Сервис брони.**
- `book_ticket(..., waiver_signed_name="", health_confirmed=False)`.
- Если `event.waiver_required`: нет имени-подписи → `WaiverRequired` (новое исключение,
  вся транзакция откатывается). Иначе создаём `TicketWaiver` со снимком текста + подпись
  (имя/время/IP) — в той же атомарной транзакции, что и билет.
- Для бесплатного авто-confirm и платного потоков одинаково (подпись до оплаты).

**R8.3 — Витрина (форма брони).**
- Если `waiver_required`: блок с текстом waiver (скролл), чекбокс «Ich habe gelesen
  und akzeptiere», поле «Unterschrift (Name)», опц. чекбокс health-Selbstauskunft.
- Вьюха `veranstaltung_book`: парсит подпись/health, прокидывает в `book_ticket`,
  ловит `WaiverRequired` → сообщение об ошибке (без потери данных формы — redirect+msg, как сейчас).
- IP берём `ratelimit.client_ip(request)` (уже есть).

**R8.4 — Кабинет.**
- `EventForm`: поля `waiver_required` (чекбокс) + `waiver_text` (textarea).
- `event_detail` (ростер) + `roster.csv`: колонка «Waiver» (✓ подписан / —) и дата/имя подписи.

**R8.5 — Памятка/документ.**
- В `memo.py` (Teilnehmer-Infoblatt) — строка «Haftungsausschluss unterschrieben am …»
  если подписан (без полного текста; полный — в кабинете/снимке).

**R8.6 — Демо.**
- На флагманских ретритах (`Waldlicht Wochenend-Retreat`, `Ayurveda-Detox`) включить
  `waiver_required` + короткий текст; в `seed_records` — пара подписанных waiver.

**R8.7 — Тесты.**
- waiver обязателен → без подписи `WaiverRequired`, билет не создан;
- с подписью → `TicketWaiver` создан, снимок текста, IP/время;
- health-флаг сохраняется; не-required событие подпись не требует;
- форма кабинета сохраняет `waiver_required`/`waiver_text`; ростер-CSV содержит колонку.

## Не делаем (сознательно)
- Полноценную квалифицированную подпись (QES) — избыточно; «einfache» eIDAS достаточно
  (как Meldeschein). Авто-purge — нет (юр. удержание). Отдельный PDF-waiver — позже, если попросят.

## Порядок
R8.1 → R8.2 → R8.3/R8.4 (вместе) → R8.5 → R8.6 → R8.7. Один коммит (фича целиком),
CI зелёный, чекпоинт. Следующий по бэклогу — R9 (pre/post-event авто-письма).
