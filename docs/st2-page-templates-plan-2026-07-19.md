# ST-2 «Шаблоны всех страниц» — план (2026-07-19)

ТЗ (`next-gen-master-tz-2026-07-19.md` §3 B4): довести пикеры уровня L2 (Page)
до всех `page_types()`: меню/контакт/корзина/тексты + листинги услуг/номеров/
событий (те же `LAYOUT_PRESETS`), по 3–5 вариантов, фильтр по архетипу; выбор —
в Studio (page-лента ST-3b) и в мастере. Хранение (концепт Studio §3): ТОЛЬКО
существующие ключи (`page_templates`, `catalog_layout`, `<module>_detail`,
`page_blocks`, `sections`) — **новых top-level ключей normalize НЕ вводим**
(golden-риск ноль). Без миграций.

## §1 Матрица «страница × что есть × что делает ST-2» (разведка 2026-07-19)

| Страница | Ключи | Пикер сейчас | ST-2 |
|---|---|---|---|
| Главная | `sections`, `page_templates` | галерея шаблонов + Look (ST-1b) | — (есть) |
| Листинг каталога | `catalog_layout` | `catalog_preset` (LAYOUT_PRESETS, SE-7b диаграммы) | — (есть) |
| Листинги услуг/номеров/событий | `service/stay/events_index_layout` | **уже есть** — `service/stay/events_preset` в fieldset «Landing pages» + «Apply to all» (site_home.html:543-611) | пункт ТЗ фактически закрыт прежними волнами; довесок — мастер (§5) |
| Деталь (4 вида) | `<module>_detail`, `site_defaults` | пресеты карточек + скрытие секций (AB6.10 слайд `detail`, инспектор) | — (есть) |
| Меню/шапка | `nav.style/sticky` | 3 пресета Classic/Centered/Minimal с мокапами (UC6-6h, site_home.html:812-837) + слайд `menu` мастера | — (есть, 3 варианта = норма ТЗ) |
| «О нас» (info) | `page_blocks["info"]` | `_ABOUT_PRESETS` (4) — но ТОЛЬКО в мастере (setup_steps.py:388-512) | **пикер и в билдере/Studio** (§3), реестр — в общий модуль (§2) |
| Корзина | `cart_show_upsell`, `cart_*`-тексты, host `cart` | только чекбокс upsell | **3 пресета** (§4) |
| Контакт | секция `contact` главной (data-driven) | нет | **стили секции через SECTION_STYLES** (§4) |
| Право (legal) | LegalDoc | — | вне объёма (юридический текст ≠ раскладка) |

Вывод разведки: универсальный механизм «пресет НЕ-home страницы» уже есть —
идемпотентная замена C-блоков `page_blocks[host]` по префиксу id
(`_ABOUT_PRESETS`, префикс `pb-about-*`, блоки владельца сохраняются). ST-2 =
обобщить его в реестр + дотянуть до корзины/контакта + выбор из билдера.

## §2 ST-2a — реестр PAGE_PRESETS + generic-апплаер

Новый модуль **`apps/core/page_presets.py`**:

```python
PAGE_PRESETS = {
  "info": [ {id, label, hint, prefix="pb-about-", blocks=[...],
             flat={}, recommended_for=()} , ×4 ],   # переезд _ABOUT_PRESETS
  "cart": [ ×3 ],                                    # §4
}
def presets_for(host, business_type) -> list  # recommended первыми (паттерн template_cards)
def apply_page_preset(cfg, host, preset_id)   # идемпотентно: keep чужие блоки,
                                              # replace только blocks с префиксом
                                              # пресет-семейства; + flat-ключи
def current_preset(cfg, host) -> str          # по префиксу id (паттерн _ctx_about)
```

- Правила: только whitelist `PAGE_BLOCK_HOSTS`-хостов + flat-ключи из
  существующего normalize (напр. `cart_show_upsell`); кап `_MAX_CBLOCKS=30` не
  превышать (пресеты ≤ 4 блоков); `page_blocks` остаётся presence-minimal.
- `setup_steps._post_about/_ctx_about` делегируют реестру (поведение байт-в-байт,
  префикс `pb-about-` сохранён — совместимость с уже засеянными конфигами).
- POST-приёмник в `home_builder_view` (паттерн `use_page_template:`):
  `action=use_page_preset:<host>:<id>` → normalize → apply → save → redirect
  `?page=` обратно (страница остаётся в канве).
- Замки: идемпотентность повторного применения; блоки владельца целы; golden
  не тронуты; about-слайд мастера рендерит те же пресеты (паритет).

## §3 ST-2b — пикер в билдере/Studio

- Строки пикера в панели билдера: карточки пресетов (label+hint, актив
  подсвечен `current_preset`) в scoped-области соответствующей страницы —
  «О нас» и «Корзина» как `.page-block[data-page-key="info"|"cart"]` в
  fieldset «Landing pages» (cart-строка уже существует — дополняется).
- Studio-путь: чип page-ленты ST-3b → `?page=` → авто-скоуп панели по
  `PAGE_GROUPS` (уже работает) → видна строка пикера. Проверить маппинг группы
  `text` → `data-page-key="info"` в `applyPageScope` (views.py:1820,
  site_home.html:2199) — при необходимости дополнить соответствие.
- classic_ui: пикер живёт в ОБЫЧНОЙ панели (не в ST-рейке) → доступен и в
  классик-виде; Studio лишь добавляет путь через ленту. Железное правило §8b
  соблюдено без дубля.
- Применение — форм-POST с перезагрузкой (как about-слайд); живой draft-канал
  пресетов страниц — не в v1.

## §4 Содержимое новых пресетов (3–5 вариантов, DE-контент как C-блоки)

- **Корзина** (`cart`, префикс `pb-cart-`):
  1. «Schlicht» — без блоков, upsell выкл;
  2. «Mit Empfehlungen» — upsell вкл (флат-ключ);
  3. «Vertrauen» — upsell вкл + C-блок trust-текста (Abholung/Zahlarten-Hinweis)
     + C-блок note («Fragen? Rufen Sie uns an») из `CBLOCK_DEMO_DATA`-паттерна.
- **Контакт** — НЕ page_blocks (секция data-driven): `SECTION_STYLES["contact"]
  = ("split", "compact", "map_first")` + варианты в
  `templates/storefront/sections/_contact.html` (`section_row`-переключение,
  паттерн UC6-6f gallery; "" = текущий вид) + `SECTION_STYLE_LABELS` (+3 DE).
  Выбор — существующий селект стилей секции в инспекторе → «контакт: 4 варианта».
- **Меню**: уже 3 пресета UC6-6h — новых не делаем (ТЗ-норма «3–5» выполнена).

## §5 ST-2c — мастер

- Слайд `category` (раскладка каталога): чекбокс «Für alle Listen übernehmen»
  — выбранный `LAYOUT_PRESETS`-пресет пишется и в `events/stay/service_index_layout`
  (только для активных модулей; семантика «Standard = удалить ключ» для
  service сохранена). Зеркало кнопки «Apply to all» билдера.
- Слайды `menu`/`about`/`detail` уже дают пресеты — без изменений.
- Корзина в мастер не идёт (второстепенно при онбординге; Studio-only v1).

## §6 Риски / инварианты

- `page_templates` НЕ трогаем вообще (материализуется всегда — любое изменение
  формы ломает `normalize_rich_home.json`).
- `page_blocks` presence-minimal; `service_index_layout` «Standard = pop»
  (site_home/views.py:1429-1432) — семантика сохраняется в мастере §5.
- `apply_page_payload`/`PAGE_CONFIG_KEYS` не расширяются (новых per-page плоских
  ключей нет) → замок test_page_registry:120 цел.
- Контакт-стили: секция рендерится только при заполненных контактах — стили
  не должны ломать пустой случай (гейт остаётся снаружи вариантов).
- i18n: новые лейблы пикеров — немецкие msgid + переводы en/tr/ru/uk .po.

## §7 Инкременты (батч-конвенция: локальные гейты → push → CI → FF-merge)

1. **ST-2a** реестр + апплаер + POST-приёмник + делегация about + тесты.
2. **ST-2b** пикер в панели (info/cart) + cart-пресеты + скоуп-проверка + тесты.
3. **ST-2c** контакт-стили SECTION_STYLES + мастер «für alle Listen» + i18n + докблок
   (build-log, CLAUDE.md, task-catalog, маркер ✅ в ТЗ).
