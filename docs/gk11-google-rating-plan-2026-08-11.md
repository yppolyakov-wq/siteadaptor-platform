# План GK-11 «Google-рейтинг через Places API» (2026-08-11)

Отмашка владельца «Делай Google-рейтинг через Places API». ID — GK-11 (= C-11
gap-анализа goodkarma). Разведка — Explore-агент, чек-лист file:line в отчёте.

## Решения

1. **Хранение**: 4 колонки Tenant (⚠️ миграция `tenants/0030`, аддитивная) —
   `google_place_id` (владелец вводит), кэш `google_rating` (Decimal 3,2 —
   зеркало BusinessRating), `google_rating_count`, `google_rating_updated_at`
   (свой, auto_now Tenant.updated_at не годится). Кэш обязателен: ToS Google
   ограничивает кэширование контента (≤30 дней) — обновляем беатом, при
   ошибке API держим последнее значение (fail-safe).
2. **API**: Places API (New) — `GET https://places.googleapis.com/v1/places/{id}`
   с `X-Goog-Api-Key` + `X-Goog-FieldMask: rating,userRatingCount` (2 поля =
   дешёвый Basic-SKU). Сервис `apps/tenants/google_places.py` по идиоме
   publishing/adapters (module-level `import requests`, timeout 15,
   raise_for_status, RuntimeError «nicht konfiguriert» без ключа).
3. **Ключ**: платформенный — `apps.secrets.store.get_or_setting(
   "google_places_api_key", "GOOGLE_PLACES_API_KEY")` (шифрованный стор →
   env-фолбэк). ⚠️ EXTERNAL-блокер владельца: ключ с включённым Places API
   (billing) в `.env.prod` или через админ-стор. Без ключа фича молчит.
4. **Beat**: `apps/tenants/tasks.py::refresh_google_ratings` — SHARED-обход
   Tenant (public-схема, schema_context не нужен — прецедент
   recheck_pending_custom_domains), фильтр «place_id задан И
   updated_at старше GOOGLE_RATING_REFRESH_DAYS (env, дефолт 7)»,
   per-tenant try/except (одна ошибка не роняет проход), targeted
   update_fields; расписание в CELERY_BEAT_SCHEDULE (сутки).
5. **Кабинет**: карточка «⭐ Google Bewertungen» в Einstellungen→Integrationen
   (status ok/warn/muted) → экран `/dashboard/settings/google-bewertungen/`:
   GoogleRatingForm (только place_id; help «где взять Place ID» + ссылка на
   Place ID Finder), targeted-save (W7a), кнопка «Jetzt aktualisieren»
   (синхронный fetch с messages-ошибкой при неконфиге), read-only кэш.
   Ctrl+K-запись в nav_registry.
6. **Витрина**: `_trust.html` — Google-элемент РЯДОМ с внутренним рейтингом
   (чтение прямо из `request.tenant.google_rating`, None → пусто; подпись
   «N Google-Bewertungen» — источник назван честно, атрибуция Google);
   попутно исправить вводящий в заблуждение комментарий «рейтинг Google»
   (рендерился ВНУТРЕННИЙ BusinessRating — находка ещё gap-анализа);
   страница `/bewertungen/` — вторая строка рейтинга в шапке. В JSON-LD
   Google-рейтинг НЕ кладём (политика Google: aggregateRating в разметке —
   только собственные отзывы сайта; наш entity/localbusiness LD продолжает
   нести внутренний рейтинг).
7. **Тесты**: `_Resp`-стаб + monkeypatch requests.get (идиома test_gbp);
   fetch+кэш (только 4 update_fields), скип свежих, no-op без place_id,
   RuntimeError без ключа, ошибка одного тенанта не роняет beat, форма
   сохраняет place_id, витрина: рендер при кэше / пусто без. site_config
   не трогаем → golden целы. msgid × 5 .po; i18n_gap теперь гоняется локально.
