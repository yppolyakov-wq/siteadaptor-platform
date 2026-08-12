# План DS-5 «Сеточные контролы Studio» (2026-08-12)

Запрос владельца: количество плиток задавать произвольно (5/6/10), автоматически
их симметрировать (центрировать неполный ряд), выбирать что выводить в плитке,
опция горизонтального скролла при многих плитках (15), настройка размера
картинок категорий на главной (высота). Всё — в Studio.

## Оси (всё presence-minimal, кроме limit категорий)

1. **Колонки до 6** (было ≤5): `_clamp` cols 1..6 + `_GRID_LG[6]` +
   `_SM_FROM_COLS[6]=3`; input в панели max=6. (>6 колонок на десктопе —
   нечитаемо; «10 плиток» решает Anzahl + скролл/симметрия.)
2. **Anzahl для категорий**: `GRID_SECTION_LIMITS += categories: 8` → появляется
   штатный инпут «Anzahl» билдера; `_SECTION_LIMIT_MAX` 24→30.
   ⚠️ limit-ключ материализуется на categories-строке → осознанная golden-реген.
3. **Симметрия** `layout.balance` (bool, ключ только при True): grid_class_string
   → `sf-balance-grid sf-bal-<cols> + gap` (flex-wrap justify-center, ширина
   ~100%/cols; неполный последний ряд центрируется). CSS-правила в input.css.
4. **Скролл** `layout.scroll` (bool): grid_class_string → `sf-scroll-grid + gap`
   (flex, overflow-x, snap; ширина плитки 15rem дефолт через --sf-tile-w).
   scroll побеждает balance. Работает у ВСЕХ секций-сеток (класс генерится
   централизованно — шаблоны не трогаем).
5. **Инфо в плитке категории** `tile_info` ⊆ {price, count} на строке секции:
   «ab X €» (Min base_price) и/или «N Produkte» под названием
   (расширение categories_with_min_price до цены+счётчика одним проходом).
6. **Высота картинки категорий** `img_h` (0=аспект по стилю; 80..480 px):
   инлайн height вместо aspect-класса — только секция главной
   (страница /sortiment/ остаётся на аспектах).

## Studio-панель (строка секции-сетки)

cols max 6 · чипы «Zentriert ausgleichen» (balance_{key}) / «Horizontal
scrollen» (scroll_{key}) · для categories: «Bildhöhe (px)» + чекбоксы
«ab-Preis» / «Anzahl Produkte». Save: layout собирается из POST заново
(чекбокс не прислан = off — presence-семантика бесплатно); categories-extras —
в строку секции (normalize клампит/whitelist'ит). Live-draft: JS-коллектор
секций дополняется новыми полями (normalize на драфт-пути уже валидирует).

## Замки

normalize (cols=6 держится, 7 клампится; balance/scroll presence; tile_info
whitelist; img_h кламп; categories limit) · рендер (limit=15 у категорий
уважается; sf-scroll-grid/sf-balance-grid в классах; img_h инлайн; ab-цена и
счётчик в плитке) · характеризация (без новых ключей — прежние классы грида
байт-в-байт). Golden: +limit у categories (реген с indent=1).
