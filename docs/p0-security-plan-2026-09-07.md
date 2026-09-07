# P0 безопасности — план (2026-09-07)

Источник: `docs/style-inheritance-audit-2026-09-03.md` §9.3/§11; каждый пункт
подтверждён адверсариальным скептиком (воркфлоу 40/40). Отмашка владельца:
«P0 безопасности делай». Правила: замки ДО правок · минимальный дифф ·
без миграций · ребейз на main перед пушем · ruff/format по всему дереву.

## P0-1. CSRF-токен утекает через кэш витрины
**Факт (воспроизведён пробником):** `cache_storefront_page`/`cache_public_page`
(`apps/core/pagecache.py`) кладут в кэш `(content, content_type)` и на хите
отдают голый `HttpResponse`. Тело закэшировано вместе с `{% csrf_token %}`;
`Set-Cookie`/`Vary` теряются. В течение TTL все анонимы получают токен ПЕРВОГО
посетителя без своей куки → POST даёт 403 (обе ветви: без куки / чужой токен).
**Фикс (вариант A — fail-safe):** не кэшировать ответ, если
`request.META.get("CSRF_COOKIE_NEEDS_UPDATE")` (Django 5.1: `get_token()` ставит
его всегда, `csrf.py:111`) ИЛИ `response.cookies` непуст. Кэш-хит ничего не
теряет, потому что такие ответы в кэш не попадают. Дополнительно хранить и
восстанавливать `Vary` (новый префикс ключа `sfpage2:`/`pubpage2:` — старые
кортежи осиротеют по TTL). Оба декоратора.
**Цена:** страницы с формами (главная, деталь, корзина — 30 шаблонов витрины
с `csrf_token`) перестают кэшироваться для анонимов = состояние до SE-5a.
**Follow-up P1 (не сейчас):** токен вне тела — JS читает куку `csrftoken`
(+ `ensure_csrf_cookie`-эндпоинт), формы без `{% csrf_token %}` → кэш вернётся.
**Замки (красные до правки):** страница с токеном не кэшируется; второй визит
получает СВОЙ токен и `Set-Cookie`; страница без токена по-прежнему кэшируется;
`Vary` переживает хит.

## P0-2. Медиа вне изоляции
**Факт:** один `MEDIA_ROOT` без префикса схемы; `django.views.static.serve` в
трёх urlconf (`urls_tenant.py:641`, `urls_public.py:116`, `urls_portal.py:58`)
без авторизации; в проде `SERVE_MEDIA=True` по умолчанию. Загрузки мастера
импорта — `imports/<ИСХОДНОЕ имя>` (`apps/imports/models.py:19`), не удаляются
(`run_import` читает `job.rows`, файл после превью не нужен). Фото заявок —
uuid (опровергнуто). `documents/*.enc` — шифротекст под `/media/`.
**Фикс (минимальный, без миграции хранилища):**
1. `ImportJob.source_file.upload_to` → callable `imports/<uuid4>.<ext>` (исходное
   имя — только в БД, если нужно показывать).
2. После `run_import` со статусом `completed` — удалить `source_file` (storage
   + поле). При `failed` — оставить (повтор), но путь уже не угадываем.
3. Единая обёртка `apps/core/media_views.py::serve_media` вместо голого `serve`
   в трёх urlconf: deny-list приватных префиксов (`imports/`, `documents/`) →
   404 (не 403 — не подтверждать существование). Остальные префиксы — как были.
**Что НЕ делаем сейчас (P1):** префикс схемы в путях + бэкфилл, гейт «файл
принадлежит хосту» (нужен реестр файл→тенант поверх `media_registry`).
**Замки:** `/media/imports/x.csv` → 404 на всех трёх urlconf; `/media/products/…`
отдаётся; новый импорт ложится под uuid; после `completed` файла нет.

## P0-3. Ключ шифрования: деплой не блокируется, фолбэк из SECRET_KEY
**Факт:** `scripts/deploy.sh:71` — `check --deploy || true` (шаг 8/8, ПОСЛЕ
рестарта); `apps/secrets/crypto.py:18-24` — при пустом `SECRETS_ENCRYPTION_KEY`
ключ выводится из `SECRET_KEY`; один ключ на процесс (`lru_cache`, без аргументов).
**Опасность наивного фикса:** просто задать ключ в проде = все существующие
шифротексты (токены ботов, Meldeschein, документы) читаются как `''` — `decrypt`
глотает `InvalidToken`. Нужна непрерывность.
**Фикс:**
1. `crypto._fernet()` → `MultiFernet([явный_ключ, производный_из_SECRET_KEY])`
   когда явный задан: шифруем ПЕРВЫМ, читаем обоими. Без явного — как сейчас.
2. Команда `rotate_secrets` (public + все схемы): перешифровать
   `PlatformSecret.value_encrypted`, все `EncryptedTextField`
   (`stays.GuestRegistration.doc_number`, `telegram.TelegramBot.token`,
   `documents.SecureDocument.note`), файлы `documents/*.enc` через
   `read_decrypted`/перезапись. Идемпотентна, `--dry-run`, отчёт.
3. `deploy.sh`: ПРЕФЛАЙТ `compose run --rm web python manage.py check --deploy`
   ДО миграций и рестарта (шаг после build); падает — деплой прерван, контейнеры
   не тронуты. Шаг 8 остаётся информационным (`migration_state || true`).
**Ops-инструкция владельцу:** до мержа прогнать `check --deploy` на сервере —
если есть чужие Error'ы, деплой после мержа остановится на них (безопасно, но
внезапно).
**Замки:** MultiFernet читает старый шифротекст; шифрует новым ключом;
`rotate_secrets --dry-run` считает; после ротации старый ключ не читает.

## P0-4. `_voucher_cap_percent` читает Tenant из public
**Факт:** `apps/promotions/services.py:326-337` — `connection.schema_name`
читается ВНУТРИ `schema_context("public")` → всегда `"public"` → потолок
промокода владельца НИКОГДА не применяется (функциональный дефект, не только
кросс-тенант). Собратьев по grep нет.
**Фикс:** снять `schema = connection.schema_name` ДО входа в контекст.
**Замок (красный до правки):** `connection.set_schema("t1")` + Tenant(t1, cap 25)
→ `_voucher_cap_percent() == 25`; в `finally` — `set_schema_to_public()`.
Существующий `test_voucher_cap.py` маскирует баг (тенант с `schema_name="public"`).

## P0-5. Чёрный список админки вместо правила
**Факт:** `apps/core/admin.py:21-30` — `_HIDE_APP_LABELS` перечисляет
`catalog`, `promotions`; `loyalty` (TENANT) не попал → `loyalty.Voucher`
зарегистрирован в платформенной админке. Таблицы нет в public → раздел падает,
данных не отдаёт, но защита случайная.
**Фикс:** в `base.py` — `TENANT_ONLY_APPS = [a for a in TENANT_APPS if a not in
SHARED_APPS]` (вычисляется ДО переопределения в `test.py`, где все tenant-апп
делаются SHARED). `tidy_platform_admin()` снимает с регистрации все модели, чей
`AppConfig.name ∈ TENANT_ONLY_APPS` + прежний список стороннего шума.
**Замок:** после `tidy_platform_admin()` ни одна зарегистрированная модель не
принадлежит tenant-only приложению; `loyalty.Voucher` снят; `tenants.Tenant`,
`aggregator.*`, `support.*` остаются.

## Порядок и гейты
P0-4 → P0-5 → P0-1 → P0-3 → P0-2 (от дешёвого к рискованному). Каждый — свой
коммит, замки в том же коммите. Перед пушем: `ruff check .`, `ruff format
--check .`, `i18n_quickcheck`, template_comments (если шаблоны). Коммит —
перечислением путей. Мерж — FF после зелёного CI.
