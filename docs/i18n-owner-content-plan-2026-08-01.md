# План: свободный текст владельца на витрине — переводы (2026-08-01)

Закрывает ограничение, записанное в roadmap §Отложено после волны HF:
«`Service.attributes`/`faq` и `Promotion.group` без overlay → на не-немецких
локалях остаются немецкими».

## 1. Что не так сегодня

Витрина умеет N локалей (Волна L). Модельный контент переводится по двум
схемам:

* **full-JSON** — всё поле словарь `{de,en,…}` (`Product.name`,
  `Promotion.title`/`description`), чтение через `I18nMixin.get_i18n`;
* **flat+overlay** — база в плоском поле, переводы в `*_i18n`
  (`Service.name`, `StayUnit.description`, `Event.title`, …), чтение через
  `I18nMixin.get_overlay`, полный словарь — `i18n_full`.

Мимо обеих схем прошли три поля, которые ВИДНЫ гостю:

| Поле | Где видно | Тип |
|---|---|---|
| `Service.attributes` | секция «Leistungen im Detail» детали услуги | `list[str]` |
| `Service.faq` | секция FAQ детали услуги | `list[{q,a}]` |
| `Promotion.group` | заголовки секций и чипы на `/aktionen/`, плашка на детали акции | `CharField` |

На демо это ровно те экраны, которые владелец смотрит на пяти языках:
`friseur`/`werkstatt` (богатая карточка услуги) и `aktionsmarkt` (группы акций).

## 2. Решение

Обе новые пары — **flat+overlay**, как у всего остального; базовая локаль
всегда авторитетна из плоского поля (инвариант «без дрейфа»).

### 2.1 `Service.attributes_i18n` / `faq_i18n` (миграция `booking/0018`)

Оверлей хранит **список той же формы**, выровненный по индексу базового:

```
attributes = ["Dauer 60 Min", "Inkl. Beratung"]
attributes_i18n = {"ru": ["Длительность 60 мин", ""]}     # "" → фолбэк на базу
```

Аксессоры на модели (не в шаблоне — шаблону нужен готовый список):

* `attributes_localized(locale=None) -> list[str]`
* `faq_localized(locale=None) -> list[{q,a}]`

Правила резолвинга (общие, один хелпер `apps/core/i18n_seq.py`):

* локаль == базовая → база целиком;
* индекс за пределами оверлея / пустое значение → элемент базы;
* лишние элементы оверлея игнорируются (база задаёт длину — иначе
  перевод мог бы «дорисовать» пункт, которого владелец не писал);
* нормализация (`normalize_service_attributes`/`_faq`) применяется к
  результату, а не к оверлею, — форма гарантирована та же.

Рендер: `_service_attributes.html` / `_service_faq.html` → `*_localized`.
(FAQPage JSON-LD строится из `site_config.faq` — секции сайта, а не услуги;
services-FAQ в разметку не попадает, так что расхождения нет.)

**Ввода в кабинете у этих полей сегодня НЕТ** (UA4-3 завёл поля, форма услуги
их не показывает) — значит per-locale инпут делать нечего. Наполняются они
демо-китами; поэтому в объём входит только рендер + засев переводов.
Появится форма — per-locale ввод добавится тем же паттерном Ф1.

### 2.2 `Promotion.group_i18n` (миграция `promotions/0024`)

`group` — одновременно **ключ фасета** (`?gruppe=…`) и **метка**. Переводим
только метку; ключ остаётся плоским немецким значением, иначе ссылки
разъедутся между локалями.

* `group_localized(locale=None)` — `get_overlay("group", "group_i18n", locale)`;
* вьюха `promotions_list` отдаёт тройки `(slug, label, items)` вместо пар
  `(slug, items)`; чипы — `(slug, label)`. Ключ фильтрации не меняется;
* деталь акции: плашка `🏷️ {{ promotion.group }}` → `group_localized`;
* форма акции уже под свитчером Ф1 → добавляем `group` в per-locale инпуты
  (`apply_i18n_overlay(..., fields=("group",))`), поле редактируемое.

### 2.3 Засев демо

`apps/tenants/demo_i18n.py::translate_tenant_content`:

* `_fill_overlay(promo, "group", "group_i18n", locales)` в существующем
  проходе по `Promotion`;
* новый `_fill_seq_overlay(obj, base, overlay, locales, keys=None)` для
  `Service.attributes` (список строк) и `Service.faq` (список словарей по
  ключам `q`,`a`).

Словари `demo_i18n_<loc>.json` пополняются строками attributes/FAQ демо-услуг
и названиями групп акций (`aktionsmarkt`).

## 3. Вне объёма (осознанно)

* `ProductVariant.label`, `ProductOption.label`, `Extra.label` — тот же класс
  «free-text владельца», но перевод отложен решением владельца (2026-07-09,
  «variant/modifier labels — отдельным решением»). Трогать без него не будем.
* `Service.attributes`/`faq` в форме кабинета — отдельная задача (фича, не i18n).

## 4. Порядок работ (все пункты выполнены 2026-08-01)

1. `apps/core/i18n_seq.py` + замки резолвинга (длина/пустые/лишние).
2. Миграция `booking/0018` + аксессоры + рендер двух партиалов + JSON-LD.
3. Миграция `promotions/0024` + `group_localized` + вьюха/шаблоны + форма.
4. Засев `translate_tenant_content` + словари демо.
5. Гейты: `ruff` целиком, `pytest` booking/promotions/tenants/core,
   `test_template_comments`, `i18n_gap`, `npm run build:css` при новых классах.

⚠️ Две аддитивные миграции — деплой владельцем (в общей очереди CLAUDE.md).
