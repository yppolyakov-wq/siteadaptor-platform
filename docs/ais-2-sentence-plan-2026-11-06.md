# AIS-2 «Beschreiben Sie Ihr Geschäft in einem Satz» — план (2026-11-06)

Источник: анализ `ais-ai-setup-simplification-analysis-2026-11-05.md` (строка AIS-2),
план агента `planner`, сверен с кодом.

## 0. Что умеет `setup_plan`
- `setup_assistant.build_plan(text, tenant, user)` — разбор запроса на создание: до
  `MAX_STEPS=4` шагов `category|product|service|room|event|promotion` (имя, цена,
  длительность). Тип бизнеса и поля компании НЕ возвращает — их не подставляем.
- «Никаких новых фактов» уже встроено: правила берут цену только с валютой, ИИ —
  имя из слов фразы, цена/длительность сверяются с текстом; пустой ответ ИИ → правила.
- Права — `allowed_entities` (модуль + `sortiment.edit`).

## 1. Где поле
Р-1 (владелец): необязательное поле под 4 карточками шага `quelle`, та же кнопка
«Weiter» — ноль новых кликов. Запасной вариант B: кнопка «✨ Aus einem Satz» в `pruefen`.
Шаг пройден при `had or sentence`.

## 2. Что подставляем
- Адаптер `apps/core/offer_sentence.py`: `build(tenant, user, text) -> Result(lines, note)`,
  `lines_for_kind(lines, kind) -> str`. Строка — формат `offer_lines`:
  `«name — price €»` (+ `« — N min»` у услуги); без цены — только имя.
- Вид: service→termine, room→zimmer, event→tickets; product — к любому активному виду.
- category/promotion строками не становятся (подсказка «später»).
- Вступление до первого `:` в план не идёт.
- В БД ничего: только ТЕКСТ textarea `pruefen`, создание — штатный «Übernehmen».

## 3. ИИ
- Синхронно в POST quelle (как `page_templates.setup_plan_for`); лимит тот же
  `setup-plan` 20/10 мин; при лимите — молча правила. Пересчёт только при изменённой фразе.
- `{% ai_notice "setup_plan" %}` под полем; `disclosure.TASK_DATA["setup_plan"]` += мастер
  (Р-2: правовая вычитка за владельцем).

## 4. Хранение
- `onboarding["sentence"]` (str ≤ 400), `onboarding["sentence_lines"]` (≤4 `{e,t}`),
  presence-minimal, в белом списке нормализатора и в `_OWNED_STATE_KEYS`.
- Писатель `onboarding.set_sentence` под `select_for_update`; пишется ДО ветки website.
- `_ctx_pruefen`: черновик сессии → строки фразы → образцы «Nichts davon»; только пока
  нет предложений; подпись «Aus Ihrem Satz übernommen — bitte prüfen».

## 5. Инкременты
- **2a** адаптер + тесты (`apps/core/tests/test_ais2_sentence.py`).
- **2b** поле + состояние (`apps/tenants/tests/test_ais2_quelle_sentence.py`).
- **2c** подхват в `pruefen` + стенд `wizard_v4_e2e_stand.py` (bakery, friseur, 390/1440).

## ECC-прогоны
- Скиллы до кода: django-patterns, django-tdd, django-security, accessibility.
- `django-reviewer` — каждый инкремент; `security-reviewer` — фраза уходит в ИИ и хранится;
  `silent-failure-hunter` — откаты ИИ/лимита; `a11y-architect` — поле; стенд Playwright.
- `database-reviewer` не нужен (миграций нет).

## Риски
- Описательные фразы плохо ложатся на правила → плейсхолдер с форматом, строки правятся
  до «Übernehmen». Промпт ИИ общий с A-3a/A-4 — не трогаем в v1.
- До ~15 с ожидания на «Weiter» при ИИ → `aria-busy`, v2 — Celery.
