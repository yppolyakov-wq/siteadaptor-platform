# План Г3 + Г4 — «срок свежести» позиций в каталоге города и цифры акций в дайджесте владельцу

**Дата:** 2026-10-17 · **Источник:** `docs/backlog-portal-direction-2026-10-16.md §4` (Г3, Г4, размер S) ·
**Статус:** план, кода нет. Нужны решения владельца из §5.

## 0. Коротко

- **Г3.** Товар или услуга, которые владелец не подтверждал N дней (по умолчанию 60), **уходят из
  каталога города**. На собственной витрине бизнеса позиция остаётся. За K дней до этого (по
  умолчанию 7) владелец получает предупреждение — плашку в кабинете и одно письмо. Подтверждением
  считаются только явные действия владельца: Save формы, «Bestätigen» в импорте и одна кнопка
  «Alles noch aktuell». Источник правды — новое поле `confirmed_at` у `Product` и `Service`
  (две аддитивные миграции). `updated_at` для этого **не годится**, см. §1.3.
- **Г4.** По понедельникам в утренний дайджест добавляется блок «Ihre Aktionen letzte Woche»:
  просмотры · отложено · выдано · купоны, плюс топ-3 акции. Если за неделю всё по нулям, блока нет.
  У просмотров **сейчас нет дат** (счётчик накопительный), поэтому нужна маленькая таблица дневных
  просмотров (одна аддитивная миграция). Попутно исправляется язык дайджеста: сейчас он
  рендерится без `translation.override`.

## 1. Г3 — факты из кода

### 1.1 Как строится листинг
- Товар: `_product_snapshot` — `apps/aggregator/tasks.py:1068`. Он возвращает `None`, если позиция
  не годится к показу: неактивна, `hide_in_city`, ветка категории скрыта, нет фото или цены
  (`:1081-1088`). `sync_product_listing` (`:1130`) при `None`, `_withheld(tenant)` или профиле
  «Nur Aktionen» без внешнего адреса **удаляет** строку (`:1151-1158`). Иначе пишет её через
  `_upsert_listing`.
- Услуга: `_service_snapshot` (`:1190`) и `sync_service_listing` (`:1216`) устроены так же. Там
  есть дополнительное условие «модуль booking активен» (`:1235`).
- `_upsert_listing` (`:190-203`) — единственная точка записи. Неизменённую строку она не
  переписывает, иначе съезжали бы lastmod и фид.
- Реконсиляция видов T-8.11: `_reconcile_city_kinds` (`:1322-1365`). Она перебирает
  `Product(is_active, hide_in_city=False)` и `Service(...)`, синкает каждую позицию и удаляет
  «сирот» (`:1355-1361`). Её вызывают `reconcile_city_catalog` (`:1369`) и полная
  `reconcile_schema` (`:731`). Ночная сверка `reconcile_aggregator_nightly` (`:700-728`) идёт
  по ВСЕМ схемам, включая демо, с разбросом до `NIGHTLY_MAX_COUNTDOWN=3300` с (`:689`).
  Расписание — `config/settings/base.py:547`.
- Хук на правку: `resync_on_product_save` (`:1399`) ставит синк после коммита с dedupe по
  `updated_at.timestamp()`.
- Слой чтения: `ListingQuerySet.public()` (`apps/aggregator/models.py:38-63`) фильтрует
  `is_active`, `hidden_at IS NULL` (это модерация жалоб T-8.6, поле `:207`), срок
  `ends_at` и withheld-схемы. Отдельного признака «свежести» у листинга нет.
- `FavoriteListing.listing` — `on_delete=CASCADE` (`models.py:648`). Если удалить листинг,
  избранное жителя пропадёт вместе с ним.

### 1.2 «Neu» и «auf Bestellung»
- `availability="on_request"`, если `product.primary_action == "request"` (`tasks.py:1100`).
  `"sold_out"` — если товара нет в наличии.
- `is_new = product.badge == "neu" or created_at ≥ now − NEW_PRODUCT_DAYS` (`:1106-1123`;
  `NEW_PRODUCT_DAYS = 14` — `:1003`, тот же порог использует `portal_home_blocks.py:25-27`).
  Ветка по `created_at` гаснет сама через 14 дней. **Бейдж «neu» не гаснет никогда.** Товар,
  которому полгода назад поставили бейдж «Neu», до сих пор показывается в блоке «Neu» портала.
  Г3 эту дыру закрывает, см. §2.6.
- У услуги `is_new` всегда `False` (`:1262`).

### 1.3 Годится ли `updated_at` как «последнее подтверждение»? — НЕТ
`Product(SoftDeleteMixin → TimestampedModel)` и `Service(TimestampedModel)` имеют
`updated_at = auto_now` (`apps/core/models.py:26`). Этот штамп сдвигают и фоновые записи, то
есть действия НЕ владельца:
- **каждая продажа**: `orders/services.py:61` и `orders/editing.py:74` пишут
  `save(update_fields=["stock_quantity","updated_at"])`. То же делают `jobs/services.py:203`,
  `promotions/services.py:189`, складские движения `inventory/services.py:246` и сидер демо
  `tenants/demo_kits.py:25956`;
- **фоновая подгрузка фото после импорта**: `imports/site/apply.py:415/418`
  (`update_fields=["images"|"image","updated_at"]`) и `core/media_registry.py:122/130`.

Если взять `updated_at`, товар с продажами не протухнет никогда, даже если владелец забыл про
него. Обратного дефекта тоже нет гарантии: массовые `.update()` (возврат стока
`orders/state_machine.py:122`, `option_trackers.py:173`) штамп не трогают. Вывод: нужен
отдельный штамп, который ставят **только явные пути владельца**.

### 1.4 Что уже есть для подтверждения
- `SiteImportItem.confirmed_at` (`apps/imports/models.py:134`, комментарий «шов Г3»).
  Его ставят `_confirm` (`imports/site/apply.py:293-316`; для `unchanged`/`removed` товар не
  перезаписывается) и применение позиции (`:264`).
- У `Product` есть `metadata` JSON (`catalog/models.py:296`). **У `Service` metadata нет**
  (`booking/models.py:84-143`).
- Пути владельца:
  - товар — `catalog/views.py:170` (`product_create`) и `:198` (`product_edit`), `form.save()`;
  - услуга — `booking/views.py:685` (`services_view`, редирект `:816`);
  - тумблер видимости — `core/sellable_manage.py:258` (`save(update_fields=["is_active"])`);
  - CSV-импорт — `imports/processors/product.py`.

### 1.5 Демо
Акции демо продлевает beat: `promotions/tasks.py:60-62,90-106` (`extend_demo_promotions`,
только при `tenant.is_demo`). У товаров срока нет, продлевать нечего. Достаточно, чтобы гейт
свежести **не действовал на демо** (`Tenant.is_demo`; `_tenant_base_defaults` кладёт `is_demo`
в листинг — `tasks.py:184`).

## 2. Г3 — дизайн

### 2.1 Хранение (сравнение)
| Вариант | Миграции | Плюсы | Минусы |
|---|---|---|---|
| **A. `confirmed_at` на `Product` и `Service`** | `catalog/0038` + `booking/0030`, аддитивные | индексируемо, симметрично для двух видов, массовое «Noch aktuell» = один `UPDATE`, предупреждения считаются запросом | две миграции |
| B. `Product.metadata["confirmed_at"]` | для Service миграция всё равно нужна (metadata нет) | у товара без миграции | асимметрия, фильтр по строке в JSON, полная перезапись metadata при массовом действии (гонка с T-8.2 `response` и т. п.) |
| C. Отдельная таблица `(kind, id, confirmed_at)` | 1 | модели не трогаем | join на каждом синке и в предупреждениях, сироты при удалении |
| D. Один штамп на тенанта (`Tenant.city_catalog_confirmed_at`, SHARED) | 1 SHARED | кнопка «одна на всё» тривиальна | правка ОДНОЙ позиции не продлевает её отдельно; новая позиция наследует чужой срок |

**Рекомендация: A.** Поле
`confirmed_at = DateTimeField(default=timezone.now, db_index=False)`. Почему именно так:
- `AddField` с `default=timezone.now` заполняет существующие строки **моментом миграции**. Все
  получают льготу N дней после деплоя, и RunPython не нужен. Без этого товары старше 60 дней
  пропали бы из города в момент деплоя.
- Новые строки получают `now` при создании: создание считается подтверждением.
- Без индекса: выборки идут внутри одной схемы малого бизнеса (сотни строк), а в демо до 200.
  Индекс — по замеру.

### 2.2 Кто подтверждает (`apps/core/freshness.py`, новый модуль)
- `confirm(obj)` — `type(obj).objects.filter(pk=obj.pk).update(confirmed_at=now)`. Без
  сигналов: синк запускает сам путь (хук `post_save` у формы) или явный вызов.
- `confirm_all(tenant)` — массовый `UPDATE` по `Product(is_active, hide_in_city=False)` и
  `Service(...)`. **Затем обязательно** `reconcile_city_catalog.delay(...)`: `.update()`
  сигналов не шлёт, а без реконсиляции протухшие позиции не вернутся до ночной сверки.
- Где вызывается (только явные пути владельца или сотрудника):
  1. `product_create` / `product_edit` после `form.save()`. Save без изменений тоже считается:
     «открыл и сохранил» и есть подтверждение.
  2. `services_view` (сохранение услуги).
  3. Правка варианта и модификатора — как подтверждение родительского товара.
  4. `sellable_manage.toggle` (`core/sellable_manage.py:258`), когда позицию включают.
  5. CSV-импорт (`imports/processors/product.py`) — по каждой затронутой позиции.
  6. Импорт с сайта: `apply.py:264` (применено) и `_confirm` (`:310`) для `unchanged` — ставить
     `confirmed_at` **цели** (`item.target_kind/target_id`). Это и есть «шов Г3». `removed`
     деактивирует позицию, подтверждать её не нужно.
  7. Кнопка «Alles noch aktuell» — `confirm_all`.
- **Не подтверждают:** продажи и складские движения, фоновая подгрузка фото, перевод и сидинг
  демо, миграции, `media_registry`, inline-правка фото. Inline-правка текста на канве
  (`core/inline_edit.py:185`) — вопрос В-3, по умолчанию не подтверждает: v1 минимален.

### 2.3 Гейт показа: «показано = проверено»
- `_product_snapshot` и `_service_snapshot` кладут в снимок `"confirmed_at"`.
- В `sync_product_listing` и `sync_service_listing` добавить условие
  `_stale(tenant, snap)` → `delete` + `return "removed"`. Это тот же путь, что для «нет фото» и
  `hide_in_city`, плюс гарантия консистентности с остальными причинами снятия.
- `_stale(tenant, snap)`: `False`, если `settings.CITY_FRESHNESS_DAYS` ≤ 0 (выключатель),
  `tenant.is_demo` или `snap["confirmed_at"] is None`. Иначе
  `confirmed_at < now − timedelta(days=N)`.
- Момент снятия наступает ночной сверкой (`reconcile_aggregator_nightly` уже перебирает все
  позиции). Позиция пропадает в пределах ~25 ч после истечения. Для «свежести» с порогом в
  60 дней это допустимо. Отдельный beat или поле листинга не нужны.
- **Почему удаление, а не `hidden_at`:** `hidden_at` — это поле модерации жалоб (T-8.6).
  Если смешать причины, подтверждение снимало бы скрытие модератором. Удаление согласовано с
  `hide_in_city` и `is_active`, история `PortalStat` переживает (ключ — строка, не FK,
  `models.py:470`).
- **Цена удаления:** CASCADE избранного (`models.py:648`). Принимаем как у `hide_in_city`
  (вопрос В-4). Альтернатива на будущее — поле `AggregatorListing.fresh_until` + фильтр в
  `public()`: точность до минуты и сохранённое избранное, но это SHARED-миграция и правка
  единственной точки чтения.
- Вернуть позицию = подтвердить её. Хук `post_save` формы (или `reconcile_city_catalog` после
  `confirm_all`) пересоздаст листинг.

### 2.4 Предупреждение за K дней
- Сервис `freshness.expiring(tenant, *, within_days=K)` → счётчики
  `{"soon": n_soon, "gone": n_gone, "first_expiry": date}` по товарам и услугам, которые сейчас
  **годятся к показу** (активные, не `hide_in_city`; лишние снимки не строим — грубый, но
  дешёвый фильтр). Только при `listable(tenant)` и `not tenant.is_demo`.
- **Плашка в кабинете:** на главной кабинета и на экране «Stadtportal»
  (`aggregator/owner_views.py:15`, `/dashboard/stadtportal/`). Текст: «N Positionen
  verschwinden am … aus dem Stadtkatalog» / «N Positionen sind nicht mehr im Stadtkatalog»
  и кнопка POST «✓ Alles noch aktuell».
- **Новый endpoint** `aggregator:freshness-confirm`: `@login_required` + `@require_POST` +
  членство (middleware кабинета) + `next=` с отбиванием `//host` (урок «Кабинет-X»). Запись в
  `nav_registry` не нужна — это POST-приёмник; при необходимости добавить в
  `EXPECTED_UNLISTED` (замок X7).
- **Письмо:** daily beat `warn_city_freshness` (по схемам, как `send_owner_digests`).
  `notify(dedupe_key=f"city-fresh:{schema}:{iso_year}-W{iso_week}")` — не чаще раза в неделю,
  только при `soon > 0`. Получатель — `owner_email`. Рендер внутри
  `translation.override(email_locale())` (`notifications/services.py:15-35`). Ссылка ведёт на
  экран «Stadtportal» (абсолютный URL через tenant-urlconf, урок T-8.5). Без domain — без
  ссылки и без падения.
- Строку «N Positionen laufen bald ab» можно добавить и в утренний дайджест (`core/digest.py`).
  Это необязательно (В-5), письмо выше и так работает при выключенном дайджесте.

### 2.5 Настройки (`config/settings/base.py`, env-оверрайд)
`CITY_FRESHNESS_DAYS = env.int(..., 60)` (0 = механизм выключен) ·
`CITY_FRESHNESS_WARN_DAYS = env.int(..., 7)` · расписание `warn-city-freshness` — 86400 с.

### 2.6 «Neu»-бейдж (необязательный шаг Г3-4)
`is_new` в `_product_snapshot` (`tasks.py:1123`): бейдж `"neu"` действует, только если
`confirmed_at ≥ now − NEW_BADGE_MAX_DAYS`. По умолчанию 30: «Neu» владелец подтверждает хотя
бы раз в месяц. Ветка по `created_at` (14 дней) не меняется. Это затрагивает `portal_home_blocks`
через тот же снимок (замок «блок ⊆ ленты» должен остаться зелёным). Витрину бизнеса не трогаем:
бейдж на сайте — дело владельца.

## 3. Г4 — факты из кода

- **Дайджест владельцу:** `apps/core/digest.py:25` `collect_digest` (метрики текущей схемы по
  активным модулям, каждый блок через `_safe`, пустой день → `None`, `:108-111`) и
  `apps/core/tasks.py:24` `send_digest_for_tenant`. Отправка в локальный час
  `DIGEST_HOUR = 7` (`digest.py:15`), `notify(dedupe_key=f"digest:{schema}:{date}")`
  (`tasks.py:46-52`), гейт `owner_digest_enabled` + `owner_email` (`:26`). Beat — раз в час
  (`tasks.py:77-88`). Шаблоны: `templates/emails/owner_digest.txt` и
  `owner_digest_subject.txt`. **Акций в дайджесте нет.**
- **Язык дайджеста сейчас не задаётся:** `render_to_string` без `translation.override`
  (`tasks.py:43-44`). Письмо идёт в языке воркера, а не бизнеса. Правило I18N-13 / I18N-7a —
  `email_locale()`.
- **Источники цифр:**
  - Просмотры: `Promotion.views` — только накопительный итог (`public_views.py:2260`
    `update(views=F+1)`), плюс `PromotionChannelView(promotion, channel, views)` — тоже
    накопительный, **без дат** (`promotions/models.py:589-607`). Недельного окна сейчас
    посчитать нельзя.
  - Датированный, но частичный источник — `PortalStat` (`aggregator/models.py:463-494`): день ×
    листинг × действие `view|click|...`, только визиты из каталога города; уже читается в
    `owner_stats.summary` (`aggregator/owner_stats.py:55`).
  - «Отложено»: `Reservation(created_at, status, fulfilled_at)` (`promotions/models.py:610-627`).
    Список акций считает накопительно `n_held` = статусы `pending|confirmed|fulfilled`,
    `n_handed` = `fulfilled` (`promotions/views.py:159-166`); вывод — `promotion_list.html:121,154`.
  - «Выдано»: `Reservation.fulfilled_at`.
  - Купоны T-8.3: `Voucher(promotion FK, created_at, used_count)` (`loyalty/models.py:24,72`).
    Погашение — `redeem_voucher` через `.update(used_count=F+1)` (`promotions/services.py:500`).
    `.update()` **не трогает** `updated_at` (`auto_now` срабатывает только на `save()`), поэтому
    **даты погашения нет**.
  - Продажи по акции (отклик buy, P7 `price_layer.deal_counts`, `price_layer.py:90`) — v1 не
    берём.

## 4. Г4 — дизайн

### 4.1 Дневные просмотры (нужна одна миграция)
- Новая TENANT-модель `promotions.PromotionDailyView(promotion FK CASCADE, day DateField,
  views PositiveInteger)` с `UniqueConstraint(promotion, day)`. Миграция `promotions/0031`,
  новая таблица.
- Инкремент — рядом с `channels.count_view` (`public_views.py:2263`): тот же паттерн
  «`update(F+1)` → иначе `get_or_create` → повтор `update`» (`promotions/channels.py:32-38`).
  Fail-safe: ошибка счётчика не должна ронять страницу акции.
- Ретеншн: строки старше `PROMO_DAILY_VIEWS_RETENTION_DAYS` (400) чистить в существующем
  суточном beat ретеншна. Можно и не чистить: размер мизерный (В-6).
- Сколько писать не придётся: один `UPDATE` на просмотр — столько же уже делает
  `PromotionChannelView`.
- **Запасной вариант без миграции** (если владелец против):
  - просмотры = только `PortalStat(action="view", listing_kind="promotion")` с подписью
    «aus dem Stadtportal»;
  - или дельта `Promotion.views` к снимку прошлой недели в `Promotion.metadata`.

  Второе отвергаем: запись metadata гоняется с правками владельца (T-8.2 `response`), а
  `save()` дёргает ресинк листинга.

### 4.2 Дата погашения купона (без миграции)
В `redeem_voucher` (`promotions/services.py:500`) писать
`update(used_count=F("used_count")+1, updated_at=timezone.now())`. Тогда у купона акции
(`max_uses=1`) `updated_at` и есть момент погашения. Неделя: `promotion__isnull=False`,
`used_count>0`, `updated_at` в окне.

Это приближение: последующая правка купона сдвинет дату. Купоны акций после выдачи не
правятся, так что погрешность приемлема. Точный вариант — поле `Voucher.redeemed_at`
(`loyalty/0008`), вопрос В-7.

### 4.3 Блок дайджеста
- Окно — неделя `[today−7, today)` в локальной дате тенанта. Блок только по **понедельникам**:
  `local_now.weekday() == 0` передаётся из `send_digest_for_tenant` в
  `collect_digest(tenant, weekly=...)`.
- Гейт: модуль `promotions` активен (`modules.is_module_active`), а сам блок обёрнут в `_safe`.
- `data["promo_week"] = {"views", "held", "handed", "coupons", "coupons_redeemed", "top": [...]}`:
  - `views` = Σ `PromotionDailyView.views` за окно;
  - `held` = `Reservation(created_at в окне, status in pending|confirmed|fulfilled)` — тот же
    фильтр, что `n_held`;
  - `handed` = `Reservation(fulfilled_at в окне)`;
  - `coupons` = `Voucher(promotion≠null, created_at в окне)`, `coupons_redeemed` — по §4.2;
  - `top` = до трёх акций с наибольшими `views` за окно: заголовок акции (контент бизнеса, не
    персональные данные) и три числа. Два агрегатных запроса (`values("promotion").annotate`),
    без N+1.
- **Только агрегаты.** Никаких имён и контактов клиентов, кодов резервов и купонов.
- **Пустая неделя:** все числа 0 → ключа `promo_week` нет. В `interesting` (`digest.py:108`)
  блок считается, поэтому понедельничное письмо уходит, даже если в остальном день пустой.
- **Шаблон** `owner_digest.txt`: раздел «Ihre Aktionen letzte Woche:» строкой
  «👁 N · zurückgelegt N · ausgegeben N[ · Coupons N / eingelöst M]» и топ-3. Числа — через
  `blocktrans count` там, где есть существительное (ru/uk — 4 формы).
- **Язык:** `send_digest_for_tenant` рендерит subject и body внутри
  `translation.override(email_locale())`. Это чинит весь дайджест, не только новый блок.
  Новые msgid × 5 `.po`, затем `scripts/i18n_quickcheck.py` и CI `i18n_gap`.
- **Демо:** дайджест у демо уже уходит, если у демо есть `owner_email`. Поведение не меняем
  (В-8: возможно, стоит исключить `is_demo` из всех owner-рассылок).

## 5. Вопросы владельцу (рекомендация по умолчанию)
- **В-1.** N/K = 60/7 дней через env, 0 выключает. → **Да.**
- **В-2.** Г3 действует только на товары и услуги (номера, события, наборы, карточку бизнеса не
  трогаем). → **Да**: у событий есть даты, у номеров — календарь.
- **В-3.** Inline-правка текста на канве Studio считается подтверждением? → **Нет в v1**:
  подтверждают формы, импорт и кнопка.
- **В-4.** Протухание удаляет листинг: избранное жителя на эту позицию пропадает, как при
  `hide_in_city`. → **Да в v1**. Поле `fresh_until` с фильтром в `public()` — позже по спросу.
- **В-5.** Строка «скоро истекают» ещё и в утреннем дайджесте? → **Да**: одна строка, вдобавок
  к недельному письму.
- **В-6.** Таблица дневных просмотров акций (миграция `promotions/0031`) вместо «только
  просмотры из Stadtportal». → **Да, таблица.**
- **В-7.** Дата погашения купона через `updated_at` (без миграции) или поле `redeemed_at`.
  → **`updated_at` в v1.**
- **В-8.** Исключить демо-тенантов из owner-рассылок (дайджест, предупреждения Г3)? → Для Г3
  демо не протухает вовсе. Дайджест — **отдельным решением**, в Г4 не меняем.
- **В-9.** Бейдж «Neu» гаснет в каталоге города через 30 дней без подтверждения (Г3-4)?
  → **Да.**

## 6. Замки-тесты ДО кода (красные до правок)

### Г3 — `apps/aggregator/tests/test_city_freshness.py`
1. Товар с `confirmed_at` = now−61 д → `sync_product_listing` = `"removed"`, строки нет;
   now−59 д → `"upserted"`.
2. Тот же сценарий для услуги (`sync_service_listing`).
3. **Продажа не продлевает:** товар now−61 д, затем `orders.services` списывает сток
   (`save(update_fields=["stock_quantity","updated_at"])`) → `confirmed_at` не изменился,
   листинг снят.
4. **Фоновое фото не продлевает:** `imports/site/apply._enqueue_images`-путь (`:415`) →
   `confirmed_at` не изменился.
5. Массовые `.update()` стока (`orders/state_machine.py:122`) не трогают `confirmed_at`.
6. Сохранение формы `product_edit` без изменений → `confirmed_at ≈ now`, листинг вернулся (хук).
7. `services_view` save → `confirmed_at ≈ now` у услуги.
8. Импорт с сайта: `_confirm` для `unchanged` ставит `confirmed_at` ЦЕЛИ; `removed` цель не
   подтверждает. Применение `accepted` → подтверждает.
9. `confirm_all` → все годные позиции подтверждены **и поставлена реконсиляция** (мок
   `reconcile_city_catalog.delay`). Без этого протухшие не вернутся — замок именно на это.
10. Демо (`tenant.is_demo=True`), товар now−400 д → листинг жив; ночная сверка его не снимает.
11. `CITY_FRESHNESS_DAYS=0` → ничего не протухает (выключатель).
12. Миграция: существующая строка после `AddField` получает `confirmed_at` ≈ момент миграции и
    не протухает сразу. Проверка — тест на `default` или пробник `--create-db`.
13. Ночная реконсиляция (`_reconcile_city_kinds`) снимает протухшее, сироты чистятся как прежде.
    Неизменённая свежая строка не переписывается: гард `_upsert_listing` цел, `updated_at`
    листинга не сдвигается.
14. Endpoint `freshness-confirm`: аноним → редирект на логин; GET → 405; `next=//evil` → свой
    кабинет; сотрудник-член → 200/302 (подтверждать могут сотрудники).
15. Предупреждение: позиция now−(N−K+1) д → письмо уходит; повтор в ту же ISO-неделю → нет
    второго (`dedupe`); у демо и не-`listable` тенанта → не уходит; язык = `default_locale`
    тенанта (ru-тенант → русский текст).
16. Плашка: при `soon>0` на главной кабинета и на «Stadtportal» видна кнопка; при 0 плашки нет.
17. (Г3-4) бейдж «neu» + `confirmed_at` now−31 д → `is_new=False`; `created_at` 5 дней →
    `is_new=True` независимо от бейджа; замок «блок Neu ⊆ лента» зелёный.

### Г4 — `apps/core/tests/test_digest_promotions.py`
1. Понедельник: 3 просмотра в `PromotionDailyView` за окно + 1 вне окна → `views == 3`.
2. `held` считает резервы, созданные в окне со статусом `pending|confirmed|fulfilled`; резерв
   `cancelled`/`expired` в окне не считается; резерв, созданный до окна и выданный в окне,
   идёт в `handed`, но не в `held`.
3. Купоны: выдан в окне → `coupons`; погашен в окне (`redeem_voucher` ставит `updated_at`) →
   `coupons_redeemed`. Промокод без `promotion` не считается.
4. **Пустая неделя** → ключа `promo_week` нет, строки «Ihre Aktionen» в теле нет.
5. Вторник → блока нет даже при данных.
6. Модуль `promotions` выключен → блока нет; ошибка в блоке (мок) не валит дайджест (`_safe`).
7. Понедельник, в остальном пустой день, но недельный блок не пуст → письмо уходит
   (`interesting`).
8. **Без персональных данных:** у клиента резерва уникальные e-mail/имя/телефон и есть
   `reference_code` — ни одно из них не встречается в теле письма.
9. Топ-3: ровно 3 строки при 5 акциях, порядок по `views` окна. Число запросов на блок
   ограничено (`django_assert_max_num_queries`) — без N+1.
10. **Язык:** тенант с `default_locale="ru"` → тело дайджеста по-русски (и «старые» строки
    тоже: фикс override). Требует скомпилированных `.mo` — локально через `polib`, CI арбитр.
11. Инкремент `PromotionDailyView` на детали акции: два просмотра в один день → одна строка,
    `views=2`; сбой счётчика (мок) → страница акции всё равно 200.
12. Mystery/закрытые акции: топ-3 печатает заголовок акции, но **не цену** (цифр цены в блоке
    нет вовсе — замок по `€`).

## 7. Инкременты (батч-режим; каждый — локальный гейт, затем CI)
- **Г3-1** (⚠️ `catalog/0038` + `booking/0030`): поле `confirmed_at` (default `now`), модуль
  `apps/core/freshness.py` (`confirm` / `confirm_all` / `expiring`), вызовы на путях §2.2.
  Поведение витрины и каталога не меняется. Замки 3–8, 12.
- **Г3-2:** гейт `_stale` в двух `sync_*`, демо и выключатель, настройки §2.5. Замки 1–2, 9–11, 13.
- **Г3-3:** endpoint «Alles noch aktuell», плашки (главная кабинета, «Stadtportal»), beat
  `warn_city_freshness` + письмо (+ строка в дайджесте, если В-5 = да). msgid × 5 `.po`,
  `app.css`, если появились новые классы. Замки 14–16.
- **Г3-4** (необязательный): «Neu»-бейдж с порогом. Замок 17.
- **Г4-1** (⚠️ `promotions/0031`): `PromotionDailyView` + инкремент + (опц.) ретеншн; дата
  погашения купона в `redeem_voucher`. Замки Г4 3, 11.
- **Г4-2:** блок в `collect_digest` + шаблон + `translation.override(email_locale())` в
  `send_digest_for_tenant`, msgid × 5. Замки Г4 1–2, 4–10, 12.

Порядок: Г4-1 → Г4-2 (независим, мельче) → Г3-1 → Г3-2 → Г3-3 → Г3-4. Ревью перед мержем по
правилу сессии: `django-reviewer` + `security-reviewer` (endpoint, письма); `database-reviewer`
на три миграции.

## 8. Риски
- **Массовое исчезновение после деплоя.** Если `default` у `AddField` окажется не `now`, а
  `NULL` с фолбэком на `created_at`, старые товары пропадут в первую же ночь. Это закрывает
  замок 12 и решение «`default=timezone.now`, `null=False`».
- **Забытый путь подтверждения.** Владелец правит позицию через экран, который не зовёт
  `confirm`, и позиция всё равно протухает. Смягчения: кнопка «Alles noch aktuell»,
  предупреждение за 7 дней, перечень путей в §2.2 (их проверяет ревью).
- **Удаление листинга** стирает избранное (CASCADE). Принято (В-4), путь к `fresh_until`
  описан в §2.3.
- **Задержка снятия до ~25 ч** (ночная сверка с разбросом). Для порога в 60 дней приемлемо;
  если нужна точность — `fresh_until` в `public()`.
- **`confirm_all` без реконсиляции** вернул бы позиции только следующей ночью — закрыто
  замком 9.
- **Купон по `updated_at`** — приближение (§4.2); точный вариант — В-7.
- **Тексты писем** без `.mo` локально проверяются только через `polib` (уроки I18N-9/X1).
  Арбитр — CI `i18n_gap`.
- **Импорт с сайта** (визитки «eintrag»): если владелец не перезапускает сбор и не жмёт кнопку,
  его позиции через 60 дней уходят из города. Так и задумано (Г3 = «тот же механизм дифа»),
  но предупреждение обязано дойти. Нужен `owner_email`; без него остаётся только плашка.

## 9. Ops
После деплоя: `./scripts/deploy.sh single` (три аддитивные миграции, проверка —
`python manage.py migration_state`). Beat подхватит новое расписание при рестарте. Первые
протухания возможны не раньше чем через `CITY_FRESHNESS_DAYS` после деплоя.
