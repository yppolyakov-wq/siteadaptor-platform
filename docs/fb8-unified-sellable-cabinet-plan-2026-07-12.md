# FB-8 — единое управление продаваемыми сущностями в кабинете

**Дата:** 2026-07-12 · **Ветка:** `claude/admin-simplification-handoff-dfawis`
**ID:** FB-8 (кабинетная часть «единого слоя продаваемой сущности»)
**Статус:** DRAFT на согласование (развилка §3)

Источник: ТЗ `docs/cabinet-feedback-tz-2026-07-10.md` + мастер-трек
`docs/unified-sellable-entity-master-track-2026-06-30.md` (кабинетная часть FB-8 в нём
помечена как «не закрыта»). Разведка кода — проведена (отчёт в чате 2026-07-12).

Проблема владельца: продаваемые сущности живут в РАЗНЫХ силосах кабинета — товары
`/catalog/products/`, услуги `/booking/leistungen/`, номера `/stays/units/`, события
`/events/`, заявки `/jobs/`. У мультиархетипного тенанта (напр. demo-kit **retreat**:
номера + события + услуги + товары) — 4 разных экрана. Нужен ОДИН «отдел» со всем.
Отдельная боль: у отеля в Простом режиме хаб «Sortiment» (catalog) вообще скрыт
(`ARCHETYPE_SIMPLE_HIDDEN`) → владелец не находит, где товары/допы.

## 1. Что уже есть

- **Контракт `SellableEntity`** (`apps/core/sellable.py`) — frozen dataclass, ВИТРИННЫЙ:
  `kind/pk/name/price_display/image_url/gallery/purchase_mode/detail_url(витрина)/…`.
  Адаптеры: `_product/_service/_stay/_event/_combo`. **jobs.Job — НЕ sellable** (namefully:
  `sellable_for("job")` кидает ValueError; job — это transaction, не каталожная сущность).
  В контракте НЕТ: `is_active`/видимости, `edit_url` (кабинет), `status`, `stock`.
- **Прецедент архитектуры** — `apps/core/transactions.py::manage_sections_for(tenant)`:
  per-kind, module-gated билдер секций для доски продаж (`core/board.html`). Работает по
  оси ТРАНЗАКЦИЙ (`Transaction`). FB-8 = его зеркало по оси КАТАЛОГА (`SellableEntity`).
- **Хабы** (`apps/core/templatetags/cabinet.py::HUB_TABS`): «Sortiment» (S1: Produkte/
  Kategorien/Lager/Kombi/Import — только catalog-kinds), «Verkäufe» (S2: доска+транзакции).
  Ни один хаб не сводит УПРАВЛЕНИЕ sellable-сущностями по kinds.
- Управление по приложениям (разнородное):
  - catalog — полноценный ModelForm CRUD (list/create/edit/delete + фото/варианты/комбо).
  - events — ModelForm CRUD.
  - booking services — одностраничный inline-POST (`action=create|update|toggle`, **есть
    тумблер видимости** `is_active`).
  - stays units — одностраничный inline-POST.
  - jobs — только list/detail (не авторская сущность).

## 2. Ключевые находки для FB-8

1. **Нет единой оси управления.** Нужен новый `sellable_manage_sections_for(tenant)` —
   зеркало `manage_sections_for`, но по `SELLABLE_KINDS=(product,service,stay,event,combo)`,
   gated по `is_module_active`.
2. **Контракту не хватает 2 управленческих полей:** `is_visible` (нормировать: у Product/
   Service/StayUnit/Combo — `is_active` bool; у Event — `status` draft/published/cancelled →
   bool + опц. `status_label`) и `edit_url` (кабинетный маршрут; у catalog/events есть
   per-object edit; у booking/stays per-object edit-URL НЕТ — только одностраничные хабы
   с якорем).
3. **jobs** — исключить из sellable-списка (место jobs — доска «Verkäufe»).
4. **Полноценный единый CRUD невозможен дёшево** — 5 kinds имеют глубоко разные формы
   авторинга (ModelForm vs inline-POST vs варианты/комбо; jobs не авторится). Переписывать
   под одну форму — большой риск.

## 3. РАЗВИЛКА ДЛЯ ВЛАДЕЛЬЦА (нужно решение)

### Вариант A — единый СПИСОК (read + быстрый тумблер + deep-link на правку) — РЕКОМЕНДУЮ
Один экран «Angebote / Sortiment» (или таб в хабе): все продаваемые сущности тенанта в
одной таблице с фильтром по типу. На строку: миниатюра, тип-бейдж, имя, цена, статус
видимости (тумблер вкл/выкл прямо тут), кнопка «Bearbeiten» → на РОДНУЮ форму приложения.
Плюс единый вход «＋ Neu» → выбор типа → на родную create-форму.
- **Плюс:** быстро, безопасно, сразу решает «где всё найти» и убирает силосы. Правка —
  на выверенных родных формах (не ломаем варианты/комбо/фото).
- **Минус:** правка не «внутри» единого экрана (открывает родную форму).
- Объём: 1 новый билдер + 1 экран + 2 поля в контракт + тумблеры (реюз booking-паттерна) +
  для booking/stays — добавить per-object edit-роут (маленький) ИЛИ якорь на хаб.

### Вариант B — единый CRUD (создание/правка всех типов на одном экране)
Переписать авторинг 5 типов под общий каркас формы. **Не рекомендую** — большой объём,
высокий риск регрессий (варианты/модификаторы/комбо/фото/i18n/inline-POST booking-stays).

**Моя рекомендация: A.** Даёт 90% ценности (находимость + единый обзор + видимость +
быстрый переход к правке) малой кровью. B — только если после A владельцу нужна именно
правка-в-одном-окне; тогда отдельной волной, начиная с унификации форм (пересекается с
редактором U-C).

## 4. План реализации Варианта A (по инкрементам)

### FB8-1. Управленческие поля в контракте
- `apps/core/sellable.py`: `SellableEntity` += `is_visible: bool`, `edit_url: str`,
  опц. `status_label: str`. Заполнить в 5 адаптерах (`_product/_service/_stay/_event/_combo`).
  Event: `is_visible = status == "published"`, `status_label = get_status_display`.
  edit_url: catalog `catalog:product-edit`/`catalog:combo-edit`, events `events:edit`;
  booking/stays — см. FB8-2.
- Замок: `test_sellable.py` — новые поля на всех адаптерах; `sellable_for("job")` всё ещё raises.

### FB8-2. Per-object edit-роуты для booking/stays (если решим deep-link, а не якорь)
- `apps/booking/urls.py`+`views.py`: `service-edit/<pk>/` (GET → одностраничный хаб с
  предвыбранной услугой, или мини-форма). Аналогично `stays/units`.
- Альтернатива дешевле: `edit_url = reverse("booking:services") + f"#service-{pk}"` (якорь).
  Решить в реализации; для A достаточно якоря.

### FB8-3. Билдер единого списка
- `apps/core/sellable_manage.py`: `ManagedSellable` (dataclass: kind/name/price_display/
  image_url/is_visible/status_label/edit_url/pk) + `sellable_manage_sections_for(tenant)` —
  итерирует `SELLABLE_KINDS`, gated `is_module_active(tenant, KIND_MODULE[kind])`, тянет
  querysets per kind, оборачивает через адаптер. Порядок/группировка — по kind.

### FB8-4. Экран + навигация
- Вьюха `sellable_manage(request)` + маршрут (напр. `/dashboard/angebote/`).
- Шаблон `tenant/sellable_manage.html` (зеркало `core/board.html`): таб-фильтр по типу,
  общий партиал строки `tenant/_sellable_manage_row.html`, вход «＋ Neu → тип».
- Тумблер видимости — POST на родной эндпоинт (реюз `booking action=toggle`; для catalog/
  events — маленький toggle-эндпоинт, либо дергать существующий).
- Навигация: новый таб в хабе «Sortiment» ИЛИ отдельный пункт «Angebote» в группе «sell».
  ВАЖНО: не гейтить его так, чтобы у отеля-Простого он тоже пропал (сейчас catalog скрыт у
  hotel/simple) — экран должен показываться, если активен ХОТЯ БЫ один sellable-модуль.
- Замки: `test_hub_tabs`, `test_cabinet_nav`; новый `test_sellable_manage` (мультикит retreat
  видит все 4 типа; module-gating; тумблер меняет is_active; edit_url ведёт на форму).

## 5. Файлы (A)
- Правка: `apps/core/sellable.py` (контракт + адаптеры).
- Новое: `apps/core/sellable_manage.py`, вьюха в `apps/core/views.py`, маршрут в
  `config/urls_tenant.py`, шаблоны `tenant/sellable_manage.html` + `_sellable_manage_row.html`.
- Навигация: `apps/core/templatetags/cabinet.py` (HUB_TABS) и/или `apps/core/modules.py`
  (NAV_GROUPS/NAV_TASK_LABELS).
- Опц.: `apps/booking/urls.py`+`views.py`, `apps/stays/urls.py`+`views.py` (edit-роут; или якорь).
- Замки: `apps/core/tests/test_sellable.py`, `test_hub_tabs.py`, `test_cabinet_nav.py`,
  новый `test_sellable_manage.py`.

## 6. НЕ трогаем
Родные формы авторинга (catalog/events ModelForm; booking/stays inline-POST) — правка
остаётся там. Витринные использования `sellable_for` — только ДОБАВЛЯЕМ поля, семантику
не меняем (регресс-замок витрины).

## 7. Порядок / объём
FB8-1 (контракт+поля) — фундамент, самодостаточный, первым (+ регресс-замок витрины).
FB8-2..4 — связный срез (роуты→билдер→экран). Без миграций (все поля уже на моделях).
Пересечение с мастер-треком U-C (редактор): единый список — шаг к нему, но не блокирует.
