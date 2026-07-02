# UB3-2 — мини-разведка модели `Collection` (M2M-группировка услуг/номеров) — 2026-07-02

> Требование владельца (решение B-3 + условие подзадачи): разведка модели СОГЛАСОВЫВАЕТСЯ
> ДО миграции. Это план-док на согласование; код/миграций ещё нет.

## 1. Контекст и прецеденты в коде

- **Зачем:** у `booking.Service` (A3/A7/A9) и `stays.StayUnit` (A5) нет группировки на
  витрине — листинги плоские. Решение владельца: **M2M-коллекции** (НЕ плоское поле
  `category` как у events): услуга/номер может быть в нескольких подборках
  («Damen», «Färben & Pflege»; «Seeblick», «Familienzimmer»).
- Прецеденты: `catalog.Category` (self-FK иерархия, slug, sort_order, is_active,
  JSON-i18n имя) — остаётся ТОЛЬКО у каталога; `events.category` — плоская таксономия
  из реестра (фикс-список), не подходит (коллекции — контент владельца);
  `apps.reviews` (UA4-4a) — прецедент маленького generic TENANT-приложения.
- Фасет-слой готов: UB2-1/2-3 — `FacetProvider` у services/stays уже есть; фасет
  коллекций = чипы + `apply` по slug (M2M JOIN + distinct, keyset-safe).

## 2. Предлагаемая модель (v1)

**Новое TENANT-приложение `apps.collections`** (label `collections`; по образцу
`apps.reviews`; в `TENANT_APPS` base.py — test.py подхватит):

```python
class Collection(TimestampedModel):        # UUID-pk, created/updated
    name = models.CharField(max_length=120)          # база (DE)
    name_i18n = models.JSONField(default=dict, blank=True)   # L3-оверлей {en: …}
    slug = models.SlugField(max_length=140)           # URL/фасет-параметр
    description = models.TextField(blank=True)        # опц. интро подборки
    description_i18n = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # unique slug per tenant-схеме; ordering = ["sort_order", "name"]
```

**Связи — M2M-поля на сущностях** (удобный доступ `service.collections`):
- `booking.Service.collections = M2M("collections.Collection", blank=True, related_name="services")`
- `stays.StayUnit.collections = M2M("collections.Collection", blank=True, related_name="stay_units")`

**Решения внутри модели (моя рекомендация):**
1. **Иерархии НЕТ** (плоские подборки; self-FK только у catalog.Category). Если
   позже понадобится — AddField parent, безопасно.
2. **Без пер-архетипного scope-поля**: одна таблица на тенанта; чипы на листинге
   услуг показывают только коллекции с активными услугами, на листинге номеров —
   с активными номерами (present-values из QuerySet). Микробизнес — обычно один
   архетип; scope-поле = лишняя настройка (анти-Битрикс).
3. **i18n по L3-паттерну** (база в плоском поле + `*_i18n` оверлей, `get_overlay`) —
   как Service/StayUnit, реестр DE+EN (решение S-3).

## 3. Миграции (чистые, без потерь)

- `collections/0001_initial` — новая таблица.
- `booking/0013` — AddField M2M (создаёт junction-таблицу).
- `stays/0021` — AddField M2M.
Ничего не переименовываем/не удаляем; локальный гейт с `--create-db`.

## 4. Резолвер группировки + фасет

- **Фасет (ядро UB3-2):** `ServiceFacets`/`StayDateFacets` +=
  `apply(..., {"kollektion": slug})` → `items.filter(collections__slug=…, collections__is_active=True).distinct()`;
  `present` → `collection_chips` (name_localized+slug коллекций, где есть активные
  сущности данного kind). UI — чипы над листингом (как категории каталога), в
  `listing_facets` service_index/stay_index.
- **Резолвер группировки:** хелпер `collections.services.grouped(kind, items)` →
  `[(collection, [items…]), …, (None, [без коллекции])]` — для будущего режима
  «листинг секциями по подборкам» (вкл. через site_config, отдельным шагом —
  НЕ в v1, чтобы не раздувать миграционный инкремент). В v1 отдаём только фасет-чипы.
- Тулбар/поиск/сорт UB2-2 работают поверх без изменений (фасет — обычный WHERE).

## 5. Кабинет и демо

- **Кабинет (минимум):** CRUD коллекций — страница `/dashboard/collections/`
  (список+форма по образцу категорий каталога) + чекбокс-мультиселект коллекций в
  формах услуги/номера. Вопрос владельцу: включать в UB3-2 или отдельным шагом
  (v1 можно засеять демо и управлять из admin)?
- **Демо-засев:** friseur — «Damen», «Herren», «Färben & Pflege» (услуги по 1–2
  коллекции); hotel — «Mit Seeblick», «Familienzimmer» (номера). Ретрит-кит — опц.

## 6. Риски

- Имя приложения `collections` совпадает со stdlib-модулем: абсолютные импорты
  `apps.collections` конфликтов не дают (проверено паттерном других приложений);
  внутри приложения не импортировать stdlib `collections` относительным путём.
  Альтернатива, если не нравится: `apps.showcase` (метка showcase).
- M2M JOIN + distinct на фасете — на объёмах микробизнеса дёшево.
- Миграция → после мержа деплой владельцем (`./scripts/deploy.sh single`).

## 7. Вопросы владельцу (нужно ДО кода)

1. Модель/поля из §2 (плоская, без scope, i18n-оверлей) — ок?
2. Имя приложения: `apps.collections` (реком.) или другое?
3. Кабинетный CRUD — в составе UB3-2 или отложить (демо+admin в v1)?
4. Названия демо-коллекций (§5) — ок или дадите свои?
