# UC2-4 — единый инлайн-диспетчер канвы (план до кода, 2026-07-03)

Инкремент волны U-C (`uc-plan §11` п.7): «диспетчер sellable-inline-edit, резолвит
модель+поле; 6 URL — тонкими алиасами». Разведка агентом (полная карта — в отчёте),
факты адверсариально сверены с кодом.

## 1. Объём (решение по разведке)

**Унифицируем пятёрку с единым wire-контрактом `{pk, field, value}`:**
product / event / stay / service / promotion — все три JS-канала канвы
(`data-edit-model` blur, `data-price-edit` попап, `data-dt-edit` попап) шлют
одинаковый JSON в `MODEL_EDIT_URLS[model]`. **ВНЕ объёма:** `category_inline_edit`
(`{category_pk, value}` — другой контракт) и `site_inline_edit` (`{field, value}`
без pk, site_config + авто-bump сигналом Tenant) — их унификация меняла бы
JS-провод без пользы. UE3-1-вьюха promotion мигрирует в диспетчер (как и
планировалось D3a). Свод save-блоков `home_builder_view` (отложен из UC2-1
слайса C) — НЕ здесь: это form-driven POST, не JSON-канва; отдельным решением.

## 2. Семантика 1:1 (декларации реестра; замки — существующие тесты)

| model | текст | семантика | кламп | required | цена/прочее | гейт | bump |
|---|---|---|---|---|---|---|---|
| product | name, description | i18n `['de']` | — | name | base_price Decimal 0..1e6 q(0.01) | has_variants→400 | ТОЛЬКО цена |
| event | title, description | плоско | title[:200] | title | price_eur→price_cents `int((e*100).q(1))` | has_tiers→400 | все ветки |
| stay | name, description | плоско | name[:120] | name | price_eur→цены | — | все |
| service | name, description | плоско | name[:120] | name | price_eur→центы | — | все |
| promotion | title | i18n `['de']` | — | title | price_override/compare_at_price Decimal q(0.01); discount_percent int 0..100 (0→None); ends_at ISO naive→aware | — | всё КРОМЕ title |

Общие инварианты: пустой `description` сохраняется; «главное» поле пустым → 400;
запятая→точка в числах; DoesNotExist/ValidationError/ValueError по pk → 400;
`save(update_fields=[attr, "updated_at"])`; авторизация `login_required` +
`require_POST` (изоляция — схемой тенанта). Асимметрии bump (product-текст и
promotion-title НЕ бампят) переносим ОСОЗНАННО как флаги — поведение 1:1.

## 3. Реализация

`apps/core/inline_edit.py`: `Field`-спека (kind ∈ text|decimal|cents|percent|
datetime; attr, i18n, required, clamp, bump, gate) + `INLINE_REGISTRY[model]` +
`dispatch(request, model_key)` (ленивые импорты моделей — без циклов core↔apps).
Пять вьюх становятся алиасами `return dispatch(request, "<model>")` (декораторы
и docstring-указатель остаются; module-level `_bump_*`-хелперы НЕ трогаем — их
используют photo-edit). Мёртвые константы `_*_INLINE_FIELDS` удаляем.

## 4. Гейт

Замки существующие: catalog `test_views` (8 инлайн-тестов), events/stays
`test_*_inline_edit_*`, booking `test_service_inline_edit_*`, promotions
`test_inline_edit.py` (11, вкл. engine-fields-closed), маркер-тесты. Новое:
core-тест консистентности реестра (5 моделей, поля = прежние вайтлисты).
