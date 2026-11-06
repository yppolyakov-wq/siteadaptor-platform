# AIS A-4 — «KI-Aktionen: объект × действие» (план, 2026-11-06)

План — агент ECC `planner` (сверен с кодом), принят ведущим. Источник правды —
`docs/ai-strategy-2026-11-06.md` §2–§4, §7 (В-1…В-5) и `ais-a3-assistant-panel-plan-2026-11-06.md`.
Решения владельца: первый набор — категории, товары, услуги + шаблон/сетка/карточка страницы;
затем цена/скрыть/переместить; предпросмотр с правкой → «Alles übernehmen»; «Rückgängig» 10 мин,
пока не менялось; без права — предложение без кнопки; массовые ≤ 50 с предпросмотром; названия
магазина в промпт можно, клиенты/заказы — никогда; запретный список.

## 0. Суть
Уровень 2 стратегии: фраза → пакет «объект · действие · поля» → правка в предпросмотре →
«Alles übernehmen» → запись ТЕМИ ЖЕ писателями, что экраны кабинета → «Rückgängig» 10 минут.
Новое: реестр действий `apps/core/assistant_actions.py` и модель `core.AssistantChange` (журнал
применённого пакета — для отката и журнала A-6).

## 1. Развилки (принято)
1. Предложение до клика — в кэше задачи (TTL 30 мин); в базе до клика ничего; истёк → «Vorschlag
   abgelaufen, bitte neu fragen».
2. `AssistantChange` (TENANT): user · job unique (идемпотентность) · items JSON (action, kind, pk,
   before, after, created) · applied_at · undone_at · undo_until; срок 90 дней тем же beat.
3. «Rückgängig» по снимку полей, а НЕ по `updated_at` (его двигают продажи/склад): пункт
   откатывается, если текущее значение каждого поля == `after` (под `select_for_update`), иначе
   «inzwischen geändert — nicht zurückgesetzt». Созданное: товар/категория — мягкое удаление,
   услуга — без броней; только если без ссылок (заказы, склад, брони). Откат своего создания в окне —
   не «удаление данных» из запретного списка.
4. Идемпотентность: `AssistantChange.create(job=…)` первым в atomic + claim в кэше.
5. Всё или ничего: одна транзакция, `select_for_update`, оптимистичная проверка `before`.
6. **Право цены — `preise.edit`** (как массовая правка цен), строже формы товара (`sortiment.edit`).
   ⚠️ развилка владельцу: рекомендация — `preise.edit`.

## 2. Реестр действий
| ключ | действие | поля | право | исполнитель |
|---|---|---|---|---|
| category.create | Kategorie anlegen | name, parent, page_style | sortiment.edit | извлечённый `catalog.services.create_category` |
| product.create | Produkt anlegen | name, base_price, category | sortiment.edit | `catalog.services.create_product` (форма + log_catalog_change) |
| service.create | Leistung anlegen | name, price_eur, duration | sortiment.edit | `booking.services.create_service` |
| product/service.price | Preis ändern | price | preise.edit | save(update_fields) + PriceLog |
| product/service/category.visibility | aus-/einblenden | visible | sortiment.edit | `sellable_manage.toggle_visibility` / `set_category_active` |
| product.move | verschieben | category | sortiment.edit | save(update_fields=[category]) |
| page.setting (A-4c) | Vorlage/Raster/Kartenform | code+value | website.edit | `page_settings.validate` → `write` |
| bulk.* (A-4d) | massenhaft | селектор + mode | как одиночный | те же исполнители, общая математика с WR-6 |

Факты — сервером: объект — существующий pk (casefold-совпадение имени, неоднозначность → выбор
человеком), цена — `_ai_price`, процент — число с «%» (−90…500), имя созданного — из слов
владельца, поле — только из спеки. Запретный список — по построению (закрытый реестр) + замок.

## 3. Разбор фраз
Детектор без ИИ (создание ИЛИ «имя существующего объекта + глагол изменения» на 5 языках) →
`put_actions` (обобщение `put_plan`: те же лимиты, замок). Правила — запасной путь. ИИ — новая
задача `assistant_actions` (fast, свой тумблер, абзац Datenschutz), схема с enum действий;
контекст — только названия (категории ≤ 60, товары ≤ 150, услуги ≤ 60, ≤ 3500 символов), рамка
DATA; примеры на 5 языках. ≤ 10 пунктов, массовые разворачиваются сервером до ≤ 50.

## 4. UX
`outcome="actions"` → партиал предпросмотра: карточка на пункт (fieldset/legend, «vorher →
nachher», правимые поля, галочка «übernehmen», «Im Formular öffnen»), без права — причина без
контролов. POST меняет только значения полей и галочки по индексу; action/kind/pk — из кэша.
Успех → «Erledigt: N angelegt, M geändert» + ссылки + «Rückgängig (bis HH:MM)». Без JS —
полная страница. Аудит `assistant.apply|assistant.undo` без текста фраз. ⚠️ Снижение цены
попадает в PriceLog (§ 11 PAngV, «низшая цена 30 дней») — предупреждение в превью; скрытие
категории не скрывает товары — честная подпись, без авто-каскада.

## 5. Замки ДО кода
`test_a4_registry` (allowlist, запретный список, у каждой спеки perm/module/экран/undo) ·
`test_a4_writers_parity` (извлечённые create_* = форма экрана) · `test_a4_facts` (×5 языков,
без ИИ и с замоканным) · `test_a4_apply` (без клика — пусто; подмена POST игнорируется; двойной
POST = один пакет; всё-или-ничего; изменённый после предложения — отказ; чужой job 404; без права
не применяется) · `test_a4_undo` (окно, ручная правка, продажа не блокирует, товар с заказом не
удаляется, чужой не откатит, повтор — no-op) · `test_a4_prompt` (нет ПД/цен/клиентов, кап,
маркер) · `test_a4_bulk` (51 → отказ).

## 6. ECC-прогоны
Скиллы: django-patterns, django-security, django-tdd, database-migrations, django-celery,
e2e-testing, accessibility, error-handling. Агенты: `architect` по §1 до кода; `django-reviewer`
каждый батч; `security-reviewer` a/b/d (запись по ИИ-предложению); `database-reviewer` a/d;
`silent-failure-hunter` a/b/d; `a11y-architect` a. Стенд Playwright 390/1440 de+ru: пакет
«Kategorie Kuchen, Käsekuchen 3,20 €» → übernehmen → Rückgängig; «Preis Käsekuchen auf 3,50 €»;
«скрой Käsekuchen» в Mini App; сотрудник без `preise.edit`; двойной клик; без JS.

## 7. Инкременты
- **A-4a** пакет «создать» (⚠️ `core/0016`): извлечение писателей с паритет-замком первым коммитом,
  реестр `*.create`, `put_actions`, предпросмотр, apply/undo, идемпотентность, аудит, purge.
- **A-4b** цена/скрыть/переместить (без миграций): детектор, резолвер, ИИ-задача + disclosure.
- **A-4c** шаблон/сетка/карточка страницы (без миграций).
- **A-4d** массовые ≤ 50 (без миграций).

## 8. Правки архитектора (агент `architect`, 2026-11-06) — обязательны до кода

1. **История до клика.** `_put` готовой записи пишет её в `AssistantTurn` (A-3d) — пакет попал бы в
   базу до клика. В историю — только сводка без items; `AssistantTurn.KINDS` += "actions".
   Apply читает пакет ТОЛЬКО из job-кэша (не из истории, не из POST); карточка из истории — без
   кнопки. Свой TTL у `put_actions` (30 мин), сейчас `RESULT_TTL` = 10 мин.
2. **`AssistantChange`:** unique `job` в схеме; откат — только автор + перепроверка права в момент
   отката; в JSON канонические значения (Decimal строкой, FK — pk).
3. **Откат:**
   - цена товара: `PriceLog` пишет post_save и он append-only — откат снижения НЕ убирает его из
     минимума 30 дней (§ 11 PAngV) → предупреждение в превью И в тексте отката;
   - у услуг PriceLog нет; товар/услуга с вариантами или сезонными ценами — `price` отказом
     «Im Formular öffnen»;
   - удаление созданного товара: исключить собственные строки (стартовое движение склада
     `source="catalog"`, первая запись PriceLog), иначе откат невозможен всегда; мягкое удаление;
   - категория — только без живых товаров/детей; пункты пакета откатывать в ОБРАТНОМ порядке;
   - услуга (жёсткое удаление, `Booking.service` SET_NULL): ссылки проверять самим (брони,
     `Promotion.service`, generic `Extra`/`Review`/`DealLink`, M2M collections) — есть ссылки →
     `is_active=False` с честным сообщением;
   - откат создания — право `sortiment.edit` (отмена своего действия, не удаление чужих данных).
4. **Идемпотентность:** истина — unique-индекс; `IntegrityError` ловить снаружи atomic, перечитать и
   отдать прежний отчёт (паттерн `offer_batch.confirm`); claim в кэше — только UX.
5. **Блокировки (главный риск):** checkout/правка заказа/jobs блокируют Product/Variant по одной
   строке в порядке корзины, склад — Tenant→Product. Поэтому: (а) первым `Tenant
   select_for_update` (сериализует applies тенанта), затем все целевые строки ОДНИМ запросом
   `filter(pk__in=…).order_by("pk").select_for_update()`; (б) `SET LOCAL lock_timeout '3s'` →
   «gerade in Benutzung, bitte erneut» (владелец не ждёт за покупателем и наоборот); (в) в
   транзакции ничего внешнего — gate и проверка фактов ДО atomic, `page_settings.write` получает
   `gate=` заранее; после отката транзакции — `tenant.refresh_from_db(fields=["site_config"])`.
   CAS через `update()` нельзя: обходит post_save (PriceLog, листинг города).
6. **Право цены `preise.edit`** — эшелон для ИИ и массовых правок, не реальная граница: форма
   товара/услуги (`sortiment.edit`) цену тоже меняет — закрыть это или нет, решает владелец
   отдельно. Цена при `*.create` — `sortiment.edit`, как экран создания.
7. **Писатели «создать» — обёртка над Form-классами экранов** (`create_product(tenant, data,
   actor)` = `ProductForm` → `is_valid` → `save` → `log_catalog_change`; вьюха зовёт ту же
   функцию — паритет по построению). `_service_from_post` → dict данных, единственный путь
   `service_new`. Свести на них же `offer_batch._create` (сейчас третий путь мимо форм со своей
   логикой НДС). Для правок (price/visibility/move) формы НЕ использовать (ModelForm с частичными
   данными обнулит поля — класс W0): узкие `save(update_fields)` на заблокированной строке;
   `set_category_active` — новый; `toggle_visibility` — версия на заблокированном экземпляре с
   доменной ошибкой вместо `Http404`.
8. **Замки (+ к §5):** «lock_timeout/deadlock с параллельным checkout»; «откат товара со стартовым
   остатком»; «откат в обратном порядке»; «пакет из истории не применяется».

## 9. Решения владельца (2026-11-06, «по рекомендации»)
- Цену через ассистента меняет только право `preise.edit`.
- Форма товара/услуги (`sortiment.edit` меняет цену) — оставляем как есть.
- Журнал цен не чистим; предупреждение о § 11 PAngV — в предпросмотре снижения цены и в тексте
  отката.
