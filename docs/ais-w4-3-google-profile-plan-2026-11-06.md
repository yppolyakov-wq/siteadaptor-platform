# AIS W4-3 «Google-Profil finden» — план (2026-11-06)

План — агент ECC `planner`. Спека — `ais-wizard-v4-structure-2026-11-05.md` §3 шаг 1, §5.
Без миграций, без Celery (два коротких запроса с таймаутом). Нет ключа → блока нет.

## Поток
Шаг «Firma» мастера v4: «Bei Google suchen» (название + город) → один Text Search →
владелец выбирает карточку → один Place Details → таблица «поле · сейчас · Google · ✓»
(галочка по умолчанию только там, где у нас пусто — класс W0) → «Übernehmen» пишет только
отмеченное из СЕРВЕРНОГО кэша (не из POST) + `google_place_id` (GK-11 подхватит рейтинг).

## Клиент (`apps/tenants/google_places.py`)
- `search_places(query, city, lang)` — `POST places:searchText`, FieldMask
  `places.id,places.displayName,places.formattedAddress` (дешёвый SKU), ≤ 5, таймаут (3, 6),
  id по `^[A-Za-z0-9_-]{10,255}$`, клампы длин.
- `place_details(place_id, lang)` — FieldMask
  `nationalPhoneNumber,websiteUri,regularOpeningHours,addressComponents,formattedAddress`
  (биллинг по старшему SKU = Enterprise за выбор). Фото не запрашиваются никогда (ToS).
- Данные недоверенные: телефон `[\d +()/-]` ≤ 40, сайт только https ≤ 200, адрес из
  компонентов, часы `periods` → наш формат (Google 0 = воскресенье) через `openinghours.normalize`;
  ночные/второй интервал — отбрасываются с пометкой «bitte prüfen».
- Ошибки — `PlacesError`; ключ не попадает в сообщения и логи (SEC-A).

## Эндпоинты
- `setup-google-search` (POST, лимиты: 10/ч на сеть /64 + 20/день на тенант, возврат при 5xx
  Google), `setup-google-pick` (5/ч, 10/день; кэш данных 15 мин по пользователю), применение —
  ветка шага «Firma». Права — как у шага мастера; без ключа — 404.

## Замки до кода
FieldMask и ключ только в заголовке; маппинг дней; XSS в названии экранирован; мусорный id — 400
без запроса; 11-й поиск — 429 без запроса, 5xx — возврат попытки; без ключа — блока нет и 404;
неотмеченное поле не тронуто, без кэша ничего не пишется, подделка в POST игнорируется;
`google_place_id` сохранён; аноним — 302/403.

## Риски
Стоимость (лимиты + кэш + квота в Google Console — ops владельца) · DSGVO (в Google уходят
только название и город; строка в Datenschutz платформы) · ToS (без фото) · частичная перезапись
(галочки, кэш).

## ECC-прогоны
Скиллы до кода: django-patterns, django-tdd, django-security, error-handling, accessibility.
`security-reviewer` (стоимость, XSS, утечка ключа) и `silent-failure-hunter` (клиент) — до мержа;
`django-reviewer`; `a11y-architect` (радио-список, таблица сравнения); стенд Playwright с
поддельным Google по env (390/1440, с ключом и без).
