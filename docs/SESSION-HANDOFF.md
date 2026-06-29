# SESSION HANDOFF — точка входа следующей сессии (2026-06-29)

> Новая сессия: **прочитай этот файл первым**, затем продолжай. Отвечаем по-русски.
> **Пиши простым текстом, что делаешь на каждом шаге** (не только тул-вызовы — иначе владельцу
> кажется, что всё зависло, и он прерывает). Длинные операции запускай в ФОНЕ (`run_in_background`),
> т.к. обычные команды прерываются входящими сообщениями и результат теряется.

## Связь с CLAUDE.md (память проекта — авто-грузится)
Этот хендофф = ДЕЛЬТА текущей сессии. CLAUDE.md даёт §1-2 архитектуру (Django 5.1 multi-tenant DACH),
§5 конвенции, §6 доки, §7 БОЛЬШОЙ роадмап, §8 деплой. Текущий активный под-трек = редактор витрины +
inline-content (этот документ). После него — по CLAUDE.md §7 (M20 Site Builder, архетипы «Спринт F»,
Спринт G «анти-Битрикс» AB1-5, Stage 2/3). Source of truth по сделанному — `docs/build-log.md`.

## Ветка и цикл
- Ветка: **`claude/event-detail-section-order-qk6t76`**.
- Цикл: `uv run ruff check .` + `uv run ruff format --check .` (раздельно, ВСЯ репа) → `npm run build:css`
  при правке шаблонов (коммитить `static/css/app.css`) → `uv run pytest <модули> --reuse-db` (миграции → `--create-db`)
  → push → CI зелёный → FF-merge: `git push origin <sha>:main` → строка в `docs/build-log.md`.
- Коммиты: `Co-Authored-By: Claude <noreply@anthropic.com>` + `Claude-Session: <url>`. Идентификатор модели НЕ светить.
- CI ~12-16 мин. Статус: `mcp__github__actions_list` (отдаёт ~400КБ → в файл; парсить `jq -r '.workflow_runs[0]|"\(.head_sha[0:7]) \(.status) \(.conclusion)"' <file>`, файл удалять). AskUserQuestion здесь НЕ работает — развилки текстом.

## ГЛАВНЫЙ УРОК (почему были баги на проде)
Юнит-тесты проверяют отрендеренный HTML, **а не поведение JS** редактора. Все баги были в JS
(состояние попапа, перебивка пресета, дефолт тумблера). **Правки `templates/tenant/site_home.html`
ОБЯЗАТЕЛЬНО проверять в браузере** (Chromium + Playwright в окружении) ДО отдачи владельцу.

### Готовый тестовый стенд (поднят в этой сессии — переиспользуй)
- Тенант `baeckerei_test` → **`http://baeckerei-test.siteadaptor.de:8000/`** (`manage.py create_test_tenant`).
- Юзер **owner@test.de / test12345** (superuser, public-схема). Демо: 6 товаров + категория «Brot», секции products/promotions вкл.
- Настройка (`DJANGO_SETTINGS_MODULE=config.settings.development`): `migrate_schemas --shared`, `create_test_tenant`,
  затем `shell < scratchpad/setup2.py` (юзер/товары/форс-логин сессия в схеме тенанта, печатает SESSIONID).
- Сервер: `uv run python manage.py runserver 0.0.0.0:8000` (фон).
- Браузер БЕЗ /etc/hosts: Chromium с `--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1`; навигировать на
  `http://baeckerei-test.siteadaptor.de:8000/dashboard/site/home/`; добавить cookie `sessionid=<SESSIONID>`
  (domain `baeckerei-test.siteadaptor.de`). Скрин → владельцу через SendUserFile. Проверь middleware-блок (биллинг).

## СДЕЛАНО и в `main` (деплой: `git pull origin main && ./scripts/deploy.sh single`)
- SE-9 «редактор для ребёнка»: компактный рейл, мобильная версия (рамка телефона), правка моб-раскладки в Простом,
  медиа внутрь блоков (общая «Медиа» убрана), режим «Edit on site», динамический рейл иконок блоков.
- FIX прод-500 на `/dashboard/site/` (`site_view` падал на repeatable-блоках → guard `if key in labels`).
- FIX попап копил чужие блоки (`openBlockPopup` не ставил `popupRow`). «Edit on site» дефолт → ВЫКЛ.
- Фаза 1 inline-content: имя товара правится на карточке витрины (`product_inline_edit` + `[data-edit-model]`).
- FIX скролл меню кабинета (`#dash-nav` без `min-h-0`; сайдбар `md:sticky h-screen`).

## Точное состояние git (конец сессии)
Всё из «СДЕЛАНО» — уже в **main**. НЕ в main, только на ветке: **фикс баг D (раскладка) + тесты + этот хендофф**.
Новой сессии: ПРОВЕРИТЬ баг D в браузере → push → CI → FF-merge в main → деплой. Миграций в сессии НЕ добавляли.

## ОТКРЫТЫЕ ЗАДАЧИ (ТЗ владельца, по приоритету)
1. **Баг D — раскладка («2 в ряд» показывала 3).** ФИКС НАПИСАН (в `site_home.html`: при клике по миниатюре-пресете
   сбрасывать пер-девайс `cols/mobile/tablet` — явный cols перебивал пресет в `normalize_layout`). Тесты есть
   (`test_storefront_preview_explicit_cols_overrides_preset` + рендер-страховка). **ПРОВЕРИТЬ В БРАУЗЕРЕ**, потом мерж.
2. **Убрать 2-й (плавающий) попап → одна фокус-панель «только выбранный блок».** Владелец: «зачем 2 попапа, оставь
   активный». Дизайн (вар.1): клик по блоку → его настройки В ЛЕВОЙ панели (список `#home-blocks` прячется), сверху
   «← Ко всем блокам»; убрать плавающий `#bld-block-popup`. Реюз relocate (popupRow/popupAnchor), цель — контейнер в
   панели + CSS `[data-bld-area=sections].focus-on > :not(focus){display:none}`.
3. **Крупнее иконки рейла + подписи** (SE-9a их уменьшил): `.bld-rail-btn`/`.bld-blk-btn` `w-12 py-1.5`→`w-16 py-2`,
   эмодзи `text-lg`→`text-2xl`, подпись `text-[9px]`→`text-[11px]`, nav `w-14`→`w-20`.
4. **Десктоп-ширина превью**: «Desktop» рендерить ≥1024px (масштабируя), иначе `lg:grid-cols-N` не срабатывает на узкой канве.
5. **Сворачиваемая панель** — явная кнопка (частично есть: клик по активной иконке рейла сворачивает).
6. **Аккордеон-группы в меню кабинета** (`_base_dashboard.html`): сворачивать `nav_groups`, localStorage, активная развёрнута.
7. **Inline-content Фаза 2/3** (на согл.): цена (поповер+валидация Decimal), фото-замена; «✎» на карточке → полная форма.
   Паттерн — `category_inline_edit`/`product_inline_edit`; вайтлист полей. План — `docs/storefront-inline-content-plan.md`.

## Не путать / отложено
- **«Готовые виды» (галерея обликов) — НЕ ТЗ** (была опечатка «моб[ильную] версию»; мобильное превью уже сделано).
- **SE-9c-2 «очищенный мастер» — ОТЛОЖЕН** (конфликт с SE-9g; Простой режим уже де-загромождает).

## Доки
`docs/storefront-onsite-editor-plan.md` (план редактора SE-1..SE-9) · `docs/storefront-inline-content-plan.md` (Фаза 1-3)
· `docs/build-log.md` (хронология) · `CLAUDE.md` (память проекта, роадмап §7).
