# SEC — аудит безопасности всего сервиса — 2026-11-01

> Запрос владельца: «полная проверка безопасности Telegram-приложения, авторизации и обработки данных клиентов и администраторов; использовать скиллы ECC; разработать план и пройти его целиком». Уточнение: аудит охватывает **весь сервис**, Telegram — блок A.
> Порядок по CLAUDE.md §5: план → замки (красные) → фиксы → ревью → CI. Формат — по прецеденту `p0-security-plan-2026-09-07.md`.
> Семейство ID **SEC**: находки `SEC-<блок><n>` (SEC-A1, SEC-D3…). Семейство добавлено в `docs/task-catalog.md`.
> План составлен агентом `planner` (ECC), гипотезы H-* — из первичного чтения кода; результаты фаз — в `docs/security-audit-report-2026-11-01.md`.

## §0. Цель и рамки

**Цель:** по каждому измерению §2 доказать кодом (file:line) или опровергнуть, что посторонний не получит чужую сессию, данные, деньги или действие. Подтверждённое закрыть минимальными правками; каждая правка — с замком, красным до фикса; без миграций, если без них можно.

**Блоки:**
- **A.** Telegram: Mini App, общий бот, бот бизнеса, бот портала, вход клиента через Telegram.
- **B.** Аутентификация и сессии: вход по ссылке, регистрация, быстрый старт, allauth, команда и права, ЛК клиента.
- **C.** Изоляция тенантов и авторизация кабинета: SHARED-модели, `schema_context`, домены, гейты демо/внутренних, админка на public.
- **D.** Деньги: Stripe и Connect, возвраты, фолио, остатки, чекауты и правки заказа, ваучеры, сертификаты, лояльность, лимиты акций, счета (GoBD), биллинг featured, скидки партнёров.
- **E.** Публичная витрина и формы: `csrf_exempt`, POST-приёмники, страницы по токену и коду, IDOR, перебор, лимиты, `next=`, richtext/`|safe`, загрузки, SSRF, кэш страниц.
- **F.** Портал, открытое API, MCP, ИИ: фид, поиск, Folgen, Melden, `/mcp/`, лимиты и prompt-injection ИИ, маскирование журнала.
- **G.** Данные, DSGVO, секреты, инфраструктура: шифрование секретов, документы, медиа, выгрузка и удаление ПДн, ретеншн, логи ПДн, prod-настройки, Docker/compose/Caddy/deploy, аудит зависимостей.

**Вне рамок:** реальные Telegram/Stripe/Google API (только наш код вокруг них), сервер и сеть Hetzner, прод-данные, юридическая достаточность текстов (сверяем только «код делает то, что написано»), нагрузочные атаки уровня DDoS.

## §1. Модель угроз

**Акторы:**
- X1 — аноним из интернета.
- X2 — клиент бизнеса (ЛК, ссылки из писем).
- X3 — владелец бизнеса A против бизнеса B.
- X4 — сотрудник с урезанными правами (E6.7) против владельца.
- X5 — бывший владелец или сотрудник (роль снята, связь погашена).
- X6 — житель портала.
- X7 — бот или скрейпер (перебор кодов, массовые POST).
- X8 — атакующий с утёкшим артефактом: ссылка из письма, токен, cookie, initData, URL вебхука, QR.
- X9 — партнёр (D3) против чужих клиентов.
- X10 — суперпользователь платформы (ошибки с его стороны — гигиена, не злоупотребление).
- X11 — внешний сайт или документ как источник prompt-injection (импорт сайта, ИИ).

**Активы:**
- сессии кабинета, ЛК и портала; одноразовые токены (вход, приглашение, подтверждение регистрации, handoff, DOI, отмена брони);
- секреты (`SECRET_KEY`, `SECRETS_ENCRYPTION_KEY`, ключи Stripe/ИИ/Google, токены ботов, `webhook_secret`);
- ПДн клиентов и жителей (контакты, адреса, Meldeschein, документы, переписка, заметки мастера);
- деньги (оплаты, возвраты, счета, ваучеры, лимиты акций, featured-оплата);
- целостность учёта (GoBD-нумерация, склад, журнал выручки);
- репутация каталога города (демо и скрытое не утекают).

## §2. Матрица проверок по блокам

Каждое измерение в отчёте получает: «проверено (file:line)», «находка SEC-Xn» или «отклонено (почему)». Гипотезы H-* — из первичного чтения; без верификации в фазе B они не находки.

### §2.A. Telegram

**Файлы:** `apps/platform_bot/*`, `apps/core/{tg_login,lite_cabinet,lite_home,personal_channels,integration_status}.py`, `TelegramLiteScopeMiddleware` (`apps/core/middleware.py:353-439`), `apps/telegram/*`, `apps/aggregator/{telegram_bot,portal_bot}.py`, `apps/community/telegram_bridge.py`, `apps/promotions/{telegram_promo,telegram_actions,message_parse,where}.py`, `apps/account/views.py:68-115`, шаблоны `platform_bot/miniapp.html`, `account/tg_start.html`; маршруты `urls_public.py:155-161`, `urls_tenant.py:140-146,184-185,245-249,838-841`, `urls_portal.py:75`.

| D | Измерение | Что проверить / гипотезы |
|---|---|---|
| A1 | Вебхуки | Общий бот (`platform_bot/webhook.py:33-65`) и портал (`aggregator/telegram_bot.py:64-104`) — эталон. Бот бизнеса (`telegram/public_views.py:22-43`): **H-A1** `compare_digest(str,str)` на `:33` → TypeError/500 на не-ASCII; **H-A2** синхронная обработка без дедупа `update_id`; **H-A11** нет ratelimit. |
| A2 | initData и токены | `webapp_auth.verify`; grace-повтор (`miniapp.py:315-348`); handoff `tg_login.issue/consume`; **H-A8** ticket выбора не привязан к IP; `app_signup`; вход клиента: своя подпись бота, `TG_MAX_AGE`, повтор с того же IP, `cycle_key`. |
| A3 | Граница `tg_lite` | Таблица по каждой записи `TG_LITE_VIEWS`: POST-only, CSRF, право `view_perms`, побочные эффекты GET, деньги. **H-A6:** вне `CABINET_PREFIXES` пользователь подменяется анонимом, но `_auth_user_id` остаётся. Порядок MIDDLEWARE. |
| A4 | Изоляция | `_owner_in_schema`, `owner_user`, `links.select`; `handle_platform_callback` с `owner_ok`; тот же гейт у `telegram_actions.on_callback` и `where.py`. |
| A5 | Deep links и callback | **H-A4** `/start owner-<token>`: сравнение `!=`, токен без срока, виден не только владельцу; `/start <link_token>` клиента; connect consume/restore; `pb:` ref; префиксы `pd/pp/pm/ps/g`; nonce и `_unfollow` у бота портала. |
| A6 | Данные | Инвентаризация ПДн бота и кэша; полнота `links.erase_user`, `rights`, `privacy`, `portal_bot.erase/export_data`; выгрузка без токенов. |
| A7 | Лимиты | `tgapp-ip/uid`, `tg-start`, `acct_tg_ip`, `tgportal-hook`, лимит регистраций; нет оракула «связь есть/нет». |
| A8 | Celery | Дедуп `platform_bot_update`/`portal_bot_update`; поведение при исключении. |
| A9 | Исходящие | **H-A3 (кандидат HIGH):** `raise_for_status` в `telegram/services.py` → текст HTTPError содержит `bot<TOKEN>`; ловят `logger.exception` (`public_views.py:42`, `community/telegram_bridge.py:124`), `Notification.last_error`; `before_send` текст исключения не чистит. `get_file_url` без потребителей. |
| A10 | Админка ботов | `platform_bot/admin.py`: токен не показывается после сохранения, «Webhook setzen» — POST. Кабинетные connect/disconnect — право владельца. |
| A11 | Вход клиента | Захват карточки через `/start` отбит (`auth.py:72-116`), advisory-lock, гейт модуля. |
| A12 | Шаблоны и JS | `textContent` в `miniapp.html`; `next`/`login_url` только серверные; **H-A7** CSP Mini App — только `frame-ancestors`. |

### §2.B. Аутентификация и сессии

**Файлы:** `apps/core/owner_login.py`, `apps/core/team.py`, `apps/core/{permissions,view_perms,perm_grants,roles}.py`, `SessionSchemaGuardMiddleware`/`CabinetOwnerAccessMiddleware`/`PackageScopeMiddleware`/`PendingStorefrontMiddleware` (`middleware.py`), `apps/tenants/{signup,views,quickstart,quickstart_views,tasks,adapters}.py`, allauth-настройки (`base.py:411-420`), `apps/account/{auth,views,urls}.py`.

| D | Измерение | Что проверить / гипотезы |
|---|---|---|
| B1 | Одноразовость токенов | **H-B1:** `owner_login.consume_token`, `team.consume_invite`, `account.auth.consume_magic_link` делают `get` → `delete`, не проверяя результат `delete` (в `tg_login.consume` проверка есть). |
| B2 | Побочные эффекты GET | **H-B2:** `account.login_verify` гасит токен и логинит на GET — сканеры почты сжигают ссылку. Аналогично — подтверждение регистрации, DOI, отписки. |
| B3 | Ссылки входа и подтверждения | TTL, неймспейс по схеме, `safe_next` во всех местах `next`, анти-энумерация ответов. |
| B4 | allauth | Регистрация закрыта; сброс пароля/смена e-mail не дают захватить чужой e-mail и не раскрывают аккаунт; лимиты allauth. |
| B5 | Регистрация и быстрый старт | `SignupRequest`: пароль хэшем, токен одноразовый, гонка slug, honeypot, лимиты; `provision_quick` идемпотентен; `email_pending` до клика; `/start/<token>/` — только браузер регистрации. |
| B6 | Сессии | `SessionSchemaGuardMiddleware`; `SESSION_COOKIE_DOMAIN` не задан; `cycle_key` при входах; logout чистит флаги. |
| B7 | Роли и права | Единый пол владельца; каждый экран имеет право в `view_perms`; снятие роли действует сразу; «ролевой гейт во ВСЕХ писателях». |
| B8 | ЛК клиента | Карточка по сессии, не по параметру; гейт `customer_account`; клиент A не видит заказ клиента B. |

### §2.C. Изоляция тенантов и авторизация кабинета

| D | Измерение | Что проверить / гипотезы |
|---|---|---|
| C1 | SHARED по pk | Каждая вьюха/задача, читающая SHARED-модель по pk/slug из запроса, фильтрует её по тенанту/порталу (BusinessReview, featured-checkout, Melden, PortalStat, partner dashboard, ai usage). |
| C2 | `schema_context` | Схема берётся из доверенного источника (Tenant из БД), не из ввода; ошибка одного тенанта не протекает к другому. |
| C3 | Домены | `verify_domain` строгий allowlist; custom-домен требует подтверждения владения; CustomDomainHost не подменяет тенанта Host-заголовком. |
| C4 | Демо/внутренние/скрытые | `objects.public()`/`visibility.listable` на всех чтениях портала, фида, MCP, sitemap, llms. |
| C5 | Админка public | Только `is_staff`/суперпользователь; tenant-only модели скрыты; секреты не видны в list/change/history. |
| C6 | Кабинет | Ни одной кабинетной вьюхи без входа (замок KA-H1); fetch/htmx под тем же правом; мусорный uuid → 404. |

### §2.D. Деньги

| D | Измерение | Что проверить / гипотезы |
|---|---|---|
| D1 | Вебхук Stripe | Подпись `construct_event`, отказ без секрета; **H-D1:** дедуп по `cache.add` — вытеснение Redis → повторная обработка; идемпотентность на уровне БД. Connect: тенант из `account`, не из metadata. |
| D2 | Подмена цены | Чекаут, quick-add, `/p/<uuid>/kaufen/`, `/o/<token>/`, `/angebot/<token>/`, `/bezahlen/`: сумма сервером; POST-цены/количества валидируются. |
| D3 | Возвраты | `refunds.py`/`apply_action` — право owner/бухгалтер на ВСЕХ поверхностях; сумма ≤ полученного по фолио; идемпотентность. |
| D4 | Лимиты и одноразовость | Лимит акций, купон «1 на человека», ваучер/сертификат, лимит 5 акций — под блокировкой или conditional UPDATE. |
| D5 | GoBD | Нумерация без дыр при параллели; выставленный счёт неизменен; Storno/Korrektur своим номером. |
| D6 | Featured и партнёры | Оплата featured без подмены листинга; скидка партнёра не навязывается чужим `?ref=`. |
| D7 | Ссылки оплаты | `/bezahlen/`, «Zahlungslink senden», balance-pay: без подмены суммы; повтор после оплаты без второй сессии. |

### §2.E. Публичная витрина и формы

| D | Измерение | Что проверить / гипотезы |
|---|---|---|
| E1 | Перебор кодов | **H-E1:** коды 6 символов; страницы подтверждения показывают ПДн → лимит на GET, единый 404, минимум ПДн, `no-store`. |
| E2 | Токены без срока | **H-E2:** `signing.loads` без `max_age` у отмены/check-in/iCal — осознанно ли; действие гейтится статусом. |
| E3 | `csrf_exempt` | Каждый из 8: обоснование, POST-only, размер тела, лимит, нет сессионных эффектов. Отписка RFC 8058 — только своя. |
| E4 | IDOR и мусор | Публичные формы с id в POST отвергают чужое и неактивное; мусор → 404. |
| E5 | `next=` | Все редиректы через `safe_next`/`local_next`. |
| E6 | XSS | 34 места `|safe`/`mark_safe`: источник каждого — константа/escape/nh3; JSON-LD экранирует `</`; richtext allowlist. |
| E7 | Кэш страниц | P0-1: персональное не в общем кэше; черновик Studio не утекает анониму. |
| E8 | Загрузки | Тип по сигнатуре, размер, `MAX_IMAGE_PIXELS`, SVG, uuid-имена, EXIF. |
| E9 | SSRF | Каждый исходящий запрос с пользовательским URL — через `ssrf.safe_fetch`; **H-E9:** `imports/cscart.py`, `publishing/*`, `google_places.py`. |
| E10 | Лимиты форм | Лимит по IP и контакту, honeypot, ответ без оракула. |

### §2.F. Портал, открытое API, MCP, ИИ

| D | Измерение | Что проверить / гипотезы |
|---|---|---|
| F1 | MCP | `MCP_ENABLED`; размер JSON-RPC, лимиты; только `objects.public()` в охвате портала; действия F-4 без оракула по адресу; логи без ПДн. |
| F2 | Фид, поиск, sitemap | Без демо и скрытого; мусор в курсоре/цене → не 500; `statement_timeout`; журнал поиска маскирует ПДн. |
| F3 | Folgen и DOI | Токены подписаны и со сроком; GET без побочных эффектов; отписка — только своя. |
| F4 | Melden и beacon | Лимит, дедуп солью; три голоса — без накрутки одним клиентом. |
| F5 | ИИ: шлюз | `AI_ENABLED`/`AI_REQUIRE_EU` fail-closed; дневные лимиты атомарны; ключи провайдеров не в логах. |
| F6 | ИИ: prompt-injection | Пост-проверки отбрасывают новые цены/ссылки/контакты; ИИ не исполняет действий; маркеры-разделители. |

### §2.G. Данные, DSGVO, секреты, инфраструктура

| D | Измерение | Что проверить / гипотезы |
|---|---|---|
| G1 | Секреты | MultiFernet, префлайт деплоя (P0-3), нет секретов в репозитории, ключи не в логах (класс H-A3 для Stripe/ИИ/Google). |
| G2 | Документы и медиа | Proxy-вьюха документа: чужому 404; `serve_media`: `safe_join`, приватные корни закрыты (P0-2). |
| G3 | DSGVO | Выгрузка полна и без чужих данных; удаление покрывает все модели с ПДн; ретеншн-beat'ы запускаются. |
| G4 | Логи ПДн | Grep логов на e-mail/телефон/токен; Sentry `send_default_pii=False`; `before_send` + скраббер токенов. |
| G5 | Prod-настройки | `check --deploy`; HSTS, secure cookies, `SECURE_PROXY_SSL_HEADER`; `DEBUG=False`; лимиты загрузки. |
| G6 | Контейнеры и Caddy | Не от root; Postgres/Redis не наружу; on-demand TLS `ask`; заголовки; `deploy.sh` не печатает секреты. |
| G7 | Зависимости | Разовый замер `pip-audit` по экспорту `uv.lock`; CVE ≥ HIGH — в отчёт. В CI без решения владельца не добавляем. |

## §3. Порядок исполнения

**Приоритет блоков по риску:** D → B → C → E → A → F → G. Независимые блоки идут параллельно.

**Фаза A — разведка волнами** (агенты ECC `security-reviewer`, `django-reviewer`, `silent-failure-hunter`, `database-reviewer`; при упоре в лимит агентов — ведущий доигрывает вручную и помечает это в отчёте). Каждому агенту: его подраздел §2, файлы, гипотезы, правило «находка = file:line + сценарий атаки; без сценария — отклоняется», запрет на правки.

**Фаза B — верификация (ведущий).** Перечитать код по каждой находке, при сомнении — пробник в тесте. Severity: **CRITICAL** — чужая сессия, деньги, кросс-тенант, RCE; **HIGH** — утечка секрета или ПДн, обход гейта прав; **MEDIUM** — двойное действие, оракул, перебор, 500 на вводе; **LOW** — гигиена. Отклонённые — в отчёт с причиной.

**Фаза C — замки (красные ДО фиксов).** Модули `apps/<app>/tests/test_sec_*.py`. Классовые замки:
1. Каждый consume одноразового токена пускает ровно один из двух параллельных вызовов.
2. Ни одна мутирующая вьюха в `TG_LITE_VIEWS` и публичных POST не принимает GET.
3. В модулях с вызовами Telegram/Stripe/ИИ/Google нет `logger.exception`/`str(exc)` без скраббера; `before_send` вырезает `bot\d+:[\w-]+`, `sk_(live|test)_\w+`.
4. Каждый вебхук: без заголовка / чужой / не-ASCII → 404, не 500; повтор не задваивает действие.
5. Страницы по коду: «нет» и «чужой» неотличимы; лимит GET срабатывает.
6. Каждый `|safe`/`mark_safe` — в allowlist-замке с обоснованием.
7. Каждый исходящий HTTP с пользовательским URL — через `safe_fetch`.
8. Деньги: повтор вебхука Stripe при вытеснении дедупа не создаёт второй платёж/выручку.

**Фаза D — фиксы.** Минимальные, без миграций (миграция → стоп и вопрос владельцу). Правила pitfalls §3.

**Фаза E — ревью диффа.** Каждый батч: `django-reviewer` + `security-reviewer`; при HIGH — второй раунд. `silent-failure-hunter` — на внешние вызовы/задачи/деньги; `database-reviewer` — блокировки/запросы.

**Фаза F — CI и доки.** Батч-коммиты `SEC-<Xn>: …`; гейт перед пушем: `ruff check .`, `ruff format --check .`, pytest затронутых модулей (+ `test_template_comments`, `i18n_quickcheck`); один CI → FF в main. Доки: `build-log.md`, §3 `CLAUDE.md`, `task-catalog.md`, `pitfalls.md` §3, отложенное — `roadmap-next-sprints.md` §Отложено.

## §4. ECC-прогоны

**Скиллы ДО кода:** `django-security` (все блоки), `django-patterns`, `django-tdd` + `python-testing` (замки), `error-handling`, `django-celery`, `redis-patterns`, `postgres-patterns`, `api-design`, `mcp-server-patterns` (F), `docker-patterns` + `deployment-patterns` (G6, справка), `database-migrations` — только при миграции.

| Шаг | Агент | Что |
|---|---|---|
| фаза A | `security-reviewer` ×8, `silent-failure-hunter` ×2, `django-reviewer` | волны разведки по блокам |
| фаза D | `silent-failure-hunter` | дифф внешних вызовов, задач, денег |
| фаза E | `django-reviewer` + `security-reviewer` | каждый батч; второй раунд при HIGH |
| блокировки/запросы/миграция | `database-reviewer` | дифф |
| правки JS | `e2e-runner` (Python-Playwright, Chromium `/opt/pw-browsers`) | без настоящего Telegram |
| фаза F | `doc-updater` | build-log, catalog, CLAUDE.md §3 |

## §5. Критерии готовности (DoD) и отчёт владельцу

- [ ] Все измерения §2.A–G: «проверено», «SEC-Xn» или «отклонено».
- [ ] Каждая подтверждённая CRITICAL/HIGH/MEDIUM исправлена; замок красный до фикса.
- [ ] LOW — исправлены или в roadmap §Отложено с причиной.
- [ ] Два ревью без открытых HIGH; CI зелёный; доки обновлены.
- [ ] Миграций нет (или каждая согласована владельцем).

**Отчёт владельцу:** `docs/security-audit-report-2026-11-01.md` — сводка по блокам + таблица `ID | Блок | Severity | Сценарий | Статус | Замок | Коммит` + ops-шаги и решения владельца.

## §6. Риски и границы

- Не проверяется в среде: реальные Telegram/Stripe/Google/ИИ-провайдеры, прод-логи и Sentry. Ops владельцу: поиск `api.telegram.org/bot`, `sk_live` по логам и Sentry; при находке — ротация токенов/ключей и «Webhook setzen»; `check --deploy` на сервере; `ss -tlnp` на порты Postgres/Redis.
- Гонки Redis/Postgres — тестами одного процесса и рассуждением по коду.
- `pip-audit` требует сети через прокси; при недоступности — ручная сверка.
- Юридическое — вне компетенции: только «код делает то, что написано».
- Регрессии: правки `middleware.py`, `tg_login.py`, `owner_login.py`, `billing/webhooks.py`, `refunds.py` гонять со смежными наборами и `test_money_invariant`.
