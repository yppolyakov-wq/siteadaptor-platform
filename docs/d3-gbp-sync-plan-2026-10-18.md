# Д3 «GBP-Sync» — часы работы и Offer-посты Google → черновики акций

**Дата:** 2026-10-18 · **ID:** Д3 (семейство T-8, `backlog-portal-direction-2026-10-16.md`) ·
**Статус:** черновик плана (агент planner), ждёт решений владельца В-1…В-10 (§12). Миграций нет.

## 0. Коротко

Что уже есть: подключение Google Business Profile (GBP) из кабинета (OAuth, scope
`business.manage`) и автопостинг акций — пост создаётся при активации акции и удаляется при её
окончании (`apps/publishing/adapters.py`, коммиты `3030af0d`, `02143463`).

Чего нет — это и есть Д3:
1. **Часы работы.** Источник истины — наш кабинет. Две явные кнопки с предпросмотром различий:
   «An Google senden» и «Von Google übernehmen». Автосинхронизации в v1 нет.
2. **Offer-посты.** Посты Google с типом OFFER становятся **черновиками акций**; сами никогда
   не активируются. Импорт идемпотентный, безопасный для фото и внешнего текста. Активация такого
   черновика **не** создаёт второй пост в Google.
3. **Без доступа к API.** Пока Google не одобрил доступ (квота 0), экран честно пишет
   «Google-API noch nicht freigeschaltet» и ничего не меняет.

## 1. Разведка (что есть сейчас)

- **Адаптер публикации** `apps/publishing/adapters.py`: `_GBP_API = "https://mybusiness.googleapis.com/v4"`;
  `_gbp_access_token(config)` — refresh_token-грант в `oauth2.googleapis.com/token`; client_id/secret
  платформы — `apps.secrets.store.get_or_setting("google_oauth_client_id", "GOOGLE_OAUTH_CLIENT_ID")`;
  `_gbp_publish` — POST `{_GBP_API}/{config['location']}/localPosts` (`topicType: STANDARD`,
  `callToAction LEARN_MORE`); `_gbp_remove` — DELETE по `external_ref`, 404 = успех.
- **OAuth** `apps/publishing/oauth.py`: провайдер `google_business`, scope `business.manage`;
  `store_token` кладёт refresh token в `Channel.config`, зашифрованным `apps.secrets.crypto`;
  callback на public (`/oauth/<provider>/callback/`) с подписанным `state`.
- **Модель Channel** `apps/publishing/models.py`: `Channel(type="google_business", config JSON,
  is_enabled)`, по строке на тип. **Локация вводится руками** в `config["location"]` как
  `accounts/{a}/locations/{l}` (`views._CONFIG_FIELDS`, `docs/gbp-setup.md §3`); выбора локации
  после OAuth нет.
- **Модель Publication**: уникальные `dedupe_key` и `(promotion, channel)`, `external_ref` = имя
  поста Google. `tasks._do_publish` публикует **только из QUEUED** — заранее созданная Publication
  со статусом PUBLISHED и `external_ref` не даёт повторно запостить акцию при её активации (ключ к §4).
- **Часы работы**: `Tenant.opening_hours_structured` = `{"0":["09:00","18:00"],…}`, один интервал
  на день, без ночных часов (`apps/tenants/openinghours.normalize`); `Tenant.opening_hours` —
  свободный текст, не трогаем. Особых часов и праздников **модели нет**. Правятся в
  `apps/core/views.settings_view` (`_parse_opening_hours`, `_opening_hours_rows`) с `update_fields`
  (W7a) и вызовом `aggregator.tasks.refresh_tenant_fields(tenant)`; у лёгкого кабинета свой путь
  `core/lite_cabinet.py:98`. Читают: «открыто сейчас» агрегатора (`aggregator/views.py:247`),
  JSON-LD (`core/seo.py`), ассистент акции (`promotions/quick.py:68`), presence. Разбор
  schema.org `openingHoursSpecification` уже есть в `imports/site/structured.py::_hours`.
- **Акции**: `Promotion.status` по умолчанию `"draft"`; `title`/`description` — JSON
  `{locale: text}`, `images` (список), `metadata` (JSON), `starts_at`/`ends_at`, `city_category`.
  Конструктор черновика — `QuickPromotionForm.build()` (`promotions/quick.py`); подсказки к тексту —
  `apps/core/text_check.py` (Д2).
- **Импорт фото** (Г1) `imports/site/apply.fetch_images`: `core.ssrf.safe_fetch(url,
  accept=IMAGE_TYPES, max_bytes=settings.SITE_IMPORT_MAX_IMAGE_BYTES)` → Pillow `verify` с лимитом
  пикселей и кадров → перекодирование в WEBP (без EXIF) → `save_product_image`; Celery после `on_commit`.
- **Доступ**: `/dashboard/channels/*` (config, toggle, oauth start) открыт **сотрудникам** — нет в
  `CabinetOwnerAccessMiddleware._OWNER_ONLY` (`core/middleware.py:165`). Отдельная находка, см. В-7.
- **Навигация**: «Kanäle» — в кластере Marketing (`nav_registry.py:557`); карточка Integrationen
  «Publishing (Google/Facebook/Instagram)» (`core/views.py:5832`); прецедент Google-экрана в
  настройках — GK-11 «Google Bewertungen» (`google-reviews-settings`).

## 2. API Google — проверка реальности (⚠️ — неточно, сверить перед кодом)

- **Scope** `business.manage` уже запрашиваем — переподключать не нужно.
- **Доступ**: API Business Profile требует заявки в Google; до одобрения запросы дают 403/квоту 0.
  **Внешний блокер** — заявку подаёт владелец (`docs/gbp-setup.md §1.2`).
- **Аккаунты и локации**: `GET https://mybusinessaccountmanagement.googleapis.com/v1/accounts`;
  `GET https://mybusinessbusinessinformation.googleapis.com/v1/{account}/locations?readMask=name,title,storefrontAddress&pageSize=100`.
- **Чтение часов**: `GET https://mybusinessbusinessinformation.googleapis.com/v1/locations/{L}?readMask=regularHours,specialHours`;
  `regularHours.periods[] = {openDay:"MONDAY", openTime:{hours,minutes}, closeDay, closeTime}`;
  нулевые поля TimeOfDay могут отсутствовать; круглосуточно — `closeTime.hours=24` ⚠️.
- **Запись часов**: `PATCH …/v1/locations/{L}?updateMask=regularHours`, тело
  `{"regularHours":{"periods":[…]}}`. Google может применить правку с задержкой или после
  модерации ⚠️ — это не ошибка, следующее чтение покажет фактическое состояние.
- **Чтение постов**: localPosts по-прежнему на легаси v4 ⚠️ (Google снимает части v4 по
  кусочкам — сверить статус перед D3-3):
  `GET https://mybusiness.googleapis.com/v4/accounts/{a}/locations/{l}/localPosts?pageSize=100&pageToken=…`.
  Поля: `name`, `languageCode`, `summary`, `topicType` (STANDARD/EVENT/OFFER/ALERT), `state`
  (LIVE/PROCESSING/REJECTED), `event{title, schedule{startDate{year,month,day}, startTime, endDate,
  endTime}}`, `offer{couponCode, redeemOnlineUrl, termsConditions}`, `media[]{mediaFormat, googleUrl}`,
  `createTime`, `updateTime`.
- **Форматы id локации**: v1 — `locations/{L}`, v4 — `accounts/{a}/locations/{l}`; храним v4,
  v1 выводим из него.
- **Квоты**: после одобрения — порядка сотен запросов в минуту на проект ⚠️; наш объём — несколько
  запросов в день на бизнес, риск близок к нулю. 429 всё равно обрабатывается.

## 3. Направление синхронизации часов — варианты для владельца

| | Вариант | Плюсы | Минусы |
|---|---|---|---|
| В-1 | Только отправка (наши → GBP) | один источник истины, у нас часы уже везде | кто ведёт часы в Google, вводит их заново |
| В-2 | Только забор (GBP → наши) | быстрый старт тем, кто ведёт GBP | **с потерями**: у Google несколько интервалов в день и ночные часы, у нас один интервал |
| **В-3 ✅ рекомендую** | **Обе стороны ручными кнопками с предпросмотром, без автосинхронизации** | конфликтов нет по построению; владелец видит, что изменится; онбординг через «Von Google übernehmen» | нужен клик (автоотправку можно добавить переключателем в v2) |
| В-4 | Автоматически в обе стороны, побеждает последний | «магия» | тихая потеря разрывов в смене, петли правок, задержка модерации Google ⇒ «мигание»; не рекомендую |

**Политика конфликтов и потерь для В-3:**
- День, который наша модель не выражает (2+ интервала, `closeDay≠openDay`, 24 ч), — **с потерями**.
- **Забор**: такие дни не применяются (остаётся наше значение) и показываются в диффе как
  «bei Google: 08–12, 14–18 — nicht übernommen».
- **Отправка**: если у Google есть такие дни, отправка **заблокирована**, пока владелец явно не
  подтвердит `confirm=overwrite` — иначе один клик сотрёт разрывы в смене у Google.
- **Отправка при пустых наших часах запрещена** — клик не может стереть часы в Google.
- `updateMask` — **только** `regularHours`; особые часы и праздники не трогаются никогда. В v1 они
  показываются на экране только для чтения («Sonderöffnungszeiten bei Google: N»).

## 4. Offer-посты → черновик акции

### Отбор
`topicType == "OFFER"`, `state == "LIVE"`, конец расписания в будущем (или конца нет). Исключаются
наши собственные посты: `external_ref` принадлежит Publication неимпортированной акции.

### Соответствие полей
| Поле акции | Источник |
|---|---|
| `title` | `{lang: event.title}`; запасной — первая строка `summary`, обрезка до 80 символов |
| `description` | `{lang: summary + "\n\nBedingungen: " + termsConditions + "\nCode: " + couponCode}`, обычным текстом |
| `starts_at` / `ends_at` | `event.schedule` в `Europe/Berlin` (дата + время; без времени → 00:00 / 23:59:59) |
| `promo_type` | `DISCOUNT` |
| цены / `discount_percent` | **пусто**: у GBP нет структурированной цены, выдумывать не будем (PAngV, как в Г1: никакого «statt» и процента на импортированных данных) |
| `status` | всегда `"draft"` |
| `metadata` | `{"source":"gbp", "gbp_post": name, "gbp_update_time": updateTime, "gbp_hash": sha256(нормализованных полей), "gbp_coupon_code": …, "gbp_redeem_url": … (только https, после `validate_public_url`)}` |
| `city_category` | пусто (владелец выбирает до активации) |

`lang` = `languageCode`, если он среди локалей бизнеса, иначе `settings.LANGUAGE_CODE`.

### Идемпотентность (без миграции)
- В одной `transaction.atomic()`: создать черновик **и** `Publication(promotion=draft,
  channel=<gbp>, status=PUBLISHED, external_ref=name, dedupe_key=f"gbp-import:{name}")`.
- Уникальный `dedupe_key` — журнал импорта; при гонке IntegrityError откатывает, пост пропускается.
- Нужный побочный эффект: активация черновика **не** постит повторно (`_do_publish` пропускает всё,
  что не QUEUED).

### Окончание акции (В-6)
Для импортированного поста `_gbp_remove` **не удаляет пост владельца**: если
`publication.promotion.metadata.get("gbp_post") == publication.external_ref` — выход. Google сам
снимает оффер по своей дате окончания.

### Владелец удалил или отклонил черновик
«✕ Nicht übernehmen» (или удаление черновика) кладёт `name` в `Channel.config["gbp_dismissed"]`
(ограниченный список — последние 300 имён). Такие посты повторно не импортируются.

### Пост изменён в Google (`updateTime` новее)
- Черновик, поля которого совпадают с `gbp_hash` (владелец не трогал), — поля обновляются.
- Черновик, который владелец правил, — только `metadata["gbp_changed"]=True`, бейдж «Bei Google geändert».
- Не-черновик **не меняется никогда**, только бейдж.

### Пост удалён в Google
Только после **полного** прохода по всем страницам — `metadata["gbp_gone"]=True`. Черновик не
удаляется, получает бейдж «Bei Google entfernt». Если упала хоть одна страница — ничего не помечаем.

### Фото
- Не больше `GBP_IMPORT_MAX_PHOTOS=6` на пост, только `mediaFormat == "PHOTO"`.
- Celery-задача после `on_commit`.
- `safe_fetch(url, accept=IMAGE_TYPES, max_bytes=SITE_IMPORT_MAX_IMAGE_BYTES)` + **список
  разрешённых суффиксов хоста** `GBP_MEDIA_HOST_SUFFIXES = (".googleusercontent.com",)`;
  остальное отбивается до запроса.
- Дальше тот же конвейер Pillow/WEBP, что в Г1. Конвейер выносится в общий хелпер
  `apps/core/remote_images.py::ingest_image(url, *, fetch, folder, allowed_hosts=None) -> dict | None`;
  `imports/site/apply.fetch_images` переходит на него, существующие тесты — паритет-замок.

### Внешний текст = данные
- `strip_tags`, удаление управляющих и нулевой ширины символов (Unicode Cc/Cf, кроме `\n`), NFC,
  лимиты длины (заголовок 200, описание 4000). Без `mark_safe`.
- **В ИИ не передаётся** (prompt injection невозможен по построению).
- `redeemOnlineUrl` хранится только в `metadata` и показывается текстом в карточке черновика;
  владелец добавит его вручную, если захочет.
- `text_check` (Д2) прогоняется по черновику, подсказки — в существующем блоке
  «Vor dem Veröffentlichen prüfen».

### Как часто
- Кнопка «Jetzt von Google holen», лимит 1 раз в минуту на бизнес (`ratelimit.hit`, scope `gbp-sync`).
- Плюс по желанию ежедневный beat `apps.publishing.tasks.import_gbp_offers_all` при
  `Channel.config["gbp_auto_import"]` (по умолчанию выключен). Обходит схемы (`_iter_tenant_schemas`
  уже есть) с разбросом и try/except на бизнес; 429 на весь проект останавливает проход.

## 5. Где в кабинете (DoD `docs/cabinet-screen-dod.md`; новых якорей сайдбара нет)

- **Новый экран** `/dashboard/channels/google/` (url_name `gbp-sync`), заголовок «Google-Profil»:
  статус подключения и локация (+ выбор); блок «Öffnungszeiten» — дифф и две кнопки; блок
  «Angebote von Google» — список последнего импорта, «Jetzt holen», переключатель
  «Täglich automatisch», отклонённые посты. Запись nav_registry в кластере Marketing,
  `sidebar=False` (палитра и подсветка), поисковые слова «google profil öffnungszeiten angebote sync».
- **Входы**: карточка Google на «Kanäle» (`publishing/channels.html`) — «Google-Profil
  synchronisieren»; в настройках рядом с часами (`tenant/settings.html`) — «Mit Google abgleichen →»,
  только при подключённом GBP; статус на карточке Integrationen, например «Verbunden ·
  Öffnungszeiten abgeglichen 12.10.».
- **Список акций**: бейджи «Aus Google» / «Bei Google geändert» / «Bei Google entfernt» + фильтр `?quelle=gbp`.
- **Только владельцу**: префикс `"/dashboard/channels/google/"` в `_OWNER_ONLY` (отправка часов
  пишет во внешний профиль). Действия — только POST с CSRF.

## 6. Миграции — в v1 нет (почему)

- Локация: `Channel.config["location"]` уже есть.
- Состояние синхронизации: `Channel.config["gbp_sync"] = {hours_pushed_at, hours_pulled_at,
  posts_pulled_at, last_error_code}` — точечная запись с `select_for_update` строки Channel,
  сливаются только свои ключи.
- Журнал импорта — Publication (уникальный `dedupe_key`); происхождение черновика —
  `Promotion.metadata`; отклонённые посты — `Channel.config`.
- Альтернатива для владельца (В-8): `Promotion.source` / `external_ref` с UniqueConstraint —
  чище, но миграция и database-reviewer; для v1 не нужна.
- Поиск Publication по `external_ref` (исключение своих постов) без индекса — таблица маленькая
  (строка на акцию × канал), database-reviewer не требуется.

## 7. Модули и функции

- **`apps/publishing/gbp.py`** — клиент (фиксированные хосты Google, `requests` с
  `timeout=settings.GBP_API_TIMEOUT=20`):
  - `class GbpError(Exception)`, `code ∈ {"not_configured","not_approved","auth","quota","not_found","network","bad_response"}`;
    401 или `invalid_grant` → `auth`; 403 → `not_approved` (при PERMISSION_DENIED или SERVICE_DISABLED); 429 → `quota`.
  - `access_token(config)` — переезжает из адаптера; `adapters._gbp_access_token = gbp.access_token`
    остаётся псевдонимом, чтобы моки `test_gbp.py` работали.
  - `location_ids(config) -> (v4_name, v1_name)`, `list_accounts(token)`, `list_locations(token, account)`,
    `get_hours(token, v1_name) -> dict`, `patch_regular_hours(token, v1_name, periods)`,
    `iter_local_posts(token, v4_name, *, max_pages=5) -> (posts, complete: bool)`.
- **`apps/publishing/gbp_hours.py`** (чистая логика, без I/O): `DAYS = ("MONDAY",…,"SUNDAY")`,
  `to_periods(structured)`, `from_periods(periods) -> (structured, lossy_days)`,
  `diff(ours, periods) -> HoursDiff(rows, lossy_days, equal)`, `push(tenant, channel, *, confirm=False)`,
  `pull(tenant, channel) -> HoursDiff`; `apply_pull(tenant, diff)` сохраняет с
  `update_fields=["opening_hours_structured","updated_at"]` и зовёт `refresh_tenant_fields`.
- **`apps/publishing/gbp_import.py`**: `clean_text(s, limit)`, `post_to_draft_fields(post, tenant) -> dict | None`,
  `import_offers(channel, *, now) -> ImportResult(created, updated, flagged, skipped)`,
  `dismiss(channel, name)`, `fetch_post_photos(promotion_id)` — Celery `idempotent_task`.
- **`apps/publishing/views.py`**: `gbp_sync` (GET), `gbp_location` (POST), `gbp_hours`
  (POST action=preview|push|pull_apply), `gbp_import` (POST), `gbp_dismiss` (POST).
- **`apps/core/remote_images.py::ingest_image`** — вынос из Г1.
- **Настройки**: `GBP_API_TIMEOUT`, `GBP_IMPORT_MAX_PAGES=5`, `GBP_IMPORT_MAX_PHOTOS=6`,
  `GBP_MEDIA_HOST_SUFFIXES`, `GBP_SYNC_ENABLED` (рубильник env, по умолчанию True).
- **Beat**: `"import-gbp-offers": {"task": "apps.publishing.tasks.import_gbp_offers_all", "schedule": 86400.0}`.
- **Доки**: `docs/gbp-setup.md` += Business Information API, Account Management API, выбор
  локации, статус одобрения.

## 8. Безопасность

- **Токены**: refresh token — зашифрованным в `Channel.config`; access token живёт только в памяти
  на время одного прохода. Ни тот, ни другой не попадают в логи, `last_error`, сообщения и шаблон.
- **Ошибки**: в `last_error_code` — только код из §7 и HTTP-статус; тело ответа Google не храним
  (может эхом нести данные запроса).
- **Логи**: схема, хеш имени поста (sha256[:12]), счётчики, коды. Без текстов, ПД и URL с токенами.
- **SSRF**: API — на фиксированные хосты; медиа — `safe_fetch` + список хостов ДО запроса, лимиты
  размера и типа, Pillow `verify` + перекодирование.
- **Недоверенный текст** — см. §4: только автоэкранирование, в промпты ИИ не идёт.
- **Доступ**: префикс owner-only, `@login_required` (грабля «декоратор съеден вставленным хелпером»
  — ловит `test_orphan_decorators`), только POST + CSRF. Значение выбора локации — по регулярке
  `^accounts/\d+/locations/\d+$`.
- **Лимиты частоты**: кнопки 1 в минуту на бизнес; beat с остановкой по квоте.
- **Отдельная находка (В-7)**: `/dashboard/channels/config/` и `/connect/` открыты сотрудникам.
  Рекомендация — тоже owner-only, отдельным маленьким коммитом с замком.

## 9. Тесты (замки — ДО кода)

`apps/publishing/tests/test_gbp_hours.py`:
1. `to_periods`: точное соответствие с минутами; закрытые дни опускаются.
2. Туда-обратно `from_periods(to_periods(x)) == x` на часах всех демо-китов.
3. Разрыв в смене → с потерями; 4. ночные (`closeDay≠openDay`) → с потерями; 5. 24 ч → с потерями.
6. Отправка при пустых наших часах — отказ, **без HTTP**.
7. PATCH несёт `updateMask == "regularHours"` и никогда `specialHours`.
8. `apply_pull` пишет только `opening_hours_structured, updated_at` (параллельная запись
   `site_config` выживает — W7a), зовёт `refresh_tenant_fields`, дни с потерями не меняет.
9. Отправка заблокирована при потерях у Google; проходит с `confirm=True`.

`apps/publishing/tests/test_gbp_import.py`:

10. LIVE OFFER → ровно один черновик; статус `draft`; соответствие полей, вкл. `starts_at`/`ends_at`
    в Europe/Berlin; цены пустые.
11. Повторный прогон идемпотентен: черновиков столько же, одна Publication с
    `dedupe_key="gbp-import:<name>"`, `status=published`.
12. STANDARD/EVENT/ALERT и не-LIVE пропускаются.
13. Наши собственные посты (`external_ref` неимпортированной акции) пропускаются.
14. Закончившийся оффер пропускается.
15. Отклонённое имя повторно не импортируется.
16. Изменённый пост: нетронутый черновик обновляется; правленый владельцем — только `gbp_changed`;
    активная акция — без изменений.
17. Пост пропал при полном проходе → `gbp_gone`; сбой на 2-й странице → флагов `gone` нет.
18. Активация импортированного черновика → POST в localPosts **не** вызывается.
19. Окончание импортированной акции → DELETE поста Google **не** вызывается; обычная акция
    удаляется как раньше.
20. `<script>`, управляющие и нулевой ширины символы удалены; лимиты длины держатся; купон и
    условия оказываются в описании текстом.
21. `redeemOnlineUrl` по http / на приватный адрес → отброшен.
22. Фото: хост вне `.googleusercontent.com` → отказ **до** `safe_fetch`; `accept`/`max_bytes`
    передаются; не больше 6; результат — WEBP без EXIF.
23. Задача фото ставится через `on_commit`.

`apps/publishing/tests/test_gbp_sync_views.py`:

24. Сотрудник → 403 через middleware; аноним → логин; GET на эндпоинты действий → 405.
25. `caplog` / `last_error` / ответ не содержат refresh token и access token.
26. 403 not_approved → на экране подсказка; БД не меняется; не 500.
27. Beat: сбой одного бизнеса не останавливает остальных; 429 останавливает проход; только бизнесы
    с `gbp_auto_import`.
28. Лимит частоты кнопок (фикстура `isolated_ratelimit`).

Плюс: инвариант X7 (запись `nav_registry`, достижимость), паритет-тесты `apps/imports` после выноса
`ingest_image`, существующие `test_gbp.py`/`test_oauth.py` зелёные, `i18n_quickcheck` + `template_comments`.

## 10. Инкременты (по одному циклу CI, FF в main по зелёному)

- **D3-1 — клиент, локация, экран**: `gbp.py` (+ псевдоним в адаптере), выбор локации, экран
  `gbp-sync` со статусом, owner-only префикс, входы (Kanäle, Integrationen), nav_registry.
  Замки 24–26 + X7.
- **D3-2 — часы работы**: `gbp_hours.py` + блок часов на экране + строка «Mit Google abgleichen» в
  настройках. Замки 1–9.
- **D3-3 — импорт Offer → черновик**: `gbp_import.py` без фото, кнопка «Jetzt holen», журнал
  Publication, без повторного поста и без удаления импортированных, бейджи списка акций +
  `?quelle=gbp`, отклонение. Замки 10–21.
- **D3-4 — фото, изменения, beat**: вынос `remote_images.ingest_image` (паритет Г1), задача фото,
  `gbp_changed`/`gbp_gone`, ежедневный beat по желанию, подсказки `text_check` на черновике.
  Замки 16, 17, 22, 23, 27, 28.
- Ревью на каждом инкременте: django-reviewer + security-reviewer (security обязателен на
  D3-1/D3-3/D3-4: OAuth, внешние данные, SSRF). database-reviewer не нужен — миграций нет.
- Стенд: живого API до одобрения нет, поэтому Playwright на моках (подменённые `gbp.*`) — экран и
  настройки, десктоп и 390 px.

## 11. i18n (≈26 msgid × 5 каталогов: de/en/tr/ru/uk)

«Google-Profil», «Mit Google abgleichen», «An Google senden», «Von Google übernehmen», «Bei Google»,
«Bei uns», «Nicht darstellbar – bleibt unverändert», «Bei Google sind geteilte Öffnungszeiten
hinterlegt. Trotzdem überschreiben?», «Sonderöffnungszeiten bei Google: %(n)s», «Angebote von
Google», «Jetzt von Google holen», «Täglich automatisch holen», «Aus Google», «Bei Google geändert»,
«Bei Google entfernt», «Nicht übernehmen», «%(n)s neue Entwürfe aus Google», «Keine neuen Angebote
bei Google», «Google-API noch nicht freigeschaltet», «Google-Verbindung abgelaufen – bitte neu
verbinden», «Google-Kontingent erreicht – später erneut versuchen», «Standort wählen», «Bitte zuerst
einen Standort wählen», «Zuletzt abgeglichen: %(date)s», «Bedingungen», «Code».

msgid в коде — один раз, через `_("…")` (без псевдонимов и f-строк, урок I18N-13).

## 12. Вопросы владельцу (рекомендации)

- **В-1…В-4 Направление часов**: **В-3** — ручные кнопки в обе стороны с диффом; автоотправка после
  Save — переключателем в v2.
- **В-5 Ежедневный автоимпорт постов**: **переключатель, по умолчанию выключен**; в v1 — кнопка.
- **В-6 Удалять пост в Google, когда импортированная акция кончилась?** **Нет** — это пост
  владельца, Google снимает его по своей дате.
- **В-7 Сделать существующие `/dashboard/channels/config|connect/` только для владельца?** **Да**,
  отдельным маленьким коммитом внутри D3-1.
- **В-8 Миграция `Promotion.source/external_ref` вместо metadata + Publication?** **Нет в v1**;
  вернуться, когда появится второй источник импорта (Facebook/Instagram).
- **В-9 Код купона из GBP**: **текстом в описании + metadata**; уникальный купон T-8.3 не
  создаём — у GBP один статичный код на всех.
- **В-10 Особые часы / праздники**: **только чтение в v1**; своя модель для них — отдельная задача
  (миграция).
- **Внешний блокер**: заявку на доступ к API Google Business Profile подаёт владелец
  (`docs/gbp-setup.md §1.2`). До одобрения всё работает на моках, экран честно пишет
  «noch nicht freigeschaltet».
