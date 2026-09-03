# DL-19 — формы карточки товара/акции: реестр, per-объект выбор, превью в Studio

**Дата:** 2026-09-03 · **Ветка:** `claude/aktionsmarkt-analysis-45t2vu` · **Статус:** план

## 1. Запрос владельца (дословно)

> «Делаем все 3 плюс запасные и добавляем настройку вид карточки товара и там выбор из
> вариантов и предпросмотр. Можно в карточке акции / товара выбрать только для этого товара
> или в общих настройках задать для всех. Если в карточке выбираем то оно приоритетнее для
> этого товара. Применяем с учетом стиля сайта»

Разбор на требования:

| № | Требование | Инкремент |
|---|---|---|
| R1 | 3 макета канваса (N1 Regal · N2 Lookbook · N3 Deal-Kachel) — в код | 19.2 / 19.3 |
| R2 | «Запасные» из анализа DL-16: AK2 Coupon · AK3 Countdown-Ring | 19.3 |
| R3 | Настройка «вид карточки» с ВЫБОРОМ ИЗ ВАРИАНТОВ и ПРЕДПРОСМОТРОМ | 19.4 |
| R4 | Выбор в карточке товара/акции (per-объект) ИЛИ в общих настройках (весь сайт) | 19.1 + 19.5 |
| R5 | Свой у объекта — **приоритетнее** общего | 19.1 (резолвер) |
| R6 | Формы уважают стиль сайта (Look/акцент/хром/фон) | сквозной инвариант |

## 2. Что есть сегодня (разведка 2026-09-03, факты)

- **Формы товара** живут ветками в `templates/storefront/_product_card.html`:
  `compact` (:5) · `overlay` (:55) · default `""`+`etikett` (:113–209).
- **Формы акции** — `templates/storefront/_promo_card.html`: `preis` (:4, гейт `and not wide`)
  и прежняя (:67).
- **Значения** валидируются ХАРДКОДОМ в `siteconfig.normalize_site_defaults`
  (`card_style ∈ (overlay, compact, etikett)` :1269; `promo_card ∈ (preis,)` :1272), а тот же
  список продублирован в `demo_kits.py:11608/11612`, `sitetemplates.apply_preview_bundle:1765`,
  `core/views.py:1828/1834` и в `<option>` шаблона Studio.
- **Per-объект переопределения формы карточки НЕТ.** Прецеденты такого механизма в проекте:
  `Product.variant_style` (`option_styles.variant_style(product, site_default)`) и
  `Category.page_style` (`category_styles`) — «свой у объекта → дефолт сайта → ""».
- **Контекст** уже draft-aware: `storefront_card_style` (`context.py:502`) и
  `storefront_promo_card` (:509) читаются из уже собранного `cfg` (черновик/Look-оверлей внутри),
  поэтому новые значения проходят без правок процессора.
- **Look-слой** (`static/src/app.css:400+`) цепляется за `.bg-red-600.text-white.rounded-full`
  (бейдж) и `.font-extrabold.text-red-600` (цена). Карточка ТОВАРА сегодня использует
  `rose-600` → Look её не перекрашивает. **Новые формы обязаны брать `red-600`-крючки**
  (это и есть R6), прежние ветки не трогаем (паритет).

### Замки, которые ограничивают манёвр

| Замок | Что фиксирует | Следствие для нас |
|---|---|---|
| `tenants/test_card_style.py` | `""` рендерит прежнюю разметку; overlay/compact — свои маркеры | новые ветки не должны менять `""` |
| `tenants/test_dl16_cards.py` | `preis`-форма, `etikett`, presence-minimal ключей | расширяем набор значений, семантику не меняем |
| `core/test_grid_view.py:76-82` | режет overlay-ветку срезом `body[index('overlay') : rindex("{% else %}")]` | **новые ветки — ТОЛЬКО ВЫШЕ `compact`**, иначе замок ловит чужую разметку |
| `promotions/test_discount_display_parity.py` | классы бейджа/цены байт-в-байт | новые формы зовут те же `part`-партиалы |
| `core/test_dl17_studio.py` | строки payload live-draft (`card_style: sdStyle ? …`) | имя поля `sd_card_style` СОХРАНЯЕМ, меняем только тип контрола |

## 3. Решения (архитектура)

### 3.1 Единый реестр форм — новый `apps/core/card_forms.py`

Данные без импорта моделей (его читают catalog, promotions, core-Studio, tenants):

```python
CARD_FORMS = [
    # (ключ, подпись, подсказка «когда уместно», виды сущностей)
    ("",         _("Standard"),        …, ("product", "promo")),
    ("overlay",  _("Text on photo"),   …, ("product",)),
    ("compact",  _("Compact row"),     …, ("product",)),
    ("etikett",  _("Price tag"),       …, ("product",)),
    ("preis",    _("Price first"),     …, ("promo",)),
    ("regal",    _("Shelf label"),     …, ("product", "promo")),   # N1
    ("lookbook", _("Lookbook"),        …, ("product", "promo")),   # N2
    ("deal",     _("Deal tile"),       …, ("product", "promo")),   # N3
    ("coupon",   _("Coupon"),          …, ("promo",)),             # AK2
    ("ring",     _("Countdown ring"),  …, ("promo",)),             # AK3
]

forms_for(kind)  -> [(key, label, hint), …]      # для форм кабинета и Studio
keys_for(kind)   -> frozenset                     # для normalize / китов / сборок
card_form(entity, site_default="", kind="product") -> str
```

`card_form` = R5: `own = getattr(entity, "card_style", "")`; свой при валидности побеждает,
иначе дефолт сайта, мусор → `""` (никогда не 500 — правило `option_styles`).

Реестр становится ЕДИНСТВЕННЫМ источником допустимых значений: `normalize_site_defaults`,
`demo_kits`, `apply_preview_bundle` переходят на `keys_for(...)` (сегодня три копии списка).

### 3.2 Per-объект поля (⚠️ две аддитивные миграции)

- `Product.card_style` — `CharField(max_length=16, blank=True, default="")`, `catalog/0032`.
- `Promotion.card_style` — то же, `promotions/0027`.

Choices живут в ФОРМЕ (прецедент `Category.page_style`, `Product.variant_style`) — реестр
может расти без миграций. Пусто = «как в настройках сайта».

### 3.3 Резолв в шаблоне

Два фильтра в `apps/core/templatetags/siteui.py`:
`{{ p|product_card_form:storefront_card_style }}` и `{{ p|promo_card_form:storefront_promo_card }}`.
В начале каждого партиала — `{% with cs=... %}`, дальше ветвление по `cs`, а НЕ по
`storefront_card_style`. Стабы-SimpleNamespace секций главной без `card_style` работают
(`getattr` с фолбэком).

Паритет: у объекта без своего значения `cs == storefront_card_style` → прежний рендер
байт-в-байт.

### 3.4 Разметка форм

Новые ветки — отдельными партиалами `templates/storefront/cards/_*.html`, включаются
**ДО** ветки `compact` (ограничение замка `test_grid_view`):

| Партиал | Что | Крючки Look |
|---|---|---|
| `cards/_product_regal.html` | фото-квадрат 96px слева, плашка цены справа (крупная цена, старая зачёркнутая, Grundpreis, «Sie sparen») | цена `font-extrabold text-red-600`, бейдж `bg-red-600 text-white rounded-full` |
| `cards/_product_lookbook.html` | кадр 3:4 без хрома, тихая подпись под ним | `sf-card` без тени (наследует `--sf-*`) |
| `cards/_product_deal.html` | широкая строка: фото, название, цена+выгода, условие, кнопка | те же крючки |
| `cards/_promo_regal.html` | то же для акции (плашка + `part="grundpreis"/"savings"`) | `_discount_display` |
| `cards/_promo_lookbook.html` | кадр 3:4 + подпись + цена | `_discount_display` |
| `cards/_promo_deal.html` | широкая плитка: цена, выгода, условие (`part="flags"`), срок (`part="countdown"`), кнопка | `_discount_display` |
| `cards/_promo_coupon.html` | пунктирная рамка + вырезы + номинал + «Sichern» | `_discount_display` |
| `cards/_promo_ring.html` | кольцо остатка времени поверх фото (`conic-gradient` по `Promotion.time_left_pct`) | `_discount_display` |

Общие части (сердечко, кнопки канвы ✎/📷, quick-add, PAngV-строка, `data-edit-*`) в новых
формах ТЕ ЖЕ — иначе на канве редактора форма перестанет редактироваться.

`Promotion.time_left_pct` — свойство модели (доля оставшегося окна 0..100), без миграции.

### 3.5 Studio: выбор вариантов с предпросмотром (R3)

`<select name="sd_card_style">` и `<select name="sd_promo_card">` заменяются на **плитки-варианты**
(прецедент `setup/_step_detail.html` и `variantThumb`): мини-макет формы, нарисованный див-ами,
+ подпись + подсказка; значение держит `<input type="hidden" name="sd_card_style">` — имена полей
и payload live-draft НЕ меняются (замки `test_dl17_studio` целы), меняются только 3 селектора
в JS (`select[name=…]` → `[name=…]`).

### 3.6 Кабинет: выбор для одного товара/акции (R4)

- Форма товара — вкладка **Marketing** рядом с `badge`/`variant_style` (`product_form.html:141`).
- Форма акции — панель **Anzeige** (`promotion_form.html:108`), рядом с `show_countdown`.
- Подпись обеих: «Leer = wie in den Website-Einstellungen».

## 4. Инкременты

| # | Название | Миграции | Гейт |
|---|---|---|---|
| 19.1 | Реестр `card_forms` + резолвер + поля моделей + фильтры + свод хардкодов | `catalog/0032`, `promotions/0027` | замки приоритета/паритета/presence-minimal |
| 19.2 | Формы товара: regal · lookbook · deal | — | рендер-замки + паритет `""` |
| 19.3 | Формы акции: regal · lookbook · deal · coupon · ring | — | рендер-замки + `wide`-гейт |
| 19.4 | Studio: плитки-варианты с предпросмотром + live-draft | — | `test_dl17_studio` + новые |
| 19.5 | Кабинет: per-товар и per-акция | — | форма сохраняет/чистит значение |
| 19.6 | Демо-потребители + стенд Playwright + доки/msgid | — | broad-прогон |

## 5. Инварианты волны

1. `""` в обеих карточках — прежняя разметка байт-в-байт (замки написаны ДО правок).
2. Ключи `card_style`/`promo_card` остаются presence-minimal → golden-эталоны целы.
3. Значение объекта побеждает дефолт сайта; мусор в любом слое → `""`, не 500.
4. Новые формы берут `red-600`-крючки Look'а, `sf-card`, `--accent`, `data-sf-media-box` —
   «применяем с учётом стиля сайта» проверяется стендом на нескольких Look'ах.
5. Новые ветки — только ВЫШЕ `compact` (замок `test_grid_view` режет по `rindex("{% else %}")`).
6. `_sellable_card.html` (услуги/номера) в v1 не расширяем — там нет цены-первой семантики;
   ограничение названо явно.
