# AIS A-5 «один мозг» — план (2026-11-06)

План — агент ECC `planner` (сверен с кодом), принят ведущим; ревью `architect` — §9. Источник —
`docs/ai-strategy-2026-11-06.md` §6 п. 4 и решения §7 (В-1 один вход, В-2 запретный список, В-3 массовые
≤ 50, В-4 в ИИ — названия магазина, клиенты никогда). Опирается на A-3 (`ais-a3-assistant-panel-plan`) и
A-4 §14. **Цель:** вопрос, создание, изменение и поддержка через одно поле шторки; неоднозначная фраза —
не тупиковый пункт `blocked`, а короткий вопрос с кнопками-ответами, ответ продолжает **тот же** пакет.
**Миграции:** нет (если `AssistantTurn.kind` не расширять; иначе choices-only `core/0018`).

## 1. Роутер `apps/core/assistant_router.py` (A-5a, без смены поведения)
- `Handler(key, intent(req, q, ctx) -> hit | None, handle(req, q, ctx, hit) -> dict)`; `intent` в кэш не пишет.
- `HANDLERS` в нынешнем порядке 1:1 с `assistant_views.assistant_ask`: bulk (A-4d) → changes (A-4b) →
  pages (A-4c) → mixed (A-4e-3; quota/busy/unavailable → `put_plan`) → create (A-3a) → ai_actions (A-4e) →
  answer (A-2; disabled → `put_articles`). Позже перед ними: `followup`, `escalate`, `reply`.
- `route(request, raw, seite) -> (key, got)`; ошибка `prepare_question` — сразу answer, как сейчас;
  `assistant_ask` — тонкий; `key` → метка `assistant.route` (без текста вопроса). `classify()` — dry-run.
- Замки: паритет-таблица ~40 фраз de/ru (снята на ТЕКУЩЕМ коде), ровно один обработчик на фразу,
  AST-замок «в `assistant_ask` нет `*.intent(`».

## 2. Уточняющие вопросы (A-5b)
- Состояние задачи `state="ask"` (`ENTRY_V` → 2): `slot` (pick_target | direction | price | category),
  `options [{id, label}]` 2…6, `round` 1/2, `base` — тот же пакет и индекс пункта `at`.
- `apps/core/assistant_clarify.py::need(item, ctx) -> Ask | None` — ВМЕСТО `blocked` в 4 местах:
  `assistant_changes.build` (два одноимённых → pick_target; `_RELATIVE` без знака → direction; нет суммы →
  price), `assistant_ai_actions._ambiguous` → pick_target, `assistant_pages` «mehrere Einstellungen» →
  pick_target, `item_for(move)` без цели → category (≤ 6 + ссылка «Neue Kategorie»). `apply_answer(entry, …)`.
- Валидация: `option_id` — только из `options` записи в КЭШЕ; варианты pick_target перепроверяются правом и
  пакетом; свободный ввод только у price (`core.money.parse_amount`, мусор → тот же вопрос с ошибкой);
  direction пересчитывает ПРАВИЛО (Decimal, 2 знака), предупреждение § 11 PAngV цело. После 2 раундов —
  прежний `blocked` со ссылкой. Без ИИ работает; текст вопроса — `gettext` реестра `SLOT_TEXT` (ИИ вопросов
  не формулирует).
- `POST assistant/<job>/antwort/` (`assistant_reply`, login + POST + лимит `assistant-reply`); чужой/истёкший
  → expired; тот же job, `cache.add(f"{key}:reply:{round}")` против двойного тапа.
- Замки: два «Käsekuchen» → чипы → нужный pk; чужой option → отказ; «10 % teurer» после direction = ×1,10;
  3-й раунд невозможен; уточнение не обходит `preise.edit` и потолок 50.

## 3. Продолжения (A-5c)
- `apps/core/assistant_followup.py`, обработчик `followup` первым: маркеры «auch / ebenfalls / тоже / и … тоже»
  + имя объекта, И последний ход ЭТОГО пользователя (≤ 15 мин, `kind=actions`) с применимым пакетом;
  новый пункт через `item_for` (абсолютная цена — только если владелец сам её вводил). Пакеты из истории
  не применяются (A-4a), строится НОВЫЙ.
- ИИ получает только сводку прошлого хода («hide product, 1 Position») — без цен, pk, пунктов (замок).
- Замки: «Apfelstrudel ausblenden» → «und den Käsekuchen auch»; без прошлого хода — обычная цепочка;
  чужой ход не подхватывается; старше 15 мин — нет.

## 4. Эскалация в поддержку (A-5d)
- `apps/core/assistant_escalate.py`, обработчик `escalate`: правила на 5 языках («funktioniert nicht»,
  «Mensch», «Support», «не работает», «человек») ИЛИ два подряд `fallback/unknown` → карточка «An den
  Support senden?» с ПРЕВЬЮ (≤ 5 своих вопросов + seite + коды диагнозов A-0 + key; без ответов ИИ и данных
  клиентов), правится и уходит только кнопкой → `apps.support.services` (открытый тред — добавить сообщение),
  `notify_platform`, вкладка Support. Право — как у формы Support; лимит `assistant-support` 3/час.
- Замки: ровно один тред (двойной POST); нет e-mail/телефонов клиентов; без кнопки — ничего.

## 5. Интерфейс
Одно поле; ветки `state=ask` и `outcome=escalate` в `_assistant_answer.html`, партиал
`core/_assistant_clarify.html`; чипы — `<button name="option">` в форме (без JS — POST + 302), шторка —
fetch с делегированием на `document`. a11y: `role=status aria-live=polite`, фокус на первый чип, группа с
`aria-labelledby`, чипы ≥ 44 px. Mini App: `assistant-reply` в `tg_login.TG_LITE_VIEWS` (замок паритета).

## 6. Данные и право
`AssistantTurn` для ответа на уточнение (без `options/base/slot` — `_DROP`), `SupportThread/Message` при
эскалации; сроки прежние (90 дней / 200). Datenschutz «Assistent»: до 3 своих ходов (в ИИ — только
сводка); отправка в поддержку — кнопкой с превью. Юр-вычитка — владельцу.

## 7. Инкременты
A-5a роутер (паритет) → A-5b уточнения → A-5c продолжения → A-5d поддержка; гейт каждого —
ruff + pytest apps/core apps/support + template_comments + i18n_quickcheck (+ build:css).

## 8. ECC
Скиллы: django-patterns, django-tdd, django-security, redis-patterns, accessibility, e2e-testing. Агенты:
`architect` (план, сейчас), `django-reviewer` каждый инкремент, `security-reviewer` A-5b/A-5d,
`silent-failure-hunter` A-5a, `a11y-architect` A-5b, `e2e-runner` стенд
(`scripts/assistant_a5_stand.py`, 390/1440, de+ru, bakery: два «Käsekuchen»; «Kuchen um 10 %» → «teurer»;
«und den Käsekuchen auch»; «das funktioniert nicht» → Support; без JS; Mini App).
