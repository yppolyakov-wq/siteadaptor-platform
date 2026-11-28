# M6 «своя структура объекта» — независимый инвентарь по коду (2026-11-27, HEAD bde10a2)

Только из кода. Не читались: `docs/fb33-m6-plan-2026-11-27.md`, строки «M6» журнала/скиллов,
запись «стопка 17» build-log, старый scratchpad `m6/`. Пути — от корня репозитория.
Пометка **[проверено]** — прочитан код; **[вывод]** — следствие из прочитанного, не прогон.

---

## 1. Где сегодня лежит всё, что определяет страницу одного объекта / категории

### 1.1 Поля моделей (уровень объекта)
| Модель | Поле | Что хранит | file:line |
|---|---|---|---|
| Product | `page_override` JSON `{hidden, shown, layout, blocks_first}` | отличия разделов и шаблон | `apps/catalog/models.py:282` |
| Product | `card_style`, `variant_style`, `faq`, `faq_i18n` | форма карточки, свои вопросы FAQ | `:278`, `:267`, `:285-286` |
| Service | `page_override` (+`order`), `card_style`, `faq`, `attributes` | | `apps/booking/models.py:195-202` |
| StayUnit | `page_override`, `faq`, `faq_i18n` | | `apps/stays/models.py:107-111` |
| Event | `page_override` (+`order`) | | `apps/events/models.py:291` |
| Tour | `page_override` (+`order`) | | `apps/events/models.py:96` |
| Promotion | `page_override` (реально только `blocks_first`), `page_style` (старый код шаблона), `card_style`, `group`, `group_i18n` | | `apps/promotions/models.py:263, 375, 369, 387, 390` |
| Category | `page_style` (старый код), `card_style`; **`page_override` нет** | | `apps/catalog/models.py:54, 60` |
| Combo, BlogPost, ContentPage, Teacher | **ничего** про структуру | | `catalog/models.py:974`, `events/models.py:1035, 879`, `core/models.py:506` |

`page_override` чистит один модуль — `apps/core/object_structure.py:87-118` (`clean`): только известные
разделы реестра модуля, `layout` ∈ {standard, tabs, breit}, `order` только у `events`/`booking`
(`ORDERABLE_MODULES`, `:34`), `blocks_first`. Всё остальное молча выбрасывается.

### 1.2 `Tenant.site_config` (одна JSON-строка на бизнес, public-схема, `apps/tenants/models.py:216`)
Уровень **объекта** (ключ содержит идентичность объекта):
- `page_blocks["<kind>:<uuid hex>"]`, kind ∈ product/service/stay/event/promo/tour — свои блоки объекта и якоря разделов
  (`siteconfig.py:1405-1407`, `object_structure.object_host :280`). Потолок 120 на все виды.
- `page_blocks["catalog:<slug>"]` — своя схема категории, ключ — **слаг** (`siteconfig.py:1385-1391`), потолок 120, слаг ≤ 60.
- `page_blocks["promo_group:<md5(ключа группы)>"]` — своя схема группы акций (`:1394-1396, 1447-1455`), потолок 40.
- `page_blocks["seite:<slug>"]` — блоки своей текстовой страницы (`:1401`), потолок 40.
- `i18n[<loc>]["page_blocks"][<хост>]` — переводы блоков, **позиционный** список рядом с блоками (`siteconfig.py:4728-4776`).
- `seo.pages[<хост>]` + `i18n[<loc>].seo.pages[<хост>]` — SEO текстовой страницы (`content_pages.py:170-360`).
- `promo_groups[<ключ группы>]` = строка-шаблон | `{style, layout, card}` (`siteconfig.py:5376-5421`), потолок 60.
- В превью: `_object_override[<hex>]` — черновик разделов объекта (`object_structure.py:47`, `aufbau_draft.py:358-365`); `normalize` его не хранит.

Уровень **типа страницы** (общий для всех объектов вида):
- `page_blocks["product_detail"|"service_detail"|"stay_detail"|"event_detail"|"promo_detail"|"combo_detail"|"blog_post"|"category"|"promo_group"|"info"|"versand"|…]` — фикс-хосты `PAGE_BLOCK_HOSTS` (`siteconfig.py:1286-1335`).
- `<kind>_detail` = `{hidden, order?, layout?}` — видимость/порядок разделов и шаблон детали (`siteconfig.py:2955-3013`; `_DETAIL_LAYOUT_KEYS :3076`).
- Флаги видимости разделов старыми ключами: `promo_show_share|card|related`, `combo_show_reviews|examples|cta|related`, `blog_show_more`, `about_contact`, `cart_show_upsell`, `confirm_show_recommend` (`detail_parts.py:87-106`).
- Настройки типа (окно «Seite» и строки разделов): `detail_related_layout`, `product_card_form`, сорт/фильтры/сетки и т.п. — реестр `studio_pages.PAGE_TYPES` (37 типов), `site_schema.SETTING_ROWS :4169`.
- Оси/виды: строки без `id` в хосте (`categories`, `page_head`, `combos`, маркер `main` с полями `style/grid/focus`, `offer` у акции) — `siteconfig.page_builtin_keys :1766`, `catalog_parts.py:120-184`, `promo_parts.py:91-143`.
- Старые коды шаблонов: `catalog_page_style`, `promo_page_style`, `page_styles`, `site_defaults.category_page_style|promo_group_style|promo_detail_style` (`siteconfig.PAGE_TEMPLATE_HOSTS :1548`) + поля `Category.page_style`, `Promotion.page_style`. По умолчанию **не читаются** (B3b): `page_axes_migration.legacy_reads :35-42` — только при `PAGE_LEGACY_READ=1` или внутри переноса/сверки.

Уровень **всего сайта**: `faq` (общие вопросы), `page_titles[хост]` (только листинги/формы, `page_title.HEAD_HOSTS :31`), `hero_banners`, `usp_bar`,
`block_templates`, `history` (8 снимков всего конфига, `siteconfig.py:2148`), `_draft` (автосейв Студии — полный конфиг внутри конфига, `views.py:4155`),
`site_defaults.card_style`, меню.

### 1.3 Реестры в коде
- Разделы: `detail_sections` + `detail_parts.SECTION_HOSTS :24-57` (event 17 разделов, product 11, service 7, stay 4, promo 4, combo 5, blog_post 2, info 2, versand 2).
- Виды объекта со «своей структурой»: `site_schema.OBJECT_KINDS :521`, `_OBJECT_MODELS :617`, `detail_parts.OBJECT_SHARED :138` (**без promo**), `object_structure.MODULES :22`, `LAYOUT_KINDS :37`, `aufbau_draft.OBJECT_EDIT_VIEWS :1556` (**без promo**), `siteconfig.OBJECT_HOST_KINDS :1405`. Шесть списков одного и того же — добавление вида = правка всех.

### 1.4 Сегодняшние ТРИ механизма (подтверждено кодом)
1. **Наложение** (product/service/stay/event/tour): разделы = общий `<kind>_detail` ± `page_override` (`object_structure.effective_hidden :121`, `effective_full_order :143`, `effective_layout :133`); свои блоки рисуются **вместе** с общими (`detail_parts.flow :325-351` — «у раздела сначала общие блоки, потом свои»; `siteui.object_blocks :620-645`). Общие правки доходят.
2. **Акция**: оси — слоями: свой код → общий хост → свой хост (`promo_parts.detail_parts :91-114`); блоки своего хоста — добавкой к `promo_detail` (`promotion_detail.html:318-320`).
3. **Категория — три независимых переключателя**: блоки «свои», если есть хоть один блок с `id` (`siteconfig.has_own_schema :1960`, `siteui.category_blocks :532-550` — **замена** общих); оси «свои», если `catalog_parts.has_parts` (`catalog_parts.py:187-194`); место баннеров — третье правило (`siteui.py:598-600`: иначе `"catalog"`, а не `shared_category_host`). Настройки типа (сетка, сорт, фильтры, форма карточки) — всегда общие.
4. **Группа акций**: своя, если ключ хоста просто есть в `page_blocks` (`siteui.promo_blocks :567-571`), пустой список хранится (`siteconfig.py:2136`); цепочка наследования `promo_group:<md5>` → `promo_group` → `promos` (`siteconfig.page_rows :1922-1945`).
5. **Текстовая страница**: свой хост без общего типа; «Über uns» = хост `info`, «Versand» = `versand` **или** `seite:versand`, если заказы выключены (`content_pages.schema_ref :700-711`).

---

## 2. Писатели и читатели

### 2.1 Писатели `page_override`
| Путь | Что пишет | file:line |
|---|---|---|
| «Seitenaufbau» → `aufbau_draft.commit` → `_commit_object` → `_commit_sections` | hidden/shown/order | `aufbau_draft.py:1598-1657` |
| Вкладка формы объекта → `object_structure.apply_post` | layout, blocks_first, сброс (+`card_style`) | `object_structure.py:191-224`; вызовы: `catalog/views.py:265`, `booking/views.py:1465`, `stays/views.py:1280`, `events/views.py:217, 668`, `promotions/views.py:1134` |
| **Любой `form.save()` ModelForm объекта** — полный UPDATE всех колонок, включая `page_override` из экземпляра начала запроса | затирает параллельную запись схемы | те же вьюхи (напр. `promotions/views.py:1130`) |
| Клон серии событий `clone.pk=None; clone.save()` | копирует `page_override` (но не блоки) | `events/services.py:530-537` |
| Наследник повторяющейся акции | **не** копирует `page_override` (нет в `_RECUR_CLONE_FIELDS`), копирует `page_style`, `card_style` | `promotions/tasks.py:137-171, 222-236` |

### 2.2 Писатели хостов объектов/категорий/групп/страниц в `site_config.page_blocks`
1. `aufbau_draft.commit` (сессия-черновик → под `select_for_update` Tenant) — `aufbau_draft.py:1398-1552`; `site_schema.store_items :4416`.
2. `site_schema.apply` — запись сразу; **в проде не зовётся** (только стенд `scripts/fb33_m39c_targets_stand.py:188`).
3. **Студия, Save** (`settings_site`): `merge_pages` по всем хостам формы, правит `data` блоков любого хоста, в т.ч. объектов — `views.py:2826-2876`, `site_schema.merge_pages :458`. Форма Студии рисует строки **всех** непустых хостов (`views.py:3285-3295`).
4. **Студия, `add_block` / `use_block_template`**: `page_key` проверяется только регэкспом `is_page_block_host` — **без проверки существования объекта и без потолков**, запись сразу в базу — `views.py:2324-2365, 2441-2452`. Ссылки в `templates/tenant/site_home.html` есть.
5. Студия, превью-черновик `site_preview_draft` и автосейв `_draft` (`views.py:4037-4044, 4136-4156`) — полный конфиг.
6. Студия, «Version wiederherstellen» — заменяет весь конфиг снимком из `history` и заново гонит `page_axes_migration.migrate(..., objects=build_index())` — `views.py:2578-2607`.
7. `object_structure.copy_blocks` (наследник акции, Celery beat) `:365-403`; `drop_blocks :297` (только удаление тура, `events/views.py:651`); `purge_ghost_hosts :308-357`.
8. `content_pages.move_page_blocks :362-400` — смена слага страницы (`:111`), удаление страницы (`content_page_views.py:271`), категория: `catalog/forms.py:178-191`, `catalog/views.py:1130, 1138, 1150`.
9. Шаг деплоя `materialize_page_axes` → `page_axes_objects.migrate_categories/promos/groups` (`page_axes_objects.py:162-390`) — **создаёт** хосты `catalog:<slug>`, `promo:<hex>`, `promo_group:<md5>`; он же зовётся из `page_settings._pin_own_categories :837` (правка «Alle Kategorien»), из восстановления версии и из сидера.
10. Сидеры: `demo_kits.py:25672-25689` (хосты из спеки, в т.ч. `catalog:<slug>`, id блоков `pb-kit-N`), `:25699-25707` (`migrate_objects`), `demo_i18n.py:236-271` (оверлеи).
11. Шаги деплоя, проходящие по всем хостам: `import_banners` (`banners.py:438-578`), `drop_stray_site_search`, `detach_quick_links`; `banners.delete :270-291` (чистит `pick` во всех хостах).
12. Импорт: `imports/cscart.py:1352-1395` (только `info`), `imports/site/apply.py:353`.
13. `page_settings.write/write_many/apply_override` (`:850-1011`), `siteconfig.set_page_template :1579` — пишут строки-оси общих хостов.
14. ИИ-помощник: `page_blocks` и `page_override` **не пишет** (grep пуст); пишет настройки типа `assistant_actions._write_page :893-908` и создаёт/мягко удаляет товары и категории (undo `:1179-1230` — `obj.delete()` без `move_category_blocks`).
15. Сигналов, пишущих структуру, нет. Сигнал `post_save Tenant` только сбрасывает кэш (`tenants/apps.py:31-36`).

### 2.3 Читатели
- **Витрина**: `siteui.page_blocks :350`, `object_blocks :620`, `category_blocks :532`, `promo_blocks :554`, `place_banners :576`; вьюхи деталей
  `promotions/public_views.py:482, 1668-1680, 2281, 2514-2523` (товар, категория, акция), `booking/public_views.py:888-994`, `stays/public_views.py:421-465`,
  `events/public_views.py:353-409, 1007-1102`, `content_page_views.py:42-58`; `detail_parts.page_ctx/own_anchors/own_tail :354-762`.
  Каждый читатель делает `siteconfig.normalize(raw)` всего конфига (иногда 2-3 раза на запрос: `detail_parts.py:365, 743`, `siteui.py:380, 544, 566, 597`).
- **Превью**: всё идёт через `page_settings.raw_config(request)` (`:1048-1107`): `?preview=1&aufbau=<code>` → `aufbau_draft.overlay`, Студия → сессионный конфиг целиком, `tpl=`, `stand=saved`.
- **Кабинет**: экран «Seitenaufbau» (`site_schema.blocks_for :1384`, `_with_shared_rows :3401`, `object_row :756`, `category_pages :803`, `promo_group_pages :854`, `text_pages :1010`), вкладка объекта (`object_structure.panel :227`, шаблон `templates/tenant/_object_structure.html`, 6 включений), Студия (`views.py:3285`), `window_links`, `block_i18n` (`:226-257, 838`), `banners.places :260`.
- **Команды**: `lmiv_info_audit` (`catalog/management/commands/lmiv_info_audit.py:38-39`), `materialize_page_axes --residue` (`page_axes_residue.py`).
- **Портал/агрегатор, фиды, экспорт/DSGVO, PDF**: `page_blocks`/`page_override` **не читают** (grep по `apps/aggregator`, `dsgvo_customer`, `documents`, фидам — пусто). Косвенно: `post_save` объекта шлёт пересинхронизацию листинга (§10.14).
- Медиатека `media_registry.py:17-107` — блоки `page_blocks` **не** сканирует (и сегодня).

---

## 3. Потолки, молчаливые потери, гонки, кэши

### 3.1 Потолки и обрезки
- Хосты: объекты 120, категории 120, страницы 40, группы 40 — срез **по алфавиту** в `siteconfig._page_block_hosts :1982-2004`. Проверка «места нет»
  есть только в `aufbau_draft.op` для категорий и объектов и только на `add/add_row/adopt` (`:1198-1210`). **В `commit` проверки нет** (`:1398-1552`),
  у `seite:` и `promo_group:` проверки нет вообще, у Студии `add_block` — тоже. Следствие: новый хост при полном потолке либо сам пропадает, либо
  **вытесняет чужой, алфавитно последний** (`event:` < `product:` < `promo:` < `service:` < `stay:` < `tour:`) — молча. [вывод из кода]
- 30 блоков на хост (`_MAX_CBLOCKS :185`, `:2108`); якорь раздела — один на раздел, без полей (`:2075-2080`); строка оси без вида не хранится (`:2099-2103`);
  якоря не хранятся, если ни один блок не стоит между разделами (`_compact_detail_anchors :1736`); пустой хост выбрасывается, кроме `category`,
  `promo_group`, `not_found`, `promo_group:*` (`:2136`); запрещённые блоки хоста (`banned_blocks :2029`); тексты блоков — `CBLOCK_TEXT_CAPS :601`.
- `object_lift`: нет своих блоков → `rows = []`, хост не пишется (`detail_parts.py:521-523`).
- `page_override.clean` выбрасывает неизвестные разделы: раздел, убранный из реестра релизом, тихо исчезает из отличий.
- Слаг категории > 60 знаков — своей схемы быть не может, при переименовании схема **удаляется** (`catalog/forms.py:182-191`; `Category.slug` max 100, `models.py:37`).
- Черновик: 10 черновиков на сессию (`aufbau_draft.MAX_DRAFTS :33`), живёт в сессии.
- `category_pages` — только активные, первые 200 по слагу (`site_schema.py:793, 810`); группы — 40 (`:824`); страницы — 200 (`:1028`).

### 3.2 Гонки и блокировки
- Порядок блокировок: строка `Tenant` → строка объекта (`aufbau_draft.py:1422`, `_lock_object :1631`). Формы объекта блокируют только объект (`object_faq.py:524`). Запись в поле объекта под блокировкой Tenant = весь сайт сериализуется на одной строке.
- Конфликт черновика: отпечаток `_saved_state` включает `page_override` объекта (`aufbau_draft.py:54-58`).
- Форма объекта ↔ схема: `apply_post` читает `_fresh` (`object_structure.py:60, 205`), но `form.save()` перед ним уже записал полную строку — окно гонки длиной в запрос [вывод].
- Студия ↔ схема: `structure_hash` по всему конфигу (`site_schema.py:189-231`, `views.py:2643-2644`) — предохранитель «два писателя» видит только `site_config`.
- Шаги деплоя: `config_migration.write_with_snapshot` — `lock_timeout 2s`, сверка хэша, снимок `SiteConfigSnapshot` только ключей конфига (`config_migration.py:78-116`).

### 3.3 Кэши
- Кэш HTML витрины `cache_storefront_page` стоит **только на главной** (`promotions/public_views.py:268`) + страница 404 (`pagecache.cached_not_found`). Ключ — версия `sfver:<schema>`.
- Версию поднимает: сигнал `post_save Tenant` при `site_config` в `update_fields` (`tenants/apps.py:31-36`), вручную — `page_settings :979-1010`, `assistant_actions :907`,
  `config_migration.bump :55`, галереи объектов (`catalog/views.py:1072`, `booking :1818`, `stays :1834`, `events :1213`, `promotions/views.py:56`), `publishing/tasks.py:184`, `closures.py:230`, `inline_edit.py:106`.
  **Обычное сохранение объекта версию не поднимает.** Детали объектов не кэшируются — запись структуры в поле объекта их не «заморозит»; но блок «Liste»/секции главной с этим объектом — да (TTL 120 с, `base.py:421`).
- Кэш запроса: `request._page_blocks_site` (`siteui.py:375-383`), `_aufbau_cfg`, `_stu19_tpl_cfg` (`page_settings.py:1068, 1081`), `_page_seo_memo`.
- Кэш процесса: только константы кода (`site_schema.py:720, 4325`, `siteconfig.py:352, 3282`).

### 3.4 Удаление / корзина / слаг / переименование
- Product, Promotion, Category, Combo — мягкое удаление (`SoftDeleteMixin`, `core/models.py:107-146`), `objects` = только живые. **`restore()` в коде никто не зовёт** (grep) — корзины-экрана нет.
- Товар/акция удалены мягко → хост остаётся до `purge_ghost_hosts` (только когда потолок полон). Категория → хост удаляется сразу. Тур → `drop_blocks` в транзакции. Service/StayUnit/Event — вызова `drop_blocks` при удалении нет.
- Слаг категории: `CategoryForm.save` → `move_category_blocks` (+ `banners.rename_place`). Правка слага мимо формы (импорт, ассистент, admin) хост не переносит [вывод].
- Слаг страницы: `content_pages.save_page :109-111` → `retarget_menus` + `move_page_blocks` (+ SEO и его переводы `_move_seo`).
- Группа акций: модели нет; «переименование» = правка `Promotion.group` у акций → новый md5 → своя схема **осиротела** (хост остаётся и занимает потолок; `promo_groups[старый ключ]` — тоже). Механизма переноса нет (grep `rename` пуст).

---

## 4. Права и IDOR

| Путь записи | Право | Проверка объекта |
|---|---|---|
| «Seitenaufbau» (`site-schema`) — блоки любого хоста | `website.edit` (`view_perms.py:382`) | `site_schema.resolve`/`host_for :1079-1128`: объект/категория/живая группа/страница существуют, тип активен |
| то же — разделы объекта (`page_override`) | + право формы объекта (`sortiment.edit`) — `aufbau_draft._commit_sections :1653`, `OBJECT_EDIT_VIEWS :1556` | под `select_for_update` |
| то же — свои вопросы FAQ объекта | `object_faq` своё право (`object_faq.py:891`) | |
| Вкладка формы объекта | product/service/stay/event/tour/category/combo/teacher — `sortiment.edit`; promo, blog — `marketing.edit` (`view_perms.py:188-362`) | `get_object_or_404` |
| Свои страницы (текст, слаг, удаление) | `seiten.edit` — «по умолчанию только владелец» (`view_perms.py:49, 400-408`) | |
| Студия Save / `add_block` | `website.edit` | **только регэксп хоста** — можно создать хост несуществующего объекта/категории/страницы (`views.py:2333`) |
| Превью `?aufbau=`, `?tpl=` | `website.view` (`page_settings._may_preview :1034`) | |

Следствие для M6: сегодня блоки объекта = «содержимое сайта» (`website.edit`), запись идёт в `site_config`. Если структура переедет в поле `Product/Promotion/ContentPage/...`,
сотрудник с `website.edit` без `sortiment.edit`/`marketing.edit`/`seiten.edit` начнёт писать в строки объектов. У акции права «на объект» в `OBJECT_EDIT_VIEWS` нет вовсе.

---

## 5. Модели-цели

| Модель | app · file:line | Последняя миграция app | Менеджер | PK / адрес | Детальная · общий хост · тип | Сегодня «своё» |
|---|---|---|---|---|---|---|
| Product | catalog · `models.py:141` | `0046_fb33_product_faq` | SoftDelete (`objects`=живые) | UUID; `/sortiment/<uuid>/` + slug-маршруты | да · `product_detail` · `product` | `page_override` + `product:<hex>` |
| Category | catalog · `:25` | 0046 | SoftDelete; слаг уникален среди живых | UUID; `/sortiment/<slug>/` | да · `category` (→`catalog`) · `category` | `catalog:<slug>` + `page_style` |
| Combo | catalog · `:974` | 0046 | SoftDelete | UUID; `/kombi/<uuid>/` | да · `combo_detail` · `combo` | нет |
| Service | booking · `:124` | `0045_fb29_page_override` | обычный | UUID; `/leistung/<uuid>/` | да · `service_detail` · `service` | `page_override` + `service:<hex>` |
| StayUnit | stays · `:52` | `0049_fb33_unit_faq` | обычный | UUID | да · `stay_detail` · `stay` | то же |
| Event | events · `:234` | `0039_fb29_tour_page_override` | обычный | UUID; `/veranstaltung/<uuid>/` | да · `event_detail` · `event` | то же |
| Tour | events · `:31` | 0039 | обычный | UUID; `/tour/<slug>/` | да · делит `event_detail` и тип `event` | то же (`tour:<hex>`) |
| BlogPost | events · `:1035` | 0039 | обычный | UUID; `/blog/<slug>/` | да · `blog_post` · `blog_post` | нет |
| Teacher | events · `:879` | 0039 | обычный | UUID; `/lehrer/<uuid>/` | **шаблон без блоков, типа страницы нет, хоста нет** (`lehrer_detail.html` не зовёт `page_blocks`; `storefront-teacher` нет в `PAGE_TYPES`) | нет |
| Promotion | promotions · `:245` | `0037_fb29_page_override` | SoftDelete | UUID; `/p/<uuid>/` | да · `promo_detail` · `promo` | `promo:<hex>` + `page_style` + `blocks_first` |
| ContentPage | core · `:506` | `0021_banner_show_on` | обычный; `slug` unique, max 80 | UUID; `/<slug>/` | да · общего типа **нет** («text» = хост `info`); правовые — `LegalDoc`, без хоста | `seite:<slug>` |
| PromoGroupPage | **не существует** (grep) | promotions 0037 → 0038 | — | группа = свободный текст `Promotion.group` (max 50) + встроенные `sys:*` | — · `promo_group` | `promo_group:<md5>` + `promo_groups[key]` |

Что большое: Product (импорт CS-Cart, тысячи строк, грузится списками на витрине/в фидах/портале/поиске), Event (серии-клоны), Promotion (ежедневные наследники),
Ticket и т.п. не затронуты. Category/Service/StayUnit/Tour/Combo/BlogPost/Teacher/ContentPage — десятки строк.
11 аддитивных `ADD COLUMN` × ~136 схем; прецедент `db_default` (комментарии у всех шести `page_override`: «во время деплоя старые контейнеры ещё пишут строки без этого поля»).
Новая TENANT-модель попадёт и в шаблонную схему (`ensure_template_schema`, `deploy.sh:180-191`).

---

## 6. Переводы блоков

- Адресация: `i18n[<loc>]["page_blocks"][<хост>][<позиция>]["data"][<поле>]` — **по позиции** в списке хоста (`block_i18n._block_path :838`, `siteconfig.localize :4785`, `_deep_overlay`).
- Перестановка/вставка/удаление: любой писатель обязан позвать `siteconfig.realign_block_overlays` ДО замены списка — переносит перевод за блоком по `id`
  (`_item_identity :4458`; блоки с одинаковым `id` сводятся на первое вхождение — `setdefault`, `:4746`). Зовут: `store_items`, `overlay`, Студия (4 места), пресеты.
- Удаление блока — перевод исчезает (хвост без переводов не хранится). Удаление хоста — `move_page_blocks`/`purge_ghost_hosts`/`_drop_hosts` чистят оверлей вручную.
- Копирование: `copy_blocks` копирует оверлей хоста и **сохраняет `id` блоков** (`object_structure.py:393-398`); `category_items("adopt")` даёт новые `id` и **переводы не копирует** (`site_schema.py:993-996`); `page_axes_objects._copy_overlays :403` — отдельная реализация для переноса.
- Правка немецкого текста снимает перевод поля (`block_i18n`, решение владельца в докстринге `:3-5`); Save Студии на языке перевода — `split_translation`/`_split_blocks :4610`.
- Свои вопросы FAQ объекта — переводы в самом объекте (`faq_i18n`, позиционно) — единственный пример «перевод рядом со структурой в поле объекта».
- Заголовки/вступления листингов (`page_titles`), SEO страниц, `usp_bar`, пункты секций главной — отдельные пути оверлея (`block_i18n.py:13-37`).

---

## 7. Деплой

Порядок `scripts/deploy.sh`: [1] pull → [2] build → [3] db → [4] `check --deploy` → [5] `migrate_schemas --shared` → [6a] `ensure_template_schema` →
[6b] `migrate_schemas --tenant --executor=multiprocessing` (пропуск, если `migration_state --check` чист; повтор по одной при сбое; всё под `run_locked`) →
[6c] `detach_quick_links` (+`--residue`) — **до** подъёма нового web → [7] `up -d` → [8] `migration_state`, `import_banners`, `materialize_page_axes` (+`--residue`),
`form_i18n_realign`, `drop_stray_site_search` (`deploy.sh:164-296`).

- Между [6b] и [7] работает **старый** web на новой схеме БД. Два прецедента размещения переноса данных: «до web» (6c — новый код ключ не читает) и «после web» (form_i18n_realign — старый код ключ стёр бы). В обоих случаях в комментариях расписано окно.
- Шаги, которые уже пишут хосты объектов: `materialize_page_axes` (каждый деплой; создаёт `promo:<hex>`, `catalog:<slug>`, `promo_group:<md5>`; статус `hosts_full` → сайт пропускается), `import_banners`, `drop_stray_site_search`.
- Незавершённое FB-31.7: чтение старых кодов в коде уже снято (B3b, `legacy_reads`), но (а) шаг деплоя остаётся, (б) поля `Category.page_style`/`Promotion.page_style` и ключи конфига не снесены, `_RECUR_CLONE_FIELDS` продолжает копировать `page_style`,
  (в) `--residue` считает остаток: расхождения вида, неактивные и удалённые в корзину объекты со своим кодом, старые коды в `history` и `_draft`, откаченные снимки (`page_axes_residue.py:102-156`),
  (г) прогон на сервере — за владельцем (CLAUDE.md §3). `--undo` после B3b требует `PAGE_LEGACY_READ=1` (`materialize_page_axes.py:44-51`).
- Снимки и откат шагов — `SiteConfigSnapshot` (tenants `0043`), хранит **только ключи `site_config`**; отката для строк объектов механика не знает (`config_migration.py:118-156`).
- Сидеры: 79 демо-бизнесов; смена спеки → `SEEDER_VERSION` (сейчас 24, `demo_fingerprint.py:26`) → `seed_demo_tenants --group all --changed --jobs 3`.

---

## 8. Тесты и эталоны (grep)

- Всего тест-файлов: 1416.
- `page_override|object_structure`: **26 файлов** — core 22, catalog 1, booking 1, events 1 + `test_fb31p5_object_golden.py`.
- Хосты объектов (`is_object_host`, `object_host(`, `_object_for`, `copy_blocks`, `purge_ghost`, `drop_blocks`): ≈ 25 файлов core (+ `tenants/tests/test_fb31p3_storage.py`, `promotions/tests/test_fb31p3_promo_golden.py`, стенд `scripts/fb33_m2b2b_faq_stand.py`).
- Хосты категорий/групп (`has_own_schema`, `category_items`, `promo_group_host`, `catalog:<…>` …): **54 файла** (core 41, catalog 5, tenants 2, promotions 1, publishing 1, скрипты 3).
- `seite:` / `move_page_blocks`: **28 файлов**.
- `page_blocks` вообще: core 102, tenants 16, promotions 6, catalog 3, events 2, imports 1, 6 стендов.
- Каталоги эталонов (файлов): catalog `golden_fb3016` 79; promotions `golden_fb31p3` 49, `golden_fb31p4` 20; tenants `golden` 4, `golden_fb32` 5;
  core `golden_fb31p5` 94, `golden_fb33m2d` 54, `golden_fb33m35c` 41, `golden_fb33m3` 37, `golden_fb32s6` 33, `golden_lb4c` 21, `golden_fb33m2b2a` 18, `golden_fb33m2g` 18,
  `golden_fb33m2i5b` 13, `golden_fb33m2i` 12, `golden_fb33m2h` 12, `golden_fb33m2i5` 11, `golden_fb33m5d2` 11, `golden_fb33e3` 5, `golden_fb33m2b2b` 5, по 1 — `fb31p4`, `fb33m35b`, `fb33s16t3`, `s15_m5e1a`.
  Буквальный хост объекта/категории в эталоне — только 2 файла (`golden_fb32s6`, `golden_fb33m5d2`); остальные завязаны на отрисовку детальных (`golden_fb31p5` — главный сторож «вид не изменился»).
- Сторожа-замки, которые сработают: `test_fb29_object_structure.py`, `test_fb31p5_object_schema.py`, `test_fb317_b1b2_migrate.py`, `test_fb31p6_studio_writers.py`, `test_fb29_leftovers.py`, `tenants/tests/test_normalize_golden.py` (любой новый ключ normalize), `test_media_registry_map_covers_known_fields`.

---

## 9. Отложенное в roadmap (`docs/roadmap-next-sprints.md`), которое M6 задевает

- `S14-E4-route-fp` (⏳, :566) — форма тура пишет маршрут и разделы структуры без сверки: с полем `structure` тот же класс гонки (§10.6) — закрыть вместе.
- `S14-E1-L6` (⏳, :575) — ⚙ на ключ страницы не несёт `von`, окно «Seite» правит настройки **типа**: у отвязанной копии это противоречит «общие правки не действуют» (§10.3).
- `S15-von` (⏳, :562) — `von` принимает несуществующую текстовую страницу: тот же путь адресации страниц по слагу.
- `S16-realign-dup` (⏳, :663) — `realign_*` сводит элементы с одинаковым ключом на первое вхождение: копии блоков с теми же `id` (§10.9).
- `S15-draft-fp` (⏳, :555) — восстановленный черновик Студии без отпечатка: Студия-черновик и структура объекта (§10.5).
- `S16-hreflang` (⏳, :662) — переводы SEO страницы: `seo.pages[seite:<slug>]` едет вместе со страницей, если структура страницы уйдёт в `ContentPage`.
- Уже закрыто, но держит инварианты, которые M6 обязан сохранить: `S14-E2-ghost` (ссылка на окно проверяет существование через `host_for`), `S14-E1-text` (`text@seite:<slug>`), `S15-versand`/`S15-versand-gear` (два хоста «Versand»), `S15-upper-slug` (один регэксп хоста страницы), `S14-E8-cleanup` (разовая чистка конфигов шагом деплоя).
- Строк с «M6» в roadmap нет (grep).

---

## 10. Сюрпризы и ловушки

**10.1 «Наивный перенос» молча отвязывает объекты.** Сегодня `page_override` непуст у объекта с любым пустяком (`layout`, `blocks_first`, один скрытый раздел). Правило «непусто → своя структура = полная отвязанная копия» разом заморозит эти объекты: общие правки схемы до них больше не дойдут. Серии событий: клон копирует `page_override` (`events/services.py:530-537`) — отвязанными станут все повторы. Нужен счёт на проде (`--dry-run`) до решения «что считать своей структурой».

**10.2 Копия ≠ то, что сегодня видит посетитель, без сверки.** Сегодня страница объекта = общие блоки + свои (наложение, `detail_parts.flow`). Полная копия должна включить общие блоки `<kind>_detail` (новые `id`? — см. 10.9), их переводы, якоря, общий `hidden/order/layout`, оси. У FB-31.7 есть готовый образец «сверка вида до/после, расхождение — сайт не трогается» (`page_axes_migration`, `render_path`); без неё перенос вслепую.

**10.3 «Оси/виды» в копии: настройки ТИПА останутся общими.** У строки объекта настройки типа запрещены (`site_schema.setting_codes :4257`, `row_settings :4179`), у строки категории/группы — **разрешены и пишут тип** (8 настроек `category`). Сетка, сортировка, фильтры, форма карточки, `detail_related_layout`, флаги `promo_show_*`/`combo_show_*`/`blog_show_more`/`about_contact` — ключи конфига уровня типа. «Отвязанная» страница продолжит меняться от общих правок, пока эти ключи не скопированы в структуру и у всех читателей не появится вторая ветка.

**10.4 Категория — три независимых «своих» состояния** (блоки / оси / место баннеров, §1.4) и «adopt» копирует только блоки с `id` (маркер — голый, оси и переводы не копируются, `site_schema.category_items :971-999`). Перенос должен свести четыре сочетания к одному флагу; «своя по осям, блоки общие» требует копии общих блоков, «своя по блокам, оси общие» — заморозки осей.

**10.5 Студия — второй писатель и второй черновик, оба на уровне конфига.** Save Студии правит `data` блоков любого хоста (`views.py:2826-2876`), её форма рисует строки всех хостов, превью подменяет конфиг целиком сессионным, `_draft` лежит внутри `site_config`, «Version wiederherstellen» заменяет конфиг снимком и **заново создаёт хосты объектов** (`views.py:2578-2607`). После переезда: (а) тексты/фото блоков объекта в Студии некуда писать; (б) восстановление до-M6 версии вернёт хосты в конфиг; (в) идемпотентный шаг переноса на следующем деплое перезапишет более новую структуру объекта старыми блоками, если не проверяет «поле уже занято»; (г) история версий перестаёт откатывать страницы объектов; (д) `structure_hash` не увидит правок структуры объекта.

**10.6 Полный `save()` затирает поле.** Формы объектов — ModelForm с `form.save()` (все колонки); клон серии, наследник акции, импорт (`imports/site/apply.py:310`, `cscart.py`) — тоже полные `save()`. Поле, которое правится только на «Seitenaufbau», будет перезаписано устаревшим значением из экземпляра, загруженного до правки. Сегодня это окно есть для `page_override` и частично прикрыто `_fresh` (`object_structure.py:60`), у большого `structure` цена выше. Нужен замок «никто, кроме `object_structure`, не пишет колонку» + `update_fields`/`defer`.

**10.7 Потолки сегодня теряют данные молча — и перенос их унаследует.** Срез хостов по алфавиту без проверки в `commit`, без проверки у `seite:` (40) и `promo_group:` (40), без проверки у Студии (§3.1). На проде уже могут быть вытесненные хосты и хосты-призраки (Service/StayUnit/Event без `drop_blocks`; мягко удалённые товары/акции до первой чистки; undo ассистента; группы после смены `Promotion.group`). Перенос должен отчитаться: «хост без живого объекта», «хост сверх потолка», а не молча пропустить.

**10.8 Ежедневные акции съедают потолок.** `copy_blocks` на каждого наследника (`promotions/tasks.py:236`), завершённые акции живы (не призраки) → +1 хост в день; при полном потолке наследник молча остаётся на общей схеме (`object_structure.py:389-393`, только warning). После M6 `copy_blocks` надо заменить копированием поля, а `structure` добавить в `_RECUR_CLONE_FIELDS` (сейчас там нет даже `page_override` — `blocks_first` у наследника теряется).

**10.9 `id` блоков не уникальны между хостами, а код местами считает, что уникальны.** `copy_blocks` сохраняет `id`; сидеры дают `pb-kit-1…` в каждом хосте (`demo_kits.py:25680-25687`). Студия адресует блок только по `id` (`pb_page_<id>`, `_stored_cblock_data :841-848` — первый найденный по всем хостам). Полная копия общей схемы в объект с теми же `id` размножит коллизии; с новыми `id` — надо переносить переводы вручную (`realign` их не найдёт).

**10.10 Переводы блоков живут не в блоке.** Позиционный оверлей в `site_config.i18n` (§6). Поле `structure` должно нести собственный оверлей и собственные `localize` / `realign` / `split_translation` / пути `block_i18n` / `hero_tiles.prune_label_overlays` / `demo_i18n`; иначе после переезда блоки объекта станут немецкими на всех языках. `move_page_blocks`, `purge_ghost_hosts`, `_drop_hosts`, `copy_blocks`, `_copy_overlays` — пять разных ручных реализаций «перенеси хост вместе с переводами».

**10.11 Сквозные обходчики конфига перестанут видеть блоки объектов.** `banners._picks/_banner_blocks` (удаление баннера чистит `pick` — `banners.py:270-291`; «где показан» — `:260`; `import_banners`), `place_block_present` (`:928-942`, читает `"<kind>:<hex>"` и `catalog:<slug>` из конфига), `list_blocks._list_blocks_of :1297` и `apply_type_scope`, `check_changed_pages`/`page_embeddable` (блок «Von einer Seite»), `drop_stray_site_search`, `detach_quick_links`, `demo_i18n`, `block_i18n`, Студия. Каждый будущий «разовый перенос формата блоков шагом деплоя» придётся гонять ещё и по строкам объектов во всех 136 схемах.

**10.12 `normalize` — единственный валидатор и одновременно «миграция при чтении».** Блоки чистятся `normalize_page_blocks` на каждой записи и на каждом чтении витрины (старые формы, запреты хоста, алиасы типов). Структура в поле объекта вне `normalize` = невалидированные данные навсегда; внутри — нужен свой normalize с **ключом хоста** (правила зависят от хоста: `banned_blocks`, `page_builtin_keys`, якоря, оси) и для видов, которых среди хостов нет.

**10.13 Правовые и «нескрываемые» инварианты привязаны к общему пути.** LMIV: раздел `info` у еды нельзя скрыть (`detail_parts.FOOD_LOCKED :129`, `object_structure.effective_hidden :130`, команда `lmiv_info_audit` читает `page_override`); `hideable=False` разделы; закреплённые строки и порядок (`PINNED`, `FIXED_ORDER`, `KAUF_FIRST`); § 312j. Читатель копии обязан применять те же фильтры, иначе отвязанная страница сможет скрыть обязательное. Отдельно: что делать с **новым разделом реестра**, которого нет в старой копии (сегодня — «новые в конец», `object_structure.effective_full_order :143-151`).

**10.14 Сохранение объекта — не бесплатное.** `post_save` Promotion/StayUnit/Event/Combo шлёт пересинхронизацию листинга портала на каждое сохранение, дедуп по `updated_at` (`aggregator/tasks.py:834-900`); у Product/Category — фильтр по `update_fields` (`:1671-1711`). Массовый перенос через `.save()` = шторм задач на 136 схем; через `.update()` — мимо сигналов (правильно) и мимо `auto_now`. `_commit_object` дописывает `updated_at` «как у формы (sitemap, портал)» (`aufbau_draft.py:1626-1628`).

**10.15 Кэш главной.** Версию кэша витрины поднимает запись `site_config`; запись поля объекта — нет. Детали не кэшируются, поэтому «не обновилось» всплывёт только на главной (и 404) и только если структура объекта влияет на то, что там рисуется; но писатель `object_structure` обязан сам звать `bump_storefront_cache` в `on_commit` (образец `page_settings.py:987`), иначе поведение разойдётся с нынешним.

**10.16 Права меняют смысл.** Сегодня `website.edit` пишет блоки объекта в `site_config`; завтра тот же сотрудник будет писать колонку Product/Promotion/ContentPage (`seiten.edit` — «только владелец»), меняя `updated_at` объекта. У акции нет записи в `OBJECT_EDIT_VIEWS`, у Category/Combo/BlogPost/ContentPage/Teacher — тем более. Решить явно: какое право на «сделать свою структуру» и на «вернуть общую».

**10.17 Группа акций — не объект.** Ключ = свободный текст `Promotion.group` либо встроенный `sys:*` (у встроенных нет ни одной акции-«носителя»); хост = md5 ключа; настройки вида лежат рядом в `promo_groups[key]` (тоже по ключу); живость группы считается запросом по акциям (`site_schema._live_promo_groups :838`). `PromoGroupPage` должна решить: ключ (текст ≤ 50, уникальность, пробелы — «Sale» и «Sale » сегодня разные хосты, `siteconfig.py:1451-1453`), судьбу при смене/исчезновении группы, слияние с `promo_groups[key]`, цепочку наследования из трёх звеньев (`promo_group:<md5>` → `promo_group` → `promos`).

**10.18 Текстовые страницы: общего типа нет, а системные страницы — не строки.** «Über uns» живёт на хосте `info` (строка `ContentPage(slug="ueber-uns")` может не существовать), «Versand» — на `versand` **или** `seite:versand` в зависимости от модуля заказов (`content_pages.schema_ref :707-710`); правовые — `LegalDoc`, без блоков (решение «право должно быть видимым», `siteconfig.py:1283-1285`). «Свои страницы наследуют общий тип „Textseite“» (решение 9) требует нового общего хоста, которого в `PAGE_BLOCK_HOSTS` нет, и правила «чьи блоки были на странице до переноса».

**10.19 Teacher, Combo, BlogPost.** У Teacher нет ни типа страницы, ни хоста, ни вызова блоков в шаблоне — «своя структура» у него = сначала завести общую. У Combo/BlogPost есть общий хост и разделы, но нет ни одного из шести реестров вида объекта (§1.3) и адрес BlogPost/Tour — по слагу, не по pk (`_OBJECT_PREVIEW_ROUTES :613`, `_own_code :944`).

**10.20 Шаг `materialize_page_axes` и откаты.** Он идёт на каждом деплое и создаёт хосты объектов; `--undo` и `SiteConfigSnapshot` возвращают старые ключи конфига; `page_settings._pin_own_categories` и сидер зовут тот же код. После M6 они либо пишут мимо нового хранилища, либо воскрешают хосты. Порядок шагов и «кто истина» надо решить до кода; сам FB-31.7 не закрыт (поля `page_style` на месте, остаток не подтверждён на сервере).

**10.21 Окно деплоя.** Между миграцией и подъёмом web старый код читает только хосты в `site_config`. Перенос «до web» (как 6c) — свои блоки пропадают с витрины на время шага; «после web» (как шаг 8) — новый код обязан читать оба хранилища, а старый web успевает писать хосты. И в обоих вариантах открытые сессии держат черновики «Seitenaufbau» старой формы (`aufbau_draft` в сессии; прецедент совместимости — `_rename_legacy_title :169`, `_base_fingerprint :80`).

**10.22 Размер строки в горячих запросах.** Комментарий в коде объясняет потолок 120 так: «объектов тысячи, а конфиг читается на каждом запросе» (`siteconfig.py:1402-1404`). Поле в Product решает это, но Product грузится списками (витрина, фид Google, портал, поиск); полная копия схемы с текстами блоков (до 30 блоков × 20 000 знаков, `CBLOCK_TEXT_CAPS`) поедет в каждый список без `defer`. `.only()/.defer()` по этим моделям в коде всего 15 мест.

**10.23 Адресация страниц в «Seitenaufbau» завязана на хост-строку.** Код строки `kind@kind:<hex>`, `category@catalog:<slug>`, `promo_group@promo_group:<md5>`, `text@seite:<slug>` — он же ключ черновика в сессии, параметр `?seite=`, `von`, ссылки ⚙ Студии (`window_links`), `data-pb-host` витрины, `it.host` в потоках шаблонов (`_detail_sections.html`, `event_detail.html`). «Хост» останется виртуальным именем даже после переезда хранилища — убрать его из `is_page_block_host` нельзя, пока все эти места не переведены.

**10.24 Сброс сегодня неполный, и это зашито в тексты и тесты.** «Zurück zum Standard» не трогает свои блоки и у акции не трогает оси (`object_structure.py:218-223`, текст в `_object_structure.html`), заодно сбрасывает `card_style`. Решение владельца — «сброс целиком» и правка только на «Seitenaufbau»: вкладка формы (шаблон `layout`, галочка `blocks_first`, кнопка сброса) — в шести формах, с сентинелом `page_override_present`.

**10.25 Мелкое, но чинить потом в проде.** `detail_parts.object_for_host` → `model.objects` (живые): мягко удалённый объект в окне «Seitenaufbau» даёт «объекта нет» — блоки сохраняются, разделы молча нет (`aufbau_draft.py:1613-1618`). Слаг категории освобождается при мягком удалении — новая категория с тем же слагом получила бы чужую схему, если хост не снят (поэтому `move_category_blocks(…, None)` в трёх местах; обходные пути удаления его не зовут). `site_schema.apply` — мёртвый для прода писатель, живой для стендов.
