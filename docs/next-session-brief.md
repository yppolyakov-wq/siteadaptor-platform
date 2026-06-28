# Точка входа следующей сессии (обновлён 2026-06-27)

Рабочая ветка: **`claude/archetype-platform-ux-editor-x9bzzp`**. Отвечаем по-русски.
Цикл: ветка → `ruff check` + `ruff format --check` (раздельно) → `npm run build:css`
при правке шаблонов → `uv run pytest <модули>` → push → **CI на git зелёный** →
FF-merge в `main` (`git push origin <sha>:main`) → строка в `docs/build-log.md`.
Коммиты: `Co-Authored-By: Claude <noreply@anthropic.com>` + `Claude-Session: …`.
Идентификатор модели в артефакты НЕ светим.

## Активный трек: on-canvas редактор на витрине
**SOURCE OF TRUTH — `docs/storefront-onsite-editor-plan.md`** (подзадачи SE-1…SE-5,
принципы, режимы «Обычный/Эксперт», нагрузка). Идём строго по нему.
- **SE-1a ✅** кнопка «Edit design» на витрине (владельцу) → home_builder. Тест
  `test_owner_edit_button`.
- **SE-1b ✅** инспектор блока перенесён **ВЛЕВО** (`bld-block-popup` в `site_home.html`)
  + подсветка выбранной секции на канве. Контролы (колонки/число/скрыть/переместить/
  источник) уже работают — попап переносит реальную строку формы секции.
- **SE-1f ✅** тумблер «Обычный/Эксперт» в инспекторе (progressive disclosure, `localStorage`
  ключ `sf_editor_mode`; экспертные контролы `data-expert` скрыты CSS в обычном режиме).
- **SE-3d 🟡** визуальные параметры блока: **radius (basic вкл/выкл→16px; expert slider 0–24)
  + тень — ✅**; рендер `.sf-card` + CSS `[style*="--sf-r"] .sf-card` (без регрессии для
  ненастроенных витрин). Осталось: фон/отступы + расширение на фото/баннер.
- **SE-1c ✅** инспектор доведён: колонки/число/источник/скрыть работают; **перемещение ↑▼**
  (value-based кнопки, видны и в обычном режиме — drag/число порядка остаются expert).
- **SE-2a/2b ✅** редактор на каталоге/категории (SE-2a-2/2a-3), лендингах событий/номеров
  (SE-2b-1) и **детальной события — порядок/видимость 14 тематических секций на канве (SE-2b-2):**
  `veranstaltung_detail` draft-aware, обёртка `data-sf-section="event_detail"`, инспектор
  `data-page-key="event_detail"` (value-based ↑▼ `ed_order_*` + чекбоксы `ed_visible_*`),
  presence-guard на POST, превью первого опубликованного события в переключателе.
- **Дальше:** **SE-2c** (добавить категорию на канве — план готов разведкой, см. ниже),
  SE-2d (scope «эта страница/весь сайт»), SE-3 (микрошаблоны/шрифты/устройства + фон/отступы
  SE-3d), SE-4 (блоки/шаблоны), SE-5 (кэш+версии).

### План SE-2c (готов, разведка 2026-06-28) — «Добавить категорию → сохранить → править»
Семантика: отдельная мини-форма-кнопка **«+ Kategorie»** в инспекторе «Landing pages» (по
образцу `action=add_block`, ОТДЕЛЬНАЯ `<form>` вне `#home-form`) → POST `action=add_category`
в `home_builder_view` → создаёт живую `Category` через `apps.catalog.forms.CategoryForm`
(валидация/slug/parent — НЕ переписывать) → `redirect("site-home")`. Категория сразу видна
чипом на канве каталога (`?preview=1`). Миграция НЕ нужна (`Category` есть).
- **SE-2c-1** POST-ветка `add_category` в `home_builder_view` + GET-контекст `categories`
  (guard `is_module_active("catalog")`); мини-форма в `site_home.html`. Тесты: создание,
  guard модуля, инвалидное имя.
- **SE-2c-2** «Править»: на чипах категории в `products.html` — ссылка «✎» на
  `catalog:category-edit` (видна только при `?preview=1`; пробросить флаг из `product_list`).
- **SE-2c-3 (опц., отдельно)** инлайн-правка имени категории на канве — НОВЫЙ эндпоинт
  (пишет `Category.name['de']` в БД) + JS на `[data-cat-edit]`. Риск средний → отдельным шагом.

### Что переиспользуем (НЕ писать заново)
home_builder (`/dashboard/site/home/`, `templates/tenant/site_home.html`): форма-контролы
+ live-iframe превью (`?preview=1` из `site_preview_draft`), обёртки `data-sf-section` на
секциях витрины, клик-попап E.2 (теперь слева), инсертер «+» E.3, drag E.4, Undo/Redo E.1,
пресеты раскладки, `sitetemplates`, пары шрифтов, переключатель устройств, per-page layouts,
инлайн-правка текста (`site_inline_edit`).

## Статус merge / deploy
- `main` сейчас: `1b8f8dc`. Слито FF после зелёного CI: SE-2b-2, SE-2c-1/2c-2, решение/план
  SE-2d, **CI-инкремент** (ci.yml concurrency cancel-in-progress + кэш uv/npm),
  **SE-2d-1/2/3** (мастер-настройка стиля карточек «весь сайт»: `site_defaults` +
  резолвер `effective_card_visual` с наследованием/override + рендер site-wide + UI
  в конструкторе + live-preview), конвенции CLAUDE.md §5 (подготовка до кода + батч-режим).
  Ранее: SE-1a/1b/1c/1f/3d, SE-2a-1/2a-2/2a-3, SE-2b-1. Pending нет.
- Текущая ветка сессии: `claude/event-detail-section-order-qk6t76` (= main после merge).
- **Дальше (готово к коду):** (1) CI-инкремент — concurrency cancel-in-progress + кэш uv/npm
  (ветка от main; сниппет в scratchpad se2d-plan-skeleton.md). (2) План-док SE-2d (Вариант A:
  `site_defaults.card_radius/shadow` + резолвер `effective_card_visual` + точки рендера +
  разбивка SE-2d-1..5) — скелет и карта рендера в scratchpad. (3) Опц. SE-2c-3 (инлайн-правка
  имени категории на канве, новый эндпоинт). Решение SE-2d=Вариант A; «выбранные» отложены.
- **Деплой (владелец, один раз):** `git pull origin main && ./scripts/deploy.sh single`
  (миграция `events/0021`) + `python manage.py seed_demo_tenants --kit pranasy --recreate`.
  **Кастомный домен добавлять/держать ПОСЛЕ последнего `--recreate`** (иначе привязка
  `Domain` удаляется). Автоподключение домена заработает после деплоя; до деплоя разовый
  обход — `ALLOWED_HOSTS=*` в `.env.prod` + `docker compose --profile single up -d web`.

## Сделано в этой сессии (хронология — build-log)
Pranasy полноценный двуязычный кит (PR-A…H: i18n site_config/Event, локальные демо-фото
SVG, подкатегории, Restaurant+Shop как отдельные сущности, 6 ретритов, кетеринг, лояльность,
«О нас»). Спринт G анти-Битрикс (AB1–AB5). Фиксы: инлайн-редактор (contenteditable +
заголовки секций + не уводить по ссылкам), загрузка фото баннера раздела, **автоподключение
кастомных доменов** (middleware из таблицы Domain + авто-verify beat).

## Перед боевым запуском (владелец)
Stripe live, инфра (отд. Postgres/бэкапы/секреты/Sentry/Resend), право DACH.
