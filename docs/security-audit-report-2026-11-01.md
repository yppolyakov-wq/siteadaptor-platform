# SEC — отчёт аудита безопасности всего сервиса — 2026-11-01

> План — `docs/security-audit-plan-2026-11-01.md`. Запрос владельца: «полная проверка
> безопасности Telegram-приложения, авторизации и обработки данных клиентов и администраторов»,
> уточнение — «весь сервис». Разведка: 13 агентов ECC (`security-reviewer` ×8,
> `django-reviewer`, `silent-failure-hunter` ×2, `planner`), каждая находка перепроверена
> ведущим по коду; замки писались ДО фиксов (красные без правки). Миграций нет.

## 1. Сводка по блокам

| Блок | Проверено | Найдено (C/H/M/L) | Исправлено в этом батче | Отложено / владельцу |
|---|---|---|---|---|
| A. Telegram (Mini App, боты, вход клиента) | все 12 измерений | 0 / 3 / 9 / 12 | A1 A2 A3 A5 A6 A7 A8 A9 A10 | A4 (header-секрет = путь, нужен ресинк вебхуков), A11 lite-business в TG (политика), PortalBot.token (миграция) |
| B. Аутентификация и сессии | B1–B8 | 0 / 1 / 5 / 8 | B1 B2 B5 B6 | B-H1 quick-start Domain до почты (архитектурно), B-M2 подтверждение регистрации на GET, B-M4 письма от неподтверждённых |
| C. Изоляция тенантов, админка | C1–C6 | 0 / 1 / 5 / 5 | C-H1 (= D1) | C-M1 OAuth state, C-M2 CSRF_TRUSTED_ORIGINS wildcard, C-M3 kill-switch, C-M4 admin 2FA/лимит |
| D. Деньги | D1–D7 | 0 / 2 / 5 / 4 | D1 D2 D7 | D3 SEPA payment_status, D4 FSM без блокировки у stays self-cancel, D5 нумерация счетов под гонкой, D6 hold reset |
| E. Витрина и формы | E1–E10 | 0 / 1 / 5 / 8 | E1 (лимиты) E4 E5 | E-M2 iCal коды, E-M3 CSP, E-M5 отзывы по e-mail, E-L1 unsubscribe на GET |
| F. Портал, API, MCP, ИИ | F1–F6 | 0 / 0 / 4 / 9 | F1 (city «/») F-L1 F-L7 | F-M2 MCP-письмо (выкл.), F-M3 Melden 3 IP, F-M4 неверифицированные отзывы |
| G. Данные, DSGVO, инфра | G1–G7 | 1 / 3 / 11 / 9 | G1 (= D2) G2-частично G4 G15 G8 | G2 Django 5.1 EOL + Pillow 13 (`uv lock`), G3 health-данные, G7 Notification payload, G11 compose, G12 бэкапы |

Severity: CRITICAL — чужая сессия/деньги/кросс-тенант; HIGH — утечка секрета или ПДн, обход
гейта; MEDIUM — двойное действие, оракул, перебор, 500 на вводе; LOW — гигиена.

## 2. Исправлено (замок красный до фикса)

| ID | Sev | Сценарий (актор → что получал) | Фикс | Замок |
|---|---|---|---|---|
| SEC-D1 | HIGH | Владелец с подключённым Stripe создаёт Checkout у СЕБЯ с чужой metadata → активирует себе подписку без оплаты, featured на 10 лет, выпускает Pass в чужой схеме, помечает чужой заказ оплаченным, `mark_past_due` жертве | `webhooks.handle_event`: connect-виды только при `event.account == tenant.stripe_connect_id`; платформенные (подписка, featured) — только без `account`; `account.updated` — о себе; `days` featured — только из таблицы планов | `billing/tests/test_sec_d_webhook_account.py` |
| SEC-D2 | CRIT* | Пустой `STRIPE_WEBHOOK_SECRET` → `construct_event` принимает HMAC с пустым ключом (PoC) → любой подделывает оплаты | 503 без секрета; deploy-check `billing.E001` (live-режим требует `whsec_…`); переменная в `.env.prod.example` | там же |
| SEC-A1 | HIGH | Текст `HTTPError` несёт `https://api.telegram.org/bot<TOKEN>/…` → `logger.exception` вебхука бизнеса и моста группы, `Notification.last_error`, Sentry | `services._call` → `TelegramAPIError` без URL и без `__context__`; `logger.warning(type)`; `scrub()` в last_error; Sentry `before_send` вырезает `bot\d+:…`, `sk_live_…`, `whsec_…` из исключений/логов/breadcrumbs, дропает args/kwargs Celery, `max_request_body_size="never"` | `telegram/tests/test_sec_a_token_leak.py` (скан-замок на `logger.exception`) |
| SEC-A2 | HIGH | Атакующий оформляет заказ на e-mail жертвы → на СВОЁМ подтверждении видит Telegram-токен карточки жертвы → его чат получает все уведомления жертвы | `deep_link_for_page`: ссылка на страницах подтверждения только вошедшему в ЛК владельцу карточки (ЛК — верифицированный e-mail) | `core/tests/test_sec_audit_fixes.py` |
| SEC-A3 | MED | Сотрудник с `einstellungen.view` видит owner-ссылку своего бота → становится чатом владельца (уведомления, публикация акций); бывший владелец сохранял права | ссылка только с `kanaele.edit`, TTL 15 мин, constant-time, помнит выпустившего → `owner_user_pk`; `owner_ok`/`is_owner_private`/`handle_callback`/`owner_route` проверяют `still_owner`; revoke/понижение → `links.release_user` | там же |
| SEC-A5 | MED | Перехваченная initData → `app_signup` с любого IP → чат жертвы владельцем бизнеса атакующего | повтор только с IP первого входа + лимит на uid; ticket выбора несёт `grace` | `platform_bot/tests/test_sec_a_miniapp.py` |
| SEC-A6 | MED | `still_owner` → True без `user_pk` (fail-open); DSGVO-удаление сжигало nonce до успеха, частичное удаление | связь кабинета без пользователя — не владелец; erase атомарно, nonce возвращается при сбое (оба бота) | `test_sec_audit_fixes` |
| SEC-A7 | MED | Вебхук бизнеса: не-ASCII заголовок → 500; повтор `update_id` задваивал действие; без лимита | bytes-сравнение, дедуп по `update_id`, 600/мин на IP | `test_sec_a_token_leak` |
| SEC-A8 | MED | Письмо «Telegram verbunden» (страховка от утёкшей ссылки) `fail_silently` + ключ дедупа на сутки; упавшая задача «съедала» апдейт | `fail_silently=False`, `autoretry`, `idempotent_task` освобождает ключ при исключении (класс) | `test_sec_audit_fixes` |
| SEC-B1 | LOW | `consume_token`/`consume_invite`/`consume_magic_link` ×2 — `get` затем `delete` без проверки → параллельный POST входит дважды | забирает только тот, кто удалил ключ | `test_sec_audit_fixes` |
| SEC-B5/B6 | MED/LOW | Инвайт без политики паролей; magic-link ЛК/портала без `cycle_key` | `validate_password` в `team_join`; `cycle_key()` в обоих входах | ревью |
| SEC-E5 | MED | `/lang/?next=https://evil` — открытый редирект с HSTS-домена; `/\host` в demo_switch, reviews, wishlist, shortlist | все через `owner_login.safe_next(request, value, default)` | `test_sec_audit_fixes` |
| SEC-E1/D7 | MED | Перебор 6-символьных кодов: `*_pay` ×4 (404↔302 + Stripe-сессия на GET), страница/memo билета, `cart_apply_code` (сертификаты до 2000 €), `/angebot/` ваучер, `voucher-redeem` | `ratelimit.hit` на каждом | ревью |
| SEC-SM4/6/7 | HIGH/MED | Widerruf: `sent=True` при провале всех каналов; Stripe-сбой молча переводил заказ в «на месте»; счёт юрлицу глотался | честный отказ + лог; метод остаётся онлайн + сообщение; лог | ревью |
| SEC-G4 | HIGH | Паспортные сканы из ЛК без поездки: `expires_at` NULL → хранились вечно | retention от загрузки + бэкфилл NULL в `purge_expired` | `test_sec_audit_fixes` |
| SEC-G15 | MED | `catalog.ProductReview`/`ProductWaitlist` не экспортировались и не удалялись по DSGVO | добавлены в `_email_linked` | coverage-замок dsgvo |
| SEC-G2 | HIGH | Pillow 12.3 (39 CVE в декодерах) парсит любой формат до проверки | `Image.open(formats=JPEG/PNG/WEBP)` | — |
| SEC-F1 | MED | `Tenant.city` с «/» → `NoReverseMatch` 500 на `/entdecken/` и sitemap | `{% url … as %}` guard + фильтр в sitemap | — |

\* CRIT условно — при пустом секрете в проде. Владельцу: `grep STRIPE_WEBHOOK_SECRET .env.prod`.

### 2a. Ревью диффа (фаза E, `security-reviewer`) — 3 HIGH + 6 MEDIUM, все закрыты вторым коммитом

- **H1** ретеншн документов (SEC-G4) накрыл бы `KIND_RECEIPT` — входящие счета GoBD стирались бы
  через 90 дней → квитанции без срока, бэкфилл их исключает (замок).
- **H2** `_send_platform` ловил `requests.HTTPError`, а сервис теперь бросает `TelegramAPIError`
  → 403 больше не метил чат заблокированным → ловим оба, `.status` (замок).
- **H3** токен уходил в Sentry через `breadcrumbs[].data.url` и spans → рекурсивный скраббер +
  `before_breadcrumb` (замок).
- **M2** лимит вебхука бизнеса был на IP (все боты шлют с нескольких IP Telegram — один счётчик
  накрыл бы всех) → на бота и после дедупа. **M3** autoretry у обработчика апдейтов (публикация
  не claim-идемпотентна) снят. **M5** `TelegramAPIError.response` держал живой Response с URL →
  стаб со `status_code`. **M6** два владельца с разными ботами: `still_owner` предпочитает зеркало
  своего бота, `release_user` не трогает чужой свой бот. **L1–L5** честные тексты лимитов,
  лимит прилавка 120, свой scope у `app_signup`, ошибки политики паролей в шаблоне, savepoint
  вокруг `release_user`.
- **M4 (продуктовое, владельцу):** кнопка «Updates per Telegram» на подтверждении заказа теперь
  видна только вошедшим в ЛК — для гостей её нет. Безопасный возврат кнопки гостям — ссылка в
  письме подтверждения (верифицированный канал); решение за владельцем.

### 2b. Ревью диффа (фаза E, `django-reviewer`) — 1 HIGH + 3 MEDIUM, закрыты третьим коммитом

- **H** тестовые настройки без `STRIPE_WEBHOOK_SECRET` → вьюха вебхука в тестах отвечала бы 503
  → `config/settings/test.py` задаёт `whsec_test` (замок на 503 ставит пустой секрет сам).
- **M** `owner_deep_link` писал весь `site_config` с объекта запроса без блокировки (класс W6) →
  запись через `links._lock` + `_write_mirror`.
- **M** `still_owner` при двух владельцах с разными ботами судил не того → параметр `via`
  (общий бот — владелец связи, свой бот — владелец зеркала); все 8 вызовов называют путь.
- **M** `test_receipts_are_exempt_from_retention` — NOT NULL `uploaded_by` → исправлен тест.
- **L** `logger.error` → `warning` для connect-событий без `kind`; импорт `featured` поднят; приватный
  `_notify_node` не импортируется между приложениями; `_release_telegram` логирует сбой.
- Три старых теста `test_h3_connect` привязывали чат кабинета без пользователя и ждали прав
  владельца — переписаны под реальный путь (SEC-A6 закрывает именно этот случай).

## 3. Отклонено ведущим (ложные тревоги)

- «Платформенный owner_chat_id принимается через бот бизнеса без проверки» — это тот же
  пользователь Telegram (uid одинаков у всех ботов); теперь дополнительно требуется живая
  связь в таблице (`is_owner`).
- «initData логируется» — не подтвердилось: везде только код ошибки.
- «Redis недоступен → вход fail-open» — не подтвердилось: `RedisCache` бросает, вход даёт 500;
  fail-open только у `ratelimit` (задокументировано).
- «`/tg/<secret>/` 405 на GET — оракул» — `require_POST` отвечает 405 при любом секрете.

## 4. Отложено — решения владельца

| ID | Sev | Суть | Почему не в батче |
|---|---|---|---|
| SEC-G2a | HIGH | Django 5.1.15 EOL (9 CVE, в т.ч. `get_signed_cookie`, `has_vary_header`), Pillow 12.3 → 13, pyjwt/sqlparse/urllib3/oauthlib/certifi | `uv lock` + прогон всего CI — отдельный инкремент с проверкой на стенде |
| SEC-D3 | MED | Connect-оплаты не читают `payment_status` (SEPA = «paid» до поступления денег); `async_payment_*` не обрабатываются | меняет семантику 8 обработчиков оплат; нужен план и Stripe-тест |
| SEC-D4 | MED | `StateMachine.apply` без блокировки; `unterkunft_cancel` без `atomic` → двойной возврат лимита/сертификата | трогает ядро FSM всех видов |
| SEC-D5 | MED | `issue_invoice` без `select_for_update` → дыра в нумерации GoBD при двойном клике | финансы, нужен database-reviewer |
| SEC-D6 | MED | `start_online_hold` сбрасывает срок +24 ч при каждом GET → бесконечное удержание места | решение по политике удержания |
| SEC-B-H1 | HIGH | Quick-start создаёт Domain+схему ДО подтверждения почты → спам сертификатов LE (класс T-5), 5/ч на IP, IPv6 /64 | архитектура регистрации (Domain после почты) — решение владельца |
| SEC-B-M2 | MED | Подтверждение регистрации на GET + пароль атакующего (pre-hijack) | интерстициал с POST — UX-решение |
| SEC-B-M4 | MED | Неподтверждённый владелец шлёт инвайты с платформенного отправителя | гейт `email_pending` на исходящую почту — решение |
| SEC-C-M1 | MED | OAuth `state` каналов публикации не привязан к браузеру → токен чужой страницы в канал атакующего | нужен nonce в cookie + правка callback (publishing) |
| SEC-C-M2 | MED | `CSRF_TRUSTED_ORIGINS=*.siteadaptor.de` → cookie-tossing при любом XSS на соседнем поддомене | смена политики CSRF, `__Host-` cookie — ops+код |
| SEC-C-M3 | MED | `Tenant.is_active=False` не выключает витрину | kill-switch middleware — решение о поведении (410/503) |
| SEC-C-M4 | MED | `/admin/` без лимита попыток и 2FA | Caddy IP-allowlist или django-otp — ops |
| SEC-A4 | LOW | Заголовочный секрет вебхука = путь (бизнес, портал) → лог 404 раскрывает секрет | смена требует «Webhook setzen»/`telegram_resync_webhooks` у всех ботов — ops-окно |
| SEC-A11 | MED | Mini App (12-часовая cookie) правит налоговый режим/контакты (`lite-business`, `betriebsferien`) | политика лёгкого кабинета (владелец разрешил Geschäft в T-8.31) |
| SEC-G3 | HIGH | Данные здоровья (аллергии/medical) в `Ticket.answers` открытым JSON, без ретеншна | шифрование поля = миграция + beat |
| SEC-G7 | MED | `Notification.payload` (тела писем, PDF) хранится вечно | beat очистки payload — решение о сроке |
| SEC-G10 | MED | `PortalBot.token`, `OutgoingWebhook.secret` открытым текстом | миграция на `EncryptedTextField` |
| SEC-G11 | MED | compose: `.env.prod` всем сервисам (вкл. Caddy/Postgres), Redis без пароля, root, плавающие теги, нет лимита тела у Caddy | ops/инфра |
| SEC-G12 | MED | Бэкапов в деплое нет | ops (Stage 0) |
| SEC-E-M2 | MED | iCal номера отдаёт `reference_code` броней; токен фида вечный | формат фида для OTA — согласовать |
| SEC-E-M3 | MED | Нет CSP на витрине | Report-Only сначала |
| SEC-E-M5/F-M4 | MED | Отзывы «проверенного покупателя» по одному e-mail; портальные отзывы без проверки | продуктовое решение (ссылка из письма) |
| SEC-F-M3 | MED | Melden: 3 разных IP скрывают листинг конкурента | порог/модерация |
| SEC-E-L1/G6 | LOW | Отписка и DOI рассылки на GET (сканеры почты) | интерстициал POST |

## 5. Ops владельцу

1. `grep STRIPE_WEBHOOK_SECRET .env.prod` — задать `whsec_…` (деплой упадёт на `check --deploy`
   без него, вебхук отвечает 503).
2. Поиск по логам/Sentry: `api.telegram.org/bot`, `sk_live`, `whsec_` — при находке ротация
   токенов ботов (@BotFather) + «Webhook setzen»/`telegram_resync_webhooks`.
3. `check --deploy` на сервере; `ss -tlnp` (Postgres/Redis не наружу).
4. Решения по §4 — приоритет: G2a (зависимости) → D3/D4/D5 (деньги) → B-H1 (регистрация) →
   C-M1/C-M2 → G3/G7/G10 (миграции).

## 6. Исполнение решений владельца (2026-11-02, «делай по рекомендации»)

Четыре волны, каждая — план-док → замки до кода → фиксы → ревью ECC (django-reviewer,
security-reviewer, database-reviewer) → правки по ревью → CI.

| Волна | План | Что закрыто |
|---|---|---|
| 1 деньги | `sec-wave1-money-plan-2026-11-02.md` | D4 (FSM под блокировкой строки, статус из БД), D4b (задачи после коммита), D5 (номер счёта без пропусков, сделка → счёт в одном порядке замков), D6 (удержание ставится один раз), D3 (SEPA: оплата только после зачисления, удержание 14 дней один раз и не дальше начала услуги, повторная оплата закрыта, сбой — час на оплату картой; подписка — после зачисления); по ревью: рассрочка на отменённый билет возвращается, самоотмена номера под блокировкой |
| 2 доступы | `sec-wave2-signup-access-plan-2026-11-02.md` | B-H1 (лимиты по сети /64, на ящик, общий потолок 10/ч; сертификат без подтверждённой почты — 31 день), B-M2+G16 (подтверждение регистрации паролем по POST, хэш стирается), B-M4, A11, C-M4 (лимит входа в /admin/ + `ADMIN_ALLOWED_NETWORKS`), A4 (производный секрет заголовка вебхука), SM8 (повтор уведомлений), SM13 (`billing.E002`) |
| 3 данные | `sec-wave3-data-plan-2026-11-02.md` | G3 (ответы анкеты зашифрованы, 30 дней после события), G10, G7 (30 дней), G14, G15, E-M2, E-M5 (проверенный отзыв — ссылка из письма или ЛК), F-M3 (5 сетей) |
| 4 инфраструктура | `sec-wave4-infra-plan-2026-11-02.md` | C-M2 (`__Host-csrftoken`, без wildcard), C-M3 (витрина приостановленного — 410), E-M3 (CSP report-only), E-L1/G6 (отписка/DOI кнопкой; one-click отписка заработала), G11 (env только своим сервисам, опц. пароль Redis, лимит тела), G12 (`scripts/backup.sh`) |

**Отступление от рекомендации (B-H1):** поддомен быстрой регистрации создаётся сразу —
экран «Fertig» и вход владельца живут на нём, и «домен после письма» ломал бы «Aktion in
3 Klicks». Атаку закрывают лимиты (сеть /64, ящик, общий потолок) и отказ в сертификате
неподтверждённому бизнесу. Настоящее решение квоты Let's Encrypt (~50/неделю на домен) —
wildcard через DNS-01 (Cloudflare DNS + `caddy-dns/cloudflare`): ops-решение владельца.

**Осталось за рамками волн:** ~~G2a~~ — сделано 2026-11-02 (`95ebeca`: Django 5.2.18 LTS,
Pillow 13, DRF 3.18, патч-версии); G2b 2026-11-03 — allauth 65.21.1 + oauthlib 4.0.1 (последняя
находка pip-audit, план `sec-g2b-allauth-oauthlib-plan-2026-11-03.md`); non-root в образе и фиксированные теги образов (нужен
`chown` тома `media` на сервере), портальные отзывы о бизнесе (F-M4) — без изменений,
SM11/SM15 (beat-циклы без изоляции схем в части задач, дедуп публикаций) — по спросу.

### Ops после деплоя волн 1–4
1. Деплой: `./scripts/deploy.sh single` (миграции `events/0036`, `aggregator/0037`, `webhooks/0002`).
2. Stripe Dashboard → Webhooks: добавить `checkout.session.async_payment_succeeded` и `…_failed`.
3. `python manage.py telegram_resync_webhooks --apply`, затем `TELEGRAM_WEBHOOK_LEGACY_HEADER=False`.
4. Бэкапы: cron из шапки `scripts/backup.sh`; один раз проверить восстановление.
5. По желанию: `ADMIN_ALLOWED_NETWORKS=<ваш IP>/32`, `REDIS_PASSWORD` (+ `REDIS_URL`),
   `CSP_REPORT_URI` (security-endpoint Sentry), `QUICK_START_HOURLY_CAP`.

## 7. Дозакрытие (2026-11-04)

- **SEC-C-M1 закрыт.** Подключение канала (GBP/Pinterest/Meta) привязано к браузеру:
  `oauth_start` кладёт одноразовый код в сессию кабинета и в подписанный `state`;
  callback на основном домене токен больше не сохраняет, а передаёт код в кабинет бизнеса
  (`channel-oauth-finish`, под входом и правом `kanaele.edit`), где сверяются код сессии
  (`compare_digest`, одноразово) и схема. Хост возврата — только домен этого бизнеса.
  Замки `apps/publishing/tests/test_oauth.py` (вкл. сценарий атаки «ссылка, начатая
  атакующим, открыта жертвой»). Ревью security-reviewer нашло обход через СОБСТВЕННЫЙ
  домен бизнеса (DNS проверяется один раз — потом его можно увести на свой сервер и
  перехватить код): код согласия теперь уходит ТОЛЬКО на поддомен платформы, старт с
  собственного домена переводится туда же.
- **SEC-D7 (новое, найдено при настройке Stripe).** Оплаты клиентов идут на
  подключённых аккаунтах; их события Stripe подписывает секретом ОТДЕЛЬНОГО эндпоинта
  «Connected accounts», а вебхук знал один секрет → оплаты отбрасывались как
  неподписанные. `STRIPE_CONNECT_WEBHOOK_SECRET` + проба обоих секретов, `billing.W002`.
  По ревью: событие, подписанное Connect-секретом, без `account` — 400 (утёкший секрет
  не подделает подписку/featured).
  Замки `apps/billing/tests/test_sec_stripe_connect_secret.py` (настоящая подпись).
- **SEC-G12b (новое, найдено на сервере).** `scripts/backup.sh` молча обрывался на
  отсутствующих ключах `.env.prod`, а `pg_dump` падал «out of shared memory» (~28 000
  таблиц) → бэкап не делался вовсе. Исправлено, восстановление проверено владельцем
  (134 схемы / 130 бизнесов совпали).
- **Остаётся:** SEC-F-M4 (портальные отзывы о бизнесе) — продуктовое решение; копия
  бэкапа вне сервера — отложено (roadmap §Отложено).

