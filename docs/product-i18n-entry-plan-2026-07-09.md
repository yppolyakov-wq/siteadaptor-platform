# Продукт i18n — per-language ввод + табы (диагностика + план, 2026-07-09)

Запрос владельца: (1) язык должен переключаться, данные разных языков НЕ видны одновременно
при вводе названия/описания/характеристик; (2) выбираем язык (в настройках/на форме) → вводим
всё на этом языке; (3) ВСЕ витринные параметры управляются переводом в админке; (4) «портянка в
товарах осталась, нет табов внутри».

## Диагностика (адверсариально проверено агентом)

### A. «Все языки видны сразу» + «портянка»
- `ProductForm` (`DynamicI18nFormMixin`) создаёт ОТДЕЛЬНОЕ поле на локаль: `name_de/name_en/name_tr…`
  + `description_de/…` (`i18n_input.py:101`).
- `product_form.html:52` выводит их ВСЕ сразу, стопкой (секция Basis). При 3–5 языках — 6–10 полей
  названия/описания подряд.
- **Переключателя языка НЕТ НИГДЕ** в кабинете (агент §4). Все i18n-формы (Category/Product/Promotion/
  Service/StayUnit/Combo) рендерят все локали одновременно. Единственный свитчер — на ВИТРИНЕ (для
  клиента), не на форме.

### B. «Нет табов»
- W2 сделал `<details>`-аккордеоны (Basis + Preis/Lager/Kennzeichnung/Marketing) — это сворачивающиеся
  секции, НЕ табы.

### C. «Не все витринные параметры переводимы»
Витринные поля товара (агент §2) делятся на два класса:
- **Свободный текст per-товар** (переводится per-product): `name` ✅i18n, `description` ✅i18n,
  **`origin`** (Herkunft) ❌ПЛОСКИЙ, **`ingredients`** (Zutaten) ❌ПЛОСКИЙ. Плюс дочерние: `ProductVariant.label`,
  `ModifierGroup.name`/`ModifierOption.label` — ❌плоские.
- **Коды-справочники** (переводятся ОДИН РАЗ в приложении, не per-товар): `badge` (BADGE_CHOICES),
  `allergens`/`additives`/`diets` (food.py), `unit` (UNIT_CHOICES). Сейчас German-only. Их «перевод» =
  локализованные метки приложения (реестр/`.po`), а НЕ per-product поле.
- Нет поля `attributes`/`характеристики` на Product (есть только у `booking.Service.attributes`).

### D. Механика (для реализации)
- Product: full-dict i18n (`get_i18n(name)` — весь словарь в одном JSONField).
- Service/StayUnit/Combo/Collection/Event: base+overlay (`<field>_i18n` — только неосновные локали).
- Языки формы = `tenant.active_locales` (то, что владелец включил в «Sprachen»); дефолт = `default_locale`.

## План (фазы)

### Фаза 1 — переключатель языка + табы (БЕЗ миграции, главный UX-выигрыш)
Файлы: `product_form.html`, `_pf_field.html`, `catalog/views.py` (контекст локалей), новый партиал
свитчера. Переиспользуемо на Category/Service/StayUnit/Combo/Promotion.
- **Переключатель языка** (пилюли Deutsch|English|… по `active_locales`, дефолт `default_locale`) над
  формой. Клик → показывает поля ТОЛЬКО этого языка (`data-i18n-loc`), прочие `hidden` (CSS/JS; поля
  ОСТАЮТСЯ в DOM → Save не стирает, инвариант W0). Свитчер скрыт при одной локали (как было).
- **Табы формы** (Grunddaten | Preis & Lager | Kennzeichnung | Marketing) вместо `<details>`-портянки;
  переводимые поля (name/description) — в Grunddaten, сгруппированы по языку через свитчер.
- Переводимые поля помечаются `data-i18n-loc="<loc>"`; базовое (de) видно всегда как «основной язык».
- Замок W0: все поля (все локали) в DOM при любом выбранном языке.

### Фаза 2 — сделать переводимыми origin/ingredients (МИГРАЦИЯ)
- Overlay-поля `origin_i18n`, `ingredients_i18n` на Product (аддитивная миграция `catalog/00XX`).
- Форма: `origin_<loc>`, `ingredients_<loc>` (overlay-паттерн `apply_i18n_overlay`/`i18n_inputs_for` —
  уже есть); витрина: `origin_localized`/`ingredients_localized` (`get_overlay`).
- Опц.: variant/modifier labels — отдельным решением (много мелких сущностей).

### Фаза 3 — локализация меток-справочников (badge/allergens/additives/diets/units) = трек T-1
- Метки в `food.py`/choices — через `gettext` + `.po` (chrome-перевод). Это ОТЛОЖЕННЫЙ владельцем T-1
  (массовый `.po`). Крупно; отдельный трек.

## Развилка для владельца (scope сейчас)
- **Минимум:** Фаза 1 (свитчер + табы) — сразу решает «портянку/все языки сразу/нет табов», без миграции.
- **+Фаза 2:** origin/ingredients переводимы (миграция) — «все витринные ТЕКСТЫ товара переводимы».
- **+Фаза 3:** метки badge/allergens/units переводимы (реестр/`.po`) — большой трек T-1.
