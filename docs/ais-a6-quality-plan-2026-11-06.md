# AIS A-6 «качество» — план (2026-11-06)

План — агент ECC `planner`, принят ведущим. Источник — `docs/ai-strategy-2026-11-06.md` §6 п. 5.
**Без миграций, без ИИ в CI, без нового свободного текста.**

## 1. Принципы
- Фразы храним только там, где они уже есть: `AssistantTurn.question` (вычищен `pii.scrub`, виден
  владельцу, «Verlauf löschen», 90 дней). Счётчики — только коды.
- Отказы, не доходящие до истории (лимит, выключено, пусто/длинно) — Redis-счётчики с TTL 35 дней, ключи
  строятся детерминированно (Tenant × даты × HANDLERS × CODES, `get_many`), без `scan_iter`.
- Фразы — только суперпользователю платформы через команду (`--samples`, повторный `pii.scrub`, ≤ 120
  символов, без e-mail пользователя/тенанта). Экран владельца «Was hat der Assistent nicht verstanden?» —
  отложен (roadmap).

## 2. Журнал (A-6b)
- `route()` ставит `request.assistant_route`; готовые записи несут `route` (ключ обработчика);
  `clarify_rounds` (число) в готовом пакете; `escalated=True` только после реальной записи треда.
- `apps/core/assistant_stats.py`: `bump(schema, route, code)` (белый список `CODES`, иначе `other`;
  `add`+`incr`, TTL 35 дней, никогда не бросает), `read(days, schema=None)`.
- `on_outcome(code, schema="")` — прежний вызов валиден.

## 3. Эталонные фразы (A-6a)
- `apps/core/tests/data/assistant_phrases.py`: `Phrase(text, lang, route, action=None, note="")`,
  ≥ 1 фраза на каждый ключ `HANDLERS` в каждом языке (de/en/ru/uk/tr) + негативы (налоги/право,
  болтовня, вопросы). `note`: real | synthetic (риск подгонки правил под набор).
- Тест `test_assistant_phrases.py`: `classify()` == ожидаемому ключу без ИИ; для правил — действие
  первого пункта; замки «каждый ключ × каждый язык», «без дублей».
- Команда `assistant_eval --schema <s> [--lang] [--route] [--ai] [--min]`: точность по обработчику,
  таблица промахов; `--ai` — только с ключом и `AI_ENABLED`, не пишет историю
  (`request.assistant_eval` → `assistant_history.record` пропускает).
- Промахи правил, найденные набором, — отдельным коммитом с замком на фразу (без подгонки «под набор»).

## 4. Отчёт `assistant_report` (A-6b)
`apps/core/assistant_quality.py::summarize(schema, since)` / `samples(schema, since, n)`; команда —
`--schema`/все, `--days 30`, `--json`, `--samples N`: доли исходов по обработчику, unclear/unknown/
check_failed, средний `dropped`, раунды уточнений, эскалации, предложено/применено/откачено
(`AssistantTurn kind=actions` × `AssistantChange` по job), отказы до истории из `assistant_stats`.

## 5. Замки до кода
набор фраз (§3); `assistant_stats` (неизвестный код → other, TTL, сбой Redis не бросает, в ключах нет
текста); журнал маршрута (`route` в записи, `clarify_rounds` переживает `_clean_entry`, `escalated`
только после отправки, eval не пишет историю); `assistant_quality` (точные доли на засеве, samples
чистит контакты, без `kind=answer`, фильтр периода); команды (`--ai` без ключа → CommandError).

## 6. Инкременты
A-6a набор + `assistant_eval` → A-6b журнал + `assistant_report` + строка в `ai-usage-policy`.
ops: после деплоя `assistant_report --days 14` — базовая линия; `assistant_eval --ai` вручную с ключом.

## 7. ECC
Скиллы: django-tdd, python-testing, redis-patterns, django-security, error-handling. Агенты:
A-6a — `django-reviewer` + `code-reviewer` (риск подгонки детекторов); A-6b — `django-reviewer`,
`security-reviewer` (PII в samples, текст в ключах, межтенантность), `silent-failure-hunter`,
`database-reviewer` (агрегаты `AssistantTurn` по `created_at` + JSON-фильтр).

## 8. Исполнено (2026-11-06)
A-6a — `assistant_phrases` + `assistant_eval`. A-6b — вместо `request.assistant_route` ключ
обработчика несёт contextvar `assistant_ai.ROUTE` (ставится и снимается в `assistant_router.route`;
запись задачи берёт его в `_put`, ИИ-задача и ответ на уточнение переносят `route` явно);
`assistant_stats`, `assistant_quality`, `assistant_report`. Прежний `on_outcome` — лог, не тронут.
