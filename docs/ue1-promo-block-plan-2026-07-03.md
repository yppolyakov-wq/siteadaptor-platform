# UE1 + UE4-1 — промо-блок на канве главной + промо-шаблоны (план, 2026-07-03)

Порядок владельца (2026-07-03): UE1+UE4-1 → правовой-языковой пакет. Источник
спек — `unified-sellable-entity-ue-plan-2026-06-30.md` (UE1-1/1-2/1-3, UE4-1);
решения: **D1 slots-first** (не свободная канва), **D2 LIVE** (`promo_pk` из БД,
fail-safe скрытие неактивной промо — цена/остаток/countdown всегда актуальны).

## 1. Контекст (что уже есть)

- C-блоки: `REPEATABLE_BLOCKS = (text, image, image_text, button, spacer)`;
  санитизация `_clean_cblock_data`; рендер `CBLOCK_TEMPLATES` → партиалы;
  хостятся ТОЛЬКО на главной (`config["sections"]`) — промо-блок автоматически
  наследует это ограничение (вне home — за отложенным решением per-page).
- `_discount_display.html` (UE2-1/2-2) — весь вывод скидки, включая
  `discount_style`; `_promo_card.html` — референс разметки бейджей.
- `block_templates` гейтится `REPEATABLE_BLOCKS` → UE4-1 после UE1-1 почти
  автоматичен (проверить санитизацию data в шаблоне + инсертер).
- Инлайн-механика промо на канве уже есть (UE3: цены/%/срок/фото) — внутри
  блока LIVE-промо она работает бесплатно (те же data-атрибуты).

## 2. Схема данных блока (UE1-1, БЕЗ миграции — JSON в block.data)

```
{"promo_pk": "<uuid>",              # LIVE-источник (D2); пусто → блок скрыт
 "align": "left|center|right",      # текст-оверлей (пресет)
 "badge_pos": "top-left|top-right|bottom-left|bottom-right|none",
 "show_button": bool, "button_label": str<=40,   # CTA → /p/<pk>/
 "visual": {radius, shadow, padding, background}} # реюз VISUAL-пресетов секций
```
`discount_style` НЕ дублируем в блоке — источник ЕДИН: `Promotion.discount_style`
(UE2-2), блок рендерит через `_discount_display`. Санитизация: promo_pk —
строка-UUID (без DB-запроса в normalize — purge-safe), пресеты по белым
спискам, мусор → дефолт.

## 3. Слайсы

- **A (UE1-1):** `promo` в `REPEATABLE_BLOCKS` + ветка `_clean_cblock_data`
  (+`CBLOCK_TEMPLATES["promo"]`). Замки: golden normalize (5 легаси-типов
  байт-в-байт), санитизация промо-данных, `_MAX_CBLOCKS`.
- **B (UE1-2):** `templates/storefront/sections/_block_promo.html`: LIVE-промо по
  promo_pk (fail-safe: не найдена/не active → блок пуст), фон = фото промо
  (примари/фолбэк товара), оверлей title+цена (`_discount_display` price/badge
  по badge_pos), CTA-кнопка → `/p/<pk>/`, visual-пресеты CSS-переменными,
  мобайл-стек. data-атрибуты UE3 (инлайн цены/фото) внутри работают.
- **C (UE1-3, ⚠️ горячее — мерж по diff):** инспектор блока в билдере
  (селектор промо из активных + align/badge_pos/button) + промо-поля в
  `collect()` (ловушка: не забыть сериализацию, иначе выпадут из драфта) +
  инсертер «+» уже generic для REPEATABLE_BLOCKS (проверить). Round-trip
  collect→draft→save. Тест `test_promo_block_roundtrip`.
- **D (UE4-1):** промо-блок как block_template: сохранить/вставить (реюз
  SE-4a UI); проверить санитизацию `data` в шаблоне (тот же `_clean_cblock`),
  `_MAX=50`. Тест в `test_home_builder` (`key='promo'`).

## 4. Границы/риски

- Анти-оверселл: блок ЧИТАЕТ промо (LIVE), никогда не пишет; статус/остаток —
  только отображение. Неактивная промо → fail-safe скрытие (пустой блок, не
  сломанная карточка).
- normalize НЕ ходит в БД (promo_pk — просто строка); существование промо
  проверяет рендер.
- Golden-замки normalize — обязательный гейт слайса A; legacy C-блоки
  байт-в-байт.
