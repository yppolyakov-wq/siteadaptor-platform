# AIS — сводный план с прогонами ECC (2026-11-05)

Единая таблица программы AIS (упрощение создания сайта + модули по направлениям + ИИ-помощник):
порядок инкрементов, что грузим ДО кода (скиллы ECC), каких агентов зовём и на каком шаге, статус.
Источники: `ais-ai-setup-simplification-analysis` · `ais-wizard-v4-structure` ·
`ais-modules-directions-assistant-plan` (§5 — правки ревью, §5.5 — порядок) ·
`ais-w4-0-readiness-plan` · `ais-0-onboarding-metric-plan` (все 2026-11-05).

Правило проекта (CLAUDE.md §5): `django-reviewer` — всегда; `security-reviewer` — ввод/
авторизация/деньги/внешние вызовы; `database-reviewer` — миграции/тяжёлые запросы;
`silent-failure-hunter` — деньги/внешние вызовы; `e2e-runner`/Playwright — JS и вёрстка;
`a11y-architect` — новые UI-элементы. Гейт перед пушем: `ruff check` + `ruff format --check .` +
pytest затронутого + `scripts/i18n_quickcheck.py` + `test_template_comments` при шаблонах +
`npm run build:css` при новых классах.

## 0. Уже прогнано (анализ и планы)

| Что | ECC |
|---|---|
| Анализ рынка и пути пользователя | скиллы `product-lens`, `market-research`; разведки рынка и кода |
| Ревью планов мастера/модулей/помощника | `architect`, `security-reviewer`, `planner` (product-lens: 5 персон) |
| План W4-0 | `planner` |

## 1. Инкременты

| # | Инкремент | Скиллы до кода | Агенты (когда) | Статус |
|---|---|---|---|---|
| 1 | **AIS-0** метки мастера + `onboarding_report` | django-patterns, django-tdd | django-reviewer (перед мержем) | ✅ в main |
| 2 | **M-0** `apps/core/directions.py`, делегирование меню | django-patterns, django-tdd | замки паритета; django-reviewer не гоняли — чистый перенос (компенсирует ревью W4-0) | ✅ в main |
| 3 | **W4-0** `apps/core/readiness.py` + `readiness_report` + гейт за флагом | django-patterns, django-tdd, postgres-patterns, django-security | planner ✅ · django-reviewer ✅ (3 HIGH закрыты) · security-reviewer ✅ (уязвимостей нет) · silent-failure-hunter ✅ (2 HIGH закрыты: сбой проверки = исключение, ошибки направлений видны) · database-reviewer ✅ (индексы не нужны) | ✅ в main |
| 4 | **W4-1** шаг «Rechtliches & Veröffentlichen» (Impressum полями + вариант регулируемой профессии) + часы сеткой + публикация | django-patterns, django-tdd, accessibility | architect (сразу после плана: флаг v4 и маппинг состояния v2→v4) · django-reviewer · a11y-architect · e2e-runner (Playwright 390/1440) | architect ✅ (`Tenant.published_at` вместо site_config) · django-reviewer ✅ · security-reviewer ✅ · a11y-architect ✅ · стенд `scripts/wizard_v4_stand.py` 28/28 (нашёл: кабинет не уводил в мастер v4; e-mail Impressum без подсказки) | ✅ в main |
| 5 | **W4-2** шаг «Prüfen» без ИИ: строки «Name — Preis», «Beispiele einfügen», «Ich» для Termine, фото для Zimmer, вопрос «Wie verkaufen Sie?» | django-patterns, django-tdd, accessibility, e2e-testing | planner (план) · django-reviewer · a11y-architect · e2e-runner (5 персон × телефон) · silent-failure-hunter (массовое создание позиций) | planner ✅ · django-reviewer ✅ · security-reviewer ✅ (DoS регулярок закрыт) · silent-failure-hunter ✅ (цена из чужого числа закрыта) · a11y-architect ✅ · стенд 35/35 | 🚧 CI |
| 6 | **A-0** шторка «✨ Assistent» без ИИ: «чего не хватает» по экрану + реестр диагнозов через настоящие гейты | django-patterns, django-security, accessibility | architect (план: диагнозы не дублируют гейты) · django-reviewer · security-reviewer (права сотрудника, кросс-тенант) · a11y-architect · e2e-runner (шторка, Mini App) | ⏳ |
| 7 | **M-1** экран «Richtungen & Funktionen» + пресеты по направлениям + `modules_report` (классы «пресет/владелец») | django-patterns, django-tdd, database-migrations (если пересев киты) | planner · django-reviewer · database-reviewer (пересчёт `disabled_modules` живых тенантов) · e2e-runner · a11y-architect; поднять `SEEDER_VERSION`, замки `test_demo_menus`/`test_demo_lists` | ⏳ |
| 8 | **W4-4** фото/PDF меню и прайса → позиции (Claude; прод — Bedrock EU) | django-security, error-handling, django-celery | planner · **security-reviewer** (загрузка PDF/фото, prompt injection, `pii_scrub`) · silent-failure-hunter (внешний вызов) · django-reviewer · e2e-runner (экран проверки построчно) | ⏳ external-gated (ключ ЕС для прода) |
| 9 | **A-1** статьи справки (de + переводы) + поиск статей без ИИ | django-patterns, postgres-patterns (FTS), seo (не индексировать) | django-reviewer · database-reviewer (FTS) · a11y-architect | ⏳ |
| 10 | **A-2** ИИ-ответ помощника (`assistant_answer`): только id статей и ссылок, пост-проверка | django-security, error-handling, mcp-server-patterns (принципы tools/валидации) | architect · **security-reviewer** (injection, кросс-тенант, квота) · silent-failure-hunter · django-reviewer · e2e-runner | ⏳ external-gated |
| 11 | **W4-5** «Verkauf öffnen» вопросами + карточки «Nächster Schritt» + включение гейта кассы в точках продажи | django-patterns, django-security, accessibility | planner · security-reviewer (обход гейта) · silent-failure-hunter (деньги) · django-reviewer · e2e-runner (золотые пути `scripts/golden_paths.py`) · a11y-architect | ⏳ |
| 12 | **W4-3** поиск места в Google (Autocomplete + Details, после сметы цены) | django-security, api-design, error-handling | security-reviewer (платный ключ, лимиты /64, только после почты) · silent-failure-hunter · django-reviewer | ⏳ external-gated (`GOOGLE_PLACES_API_KEY`) |
| 13 | **W4-6** стенд мастера v4 (5 типов × телефон) → v4 по умолчанию | e2e-testing, accessibility | e2e-runner · a11y-architect · django-reviewer (снятие флага) | ⏳ |
| 14 | **A-3** эскалация в Support + журнал вопросов без ПД | django-security, database-migrations | security-reviewer (что уходит в тикет) · database-reviewer (миграция `SupportMessage` или текст) · django-reviewer | ⏳ |
| 15 | **AIS-5** «🌐 Übersetzen» (ИИ, квота тарифа) | django-security, error-handling | security-reviewer · silent-failure-hunter · django-reviewer · e2e-runner | ⏳ external-gated |
| 16 | **AIS-7** тексты «О нас»/описаний из фактов | django-security | security-reviewer (нет новых фактов — гард как `check_reply`) · django-reviewer | ⏳ external-gated |
| 17 | **AIS-6** дизайн «когда есть данные» — карточка с превью на своих данных | accessibility, e2e-testing | django-reviewer · e2e-runner · a11y-architect | ⏳ |

После каждого инкремента — `doc-updater` по конвенции памяти (build-log + task-catalog + §3 CLAUDE.md;
без npx-утилит).

## 2. Внешние блокеры (на владельце)

- Claude в проде через **AWS Bedrock EU**: аккаунт AWS, доступ к модели, ключи в `.env.prod` / админке
  «KI-Einstellungen» — блокирует 8, 10, 15, 16 в проде (на разработке/стенде — прямой API).
- `GOOGLE_PLACES_API_KEY` (Places API + биллинг) — блокирует 12 и Google-рейтинг GK-11.
- Юр. вычитка: абзац о помощнике в Datenschutzerklärung, тексты Impressum-варианта регулируемых
  профессий.

## 3. Замеры

AIS-0 после деплоя ≥ 2 недели → базовая линия. Пороги v4 —
`ais-modules-directions-assistant-plan-2026-11-05.md §5.4` (медиана ≤ 15 мин, p75 ≤ 30 мин,
≥ 70 % за сутки, Impressum 100 %).
