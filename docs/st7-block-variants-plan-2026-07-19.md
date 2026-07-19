# ST-7 «Блоки: 10 видов» — план (2026-07-19)

ТЗ (`next-gen-master-tz-2026-07-19.md` §3 D3): дозаполнить CBLOCK_VARIANTS/
SECTION_STYLES + архетипные варианты карточек. Разведка (Explore, 2026-07-19):
**CBLOCK_VARIANTS уже ≥10 на все 5 наполняемых типов** (text/image/image_text/
button/promo — закрыто UC6-8, замок test_cblocks:304 зелёный; ТЗ-пункт писался
до этого). Честный остаток волны — ниже. Без миграций.

## §1 Факты разведки

- Инсертер data-driven: новые варианты в реестре появляются в UI автоматически
  (variantThumb рисует по известным осям w/pos/align/color/side/rounded/shadow/
  bg/hint; НОВАЯ ось миниатюру не нарисует без правки JS).
- spacer — единственный тип с 0 вариантов: рендер высоты не умеет (нет data) —
  нужна маленькая новая механика (поле height + шаблон).
- SECTION_STYLES: 7 секций по 4-5 видов; НЕ стилизованы простые секции about/
  cta/usp_bar/reviews (каждый стиль = ветка шаблона + CSS, не данные).
  Замок test_team_trust_five_styles_registry жёстко ждёт len==4 у team/trust.
- «Карточка пекарни ≠ карточка салона»: числовые оси (radius/shadow/bg/padding
  через --sf-* и Look-семейства) есть, оси ФОРМЫ карточки нет — sellable_card
  ветвится только horizontal/vertical, _product_card жёсткий. Единственная
  настоящая новая механика волны.

## §2 ST-7a — spacer-варианты (высота)

- `_clean_cblock_data`: spacer += `height` ∈ {"", "sm", "lg", "xl"} ("" = py-6
  как сейчас — presence-minimal, golden целы).
- `_block_spacer.html`: py-2/py-6/py-12/py-20 по height; `CBLOCK_VARIANTS`
  ["spacer"] = 4 варианта (Schmal/Standard/Groß/Sehr groß) — замок «10 на тип»
  spacer не требует (не в списке замка), вариантов честно 4.
- Инсертер: variantThumb — фолбэк-миниатюра (полоса переменной высоты) — мелкая
  правка JS с гейтом по типу.

## §3 ST-7b — стили простых секций (cta / about / usp_bar / reviews)

- `SECTION_STYLES` += `cta: (band, card, minimal)` · `about: (card, wide,
  quote)` · `usp_bar: (cards, plain, compact)` · `reviews: (quotes, list,
  single)` (reviews переиспользует ветки testimonials — те же классы).
- Ветки в партиалах секций ("" = текущий вид), лейблы в SECTION_STYLE_LABELS
  (реюз существующих ключей, новые — только недостающие).
- Замки: рендер-тесты по паттерну test_gallery_team_trust_styles_render;
  style-валидация генерическая (test_section_style_validated_by_registry).
  test_team_trust... НЕ трогаем (team/trust не меняем).

## §4 ST-7c — ось формы карточки `card_style` (архетипные карточки)

v1 — минимальная честная ось на витринных карточках:
- `site_defaults` += `card_style` ∈ {"", "overlay", "compact"} (presence-
  minimal в normalize_site_defaults; "" = текущая форма). overlay — заголовок/
  цена поверх фото (журнальный вид, салоны/отели); compact — узкая строка
  фото-слева (пекарни-прайс, ритейл-списки).
- Рендер: `_sellable_card.html` + `_product_card.html` — ветки по
  `site.site_defaults.card_style` (стиль ГЛОБАЛЕН для витрины — как прочие
  site_defaults; пер-секционного оверрайда в v1 нет).
- Билдер: селект «Kartenform» рядом с числовыми осями карточек (область Тема);
  живой draft-канал — как прочие site_defaults (паттерн ST-1b).
- Look-семейства/архетипы: `LOOK_FAMILIES`/`ARCHETYPE_LOOK_ACCENTS` могут
  задавать card_style (warm→"", nacht→overlay напр.) — ОСТОРОЖНО: apply_look
  идемпотентность + замок 42 Look'ов; в v1 Look'и card_style НЕ трогают
  (отдельное решение), ось доступна вручную и мастеру detail-слайда.
- Замки: round-trip normalize, golden (ключ presence-minimal), рендер обеих
  форм, паритет «"" = байт-в-байт текущая разметка» (характеризационный тест
  ДО правки шаблона).

## §5 Риски

- Golden: только presence-minimal ключи (height/card_style); стили секций —
  шаблоны, конфиг не трогают.
- CSS: только статичные Tailwind-классы + пересборка app.css.
- variantThumb: правка JS только для spacer-фолбэка (гейт по типу).
- `_cb_row.html`: visual-ленту для spacer НЕ включаем (незачем).
- Карточный паритет: "" ветка обязана рендерить БАЙТ-В-БАЙТ текущую разметку
  (характеризационные замки до правок — паттерн UB1-3).

## §6 Инкременты

1. **ST-7a** spacer (данные+шаблон+реестр+thumb-фолбэк+тесты).
2. **ST-7b** стили cta/about/usp_bar/reviews (+рендер-тесты, CSS-пересборка).
3. **ST-7c** card_style (нормализация+2 шаблона+селект билдера+draft-канал+
   паритет-замки) + докблок + i18n.
