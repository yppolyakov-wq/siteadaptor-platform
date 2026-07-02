# UC2-1 — page-scoped draft-модуль (план до кода, 2026-07-02)

Инкремент волны U-C (план `unified-sellable-entity-uc-plan-2026-06-30.md` §11 п.4):
«обобщить `collect()`/`site_preview_draft`/save в один page-scoped draft-модуль
(`config["pages"][page_type]`) с back-compat шимами». ⚠️ Самая горячая поверхность
(редактор/normalize round-trip) — мерж по diff, golden-замки normalize обязательны.

## 1. Разведка (адверсариально верифицированная карта; полная — в отчёте агента)

**Draft-поток:** `collect()` (site_home.html:1285-1492, плоский payload из ~25 ключей) →
debounce `schedule()`/`push()` → POST `site-preview-draft` → `apps/core/views.py:1469-1641`
`site_preview_draft`: нормализует ОПУБЛИКОВАННЫЙ конфиг и селективно накладывает ключи
payload **шестью почти одинаковыми блоками per-page ключей** (детали 1567-76, layouts
1587-95, catalog-флаги 1597-1605 и т.д.) → драфт в `session["site_preview_draft"]` +
автосейв `_draft` в БД через `.update()`.

**Save-поток:** `home_builder_view` POST (views.py:863-1123) — те же per-page ключи
собираются из POST **ещё шестью блоками с presence-guard'ами** (`ed_order_*`/`pd_present`/
`sd_present`/`std_present`/`cf_present`…) → `push_history` → `normalize` → save.

**Витрина:** 6 storefront-приложений (promotions/booking/stays/events/orders/catalog)
читают ПЛОСКИЕ ключи (`product_detail`, `catalog_layout`, …) из
`session["site_preview_draft"]` (preview) или `tenant.site_config` напрямую.

**`config["pages"]` сейчас НЕ существует.** normalize() переносит только известные
top-level ключи — неизвестный `pages` молча теряется при первом же round-trip.

## 2. Ключевое решение: `pages` — ВИРТУАЛЬНЫЙ фасад, хранение остаётся плоским

Буквальный перенос хранения в `config["pages"][page_type]` даёт 4 тяжёлых риска при
нулевой пользовательской ценности: (1) тихая потеря в normalize, (2) двойной источник
правды с 6 storefront-ридерами, (3) расхождение с presence-guard'ами save, (4) мусор
при `restore_version` из history со старым форматом. Плоские ключи УЖЕ page-scoped
по смыслу — проблема не в форме хранения, а в том, что **знание «какие ключи у какого
page_type» размазано тремя копиями** (collect / site_preview_draft / save).

Поэтому UC2-1 реализуем как **единый page-scoped модуль в `siteconfig`** (реестр
page_type → его конфиг-ключи + generic apply), на который сводятся обе серверные
копии. Хранение/ридеры витрины/history — БЕЗ изменений (back-compat = тождество).
Это то же осознанное отклонение «реестры первичны, фасад над ними», что в UC1-1′.
JS `collect()` остаётся плоским (формат провода не меняем — сервер один и тот же).
Владелец может ветировать на чекпоинте.

## 3. API (новое в `apps/tenants/siteconfig.py`)

```python
# Декларация: page_type → спецификация его конфиг-ключей
PAGE_CONFIG_KEYS = {
    "product_detail": ("product_detail",),            # {hidden}
    "event_detail":   ("event_detail",),              # {order, hidden}
    "service_detail": ("service_detail",),
    "stay_detail":    ("stay_detail",),
    "listing": ("catalog_layout", "events_index_layout", "stay_index_layout",
                 "service_index_layout", "catalog_show_filters", "catalog_sort",
                 "catalog_subcats_first", "cart_show_upsell", "detail_related_layout"),
    "home":    (...),   # sections/section_titles/… — уже generic, НЕ трогаем в UC2-1
}

def page_config(config, page_type) -> dict      # срез нормализованного конфига
def apply_page_payload(cfg, payload) -> None    # generic-наложение per-page ключей
                                                # драфта (валидация по реестру,
                                                # семантика 1:1 с текущими ветками)
```

`apply_page_payload` — переносит существующую логику веток `site_preview_draft`
(детали: order∩реестр + hidden∩реестр; layouts: `normalize_layout`; флаги: bool)
в одно место. Затем `site_preview_draft` зовёт ЕЁ вместо своих шести блоков —
**диффы веток должны показать чистое удаление с заменой на один вызов**.
Save-блоки с presence-guard'ами сводим ТОЛЬКО там, где семантика тождественна
(guard-ключи остаются в вьюхе — они из POST-формы, не из payload).

## 4. Слайсы (каждый гейтится локально, мерж по diff)

- **A. Реестр + `page_config`/`apply_page_payload` + тесты** (siteconfig only, вьюхи
  не тронуты). Замки: golden normalize (уже есть) + новые unit-тесты API.
- **B. Свод `site_preview_draft`** на `apply_page_payload` (шесть блоков → вызов).
  Замки ДО правки уже существуют: test_live_preview (`includes_event_detail`,
  `includes_landing_layouts`, `includes_service_index_layout`,
  `preserves_existing`…) — прогнать до и после, поведение 1:1.
- **C. Свод per-page блоков save** — ⚠️ ВЫВОД ПОСЛЕ АНАЛИЗА (2026-07-02): save-блоки
  form-field-driven (ed_order_*/pd_visible_* + module-activity + presence-guard'ы) —
  payload-тождественных кусков НЕТ, свод был бы переписыванием парсинга формы, а не
  переносом. НЕ сводим в UC2-1; правильное место — UC2-4 (единый диспетчер).
  Слайсы A+B закрывают draft-путь целиком.
- **D. (опц., отдельно)** `page_inspector`-группы UC2-3 поверх реестра.

## 5. Тесты-замки (существующие, гонять на каждом слайсе)

`apps/tenants/tests/test_normalize_golden.py` (байт-в-байт normalize),
`test_page_registry.py`, `apps/core/tests/test_live_preview.py`,
`test_home_builder.py` (в т.ч. `preserves_page_layouts`, presence-guards, history,
db-draft), `test_preview_pages.py`; fan-out: catalog/booking/stays/events
storefront-тесты драфта.

## 6. Риски

- Расхождение семантики при переносе веток (напр. `service_index_layout` НЕ
  материализуется по умолчанию — переносить вместе с этой особенностью!).
- `_SNAPSHOT_EXCLUDE`/history не трогаем.
- Мерж строго по diff'ам слайсов B/C (горячая зона).
