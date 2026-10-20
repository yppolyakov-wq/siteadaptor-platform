# T-8.31 «Mein Laden» — лёгкий кабинет по утверждённому макету (план, 2026-10-20)

Источник: макеты «Mein Laden — mobil» (Start · Aktion «So sehen Kunden die Aktion» ·
Sichtbarkeit & Verbindungen · то же в Telegram), решение владельца «делай по макету и
рекомендациям». План составлен агентом planner, проверен по коду. Без миграций.
Лёгкий кабинет = `storefront_profile.is_aktionen` (профили `aktionen` и `eintrag`);
полный кабинет не трогаем.

## 0. Опорные точки в коде

- `apps/core/views.py` `dashboard()`: сейчас лёгкий тенант → редирект на
  `promotions:promotion-list`; онбординг-редирект стоит раньше и остаётся первым.
- `apps/core/modules.py` `sidebar_nav`: ранний выход → `lite_cabinet.sidebar_items`;
  мобильный таб-бар = первые 4 пункта (`context.py`, `nav_primary`).
- `apps/core/lite_cabinet.py` `LITE_NAV`; в `templates/tenant/_icons.html` нет
  символа `ic-nav-integrations`.
- `apps/promotions/views.py` `promotion_list` (счётчики `n_held`/`n_handed`/`n_coupons`),
  `promotion_transition` (POST `target`, FSM, редирект всегда на edit).
- `apps/promotions/where.py` `report()` — строки для Telegram; причины в
  `_catalog_reason`/`_catalog_line`.
- `apps/aggregator/tasks.py` `sync_listing` собирает поля листинга инлайн (там же
  скрытие mystery).
- `templates/storefront/_promo_card.html` (контекст `p`, тег `card_form`);
  `templates/aggregator/_cards.html` (часть ссылок только в urlconf портала).
- `integrations_home`: статусы Stripe/бот/домен/публикация — вложенные замыкания.

## 1. Решения

1. **Start вместо редиректа.** `/dashboard/` (имя `dashboard`) у лёгкого тенанта рендерит
   новую главную (`apps/core/lite_home.py`). Новых маршрутов нет. Порядок в `dashboard()`:
   онбординг → лёгкий → полный. Замок `test_lite_dashboard_opens_promotions` переписать.
2. **Меню.** Новый `LITE_NAV`: Start (`dashboard`) · Aktionen · Angebot (`sellable-manage`,
   подпись «Angebot» только в лёгком кабинете) · Sichtbar (`lite-visibility`, ключ
   `integrations`) · Geschäft · Teilen. Таб-бар = первые четыре. `integrations-home`
   уходит из меню и становится ссылкой «Alle Verbindungen →» со страницы Sichtbarkeit.
   Добавить SVG `ic-nav-integrations`.
3. **Превью — настоящие партиалы**, без iframe, в обёртке `inert aria-hidden`.
   Сайт: `_promo_card.html` с переменными темы тенанта (хелпер витрины, не руками).
   Портал: чистая функция `listing_defaults(tenant, snap, promotion_id)` из `sync_listing`
   (поведение sync байт-в-байт), превью = несохранённый `AggregatorListing`, рендер
   `aggregator/_cards.html` под `set_urlconf("config.urls_portal")` в try/finally.
   Переключатель Website|Stadtportal — CSS/`hidden` + делегированный клик, без fetch.
4. **Структурированное «где».** `where.rows(tenant, promo)` → `{key,label,ok,detail,url}`;
   `report()` строится поверх, вывод байт-в-байт (замок Telegram).
5. **Пауза/завершение** — через `promotion_transition` + безопасный `next`
   (`url_has_allowed_host_and_scheme`, отказ `//`); без `next` — как раньше.

Ответы на открытые вопросы плана (по рекомендации): «Eigene Website freischalten» в v1 —
только ссылка/пояснение, без смены профиля; главная акция Start — ближайшая по окончанию
среди активных, при равенстве — по просмотрам; подпись «Angebot» — только в `LITE_NAV`.

## 2. Инкременты

### 31a — Start + меню
Замки ДО кода (`apps/core/tests/test_lite_home.py`): лёгкий GET `/dashboard/` → 200
`data-lite-home`, полный — прежняя петля; онбординг-редирект цел; счётчики акций
(«3 aktiv · 1 geplant»), главная акция, товары/«ohne Foto»; чипы Website/Stadtportal/
Telegram по фактам; «следующий шаг» никогда не ведёт в 404/405; лимит запросов (~8);
`LITE_NAV` + `nav_primary`; сотруднику без чисел портала.
Код: `lite_home.py` (`promo_counts`, `featured_promo`, `product_counts`,
`visibility_chips` поверх `where.rows`, реестр `next_step`), `where.rows`, шаблон
`templates/tenant/lite_home.html` (заголовок с именем и датой внутри страницы — не
зависит от шапки, для Mini App), `LITE_NAV`, иконка, i18n ×5, `app.css`.

### 31b — страница акции «So sehen Kunden die Aktion»
Замки: 200 для draft/scheduled/active; панель сайта с разметкой акции; панель портала без
NoReverseMatch (в т.ч. у тенанта с featured-листингом); mystery без цены; причины
Stadtportal; `report()` — голден; паритет `listing_defaults` ↔ `sync_listing`;
`next` на себя работает, `//evil` отвергнут; обёртка `inert`; чужая акция → 404.
Код: `listing_defaults`, `where.rows`, вьюха `promotion_preview` в
`apps/promotions/lite_views.py` (`<uuid:pk>/ansicht/`), безопасный `next`, ссылка
заголовка лёгкой карточки в списке акций → превью.

### 31c — Sichtbarkeit & Verbindungen
Замки: 200 владельцу; «Aufrufe/Woche» портала только владельцу (у сотрудника `summary`
не вызывается); Google-карточка только владельцу; свой бот в трёх состояниях (как T-8.29);
Stripe «Für Zurücklegen nicht nötig»; домен; ни одной ссылки в 404 с учётом гейтов
модулей; вход в `integrations-home`; сломанный статус-блок не роняет страницу.
Код: статусы из `integrations_home` → `apps/core/integration_status.py` (вывод
`integrations_home` без изменений), вьюха `lite_visibility`
(`dashboard/sichtbarkeit/`, `nav="integrations"`) + запись в `EXPECTED_UNLISTED`,
шаблон `templates/tenant/lite_visibility.html` (шаги BotFather в `<details>`).

### 31d — заметки для T-8.30 (Mini App)
Все экраны на 390 px, без hover, заголовок в теле страницы, делегированный JS,
`{% block lite_chrome %}` для скрытия хрома кабинета.

## 3. Проверка
Серверные замки по инкрементам; лимиты запросов на Start и превью; голдены `report()` и
`sync_listing`; Playwright-стенд 390/1440 на лёгком демо (владелец и сотрудник): таб-бар
из четырёх, переключатель панелей, превью не кликается, пауза возвращает на превью.
Гейт: ruff, `template_comments`, `i18n_quickcheck`, `app.css`, pytest затронутых модулей.
Ревью перед мержем: django + security.

## 4. Риски
- urlconf портала внутри рендера → только несохранённый листинг без `featured_until`,
  try/finally, замок «хром кабинета после превью реверсится».
- Расхождение превью с реальностью → один `listing_defaults` для sync и превью.
- Переменные темы витрины в кабинете → общий хелпер, сверка скриншотом с `/aktionen/`.
- Утечка owner-only → гейт `is_owner` во вьюхах, тест сотрудника на каждый блок.
