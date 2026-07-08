# UC2-4b — свод save-блоков `home_builder_view` (план до кода, 2026-07-08)

> **РЕШЕНИЕ 2026-07-08: WONT-FIX (владелец: «Пропустить → SEO v2»).** После
> сквозного чтения `home_builder_view` подтверждено: код УЖЕ чистый (action-ветки —
> аккуратные early-return с комментариями; форм-save — линейная комментированная
> последовательность; presence-guard'ы по 3-6 строк). «Свод» = перенос чистого кода
> в хелперы/реестр = чурн на критичной вьюхе с риском регрессии (тихо сломать guard →
> затереть конфиг) при ~нулевой пользе и нулевой пользовательской ценности. Ценная
> половина UC2-4 (инлайн-JSON-диспетчер) уже сделана. План ниже сохранён на случай,
> если структура вьюхи реально усложнится в будущем. **UC2-4 закрыт целиком.**

Вторая половина UC2-4 (первая — инлайн-JSON-диспетчер — ✅ `apps/core/inline_edit.py`).
Отложена планом uc2-4 как «form-driven POST, отдельным решением». Владелец: делаем
(«Оба + save-блоки», 2026-07-08). **Это ЧИСТЫЙ рефактор: 0 пользовательской ценности,
реальный риск регрессии.** Поэтому — characterization-first.

## 1. Что сводим (карта `home_builder_view`, apps/core/views.py:926+)

**A) Action-ветки (ранний return → хелпер → redirect), ~15:**
upload_gallery, delete_gallery_image, upload_logo, delete_logo, save_hero_slide,
delete_hero_slide, move_hero_slide, upload_cover_hero, add_block,
save_block_template:/use_block_template:/delete_block_template:, save_version,
add_category, save_page_template. Уже почти чистые (каждая зовёт `_helper` + redirect).
→ **Свод:** таблица `ACTION_HANDLERS = {"upload_gallery": _upload_gallery_images, …}`
+ префиксные (`save_block_template:` → partition). Простые — прямой вызов+redirect;
сложные (add_block/шаблоны с fetch-ответом) остаются отдельными (в таблицу как call-,
возвращающие HttpResponse). Никакой смены поведения — только диспетч вместо лестницы if.

**B) Presence-guard merge-ветки (fall-through, строят cfg → normalize → save), ~8:**
| guard | область | семантика |
|---|---|---|
| (форма секций) | sections order/enabled/width/source/limit/title/view_all | всегда (главная) |
| `pb_present=1` | page_blocks[host] | UC6-7 |
| `cf_present` (catalog) | категория: фильтры/сорт/подкатегории | presence |
| `cart_present` (catalog) | корзина: кросс-селл | presence |
| `pd_present` (catalog) | product detail: скрытие секций | presence |
| `sd_present` (booking) | service detail | presence |
| `std_present` (stays) | stay detail | presence |
| банер SE-7d / nav | hero-заголовок/текст, nav_style/sticky | `nav_style in POST` |
→ **Свод:** каждая ветка → `_merge_<area>(post, cfg, tenant) -> cfg` (no-op при
отсутствии guard); реестр `MERGE_STEPS = [_merge_sections, _merge_page_blocks,
_merge_category_filters, _merge_cart, _merge_detail_pd/sd/std, _merge_banner, _merge_nav]`;
цикл `for step in MERGE_STEPS: cfg = step(...)` → один `normalize`+`save` в конце (как сейчас).
Module-активность (`is_module_active`) — внутри соответствующего step (1:1).

## 2. Порядок безопасности (characterization-first — ОБЯЗАТЕЛЬНО)
1. **Инвентаризация покрытия:** `test_home_builder.py` уже ~40 тестов (sections/layout/
   width/source/title/view_all/page_blocks/hero/logo/gallery/covers/version/category).
   Свести матрицу «ветка → тест». Дырки (cf_present, cart_present, pd/sd/std_present,
   banner-tagline, nav_style-save) — дописать характеризационные тесты ДО рефактора.
2. **Рефактор А (ACTION_HANDLERS)** — отдельный коммит, тесты зелёные.
3. **Рефактор B (MERGE_STEPS)** — отдельный коммит, тесты зелёные. Каждый step —
   pure `(post,cfg)->cfg`, легко юнит-тестится.
4. Гейт: полный `apps/core` + `apps/tenants` (секции главной рендерят карточки —
   урок CI 1145) + template-comments; ruff; CI зелёный; FF-merge.

## 3. Границы
- НЕ меняем сохраняемую форму данных (site_config-схему), URL, шаблоны билдера.
- НЕ трогаем `site_inline_edit`/`site_preview_draft`/`_cblock_entry_from_post` (другой слой).
- Onboarding-ветки (apply_template/load_demo/clear_demo/demo_start) — в `wizard`-вьюхе,
  НЕ в home_builder_view (разные функции); не сюда.
- Если хоть одна ветка не покрывается тестом и поведение неочевидно — сначала тест,
  потом трогаем.

## 4. Оценка/риск
Средний-крупный, чисто-внутренний. Выигрыш: читаемость 500-строчного POST →
две таблицы. Риск: тихо сломать presence-guard (POST без формы затрёт конфиг) —
митигируется characterization-тестами на «POST без guard НЕ меняет область».
