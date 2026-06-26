# Бриф для новой сессии — продолжение этапа «витрина/UX + анти-Битрикс»

> Создан 2026-06-25 по завершении большого инкремента (Спринты A–D). Это
> **точка входа для следующей сессии**. Source of truth по шагам —
> `docs/archetype-ux-execution-plan.md`; хронология сделанного — `docs/build-log.md`;
> рыночное обоснование — `docs/archetype-market-analysis.md` (+ `docs/market-analysis/*`).

## 0. Контекст за 30 секунд
Мультитенантный Django 5.1 SaaS для микробизнеса DACH (один тенант = сайт на
субдомене, ~39 €/мес, витрина без трекинг-куки, GDPR-first, анти-маркетплейс).
Стек витрины/билдера: **HTMX/Alpine/Tailwind, server-rendered, НЕ SPA**. Секции
главной — JSON поверх `Tenant.site_config` (без пер-секционных моделей).

**Северная звезда (владелец):** «анти-Битрикс» — настройка за ≤5–10 шагов, нативное
максимально лёгкое редактирование, «чтобы ребёнок собрал себе сайт». Блочная структура.

## 1. Рабочая ветка и цикл
- Ветка этапа: **`claude/archetype-analysis-market-gaps-dkwo87`** (продолжать на ней
  или новой `claude/<кратко>` по согласованию). Мерж в main — git-only FF push.
- Цикл: один инкремент = правка → `ruff check .` **и отдельно** `ruff format --check .`
  → при правке шаблонов `npm run build:css` (CI гейтит свежесть `static/css/app.css`)
  → тесты `uv run pytest <модули>` → коммит → push → отметить статус в
  `archetype-ux-execution-plan.md` + строка в `build-log.md` → чекпоинт с владельцем.
- Коммиты: завершать `Co-Authored-By: Claude …` + `Claude-Session: …` (как в истории).
  Идентификатор модели в артефактах НЕ светить.

> **ОБНОВЛЕНО 2026-06-26:** Спринт E полностью закрыт + большой кусок Спринта F.
> Разделы 1a/2/3 ниже переписаны под актуальное состояние. Детали каждого инкремента —
> в `build-log.md` (хвост); статусы — в `archetype-ux-execution-plan.md`.

## 1a. Статус мержа в main (2026-06-26)
**Всё смержено в `main` (вершина `90107c6`, CI зелёный, FF-push).** Ветка
`claude/archetype-platform-ux-editor-x9bzzp` == `origin/main` (расхождение 0/0).
**Миграций за сессию 2026-06-26 нет** (только JSON/шаблоны/вьюхи/демо/доки) → деплой
простой: `git pull origin main && ./scripts/deploy.sh single` (ручной шаг владельца на
сервере Hetzner; из агент-окружения деплой недоступен — нет SSH). После деплоя для показа
календаря наличия: `seed_demo_tenants --kit hotel --recreate`.

## 2. Что уже сделано (✅, всё в `main`, тесты/CI зелёные)
**Спринты A–D** (раньше): сквозные блоки (services/отзывы/USP-bar/лайтбокс), анти-Битрикс
Phase 1 (демо в мастере, тема, hero-фото, онбординг `/willkommen/`), Widerruf, реестр
блоков `render_block` + C-блоки с билдером. Подробности — в истории build-log.

**Спринт E — анти-Битрикс «on-canvas» (закрыт, 2026-06-25/26):**
- **E.1 Undo/Redo** — клиентский стек снимков состояния редактора (N=20), ↶/↷ + Ctrl+Z/
  Ctrl+Shift+Z; «Отменить» влияет и на Сохранение (а не только превью).
- **E.2 click-to-edit → попап** — клик по блоку в live-preview переносит его реальный
  control-row в плавающую карточку (внутри `#home-form`).
- **E.3 инсертер «+»** — зоны «+» между блоками превью → библиотека → `add_block` с новым
  параметром `add_after` (вставка сразу после блока).
- **E.4 drag-on-canvas** — drag-ручка ⠿ на блоках превью → `moveBlock` переносит порядок
  в редактор. (Обёртки `display:contents` → ручка на первом элементе секции.)

**Спринт F — глубина по архетипам (частично, 2026-06-26):**
- **A7 Handwerker** — отдельный демо-кит `handwerker` (Maler/Elektro/SHK, ядро jobs/Angebot
  + booking-Festpreise, без shop). `seed_demo_tenants --kit handwerker`.
- **A6 ретрит:** RV3 грид-обложки событий + countdown-пилюля · RV2 agenda-timeline программы.
- **A5 отель:** PAngV-разбивка цены номера · рейтинг бизнеса на странице номера ·
  **визуальный календарь наличия C1–C4** (хелпер `availability.month_availability` → вьюха
  `/unterkunft/<pk>/kalender/` + партиал `_stay_calendar.html` → встроен в страницу номера +
  выбор диапазона кликом → демо Sperrung/embed). Без новых моделей. План —
  `docs/hotel-availability-calendar-plan.md`.
- **A4 Gastro:** аллергены LMIV на карточке меню · Kombo/Tagesgericht-тизер вверху меню.
- **A9/A7:** пометка «Festpreis» в блоке услуг (при активном модуле jobs).
- **A8 агрегатор:** сортировка выдачи города (Neueste / Name A–Z).

## 3. Что делать дальше (порядок плана)
Спринт E закрыт; идём по остатку Спринта F (source of truth — `archetype-ux-execution-plan.md`).
Незакрытые пункты (по архетипам, размер в скобках):
- **A6 ретрит:** **RV1** 2-шаговый чекаут билета (M) · **RT1** QR-билет + check-in (M) ·
  **RT2** онлайн/Zoom-события (S–M, **нужно поле `Event.is_online`/`online_url` → миграция**) ·
  RT3 recurring-серии (M) · RT4 блог (M).
- **A4 Gastro:** диет-иконки/фильтр (S–M) · гибкий депозит за стол + no-show (M) · виджет
  брони стола + reminder (M) · слоты доставки + Trinkgeld для QR (M).
- **A3 Termin:** богатая карточка услуги (поля `Service.description/image` → миграция) ·
  профили мастеров↔Resource (M) · визуальный календарь слотов (M) · выбор мастера (M).
- **A9 Werkstatt:** структурные данные авто Kennzeichen/HSN-TSN (M) · Repair-Status (S–M) ·
  TÜV/Service-Reminder (M).
- **A7 Handwerker:** before/after-галерея (M) · PLZ/Einzugsgebiet (M) · Rückruf (S).
- **A8 агрегатор:** фасетные фильтры (рейтинг/«offen jetzt») + автоподсказки (M) · богатая
  карточка бизнеса (S–M) · карта как режим (M) · self-serve Featured через Stripe (M).
- **A1/A2 Retail:** отзывы о товаре (M, нужна модель отзыва на Product) · (featured/Trust/
  галерея — уже покрыты существующей инфраструктурой).

### Опционально
- **D.3** — свести 6 экранов билдера (Site/Home/Sections/Pages) в один + Menu отдельно.
- **C.3** — PayPal / Kauf auf Rechnung (L, гейт владельца по провайдеру).
- **Параллельно (на владельце) — Stage 0:** Stripe live · инфра (отд. Postgres, бэкапы,
  секреты, Sentry/Resend) · право DACH (AVV/DSGVO, k6).

## 4. Подсказки/грабли этой сессии (сэкономят время)
- **Тесты, требующие tenant-схемы** (демо, каталог, C-блоки через вьюхи): создавать
  тенант как `TenantFactory(schema_name="public", slug=…, name=…)` — тогда
  catalog/promotions/booking таблицы доступны (TENANT_APPS = SHARED в test-настройке).
- **Вьюхи с `messages`** в тестах через RequestFactory: навесить `SessionMiddleware`
  + `MessageMiddleware` на request (см. `test_onboarding_wizard._req`).
- **`Service.pk`/многие pk — UUID**: в URL-reverse передавать строку UUID, не int.
- **Реестр секций** — единый источник: `siteui.BLOCK_TEMPLATES` (фикс) +
  `CBLOCK_TEMPLATES` (C-блоки); `render_block` принимает строку-ключ ИЛИ dict-блок.
- **Главная** рендерится из `section_blocks` (включённые записи, фикс+C) во вьюхе
  `apps/promotions/public_views.py::storefront_home`; `sections` (ключи) — для гейтинга.
- **C-блоки** хранятся в `site_config["sections"]` рядом с фикс-секциями; `normalize`
  их сохраняет (id+data, кап 30). Сохранение главной (`home_builder_view`) делает их
  round-trip — не пересобирать sections только из `SECTIONS` (был баг, исправлен).
- Демо-тенанты: `python manage.py seed_demo_tenants --recreate` (киты в
  `apps/tenants/demo_kits.py`). Проверка онбординга: `/willkommen/`.
- **Многострочные комментарии в шаблонах — только `{% comment %}…{% endcomment %}`**,
  НЕ `{# … #}` (многострочный `{# #}` Django не вырезает → текст утекает в HTML;
  ловится `test_storefront_header_does_not_leak_template_comment`).
- **CI ~16 мин** на полном suite (serial, schema-heavy django-tenants). Это норма,
  не зависание. Канонический гейт — CI на git (CLAUDE.md §5), локальный прогон — фолбэк.

## 5. Definition of done каждого инкремента
ruff (раздельно check/format) зелёный · build:css свежий (если шаблоны) · новые тесты
зелёные · регрессия затронутых модулей зелёная · статус в execution-plan + build-log
обновлён · коммит+push · краткий чекпоинт владельцу.
