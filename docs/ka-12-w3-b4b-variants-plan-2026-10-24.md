# KA-12 W3 B4b «Варианты услуги» (E4.4) — план, 2026-10-24

План — агент `planner` по коду HEAD (после E4.4a). Миграция — **`booking/0037`**
(0036 занята правками E4.4a по ревью). Решения развилок — по рекомендации (владелец
2026-10-24: «делай по рекомендации»):
- **Р-1:** акция «счастливые часы» + вариант = цена акции + доплата варианта
  («показано = списано» в форме и в `price_cents`).
- **Р-2:** вариант не выбран → первый активный по `sort_order`.

## Суть
`ServiceVariant` (service FK CASCADE `related_name="variants"`, `name`+`name_i18n`,
`price_delta_cents` со знаком, `duration_delta_minutes` со знаком, `sort_order`,
`is_active`) + `Booking.variant` (SET_NULL) + снимок `Booking.variant_label`.
Длина брони живёт в `end`, буфер — `end + buffer`, поэтому `move`/буфер/resync
подхватывают вариант сами; вариант нужен в сетке, назначении ресурса и цене.

Единые хелперы (`apps/booking/pricing.py`): `effective_minutes(service, variant)` (кламп
≥ 5 мин), `variant_price_cents(service, day, variant)` (кламп ≥ 0), `resolve_variant(service,
raw) → (variant|None, ok)` (пусто → дефолт; чужой/выключенный/мусор → ok=False → 404).

## Срезы
- **S1 модель + кабинет:** миграция 0037; мини-формы вариантов в `services.html` (по образцу
  сезонных цен — отдельные формы, без риска W0), ветки `variant_add/update/toggle/delete`
  с 404 на чужой вариант, переводы `apply_i18n_overlay(fields=("name",))`, сотрудник может
  править. Витрина не меняется, пока вариантов нет.
- **S2 витрина + снимок:** `?variante=` в `service_slots` (сетка = units × длина варианта,
  `next_free_slot` получает `duration_minutes`, перенос параметра во всех построителях
  ссылок; при дефолтном варианте разметка байт-в-байт), чипы вариантов в
  `_service_slots_box.html`, hidden в `_buybox_service_form.html`; `service_book` (404 на
  подделку, длина, цена, акция + доплата), `services.book` (guard variant.service == service,
  снимок); подписи «Услуга · Вариант» на подтверждении, карточке кабинета, `deal_lines`,
  `invoice_from_booking`, `_booking_fields` (+поиск), customer360, письме post-visit.
- **S3 контракт + демо:** `sellable._service` «ab min» с `prefetch_related("variants")`
  (гейт включая `apps/tenants`), демо friseur «Haarschnitt Damen» Kurz/Mittel/Lang +
  переводы ×4 + проход в `translate_tenant_content`, `SEEDER_VERSION=6`; ручная запись в
  Tagesplan — селект варианта (мусор → предупреждение, не 404).

## Замки (red-first) — `apps/booking/tests/test_e44b_variants.py`
resolve_variant (дефолт/чужой/выключенный/без вариантов) · сетка с удлинённым вариантом ·
`?dauer` × вариант · буфер `occupied_until` от конца варианта + `move` · цена (дельта,
отрицательная не в минус, сезон, per_person) · акция + доплата = `price_cents` · подделка
POST → 404 без брони · снимок переживает удаление варианта, группа HF-6c — снимок на каждой ·
перенос `variante` в ссылках + паритет `test_buybox_parity` при дефолте · `next_free_slot`
по длине варианта · подписи на 5 поверхностях · кабинет CRUD + 404 + staff + Save услуги
не трогает варианты · демо 3 варианта, без identity в словарях · sellable «ab» + N+1-замок.

## ECC-прогоны (правило CLAUDE.md §5)
| Когда | Что |
|---|---|
| До кода (S1–S3) | скиллы `django-patterns`, `django-tdd`, `database-migrations`, `django-security` |
| Сразу после плана | `database-reviewer` по схеме 0037 (до написания кода — дешевле поправить) |
| После каждого среза | `django-reviewer`; `security-reviewer` (подделка формы/вариант чужой услуги, цена) |
| S2 | `silent-failure-hunter` по ценовым путям (дельта/акция/per_person — деньги); Playwright-стенд «вариант → слот → бронь» (скилл `e2e-testing`) |
| S2/S3 | `a11y-architect` — чипы вариантов (роль/`aria-current`, фокус) |
| Перед мержем | i18n_quickcheck, template_comments, `npm run build:css` при новых классах, `ruff format --check .` целиком |

## Поправки по ревью схемы (`database-reviewer`, до кода)
1. Дельты знаковые с потолком: `price_delta_cents` ±1 000 000 ц., `duration_delta_minutes`
   ±480 мин — валидаторы + CheckConstraint на НОВОЙ таблице (бесплатно в CreateModel);
   на `booking_booking` констрейнтов не добавляем.
2. `UniqueConstraint(service, name)`; `ordering = ["sort_order", "id"]` (детерминизм «первого»).
3. `variant_label` = только имя варианта, `max_length=100`, склейка «Услуга · Вариант» при
   рендере; снимок не пересчитывается при переименовании.
4. Кламп длительности ≥ 5 — только в `effective_minutes` и проверке формы (кросс-таблица в
   БД невозможна); тест на уменьшение `Service.duration_minutes`.
5. Активные варианты — ОДНА точка: `Prefetch("variants", queryset=…is_active…, to_attr=
   "active_variants")`; никаких `.filter()` поверх prefetch в хелперах; списки броней
   читают снимок, `select_related("variant")` не нужен.
6. Лимит ≤ 12 вариантов на услугу (форма). Удаление варианта с бронями — предпочтительно
   «Aus»; жёсткое удаление допустимо (SET_NULL + снимок).
7. `Booking.variant` — обычный индекс FK (нужен для SET_NULL); миграция без CONCURRENTLY.
8. После генерации — `sqlmigrate booking 0037` и повторный `database-reviewer` по SQL.

## Что учесть в S2 (ревью Django S1)
- Дефолт «первый активный» меняет цену ВСЕХ входов без параметра (ссылки, embed, Finder, MCP,
  фид, акции `/p/<uuid>/`, письма) — в S2: «ab …» и цена без выбора считаются от дефолтного
  варианта честно и одинаково на всех поверхностях; демо — первым вариант с дельтой 0.
- Prefetch `active_variants` (to_attr) — заводится в S2 в листингах/контракте (сейчас нет).
- `duration_minutes` встречается ~40 раз — в S2 замок «сетка и бронь считают `effective_minutes`»
  и проход по всем вхождениям на витринных путях (кабинет/напоминания — по `end` брони).
- Снимок `variant_label = name_localized()[:100]`; цена — через `variant_price_cents` с
  сезоном и слоем акций («показано = списано»).
