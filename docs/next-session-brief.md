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

## 2. Что уже сделано (✅, всё запушено, тесты зелёные)
- **Спринт A** — сквозные витринные блоки: блок услуг `services` (A3), отзывы на
  витрине в китах, Trust/USP-bar (`usp_bar`), полноэкранный лайтбокс галереи.
- **Спринт B** — анти-Битрикс Phase 1: демо-контент в мастере, тема-пикер, hero-фото
  файлом, **линейный онбординг `/willkommen/` (7 шагов)**.
- **Спринт C** — правовой долг: Widerrufsbelehrung für Waren (авто, при
  `delivery_enabled`) + онлайн-форма `/widerruf-formular/`.
- **Спринт D** — **реестр блоков** `siteui.render_block` (D.1, заменил if/elif в
  `home.html`) + **C-блоки** `text/image/image_text/button/spacer` (D.2a движок +
  D.2b билдер: добавить/править/порядок/удалить в `/dashboard/site/home/`).

## 3. Что делать дальше (порядок плана)
### Вариант 1 — Спринт E «on-canvas» (рекомендуется, если цель — добить анти-Битрикс)
Тяжёлый фронт (HTMX/Alpine + iframe↔parent postMessage, без SPA). Делать инкрементами:
- **E.1 Undo/Redo** (S, быстрая победа): стек снимков draft в `request.session`
  (`site_preview_history`, N≈20), Ctrl+Z/кнопка → откат → swap превью. Файлы:
  preview-вьюхи (`apps/core/views.py` live-preview), `templates/tenant/site_home.html`.
- **E.2 Click-to-edit блока → попап** (M): в превью-iframe каждый блок обернуть
  `data-block="<key|id>"`; клик → postMessage родителю → hx-get формы настроек блока.
  Опирается на реестр D.1 (`siteui.BLOCK_TEMPLATES`/`CBLOCK_TEMPLATES`).
- **E.3 Инсертер «+»** (M): зоны между блоками → библиотека блоков (миниатюры) →
  hx-post добавляет запись в `site_config["sections"]` (для C-блоков — с новым `id`)
  → swap. Переиспользует `add_block`-логику из `home_builder_view`.
- **E.4 Drag-on-canvas** (M): SortableJS по контейнеру секций в iframe → POST порядка.
Готовый фундамент: live-preview draft (`site_preview_draft`), инлайн-правка текста
(`[data-edit]` + `site_inline_edit`), реестр блоков, `normalize` уже принимает C-блоки.

### Вариант 2 — Спринт F «глубина по архетипам» (если нужны быстрые видимые улучшения)
Каждый пункт самодостаточен; крупные — отдельным план-доком до кода. Приоритетные,
с обоснованием в `docs/market-analysis/*`:
- **A6 ретрит (визуальный трек, см. `retreat-archetype-plan.md` §6):** RV2 agenda-
  timeline (S–M) · RV3 грид-обложки событий + hero-countdown (S–M) · RV4 лайтбокс
  на детальной события (S, уже почти даёт A.4) · RV1 2-шаговый чекаут билета (M).
- **A5 отель:** визуальный календарь наличия (M–L, сильнейший рычаг конверсии) ·
  разбивка цены PAngV + рейтинг на странице номера (S–M).
- **A4 Gastro:** food-hero пресет (S) · гибкий депозит за стол + no-show (M).
- **A9 Werkstatt:** прайс-блок Festpreis на витрине (S) · структурные данные авто
  Kennzeichen/HSN-TSN (M) · TÜV/Service-Reminder (M).
- **A7 Handwerker:** **отдельный демо-кит** (Maler/Elektriker/SHK, generic) +
  Referenzen/before-after-галерея + Notdienst-CTA (рекомендация отчёта A7).
- **A8 агрегатор:** фасетные фильтры + сортировка (M) · полный JSON-LD для Map Pack/
  AI (S–M) · self-serve Featured через Stripe (M, монетизация без комиссии с оборота).

### Опционально
- **D.3** — свести 6 экранов билдера (Site/Home/Sections/Pages) в один + Menu отдельно.
- **C.3** — PayPal / Kauf auf Rechnung (L, гейт владельца по провайдеру).

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

## 5. Definition of done каждого инкремента
ruff (раздельно check/format) зелёный · build:css свежий (если шаблоны) · новые тесты
зелёные · регрессия затронутых модулей зелёная · статус в execution-plan + build-log
обновлён · коммит+push · краткий чекпоинт владельцу.
