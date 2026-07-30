# Первый экран для ВСЕХ архетипов: слайдер + плитки направлений (2026-07-30)

Продолжение фидбэка владельца «главная должна ловить направления» (сделано для
bakery / butcher / mode / гастро). Осталось 8 демо-китов без первого экрана:
`friseur`, `werkstatt`, `handwerker`, `shop`, `aktionsmarkt`, `touren`,
`retreat`, `pranasy` (+ у 10 китов нет слайдера `heroes`).

## Проблема подхода «ещё одна ветка в шаблоне»
`sections/_hero_widget.html` уже несёт 5 хардкод-веток (stays / gastro /
bakery+butcher / mode / services). Ещё 7 веток = ~250 строк дублирующейся
вёрстки и 7 мест, где легко разойтись гейтам. При этом сами ветки различаются
ТОЛЬКО данными: иконка, подпись, подподпись, url, гейт модуля.

## Решение: реестр плиток в Python + один generic-цикл
- **НОВЫЙ `apps/core/hero_tiles.py`** — `HERO_TILE_SETS = {widget: [tile, …]}`.
  Плитка: `icon`, `label`, `sub`, `url` (url_name), `query`, `gate`.
  `gate` ∈ `""` (всегда) | ключ модуля (`booking`/`orders`/`jobs`/`events`/
  `stays`/`gift`/`loyalty`) | `"deal"` (живая акция, иначе плитки нет).
  Плитка с `deal_sub=True` подставляет заголовок акции в подподпись.
  Резолвер `tiles_for(widget, tenant, deal=None)`: гейты + `reverse()` с
  `NoReverseMatch` → плитка выпадает (fail-safe, как `_reverse` в
  `sellable_manage`). Неизвестный widget → `[]`.
- **`{% hero_tiles %}`** (inclusion_tag, takes_context) → новый партиал
  `sections/_hero_tiles.html` — один цикл, вёрстка 1:1 с существующими
  плитками bakery/mode (белая карточка, ring-amber у deal-плитки).
- **`_hero_widget.html`**: генерик подключается ВЕТКОЙ `{% else %}` — он
  самогейтящийся (пустой список → партиал ничего не рендерит), поэтому
  существующие 5 веток и их замки не трогаются.

## Наборы плиток (по активным модулям китов)
| widget | плитки (гейт) |
|---|---|
| friseur | Termin buchen (booking) · Aktionen (deal) · Pflegeprodukte (orders) · Gutschein (gift) |
| werkstatt | Termin vereinbaren (booking) · Kostenvoranschlag (jobs) · Teile & Zubehör (orders) · Aktionen (deal) |
| handwerker | Angebot anfordern (jobs) · Termin vereinbaren (booking) · Rückruf (—) · Aktionen (deal) |
| shop | Aktionen (deal) · Sortiment (—) · Zur Wunschzeit vorbestellen (orders) · Treuepunkte (loyalty) |
| aktionsmarkt | Aktuelle Deals (—, sub из акции) · Sortiment (—) · Treuepunkte (loyalty) · Newsletter (—) |
| touren | Touren & Termine (events) · Private Führung (booking) · Gutschein (gift) · Aktionen (deal) |
| retreat | Retreats & Kurse (events) · Unterkunft (stays) · Einzeltermin (booking) · Anfrage (jobs) |
| pranasy | — переиспользуем существующий `gastro` (ресторан без booking → 2 плитки) |

## Слайдеры
`heroes` (3 слайда: image_kw/title/text/button) добавляем китам, у которых их
нет: friseur, werkstatt, handwerker, shop, aktionsmarkt, touren, retreat, cafe,
restaurant, hotel. Тексты — по профилю бизнеса, кнопки ведут на реальные
маршруты кита (проверять по `url_names`, иначе 404 в демо).

## Гейты и замки
- `siteconfig.normalize` — whitelist `hero_widget` расширяется новыми ключами
  (иначе normalize выбросит ключ и демо потеряет плитки).
- `demo_kits._apply_site_defaults` — тот же список ключей.
- Новые замки: `tiles_for` для каждого widget возвращает непустой список при
  всех активных модулях; неизвестный widget → `[]`; плитка с мёртвым url_name
  выпадает; golden normalize не меняется (ключ presence-minimal).
- `apps/core/tests/test_template_comments.py` + `npm run build:css` (новых
  Tailwind-классов не вводим — переиспользуем существующие).
