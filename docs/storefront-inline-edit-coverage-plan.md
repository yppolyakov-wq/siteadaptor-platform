# Инлайн-редактор на витрине — покрытие по архетипам (план, 2026-06-30)

Фидбэк владельца: «проверь изменение цены, заголовков, опций на ВСЕХ архетипах и на
текстовых страницах; замену фотографий на всех архетипах; скидки из редактора. При
настройке детальной/категории в шаблоне показывать только блоки этой группы вывода.»

## Аудит (grep маркеров) — что есть / чего нет
| Архетип | Заголовок/описание | Цена | Фото |
|---|---|---|---|
| catalog (товар) | ✅ card+detail (data-edit-model=product) | ✅ card+detail+(promo) | ✅ ТОЛЬКО card (M4) |
| promotions (акции) | ✅ card title | ✅ card price (price_override) | ❌ |
| events (события) | ✅ detail (title+desc) | ❌ | ❌ |
| stays (номера) | ✅ detail (name+desc) | ❌ | ❌ |
| booking (услуги) | ❌ | ❌ | ❌ |
| jobs (Handwerker) | ❌ | ❌ | ❌ |

Механизмы (generic, уже есть): `data-edit-model`+`MODEL_EDIT_URLS` (текст/цена),
`data-price-edit`+обобщённый обработчик (модель/поле из атрибутов), `data-photo-edit`+
`PHOTO_EDIT_URL` (ТОЛЬКО product — надо обобщить как цену).

## Part A — Цена на всех архетипах
- **A1 events:** `event_inline_edit` + field `price_eur`→`price_cents` (если НЕ has_tiers);
  маркер на цене `event_detail` (и карточках событий). ✅/❌
- **A2 stays:** `stay_inline_edit` + field `price_eur`→`price_cents`; маркер на `stay_detail`
  (и stay-карточках/index/главной stay_rooms).
- **A3 booking:** новый `service_inline_edit` (name/price/photo) + маркеры на service_index/
  main services-секции/termin.

## Part B — Фото на всех архетипах (обобщить M4)
- Обобщить `data-photo-edit`: `MODEL_PHOTO_URLS` (product/event/stay/service/promotion) +
  чтение модели из `data-edit-model`. Эндпоинты фото на event/stay/service/promotion
  (зеркало `product_photo_edit`: новое primary-фото + bump кэша). Маркеры на детальных/
  карточках + product_detail (сейчас фото-правка только на product card).

## Part C — Заголовки/опции карточек + текстовые страницы
- Заголовки на КАРТОЧКАХ списков (event/stay/service cards) — сейчас только детальные.
- «Опции» — уточнить (варианты товара / секционные настройки). Пока: настройки секции
  (заголовок/описание/раскладка) уже есть в билдере.
- Текстовые/легал-страницы (impressum/datenschutz/widerruf) — тексты правятся в Settings;
  about (ueber-uns) — about_title/about_text инлайн. Проверить/докрутить.

## Part D — Билдер: фильтр блоков по группе страницы
При настройке ДЕТАЛЬНОЙ или КАТЕГОРИИ в билдере (вкладка Pages / per-page) показывать
ТОЛЬКО блоки/секции, принадлежащие этой группе вывода (деталь ≠ главная ≠ категория).
Сейчас per-page инспектор есть; нужно гейтить набор секций по типу страницы.

## Part E — AB3-v2 (живое превью в мастере) / AB4 (чек-лист) — оба УЖЕ есть (verify/полировка).

## Порядок
A (цена) → B (фото) → C (карточки/текст) → D (билдер-фильтр) → E (AB verify).
Каждый — браузерная проверка (редактор-JS!), реюз CSS, без миграций где возможно.
