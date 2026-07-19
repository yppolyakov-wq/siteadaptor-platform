# LS-6 «Прямая линия» — план (2026-07-19)

Этап C1 ТЗ `next-gen-master-tz-2026-07-19.md §3` (концепт LS-6 в
`live-selling-finder-concept-2026-07-18.md`): недовольный клиент попадает к
владельцу ДО публичного отзыва. Разведка — фоновый Explore 2026-07-19 (карта
файл:строка в отчёте): priority=high, ref сделки, contact-префилл из query,
Telegram-канал владельцу (UD4-2) и паттерн `_telegram_cta.html` — ГОТОВЫ.

## 1. Решения

- **Кнопка «⚠️ Etwas stimmt nicht?»** — новый партиал
  `storefront/_problem_cta.html` (образец `_telegram_cta.html`), include на
  7 поверхностях: подтверждения order/booking/stay/ticket/reservation
  (у reservation `_telegram_cta` нет — отдельный include), публичная страница
  предложения `/o/` (LS-3) и ЛК клиента. Ссылка →
  `/nachricht/?problem=1&ref_kind=<kind>&ref_id=<reference_code>&ref_label=…&subject=…`.
- **Доверенный маркер, не открытый priority:** публичная форма НЕ принимает
  `?priority=` (аноним поставил бы high всем) — `contact()` распознаёт
  `problem=1` И непустой ref → `start_conversation(..., priority="high")`
  (новый параметр сигнатуры). **Договорённость ключа: `ref_id =
  reference_code`** (то, что видит клиент; единая с lookup канбана — риск N+1
  разведки).
- **Немедленный пуш владельцу:** в `start_conversation` при priority=high —
  `send_to_owner(type="inbox_problem", dedupe_key=f"inbox:conv:{id}:problem:owner:tg")`
  (одна тревога на тред — осознанно) + owner-email как обычно.
- **Красная полоса на канбане:** batch-lookup ОДНИМ запросом на секцию
  (`Conversation.filter(status__in=[open,pending], priority="high",
  ref_kind=kind, ref_id__in=<codes>)`) → поле `has_problem` в dataclass
  `Transaction` → красная полоса + «⚠️ Problem» в `_kanban_card.html`.
  Никаких per-card запросов (N+1 риск).
- **SLA-таймер v1:** новое денормализованное поле НЕ вводим (без миграции):
  время реакции треда = `первый staff-Message.created_at − created_at`
  (запрос в кабинетном треде + средний по решённым за 30 дней в списке inbox
  — две агрегации, показ «⌀ Reaktionszeit»). Публичный бейдж доверия — LS-4.
- **Service recovery:** хук `ConversationSM.on_transition` при `resolved` у
  HIGH-треда с ref → мягкое письмо «Alles wieder gut?» со ссылкой на отзыв
  (реюз review-роутов post_visit/post_stay), dedupe
  `inbox:conv:{id}:recovery`; гейты `customer.email`, `unsubscribed`,
  unsubscribe-ссылка (UWG — как post_purchase).
- **Письма:** `problem_url` в confirmed-письмах order/booking/stay/ticket
  (`_base_url`-паттерн; без домена — без ссылки).

## 2. Инкременты

1. Ядро: `priority=` в `start_conversation` + problem-гейт в `contact()` +
   Telegram-пуш + партиал кнопки + 7 include + письма. Тесты: high только с
   problem+ref; пуш с dedupe; кнопка на поверхностях; письмо с problem_url.
2. Канбан+SLA: `has_problem` batch (замок: 1 запрос на секцию —
   assertNumQueries), полоса на карточке; ⌀ Reaktionszeit в списке/треде.
3. Recovery: on_transition resolved → письмо (дедуп, UWG-гейты); финал —
   i18n/CSS/доки/CI.

Без миграций. Приёмка ТЗ C1: проблемный клиент → high-тред с контекстом ✅,
владелец видит в Telegram/канбане за секунды ✅, SLA виден ✅, recovery ✅.
