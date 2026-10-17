# AI-0 — общий ИИ-слой `apps/ai/` (план, 2026-10-17)

**Источник требований:** `docs/ai-providers-setup-2026-10-16.md §4`, будущие потребители —
`docs/t8-ai-layer-2026-10-09.md` (T-8.10a/c, Г1). План составлен агентом planner.
**Вводная владельца (2026-10-17):** сейчас частное лицо, демо/разработка → личные dev-ключи
(прямой Anthropic / OpenAI / Mistral); Bedrock EU / Azure EU — позже на фирму. Переключение —
только настройкой. В прод-режиме dev-маршруты закрыты (fail-closed).

## 1. Переиспользуем
- ключи — `apps/secrets/store.py::get_or_setting` (как `tenants/google_places.py`);
- минимизация ПД — `aggregator/search_log.py::scrub` → выносится в `apps/core/pii.py`
  (в search_log — реэкспорт, замки T-8.21 целы);
- учёт без ПД, fail-safe — по образцу `aggregator/portal_stats.py::record` + `PortalStatAdmin`;
- настройки — `config/settings/base.py` через `env(...)`, словарь-конфиг как `AGGREGATOR_SEARCH_LOG`.

## 2. Зависимости — без новых пакетов
Bedrock — `boto3` (уже есть), `bedrock-runtime.converse` (Claude и Mistral на Bedrock одним
форматом). Прямой Anthropic Messages, OpenAI Chat Completions, Azure OpenAI, Mistral — HTTP через
`requests` (два диалекта: `anthropic_messages` и `openai_chat`). SDK anthropic/openai не берём:
тянут httpx/pydantic/jiter, стриминг и tool-use AI-0 не нужны. `jsonschema` — явной зависимостью
(уже в lock транзитивно).

## 3. Архитектура
`generate(task, prompt, *, schema=None, images=(), system="", tenant=None, locale="de") -> AIResult`

- `AIResult` (frozen): data, text, provider, model, route, tokens_in/out, cost_cents, duration_ms,
  `ai_generated=True` (контракт пометки «KI-generiert»), fallback_used.
- Реестр задач `TASKS` (tier fast|strong, schema, max_tokens, temperature, timeout, allow_images,
  pii_scrub). Неизвестная задача → `AIConfigError`. В AI-0 только `smoke`/`smoke_strong`;
  потребители добавляют свои записи.
- Маршруты: `AI_ROUTE_FAST`/`AI_ROUTE_STRONG` = списки (`bedrock, azure, mistral, anthropic,
  openai, fake`); порядок = резерв. `eu`: bedrock/azure/mistral/fake — да, anthropic/openai — нет.
- **ЕС fail-closed:** при `AI_REQUIRE_EU=True` (дефолт в production.py) не-ЕС маршруты вырезаются
  ДО вызова; пусто → `AIUnavailable`; system check `ai.E001`; у Mistral — только адрес ЕС.
- Ошибки `AIError(code)`: Disabled · Unavailable · RateLimited · QuotaExceeded · SchemaError ·
  ConfigError · Refused. Потребитель ловит `AIError` → ручная форма.
- 1 повтор на маршруте при 429/5xx/таймауте, затем следующий маршрут; ConfigError/4xx резерв не
  включают. Невалидный JSON — один повтор с текстом ошибки схемы, затем `AISchemaError` (без резерва).
- Изображения: JPEG/PNG/WebP по сигнатуре, ≤ 5 МБ, ≤ 4 шт.

## 4. Учёт и лимиты
`AIUsage` — SHARED (public): day, created_at, tenant_schema ("" = платформа), task, route, model,
tokens_in/out, images, cost_cents (Decimal 10,4), duration_ms, ok, error_code, fallback_used,
is_demo. **Без текста, хешей, пользователя, IP.** Лимиты по SUM за сегодня (мягкие, без блокировок):
`AI_TENANT_DAILY_CALLS=50`, `AI_TENANT_DAILY_EUR=1`, `AI_DAILY_BUDGET_EUR=10`. Цены — `AI_PRICES`
(env-JSON), неизвестная цена → 0 + `ai.W002`. Хранение 13 мес., beat `purge_ai_usage`.
Миграция `ai/0001` — аддитивная, database-reviewer.

## 5. Безопасность
`AI_ENABLED=False` по умолчанию → `AIDisabled` без сети и учёта. PII scrub промпта. Логи — только
task/route/model/tokens/ms/код; тела ответов и ключи не логируются. Константа
`AI_LABEL = "KI-generiert, bitte prüfen"`.

## 6. Фейк и живая проверка
Маршрут `fake` (детерминированный, валидный пример по схеме; режимы ok/down/429/bad_json/
bad_json_once/refuse) — дефолт тестов и dev без ключей. Сеть в тестах `apps/ai` запрещена.
`manage.py ai_smoke [--route] [--tier] [--image]`. Экран: только admin public (`AIUsageAdmin`,
суперпользователь, итог «сегодня / 30 дней»); экран владельца бизнеса — с первым потребителем.

## 7. Инкременты
- **AI-0a** ядро без сети: app в SHARED_APPS, настройки, errors, реестр, routing + ЕС, fake,
  generate, `core/pii.py`, system checks.
- **AI-0b** учёт и лимиты: `AIUsage` + миграция, budget, pricing, admin, purge.
- **AI-0c** адаптеры: bedrock, anthropic, openai, azure, mistral; ключи через secrets; `ai_smoke`;
  msgid «KI-generiert».

## 8. Решения по дефолтам (владелец может поправить env)
1. Лимиты пилота: 50 вызовов или 1 € на бизнес/день, 10 € на платформу/день.
2. Dev-ключи — в `PlatformSecret` или `.env` (оба работают); `AI_REQUIRE_EU=False` только на
   dev-сервере с демо-данными.
3. Хранение учёта — 13 месяцев.
4. Mistral на проде — прямой API ЕС.
