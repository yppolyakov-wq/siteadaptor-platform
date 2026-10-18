# ИИ-провайдеры: Claude + ChatGPT (+ запасной Mistral) — что купить, как подключить, что разрабатываем

**Дата:** 2026-10-16. **Решение владельца:** Р-E — Claude по рекомендации **и ChatGPT как один из
провайдеров**. Документ — инструкция для владельца (аккаунты, ключи, договоры) и план нашей
разработки (общий ИИ-слой). Факты о доступности моделей в регионах меняются — перед подключением
сверить с официальными страницами (ссылки в §6).

## 1. Главное в двух строках

- **Покупать заранее ничего не нужно.** Все варианты — оплата по факту (за токены), без
  абонплаты. Нужно: завести аккаунты, включить доступ к моделям, создать ключи, поставить лимит
  бюджета.
- **Данные клиентов должны обрабатываться в ЕС** (DSGVO). Поэтому Claude и GPT берём не напрямую
  у Anthropic/OpenAI, а через облака с размещением в ЕС: **Claude — AWS Bedrock**, **ChatGPT —
  Microsoft Azure (Azure OpenAI)**. Договор обработки данных (AVV/DPA) в обоих облаках входит в
  стандартные условия.

## 2. Какие провайдеры и почему

| Провайдер | Через что | Где обрабатываются данные | Зачем у нас |
|---|---|---|---|
| **Claude** (Anthropic) | **AWS Bedrock**, профиль «EU» | только регионы ЕС (Франкфурт, Стокгольм, Ирландия, Париж, Милан…); между ними данные могут перемещаться | основной: разбор сайтов/Instagram, тексты, проверка публикаций |
| **ChatGPT** (OpenAI GPT) | **Azure OpenAI**, развёртывание «Data Zone Standard — EU» (Германия West Central / Швеция) | ЕС | второй провайдер: сравнение качества, резерв при сбое, задачи, где GPT лучше |
| **Mistral** (Франция) | прямой API Mistral | ЕС | запасной, независимый от США |

Почему не напрямую:
- **OpenAI напрямую:** европейская обработка данных доступна только одобренным корпоративным
  клиентам (отдельный проект с регионом Europe, адрес `eu.api.openai.com`); обычный аккаунт
  обрабатывает в США.
- **Anthropic напрямую:** технически проще всего, но обработка не гарантированно в ЕС.
- **Claude в Azure:** работает, но EU-зоны для Claude в Azure пока нет — только глобальная/US.
- **Claude в Google Vertex:** вариант «EU multi-region» есть; можно вместо AWS, если удобнее
  Google Cloud (держим как запасной маршрут к Claude).

## 3. Что сделать владельцу — по шагам

### 3.1 Claude через AWS Bedrock
1. Завести **аккаунт AWS** на фирму (карта/счёт, НДС-номер для корректных счетов).
2. В консоли выбрать регион **Europe (Frankfurt) eu-central-1** → сервис **Amazon Bedrock** →
   **Model access** → запросить доступ к моделям **Anthropic Claude** (Haiku — быстрая/дешёвая,
   Sonnet — сильная; Opus — только если понадобится максимум). AWS попросит коротко описать
   сценарий использования — «SaaS für lokale Geschäfte: Texte, Import von Produktdaten».
3. В **IAM** создать отдельного пользователя/роль `siteadaptor-ai` только с правом
   `bedrock:InvokeModel` на EU-профили Claude; выдать ключ доступа.
4. **Budgets** → месячный лимит (на пилот — например 50 €) с письмом-оповещением на 80 %.
5. Передать нам: регион, ключ доступа (через шифрованный стор секретов платформы, не по почте),
   идентификаторы EU-профилей моделей (вида `eu.anthropic.claude-…`).

### 3.2 ChatGPT через Azure OpenAI
1. Завести **подписку Azure** (Pay-As-You-Go) на фирму.
2. Создать ресурс **Azure AI Foundry / Azure OpenAI** в регионе **Germany West Central**
   (если нужной модели там нет — Sweden Central).
3. Развернуть модель (GPT) с типом **Data Zone Standard (EU)** — именно этот тип держит
   обработку в ЕС; **Global Standard не брать**.
4. Скопировать **Endpoint**, **ключ** и **имя развёртывания**.
5. **Cost Management → Budgets** — месячный лимит с оповещением.

### 3.3 Mistral (запасной)
1. Аккаунт на **console.mistral.ai** (La Plateforme), платёжный план «по факту».
2. Создать **API-ключ**, поставить лимит расходов в настройках аккаунта.

### 3.4 Документы (для Datenschutz)
- AVV/DPA: у AWS и Microsoft — часть стандартных условий (скачать и сохранить в папку договоров);
  у Mistral — DPA в разделе Legal.
- Дописать в **Datenschutzerklärung платформы** раздел «KI-Dienste» (какие провайдеры, цель,
  ЕС-обработка, что не используется для обучения) — текст подготовим, проверка юристом.
- В интерфейсе всё сгенерированное помечаем «KI-generiert, bitte prüfen» (AI Act, ст. 50).

## 4. Что разрабатываем мы (фундамент «AI-0», до импорта Г1)

| Часть | Суть |
|---|---|
| `apps/ai/` — единый интерфейс | `generate(task, prompt, schema=…, images=…)` → проверенный JSON по схеме; задача выбирает класс модели «fast» / «strong» |
| Адаптеры | `bedrock` (Claude, `boto3`), `azure_openai` (GPT, SDK `openai` с Azure-адресом), `mistral`; одинаковый ответ для всех |
| Маршрутизация | настройка «какой провайдер для какой задачи» + резерв: упал основной → второй; провайдера меняем настройкой, не кодом |
| Ключи | в шифрованном сторе `apps.secrets` (как Google Places/Meta), фолбэк — переменные окружения |
| Лимиты | на тенанта и на платформу в день (A-3 «мягкий лимит в пилоте»), учёт токенов и стоимости |
| Безопасность | в запрос не уходят лишние персональные данные; в логах — только тип задачи, токены, длительность, без текста |
| Пометка | флаг «KI-generiert» у каждого созданного черновика, человек подтверждает перед публикацией |
| Тесты | фейковый адаптер — CI не ходит к провайдерам; живой «дымовой» тест — командой вручную |
| Выключатель | `AI_ENABLED=False` — все ИИ-функции скрываются, платформа работает как раньше |

Зависимости — через `uv` в `uv.lock`: `boto3`, `openai`, (`mistralai` или HTTP-вызов).

Переменные окружения (черновик): `AI_ENABLED`, `AI_ROUTE_FAST`, `AI_ROUTE_STRONG`,
`AWS_REGION=eu-central-1`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, `BEDROCK_MODEL_FAST`,
`BEDROCK_MODEL_STRONG`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_DEPLOYMENT`, `MISTRAL_API_KEY`, `AI_DAILY_BUDGET_EUR`.

ИИ-модерация каталога города (D2b-2) включается ОТДЕЛЬНО и только после ЕС-маршрута fast:
`AI_CATALOG_MODERATION=True` (потолки `AI_CATALOG_MODERATION_DAILY=300`,
`AI_CATALOG_MODERATION_TENANT_DAILY=20`; бюджет платформы).

## 5. Порядок

1. Владелец: аккаунты AWS + Azure (параллельно), доступ к моделям, ключи, бюджеты.
2. Мы: AI-0 (интерфейс + 3 адаптера + лимиты + фейк для CI) — можно начинать до ключей.
3. Первый потребитель — Г1 «импорт с сайта клиента» (Р-A/B/C), затем Д1/Д2.

## 6. Источники

- OpenAI: [Introducing data residency in Europe](https://openai.com/index/introducing-data-residency-in-europe/),
  [eligibility (community)](https://community.openai.com/t/how-can-an-api-customer-become-eligible-for-eu-data-residency/1381888).
- AWS Bedrock: [Regional availability by models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html),
  [Claude Sonnet 5.5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html),
  [Claude in Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock).
- Azure: [Region availability for Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability),
  [Claude in Foundry — EU timeline](https://learn.microsoft.com/en-sg/answers/questions/5867930/timeline-for-claude-in-microsoft-foundry-to-run-on).
- Google: [Vertex AI data residency](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/data-residency).
- Обзор: [EU Data Residency for AI APIs 2026](https://wavect.io/blog/eu-data-residency-ai-apps-2026/).
