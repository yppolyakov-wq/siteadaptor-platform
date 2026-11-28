# FB-33 M6 «своя структура объекта» — план-док (независимый второй прогон, 2026-11-27)

Только проектирование. Реализация — стопка 18 (товар, услуга, номер, событие, тур, акция, категория,
группа акций; перенос; интерфейс) и стопка 19 (Kombi, блог, «Textseite», «Lehrer», вынос хостов
страниц). Кода и миграций в этом документе нет. Утверждение о коде — с `file:line` (проверено
чтением) либо с пометкой «предпосылка — проверить в срезе». Тексты интерфейса — дословно с
артбордов M6Struktur / M6Zurueck / M6Wo / M6Phone.

Коротко о решении:
- **Хранилище** — поле `structure` (JSON, `db_default={}`) у объекта; у группы акций — новая модель
  `PromoGroupPage`. В `site_config` новых ключей нет.
- **Три состояния по одному полю**: `{}` — «не тронуто» (читаются старые данные, если они есть);
  `{"v": 1}` — «наследует, старое не читать»; `{"v": 1, "rows": […], …}` — своя структура.
  Признак переноса лежит в самом объекте, отдельного флага сайта нет.
- **Структура = фрагмент конфига страницы** той же формы, что ключи `site_config`. Читается одной
  проекцией в `page_settings.raw_config` (все читатели витрины ниже не меняются), пишется одним
  писателем `object_structure.write`.
- **Старые данные не трогаем до стопки 20**: хосты `<kind>:<hex>`, `catalog:<slug>`,
  `promo_group:<md5>`, `page_override`, `promo_groups[key]` остаются на месте и читаются только у
  объектов с `structure == {}`.

## 0. Вводы

### 0.1. Решения владельца (обязательны; номера — как во вводе)
1. Своя структура = полная отвязанная копия общей (разделы, порядок, блоки, виды разделов и настройки
   типа страницы), плашка, сброс целиком. У товара и номера порядок разделов закреплён (двигаются
   только свои блоки между разделами).
2. Перенос уже настроенного — автоматически, шагом `deploy.sh` (`--dry-run`, идемпотентно); без
   отличий — наследует; старые данные читаются до уборки (стопка 20).
3. Группа акций — новая модель `PromoGroupPage`.
4. Kombi и блог — своя структура в стопке 19.
5. «Textseite» — общий тип: наследуют `seite:<slug>`, «Über uns» (+ контакт закреплён), «Versand»
   (+ стоимость закреплена, PAngV); страница с блоками → своя структура, пустая → наследует;
   правовые — без блоков.
6. «Lehrer» — общий тип + своя структура у Teacher, стопка 19.
7. Правится только на «Seitenaufbau»; вкладка «Seitenaufbau» формы объекта снимается, вместо неё —
   строка «Seite im Shop» с состоянием и ссылкой; форма структуру не пишет. «Kartenform» остаётся
   полем формы.
8. Категории — `Category.structure` в стопке 18; места баннеров `category:<slug>` не трогать.
9. A2: первая правка на странице объекта сама делает копию.
10. Студия структуру объекта / категории / группы не правит.
11. Права: `website.edit` + право на сам объект; имена объектов в «Gilt für …» — только при праве
    просмотра объекта.
12. Выкат стопки 18 одним деплоем, вне пиковых часов, после замера миграций на стенде.
13. Сброс места баннеров («Wo zeigen») не трогает.
14. Разделы Kombi и «Textseite» в стопке 19 раскрепить.
15. Своя страница группы акций после удаления последней акции остаётся.
16. Счётная фраза: n = 1 «Änderungen hier gelten dort nicht.», иначе «… für diese %(n)s nicht.»;
    ⠿ — без фокуса, как сегодня.

Исходное решение 7 и «хранилище»: `docs/fb33-editor-model-2026-11-19.md:27-29, 115-125`.

### 0.2. Что не читалось (условие независимого прогона)
`docs/fb33-m6-plan-2026-11-27.md`, строки «M6» журнала, запись «стопка 17» `build-log`, строки 17–19
`fb33-handoff` и `fb33-map`, строка «M6-0» каталога, старый scratchpad `m6/`. Одна строка журнала
про M6-0 попала в вывод `scripts/codemap.py apps/core/object_structure.py` (раздел «Находки
журнала») — решений по ней не принималось, расписывать старые тесты по срезам (§13) требует и
`sa-increment` без неё.

## 1. Опорные факты кода (проверено чтением)

- Сегодня у объекта нет копии: разделы = общий `<kind>_detail` ± отличия `page_override`
  (`apps/core/object_structure.py:121-151`), свои блоки рисуются вместе с общими — «у раздела
  сначала общие блоки, потом свои» (`apps/core/detail_parts.py:325-351`).
- Свои блоки объекта лежат в `site_config.page_blocks["<kind>:<hex>"]`
  (`apps/core/object_structure.py:280-284`); читает тег `object_blocks`
  (`apps/tenants/templatetags/siteui.py:620-645`).
- Категория: своя схема заменяет общую, если в хосте есть блок с `id`
  (`apps/tenants/templatetags/siteui.py:532-550`); группа акций — если ключ хоста просто есть
  (`:554-571`); место баннеров категории — третье правило (`:598-600`).
- Вся витрина и превью берут конфиг через `page_settings.raw_config(request)`
  (`apps/core/page_settings.py:1048-1107`); превью «Seitenaufbau» —
  `aufbau_draft.overlay(saved, draft)` (`apps/core/aufbau_draft.py:335-375`).
- Запись «Seitenaufbau»: `aufbau_draft.commit` под блокировкой строки `Tenant`, затем объект
  (`apps/core/aufbau_draft.py:1398-1470`, `_commit_object :1598-1628`, `_lock_object :1631`); разделы
  объекта требуют право формы объекта (`_commit_sections :1653`, `OBJECT_EDIT_VIEWS :1556-1562` — без
  акции и категории).
- Отпечаток черновика включает `page_override` объекта (`apps/core/aufbau_draft.py:54-58`).
- Прецедент «поле пишет только свой писатель, полный `save()` его не перетирает»:
  `Tenant.SELF_MANAGED_FIELDS` и `Tenant.save` (`apps/tenants/models.py:446-457`).
- Клон серии событий ставит `clone._state.adding = True` и делает полный `save()`
  (`apps/events/services.py:530-537`) — значение поля уезжает в клон как есть.
- Наследник повторяющейся акции: `Promotion(**поля из _RECUR_CLONE_FIELDS)`, затем
  `object_structure.copy_blocks("promo", promo, heir)` (`apps/promotions/tasks.py:138-236`).
- Порядок `scripts/deploy.sh`: миграции схем [6b] → `detach_quick_links` [6c] → `up -d` [7] →
  `import_banners`, `materialize_page_axes` (+`--residue`), `form_i18n_realign`,
  `drop_stray_site_search` [8] (`scripts/deploy.sh:193-296`).
- Сверка «вид до == вид после» в переносе FB-31.7 уже нормализует `data-pb-host`
  (`apps/core/page_axes_migration.py:454`); атрибут рисуется всегда
  (`templates/storefront/_page_blocks.html:6,18`).
- `page_axes_objects.migrate_categories` создаёт хосты `catalog:<slug>` и зовётся ещё и из
  `page_settings._pin_own_categories` (`apps/core/page_axes_objects.py:162-200`,
  `apps/core/page_settings.py:837-847`).
- Приёмники портала фильтруют по `update_fields` только «не None и не пересекается»
  (`apps/aggregator/tasks.py:1672-1673, 1711`) — полный список полей для них равен `None`.
- Миграция-образец аддитивного JSON-поля: `apps/booking/migrations/0045_fb29_page_override.py`
  (`db_default={}`, `default=dict`).
- Права: `catalog:product-edit`… — `sortiment.edit`; `promotions:promotion-edit` — `marketing.edit`
  (`apps/core/view_perms.py:356`); `catalog:category-edit` (`:237`), `catalog:combo-edit` (`:247`),
  `events:teacher-edit` (`:220`); свои страницы — `seiten.edit` (`:49, 400-406`).
- Настройки сайта «Design» общие и в панель страницы не входят: `page_settings.DESIGN_SETTINGS`
  (`apps/core/page_settings.py:1162-1168`); настройки строки объекта сегодня запрещены
  (`apps/core/site_schema.py:4177-4182, 4251-4257`).
- Общие блоки в схеме объекта сегодня — пунктиром «Auf allen Seiten dieser Art · dort bearbeiten»,
  закреплены (`apps/core/site_schema.py:3401-3440`).

Остальные факты — инвентарь `scratchpad/m6v2/inventory.md` (ссылки §N — на него).

## 2. Заметки артбордов о поведении, которые расходятся с кодом или решениями

| № | Артборд | Заметка | Что в коде / решениях | Что делаем |
|---|---|---|---|---|
| 1 | M6Struktur A | у «Ähnliche Produkte» стоит ⠿ и нет 🔒 | у товара порядок разделов постоянный: `FIXED_ORDER` (`detail_parts.py:123`), раздел `related` — `WIDE_LAST` (`:127`); решение 1 | 🔒 «Reihenfolge fest», без ⠿. Вопрос владельцу №1 |
| 2 | M6Struktur | «Порядок разделов у Kombi и Textseite — как в общей … вопрос владельцу» | решение 14 принято | в 18 не трогаем, в 19 раскрепляем (`FIXED_ORDER_MODULES`, `detail_parts.py:79-81`) |
| 3 | M6Wo | «Änderungen hier gelten für diese beiden nicht.» | решение 16: «… für diese %(n)s nicht.» | текст по решению 16 («für diese 2 nicht.») |
| 4 | M6Wo | «Число — по полю `structure` объектов, без перебора site_config» | до уборки есть объекты `{}` со старыми отличиями (пропущенные переносом) | счёт = `structure` с `rows` + объекты `{}` со старыми данными; конфиг уже в памяти, отдельного обхода нет (§4.4) |
| 5 | M6Wo | «у строки товара — „Im Seitenaufbau ansehen →“» в списке товаров кабинета | списки кабинета в M6 не входят; редизайн — только по утверждённым макетам списка | в 18 ссылка ведёт на список, дальше — форма и «Seite im Shop». Вопрос №2 |
| 6 | M6Wo | «форма тура перетирает разделы — S14-E4-route-fp — уходит вместе с этим» | у S14-E4 две половины: разделы и маршрут (`roadmap:566`) | закрывается только половина «разделы»; маршрут остаётся открытым |
| 7 | M6Struktur A | «⚙ строки открывает окно блока ЭТОЙ страницы» | сегодня общие строки у объекта закреплены и не правятся, настроек у строки объекта нет (§1) | строки состояния A строит копия-кандидат; `setting_codes` у кода объекта возвращает коды общего типа (срез S3) |
| 8 | M6Struktur B | метка «nur hier» у своих блоков | в полной копии происхождения блока нет | «nur hier» = `id` блока нет среди блоков общей сейчас; при копии `id` сохраняются (§5.1) |
| 9 | M6Zurueck | «gilt für 15 Produkte» после сброса (было 14) | счёт идёт по сохранённому | к сохранённому счёту прибавляется поправка черновика этой страницы (сброс: +1, новая копия: −1) |
| 10 | M6Zurueck | строка про блок «Banner» помечена вопросом | решение 13 принято | строка «Block „Banner“: Banner dieser Seite stehen danach dort, wo die gemeinsame Struktur sie zeigt.» остаётся |
| 11 | M6Struktur | «Kopf und Fuß der Website sind hier nicht änderbar.» | показан только на A | показываем на A и B страниц объектов; на общих страницах — нет (эталоны окна не меняются) |

## 3. Модель хранения

### 3.1. Поле и формат (версия 1)

`structure = models.JSONField(default=dict, db_default={}, blank=True)` — через абстрактный миксин
`OwnStructureMixin` в `apps/core/models.py` (поле + охрана `save`, §4.3).

```
{}                                — не тронуто: старые данные читаются, если есть
{"v": 1}                          — наследует общую; старые данные этого объекта не читаются
{"v": 1,
 "rows":     [...],               — как page_blocks[<хост>]: блоки с id, якоря разделов {"key": …}, строки осей
 "sections": {"hidden": [...], "order": [...], "layout": "tabs"},   — как <module>_detail
 "flags":    {"promo_show_share": false, ...},                       — ключи видимости разделов (VISIBILITY_KEYS / VISIBILITY_ON)
 "settings": {"<код настройки>": значение, ...},                    — настройки типа страницы по коду page_settings
 "view":     {"style": …, "layout": …, "card": …},                  — только группа акций (бывший promo_groups[key])
 "i18n":     {"en": [...], "ru": [...]},                             — позиционный оверлей, как i18n[<loc>].page_blocks[<хост>]
 "src":      "migrate"}                                              — только у записанного переносом и не правленного после
```

- «Своя» ⇔ есть ключ `rows`. «Наследует» ⇔ `v` есть, `rows` нет. Сброс пишет ровно `{"v": 1}`.
- Версия формата — `v`. Незнакомая версия (`v > 1`) читается как «наследует» с записью в лог; писатель
  отказывается её перезаписывать. Смена формата — новая ветка в `object_structure._upgrade`, не
  миграция при чтении в других местах.
- **Виды разделов** едут внутри `rows` (строки осей с `style / grid / focus`, строка `offer` у акции —
  §1.2 инвентаря); **порядок, скрытые, шаблон** — в `sections`; **флаги видимости** старыми ключами
  (`detail_parts.VISIBILITY_KEYS`, `apps/core/detail_parts.py:87-106`) — в `flags`.
- **Настройки типа страницы** — в `settings`, по коду `page_settings`. Набор кодов для вида берётся из
  реестра: `page_settings.cabinet_settings(<тип>)` минус `DESIGN_SETTINGS` плюс коды строк
  `site_schema.SETTING_ROWS`. Общие настройки «Design» (форма карточки, ширина текста) остаются
  общими для сайта — в копию не входят, как шапка и подвал.
- **Переводы** — тот же позиционный формат, что в `site_config`, чтобы выравнивание оставалось одним:
  `siteconfig.realign_block_overlays` работает на проекции (§4.2), писатель снимает оверлей обратно.
- **Не входят в структуру**: «Kartenform» (`card_style`, решение 7), свои вопросы FAQ объекта (`faq`,
  `faq_i18n` — содержимое объекта; вопрос №3), SEO страницы (`seo.pages`), места баннеров (решения 8, 13).

### 3.2. Потолки
- Блоков в `rows` — прежние 30 (`_MAX_CBLOCKS`, §3.1 инвентаря), тексты — `CBLOCK_TEXT_CAPS`: структура
  проходит тот же `siteconfig.normalize` на проекции.
- Новая именованная константа `STRUCTURE_MAX_BYTES` (предложение 262 144) — размер сериализованной
  структуры. Превышение — отказ с существующим сообщением потолка страницы, а не обрезка.
- Потолки числа хостов (120 / 120 / 40) для своих структур перестают действовать: новых хостов
  писатель не создаёт. У старых хостов потолок остаётся как есть до стопки 20.
- Список имён «с собственной структурой» на общей странице — первые `OWN_NAMES_MAX = 50` по имени;
  число в заголовке — полное.

### 3.3. Миграции (все аддитивные)

| Приложение | Файл | Что |
|---|---|---|
| catalog | `0047_fb33_m6_structure` | `Product.structure`, `Category.structure`, `Combo.structure` |
| booking | `0046_fb33_m6_structure` | `Service.structure` |
| stays | `0050_fb33_m6_structure` | `StayUnit.structure` |
| events | `0040_fb33_m6_structure` | `Event.structure`, `Tour.structure`, `BlogPost.structure`, `Teacher.structure` |
| promotions | `0038_fb33_m6_structure` | `Promotion.structure`; `CreateModel PromoGroupPage` |
| core | `0022_fb33_m6_structure` | `ContentPage.structure` |

- Поля четырёх моделей стопки 19 (Combo, BlogPost, Teacher, ContentPage) добавляются уже в стопке 18:
  один проход миграций по ≈ 136 схемам вместо двух (решение 12 — деплой вне пика). До стопки 19 поля
  пустые и никем не читаются. Вопрос владельцу №4 (если строго по стопкам — три поля переезжают в 19).
- Блокировки: `ADD COLUMN … jsonb NOT NULL DEFAULT '{}'` в Postgres 16 — без перезаписи таблицы,
  `ACCESS EXCLUSIVE` на время правки каталога. Риск — очередь за долгой транзакцией (импорт, Celery).
  Первая операция каждой миграции — `SET LOCAL lock_timeout` (предложение 5 с): занятая таблица даёт
  быстрый отказ, а `deploy.sh` повторяет схему по одной (`scripts/deploy.sh:201-216`). Предпосылка —
  подтвердить у `database-reviewer`, что `SET LOCAL` внутри атомарной миграции django-tenants
  действует на схему (проверить в срезе S1).
- `PromoGroupPage` (TENANT, `apps/promotions/models.py`): `key` — `CharField(max_length=64, unique)`,
  байт-в-байт ключ группы (текст `Promotion.group` ≤ 50 либо `sys:*`; пробелы не обрезаются — сегодня
  «Sale» и «Sale » разные хосты, §10.17 инвентаря); `host` — `CharField(max_length=48, unique)` =
  `siteconfig.promo_group_host(key)`, считается при создании (поиск по коду страницы без перебора
  групп); `structure`; `created_at / updated_at`. Строка появляется при первой своей структуре или
  при переносе; у наследующей группы строки нет. Новая модель попадёт в шаблонную схему
  (`ensure_template_schema`, `scripts/deploy.sh:180-191`).
- Откат миграций не нужен для отката кода (старый код поле не знает). Обратные операции —
  `RemoveField` / `DeleteModel`, без согласия владельца не запускаются (`project-overrides.md`).
- Замер до выката (решение 12): на стенде с копией числа схем — время шага [6b] и самая долгая
  блокировка; цифры — в план стопки 18 до пуша миграций.

## 4. Один писатель, одна точка чтения

### 4.1. API `apps/core/object_structure.py`

| Функция | Что делает |
|---|---|
| `KINDS` | реестр видов: модель, модуль разделов, общий хост, тип страницы, префикс своего хоста, цель проекции (`shared` / `own`), порядок закреплён или нет, маршрут формы (право записи), маршрут списка (право просмотра), адрес превью |
| `ref(kind, obj)` / `ref_for_host(host)` | адрес страницы; `ref_for_host` — единственный разбор виртуального хоста, точное сравнение префикса |
| `state(ref)` | `"legacy"`, `"inherit"`, `"own"` — по сохранённому полю (чтение по pk, не по экземпляру) |
| `candidate(config, ref)` | копия-кандидат: то, что страница показывает сейчас, в формате v1 (A2 и перенос — одна функция) |
| `project(config, ref, structure, target)` | чистая: конфиг, в котором страница выглядит по `structure`; `target` — общий хост (витрина) или свой виртуальный хост (редактор) |
| `lift(config, ref, source)` | чистая, обратная `project`: из конфига-проекции — структура v1 |
| `bind(request, ref)` | витрина: помечает запрос; `raw_config` дальше отдаёт проекцию |
| `write(ref, structure, user, base, force, migrate=False)` | единственный писатель: под блокировкой строки, сверка отпечатка, `normalize`, потолки, `QuerySet.update`; `structure=None` — сброс в `{"v": 1}` |
| `losses(config, ref)` | что пропадёт при сбросе: блоки «nur hier» поимённо, отличия разделов и настроек |
| `counts(config, kind, user)` | «Gilt für N von M …», имена — только при праве просмотра |
| `walk(kinds=None)` | итератор по всем своим структурам (обходчики форматов блоков) |
| `clone(src, dst)` | наследник акции и клон серии |
| `shop_state(obj)` | данные строки «Seite im Shop» формы объекта |

Существующие `clean / effective_* / panel / apply_post / copy_blocks / drop_blocks /
purge_ghost_hosts / own_blocks` остаются как **старое чтение** для `structure == {}` и уходят в
стопке 20; `apply_post`, `from_post`, `panel` снимаются уже в S8 (вкладки больше нет).

### 4.2. Чтение

- Деталь объекта / страница категории / страница группы в начале вьюхи зовёт
  `object_structure.bind(request, ref)`. `bind` читает поле по pk и по `state`:
  - `own` → `request._own_structure = (ref, structure)`;
  - `inherit` → то же с пустой структурой: проекция только **убирает** старый свой хост и черновик
    `_object_override`, а чтение `page_override` (`object_structure._raw`) у такого объекта даёт `{}`;
  - `legacy` → ничего: сегодняшний путь байт-в-байт (30 эталонов `golden_fb31p5` — сторож).
- `page_settings.raw_config(request)` при привязанном запросе возвращает
  `project(config, ref, structure, target=shared)`: `rows` кладутся под ключ общего хоста
  (`product_detail`, `category`, `promo_detail`), оверлеи — под тот же ключ в `i18n`, `sections`,
  `flags`, `settings` — на свои ключи конфига (`page_settings.apply_override`,
  `apps/core/page_settings.py:850`), старый свой хост из проекции удаляется. Все читатели ниже
  (`detail_parts.page_ctx / flow`, теги `page_blocks`, `category_blocks`, `place_banners`,
  `normalize`, `localize`, фильтры LMIV и `hideable=False`) работают как для общей страницы и
  **не меняются**. У группы акций цель — свой хост `promo_group:<md5>` (у неё семантика «ключ есть —
  своя» уже родная, `siteui.py:567-571`) плюс `promo_groups[key]` из `view`.
- `bind` сбрасывает памятки запроса, снятые до него (`_aufbau_cfg`, `_stu19_tpl_cfg`,
  `_page_blocks_site`, `_page_seo_memo` — §3.3 инвентаря). Проекция считается один раз на запрос.
- Превью «Seitenaufbau» (`?preview=1&aufbau=<код>`): `bind` берёт структуру из черновика этой
  страницы, если он есть и пользователь вправе его видеть (`page_settings._may_preview`).
- На странице со своей структурой `templates/storefront/_page_blocks.html` не печатает
  `data-pb-host`: Студия на такой странице блок не вставляет (решение 10; иначе вставка ушла бы в
  общий тип и на этой странице не появилась бы).
- Битая структура (не словарь, нет `rows`, незнакомая версия, `normalize` выбросил всё) — страница
  рисуется как наследующая, 200, запись в лог с pk и схемой.
- Новый раздел реестра, которого нет в старой копии: `detail_parts.full_order` дописывает его в конец
  видимым (`apps/core/detail_parts.py:392-403`) — то же правило действует на проекции. Обязательные
  разделы (LMIV `FOOD_LOCKED`, `hideable=False`, § 312j) фильтруются теми же читателями и ещё раз
  писателем.

### 4.3. Запись: кто пишет сегодня и что с каждым

| Писатель сегодня | Где | Что с ним |
|---|---|---|
| «Seitenaufbau» → `aufbau_draft.commit` → `_commit_object` | `aufbau_draft.py:1398-1657` | остаётся входом; для кодов объекта / категории / группы зовёт `object_structure.write`, в `site_config` хост не пишет (S3) |
| вкладка формы объекта → `apply_post` | шесть вьюх (§2.1 инвентаря) | снимается вместе с вкладкой (S8) |
| полный `form.save()` / импорт / ассистент | вьюхи форм, `imports/*` | миксин исключает `structure` из полного `save()` существующей строки — по образцу `Tenant.save` (S1) |
| клон серии событий | `events/services.py:530-537` | клон — вставка, поле уезжает как есть: это и нужно; замок на поведение (S4) |
| наследник акции → `copy_blocks` | `promotions/tasks.py:236` | `object_structure.clone(promo, heir)`; новых хостов не создаёт (S4) |
| Студия: Save, `add_block`, `use_block_template`, черновик, автосейв | `apps/core/views.py:2324-2452, 2826-2876` | хосты объекта / категории / группы / своей страницы отклоняются и не рисуются в форме (S5) |
| Студия: «Version wiederherstellen» | `apps/core/views.py:2578-2607` | конфиг откатывается как раньше; структуры объектов не трогает (вопрос №5) |
| `materialize_page_axes`, `_pin_own_categories`, сидер | `page_axes_objects.py:162-390` | работают только по объектам с `structure == {}` — один фильтр в `page_axes_objects.build_index` (S4) |
| `move_page_blocks` при смене слага / удалении категории | `catalog/forms.py:178-191`, `catalog/views.py:1130-1150` | остаётся для старых хостов; своя структура едет со строкой категории сама (S4) |
| `purge_ghost_hosts`, `drop_blocks` | `object_structure.py:297-357` | только старые хосты; до стопки 20 |
| обходчики конфига: `banners._picks / places`, `list_blocks.apply_type_scope`, `drop_stray_site_search` | §10.11 инвентаря | дополнительно проходят `object_structure.walk()` и пишут через `write` (S4) |
| `site_schema.apply` | только стенд `scripts/fb33_m39c_targets_stand.py:188` | для кодов объектов отказывает; замок «один писатель» его видит |
| сидеры | `demo_kits.py:25672-25707` | после сборки конфига зовут ту же функцию переноса (S10) |

Замки «один писатель / один читатель»:
- `test_m6_structure_single_writer` — AST: присваивание `.structure`, `structure=` в `update / create /
  bulk_*` — только в `apps/core/object_structure.py` (образец — `test_fb33_m35b_faq_writers.py`);
- `test_m6_structure_single_reader` — чтение атрибута `.structure` и `values*("structure")` — только там же;
- `test_m6_full_save_keeps_structure` — для каждой модели реестра: устаревший экземпляр + `save()` не
  меняет поле; `save(update_fields=[…])` и вставка работают как раньше;
- `test_m6_kind_registry_is_single_source` — шесть нынешних списков видов (§1.3 инвентаря) равны
  выводу из `KINDS`.

### 4.4. Счёт «Gilt für …»
`counts(config, kind, user)`: всего живых объектов вида; своих — `filter(structure__has_key="rows")`
плюс объекты `{}` со старыми отличиями (`page_override != {}` или их хост есть в уже загруженном
конфиге). Два запроса на вид, без цикла. Имена — отдельным запросом с потолком 50 и только при праве
просмотра вида. Тур и событие делят тип «Veranstaltungsseite» — счёт общий (вопрос №6 о слове).

## 5. Копия (A2), сброс, закреплённый порядок, черновик

### 5.1. Копия
- Строится `candidate(config, ref)` — «что страница показывает сейчас»:
  - объект `{}` без старых данных или `inherit`: строки общего хоста, общие `sections / flags /
    settings`, оверлеи общего хоста;
  - объект `{}` со старыми данными: слияние по сегодняшнему правилу показа — у каждого раздела
    сначала общие блоки, потом свои (`detail_parts.flow`), `sections` = общий ± `page_override`,
    `blocks_first` акции учитывается местом своих блоков;
  - категория: четыре сочетания сегодняшних переключателей (§10.4 инвентаря) сводятся к одному:
    блоки — свои, если `has_own_schema`, иначе общие; оси — свои, если `has_parts`, иначе общие;
  - группа: строки по цепочке `promo_group:<md5>` → `promo_group` → `promos`
    (`siteconfig.page_rows`), `view` — из `promo_groups[key]`.
- `id` блоков **сохраняются** (вид «до == после» байт-в-байт, «nur hier» считается по `id`).
  Коллизия внутри одной копии (сидеры дают `pb-kit-N` в каждом хосте, §10.9 инвентаря) — у своего
  блока `id` получает суффикс; перевод едет парой «блок + его оверлей», не по `id`.
- Оверлеи переводов собираются парами до слияния и раскладываются обратно по новым позициям.
- A2: в состоянии A экран показывает строки кандидата (ничего не записано, черновика нет). Первая
  правка (любая операция окна или схемы) создаёт черновик со строками кандидата и флагом «своя»,
  применяет операцию, кладёт в живую область «Diese Seite hat jetzt eine eigene Struktur. Mit
  „Speichern“ wird es wirksam.». «Verwerfen» — черновика нет, страница снова A.

### 5.2. Сброс
- Операция `reset` черновика: строки = общая сейчас, флаг «сброс». До «Speichern» ничего не меняется,
  «Verwerfen» возвращает всё.
- «Speichern» → `write(ref, None)` → поле становится ровно `{"v": 1}`.
- **Почему сброс не оживает**: старые хосты и `page_override` читаются только при `structure == {}`.
  У сброшенного объекта стоит `v`, поэтому старые данные (они остаются на месте до стопки 20), шаг
  `materialize_page_axes`, `_pin_own_categories`, «Version wiederherstellen» и повторный перенос на
  следующем деплое его не касаются. Замок `test_m6_reset_never_resurrects_legacy` — все пять путей.
- Сброс не трогает: места баннеров (решение 13), «Kartenform», свои вопросы FAQ, SEO страницы.
- Список потерь — `losses()`: блоки, чьих `id` нет в общей сейчас («nur hier», поимённо, с переводами),
  отличия `sections / flags / settings / rows-осей` от общей сейчас; строка про блок «Banner», если
  он есть в копии.

### 5.3. Закреплённый порядок
- Товар и номер: якоря разделов в `rows` не двигаются (`detail_parts.FIXED_ORDER`), скрыть можно, свои
  блоки двигаются между разделами. Проверяет и редактор (операция `move` раздела — отказ), и писатель
  (порядок якорей в копии обязан совпасть с реестром — иначе `sections.order` не пишется).
- «Kaufen» — прежняя «feste Position» (`KAUF_FIRST`, `detail_parts.py:133`).
- Услуга, событие, тур: порядок в копии свой (`ORDERABLE_MODULES`, `object_structure.py:34`).
- Акция, группа, категория: как у общей страницы сегодня.

### 5.4. Черновик и конфликты
- Черновик страницы объекта: `{"host": <свой виртуальный хост>, "items": rows, "sv": 1, "own": true
  или "reset": true, …}`; редактор работает на проекции с целью «свой хост» — все операции окна
  (`store_items`, `block_i18n`, «Wie», «Karte», «Texte», настройки ★) идут прежним кодом по конфигу.
- Отпечаток (`_saved_state`) для кодов объекта / категории / группы: сохранённая структура; пока
  страница наследует — ещё и отпечаток кандидата (общая изменилась, пока шла правка, — конфликт
  существующим сообщением).
- Черновик старой формы (без `sv`) у таких кодов не применяется: снимается с существующим сообщением
  о конфликте (прецедент совместимости — `_base_fingerprint`, `aufbau_draft.py:80-97`). Выкат вне
  пика (решение 12) делает случай редким.
- Порядок блокировок прежний: строка `Tenant` → строка объекта. Сверка отпечатков повторяется под
  обеими, до первой записи. `site_config` при правке структуры не пишется (кроме частей черновика,
  которые и сегодня живут отдельно: «Wo zeigen», SEO).
- Объект удалён, пока шла правка: писатель не нашёл строку — отказ существующим сообщением, черновик
  снят; частичной записи («блоки сохранены, разделы нет», §10.25 инвентаря) больше не бывает.
- Двойная отправка «Speichern» и сброса — вторая видит отсутствие черновика и возвращает «нет» без
  сообщения об успехе (как сегодня, `aufbau_draft.py:1398-1404`).

## 6. Перенос: команда и шаг `deploy.sh`

### 6.1. Команда `migrate_object_structures` (`apps/core/management/commands/`, ядро — `apps/core/structure_migration.py`)
По каждой схеме, по каждому виду реестра стопки 18:
1. Кандидаты — объекты с `structure == {}` и старыми данными: `page_override != {}` или свой хост в
   `page_blocks` (у мягко удаляемых моделей — через `all_objects`); категории — хост `catalog:<slug>`
   с блоками или осями; группы — хост `promo_group:<md5>` или запись `promo_groups[key]` у живых и
   встроенных `sys:*` групп.
2. `candidate()` → если равен общей (отличий нет) — пишется `{"v": 1}`; иначе структура с `"src":
   "migrate"`.
3. Сверка до записи: «подпись вида» (видимые разделы по порядку, последовательность блоков с данными,
   шаблон, значения настроек, тексты на каждом языке сайта) по старому пути и по проекции должна
   совпасть. Не совпала — объект не трогается, строка «ПРОПУЩЕНО» с причиной. Выборочно
   (`--verify-render N`, по умолчанию 3 на вид на сайт) — сверка HTML через тот же помощник, что у
   `materialize_page_axes` (нормализация `data-pb-host`).
4. Запись — `object_structure.write(…, migrate=True)`: `QuerySet.update` под блокировкой строки
   (`lock_timeout 2s`, занятая строка — «ПРОПУЩЕНО, занято»), без `post_save` (нет шторма
   пересинхронизации портала, §10.14 инвентаря) и без смены `updated_at` (вид не изменился).
5. Отчёт на сайт: своя / наследует / пропущено (по причинам) / хост без живого объекта / хост сверх
   потолка (есть в сыром конфиге, выброшен `normalize`) / хост группы без известного ключа / серии
   событий с одинаковыми отличиями (число повторов).

Флаги: `--dry-run` (тот же отчёт, без записи), `--schema <имя>`, `--residue` (только остаток: объекты
`{}` со старыми данными), `--undo` (поле → `{}` только там, где стоит `"src": "migrate"`, то есть
после переноса не правили), `--verify-render N`.

Идемпотентность: повтор берёт только `structure == {}`; перенесённое, сброшенное и правленное не
трогает. Пропущенные пробует снова.

### 6.2. Место в `deploy.sh`
В шаге [8], **после** `drop_stray_site_search` (последним из переносов), затем
`migrate_object_structures --residue`. Причины порядка:
- после `materialize_page_axes` — старые коды шаблонов уже стали строками хостов, копия их заберёт;
- после `form_i18n_realign` и `drop_stray_site_search` — блоки хостов уже в окончательной форме;
- после подъёма нового web [7] — старый web поле не знает; его правки старых данных после переноса
  объекта потерялись бы для этого объекта.

Сбой шага деплой не останавливает (`warn_step`, как у соседей): непернесённое продолжает читаться
старым путём.

### 6.3. Окно деплоя «старый web ↔ новые данные»
- [6b] → [7]: старый web на новой схеме. Поле с `db_default` — вставки старого кода проходят; поле
  пустое у всех, новых данных ещё нет. Старый код пишет только старые данные — они и читаются.
- [7] → конец шага [8]: новый web, перенос ещё идёт. Объект `{}` читается старым путём; первая правка
  такого объекта в «Seitenaufbau» сама делает копию тем же `candidate()` — команда его потом пропустит.
- Незавершённый FB-31.7: шаг `materialize_page_axes` остаётся на каждом деплое; с фильтром
  `structure == {}` он не создаёт хосты перенесённым и сброшенным. Его `--undo` возвращает ключи
  конфига — на объекты с `v` это не влияет. `--residue` FB-31.7 считает по-прежнему; поля
  `page_style` и снятие шага — отдельная работа FB-31.7, в M6 не входит. Наследник акции продолжает
  копировать `page_style` через `_RECUR_CLONE_FIELDS` (чтение кодов выключено B3b) — не трогаем.
- Сидеры и пересев демо после деплоя (`seed_demo_tenants --group all --changed`) — через ту же
  функцию переноса, `SEEDER_VERSION` 25.

## 7. Обратная совместимость, откат кода, порядок выката
- Старые данные не удаляются и не меняются до стопки 20 → откат кода стопки 18 не требует отката
  данных: старый web читает старые данные. Правки, сделанные в структурах после выката, старый код не
  видит; после повторного выката они на месте.
- Чистый откат: до отката кода — `migrate_object_structures --undo` новым кодом. Вернутся в `{}`
  только не правленные после переноса; правленные и сброшенные остаются с `v` (старому коду всё равно).
- Виртуальные имена хостов (`product:<hex>`, `catalog:<slug>`, `promo_group:<md5>`) остаются кодом
  страницы, ключом черновика, параметром `?seite=`, `von`, адресом ⚙ (§10.23 инвентаря);
  `is_page_block_host` не сужается.
- Порядок выката стопки 18 (один деплой, решение 12): замер миграций на стенде → `--dry-run` на копии
  прода, отчёт владельцу (число «своих», пропусков, серий) → деплой вне пика → отчёт шага →
  `--residue` → пересев демо. Ветка стопки до конца второй сессии в `main` не вливается.

## 8. Кэш витрины
- Кэшируются только главная и 404 (`promotions/public_views.py:268`, §3.3 инвентаря); детали,
  категории и группы — нет. Запись поля объекта версию кэша сама не поднимает.
- `object_structure.write` зовёт `bump_storefront_cache` в `transaction.on_commit` (образец —
  `apps/core/page_settings.py:979-1010`), кроме режима `migrate=True` (вид не менялся).
- Пользовательская запись ставит `updated_at` (sitemap) в том же `update`; сигналы портала не
  шлются — портал структуру не читает (§2.3 инвентаря).
- Замок `test_m6_write_bumps_storefront_cache_on_commit` — с включённым кэшем (в тестах TTL 0),
  непустым хостом и проверкой «после коммита, не до».

## 9. Права и IDOR
- Правка своей структуры (первая копия, любая операция, сброс, «Speichern»): `website.edit` **и**
  право формы объекта из реестра: товар, услуга, номер, событие, тур, категория — `sortiment.edit`;
  акция и группа акций — `marketing.edit`; в стопке 19: Kombi, учитель — `sortiment.edit`, блог —
  `marketing.edit`, своя страница — `seiten.edit`. Проверка — на операции (отказ сразу существующим
  сообщением о правах) и ещё раз в `write` под блокировкой.
- Следствие решения 11: сотрудник только с `website.edit` больше не правит блоки страницы объекта
  (сегодня может, §4 инвентаря). В отчёт владельцу при выкате.
- Просмотр: `website.view`. Имена объектов (список «… mit eigener Struktur», выбор страницы) — только
  с правом просмотра вида; иначе число без имён и без ссылок.
- Страница подтверждения сброса без JS: GET ничего не меняет, требует те же права; неизвестный код,
  чужой или удалённый объект — 404; POST — CSRF и код страницы.
- Код страницы из запроса разбирает только `site_schema.resolve / host_for`
  (`apps/core/site_schema.py:1079, 2656`) — объект существует и жив, тип включён; `ref_for_host`
  сравнивает префикс точно.
- Студия: `add_block` и `use_block_template` сегодня принимают любой хост по регэкспу
  (`apps/core/views.py:2333`) — хосты объекта / категории / группы / своей страницы отклоняются;
  заодно закрывается создание хоста несуществующего объекта.
- Изоляция бизнесов — схема Postgres; `PromoGroupPage` — TENANT-модель.

## 10. Интерфейс по артбордам, доступность, строки

### 10.1. «Seitenaufbau», страница объекта
- A: заголовок «Wie alle Produktseiten»; плашка «Gemeinsame Struktur „Produktseite“ · gilt für 14
  Produkte. Änderungen dort gelten auch hier. Sobald Sie hier etwas ändern, bekommt diese Seite eine
  eigene Struktur.»; строки «★ Einstellungen der Seite ⚙», «🔒 feste Position · Kaufen ⚙», «🔒
  Reihenfolge fest · Beschreibung ⚙» …; ссылка «Gemeinsame Struktur bearbeiten →»; «Kopf und Fuß der
  Website sind hier nicht änderbar.».
- B: живая область «Diese Seite hat jetzt eine eigene Struktur. Mit „Speichern“ wird es wirksam.»;
  плашка «Eigene Struktur · Änderungen an der gemeinsamen Struktur „Produktseite“ gelten hier nicht.»
  с кнопкой «Zur gemeinsamen Struktur zurück»; метки «nur hier», «ausgeblendet»; «＋ Block»;
  «Verwerfen», «Speichern».
- Сброс с JS: окно «Zur gemeinsamen Struktur zurück?» — «„Roggenbrot 750 g“ zeigt danach wieder die
  gemeinsame Struktur „Produktseite“.», «Dabei geht verloren:», «2 Blöcke nur für diese Seite: „Unser
  Sauerteig“, „Aus der Backstube“ – mit Texten und Übersetzungen», «eigene Einstellungen: „Bewertungen“
  ausgeblendet, „Ähnliche Produkte“ als Slider», «Wirksam erst mit „Speichern“. Bis dahin können Sie
  mit „Verwerfen“ alles zurückholen.», кнопки «Abbrechen», «Eigene Struktur verwerfen».
- После сброса: «Gemeinsame Struktur übernommen. Mit „Speichern“ wird es wirksam.».
- Без JS: страница `<title>` «Zurücksetzen – „Roggenbrot 750 g“ – Seitenaufbau», крошки «Seitenaufbau ›
  „Roggenbrot 750 g“ › Zurücksetzen», «Dabei gehen 2 Blöcke nur für diese Seite und die eigenen
  Einstellungen verloren.», кнопки «Eigene Struktur verwerfen», «Abbrechen».
- Общая страница типа: «Produktseite (für alle Produkte)», «Gilt für 13 von 15 Produkten.», раскрытие
  «2 Produkte mit eigener Struktur» с именами-ссылками, фраза по решению 16.
- Выбор страницы: «Produktseiten», «Für alle Produkte», пометка «eigene Struktur», «Anderes Produkt
  öffnen →».
- Форма объекта: `<fieldset>` с `<legend>` «Seite im Shop»: «Eigene Struktur · 2 Blöcke nur für diese
  Seite» + «Im Seitenaufbau bearbeiten →» либо «Wie alle Produktseiten» + «Im Seitenaufbau ansehen →»;
  поле «Kartenform» остаётся. Сентинел `page_override_present`, поля `ps_layout`, `ps_blocks_first`,
  `ps_reset` из шести форм убираются.

### 10.2. Доступность (из заметок артбордов)
- Плашка — `<section aria-labelledby>` с именем «Eigene Struktur»; живая область `role="status"` —
  постоянная, пустая при загрузке, лежит в обёртке схемы и переживает подмену фрагмента; текст в неё
  кладётся через ≈ 150 мс после перевода фокуса; `aria-live` на лету не переключается.
- A → B: фокус остаётся на ⚙ строки, из окна которой шла правка. После сброса: фокус на заголовок
  «Wie alle Produktseiten» (`tabindex="-1"`), потом текст в живую область.
- Окно сброса: фокус при открытии на «Abbrechen»; Esc = «Abbrechen»; после закрытия — на кнопку
  плашки; список потерь до кнопок; липкий подвал, `scroll-padding-bottom` по его высоте.
- 🔒 — `aria-hidden`, имя текстом для экранного диктора («Reihenfolge fest» / «feste Position»); ⠿ —
  `aria-hidden`, без фокуса (решение 16), с клавиатуры — пункты «⋯»; «·» не озвучивается.
- ⚙ — ссылка «Einstellungen: <Name>», 44 × 44; «gilt für … Produkte …» и подсказка A2 — в
  `aria-describedby` каждой ⚙ (один целевой id на страницу).
- Имена объектов бизнеса — в `lang` языка бизнеса, строки интерфейса — нет.
- Телефон 390: кнопка плашки во всю ширину, строки 48 px; окно сброса — на весь экран, прокручено к
  началу; то же на 844 × 390.
- «Seite im Shop» — `fieldset / legend`, ссылки ≥ 44 px, в том числе имена в `<details>`.

### 10.3. Новые msgid (все — в P0, во все пять `.po`: de/en/tr/ru/uk; без `msgctxt`)
Уже есть и переиспользуются (grep по `locale/en/LC_MESSAGES/django.po`): «feste Position», «nur
hier», «ausgeblendet», «Verwerfen», «Speichern», «Abbrechen», «Zurücksetzen», «Einstellungen der
Seite», «Einstellungen: %(name)s», «Im Seitenaufbau bearbeiten», «Kartenform», «Produktseite».

Новые, общие для всех видов (19):
1. «Eigene Struktur»
2. «Reihenfolge fest»
3. «Diese Seite hat jetzt eine eigene Struktur. Mit „Speichern“ wird es wirksam.»
4. «Änderungen an der gemeinsamen Struktur „%(type)s“ gelten hier nicht.»
5. «Zur gemeinsamen Struktur zurück»
6. «Zur gemeinsamen Struktur zurück?»
7. «„%(name)s“ zeigt danach wieder die gemeinsame Struktur „%(type)s“.»
8. «Dabei geht verloren:»
9. «%(n)s Block nur für diese Seite: %(names)s – mit Texten und Übersetzungen» / мн. «%(n)s Blöcke …»
10. «eigene Einstellungen: %(list)s» (пункты: «„%(name)s“ ausgeblendet», «„%(name)s“ als %(view)s» — ещё 2 msgid)
11. «Wirksam erst mit „Speichern“. Bis dahin können Sie mit „Verwerfen“ alles zurückholen.»
12. «Eigene Struktur verwerfen»
13. «Gemeinsame Struktur übernommen. Mit „Speichern“ wird es wirksam.»
14. «Zurücksetzen – „%(name)s“ – Seitenaufbau»
15. «Dabei geht %(n)s Block nur für diese Seite und die eigenen Einstellungen verloren.» / мн. «Dabei gehen %(n)s Blöcke …»
16. «Block „Banner“: Banner dieser Seite stehen danach dort, wo die gemeinsame Struktur sie zeigt.»
17. «Gemeinsame Struktur bearbeiten», «Kopf und Fuß der Website sind hier nicht änderbar.»
18. «Seite im Shop», «Im Seitenaufbau ansehen», «%(n)s Block nur für diese Seite» / мн., «eigene Struktur»
19. «Änderungen hier gelten dort nicht.» / «Änderungen hier gelten für diese %(n)s nicht.» (решение 16;
    две отдельные строки, выбор по n в коде — не `ngettext`: в ru/uk у n = 21 была бы форма единственного)

Новые по виду (6 строк × 8 видов стопки 18; у товара — дословно с артбордов, у остальных — по образцу,
слова на подтверждение, вопрос №6): «Wie alle Produktseiten»; «Gemeinsame Struktur „%(type)s“ · gilt
für %(n)s Produkte. …» (мн. формы); «%(type)s (für alle Produkte)»; «Gilt für %(n)s von %(total)s
Produkten.»; «%(n)s Produkte mit eigener Struktur»; «Produktseiten» / «Für alle Produkte» / «Anderes
Produkt öffnen». Подписи видов — в реестре `KINDS` через `gettext_lazy` (не псевдоним).

Снимаются вместе с вкладкой (S8, после grep вызовов): «Zurück zum Standard», «Wie alle» (подсказка
шаблона), «Auf allen Seiten dieser Art · dort bearbeiten», «Eigene Reihenfolge der Abschnitte» и
подписи вкладки из `templates/tenant/_object_structure.html` — только те, что больше нигде не зовутся.

## 11. Стопка 19 (предварительно; свой план-док в начале стопки)
- **«Textseite»** (решения 5, 14): новый общий хост `textseite` в `PAGE_BLOCK_HOSTS`
  (`apps/tenants/siteconfig.py:1286-1335`) и тип страницы в `studio_pages.PAGE_TYPES`; стартует только
  с текстом. Наследуют: `seite:<slug>` (`ContentPage.structure`), «Über uns» (хост `info`, раздел
  контактов закреплён) и «Versand» (хост `versand` либо `seite:versand`, стоимость закреплена — PAngV).
  У «Über uns» и «Versand» своей строки может не быть (§10.18 инвентаря): их своя структура остаётся
  в фикс-хосте `site_config` (страница одна, потолка нет); «своя» ⇔ в хосте есть строки. Правовые
  страницы — без блоков, как сегодня.
- Перенос: страница с блоками → своя структура, пустая → наследует; расширение той же команды
  (`--kinds text`), отчёт «хост `seite:` без страницы», «сверх потолка 40».
- SEO страницы (`seo.pages[seite:<slug>]`) и его переводы остаются в `site_config` и по-прежнему едут
  за слагом (`content_pages.save_page`); S16-hreflang не задевается.
- **Kombi, блог**: виды `combo`, `blog_post` в реестре (общие хосты и разделы уже есть:
  `combo_detail`, `blog_post`); адрес блога — по слагу; раскрепить разделы Kombi (решение 14):
  убрать `combo` и `page` из `FIXED_ORDER_MODULES`.
- **«Lehrer»** (решение 6): общий хост и тип страницы (сегодня нет ни того, ни другого, шаблон блоки
  не зовёт — §10.19 инвентаря), разделы в `detail_sections`, вызов блоков в
  `templates/storefront/lehrer_detail.html`, затем `Teacher.structure`.
- **Вынос остальных хостов**: после стопки 19 в `site_config` не пишется ни один хост «на объект»
  (`seite:<slug>` уходит в `ContentPage.structure`); имена остаются виртуальными.
- Формы Kombi, блога, учителя, своей страницы — строка «Seite im Shop».
- Уборка — стопка 20: снятие старого чтения, хостов объектов из конфигов, `page_override`,
  `promo_groups[key]`, `copy_blocks / purge_ghost_hosts / drop_blocks`, шага переноса.

## 12. Срезы стопок 18 (S) и 19 (N)

Одна таблица на обе стопки: `plan_check` читает первую таблицу и считает волны сквозь.

| Срез | Зависит от | Свои файлы | Общие файлы | Эталоны | Ветка |
|---|---|---|---|---|---|
| P0 | — | `docs/fb33-map.md`, `docs/task-catalog.md` | `locale/*/LC_MESSAGES/django.po` | 0 | |
| S1 | — | `apps/core/object_structure.py`, `apps/core/models.py`, `apps/catalog/models.py`, `apps/booking/models.py`, `apps/stays/models.py`, `apps/events/models.py`, `apps/promotions/models.py`, `apps/core/media_registry.py`, `+apps/catalog/migrations/0047_fb33_m6_structure.py`, `+apps/booking/migrations/0046_fb33_m6_structure.py`, `+apps/stays/migrations/0050_fb33_m6_structure.py`, `+apps/events/migrations/0040_fb33_m6_structure.py`, `+apps/promotions/migrations/0038_fb33_m6_structure.py`, `+apps/core/migrations/0022_fb33_m6_structure.py` | — | 0 | |
| S2 | S1 | `apps/core/page_settings.py`, `apps/core/detail_parts.py`, `apps/tenants/templatetags/siteui.py`, `templates/storefront/_page_blocks.html`, `apps/promotions/public_views.py`, `apps/booking/public_views.py`, `apps/stays/public_views.py`, `apps/events/public_views.py`, `apps/catalog/catalog_parts.py`, `apps/promotions/promo_parts.py`, `apps/catalog/management/commands/lmiv_info_audit.py` | — | 0 | |
| S4 | S1 | `apps/promotions/tasks.py`, `apps/events/services.py`, `apps/core/banners.py`, `apps/core/list_blocks.py`, `apps/core/page_axes_objects.py`, `apps/core/management/commands/drop_stray_site_search.py`, `apps/catalog/forms.py` | — | 0 | |
| S5 | S1 | `apps/core/views.py`, `templates/tenant/site_home.html` | — | 0 | |
| S3 | S2 | `apps/core/aufbau_draft.py`, `apps/core/site_schema.py`, `apps/core/object_structure.py` | — | 0 | |
| S6 | S2, S4 | `+apps/core/structure_migration.py`, `+apps/core/management/commands/migrate_object_structures.py`, `scripts/deploy.sh` | — | 0 | |
| S7 | S3 | `apps/core/site_schema_views.py`, `apps/core/site_schema.py`, `templates/tenant/site_schema.html`, `templates/tenant/_schema_row.html`, `+templates/tenant/_schema_own.html`, `+templates/tenant/schema_reset.html`, `static/js/aufbau.js`, `+scripts/fb33_m6_struktur_stand.py` | `static/css/app.css` | 2 | |
| S8 | S3 | `templates/tenant/_object_structure.html`, `templates/catalog/product_form.html`, `templates/booking/service_page.html`, `templates/stays/unit_page.html`, `templates/events/event_form.html`, `templates/events/tour_form.html`, `templates/promotions/promotion_form.html`, `templates/catalog/category_form.html`, `apps/catalog/views.py`, `apps/booking/views.py`, `apps/stays/views.py`, `apps/events/views.py`, `apps/promotions/views.py`, `+scripts/fb33_m6_form_stand.py` | `static/css/app.css` | 0 | |
| S10 | S6 | `apps/tenants/demo_kits.py`, `apps/tenants/demo_fingerprint.py`, `apps/tenants/demo_i18n.py` | — | 0 | |
| N0 | S7, S8, S10 | `docs/roadmap-next-sprints.md` | `locale/*/LC_MESSAGES/django.po` | 0 | |
| N1 | N0 | `apps/tenants/siteconfig.py`, `apps/core/studio_pages.py`, `apps/core/detail_parts.py`, `apps/core/object_structure.py`, `apps/core/content_pages.py`, `apps/core/detail_sections.py` | — | 0 | |
| N2 | N1 | `apps/orders/public_views.py`, `apps/events/public_views.py`, `templates/storefront/combo_detail.html`, `templates/storefront/blog_detail.html`, `templates/storefront/lehrer_detail.html` | — | 0 | |
| N3 | N1 | `apps/core/content_page_views.py`, `templates/storefront/content_page.html`, `apps/tenants/templatetags/siteui.py` | — | 0 | |
| N4 | N1 | `apps/core/site_schema.py`, `apps/core/aufbau_draft.py`, `apps/core/site_schema_views.py`, `templates/tenant/site_schema.html` | `static/css/app.css` | 5 | |
| N5 | N3, N4 | `+apps/core/structure_migration.py`, `+apps/core/management/commands/migrate_object_structures.py`, `scripts/deploy.sh` | — | 0 | |
| N6 | N3, N4 | `templates/catalog/combo_form.html`, `templates/events/blog_edit.html`, `templates/events/teacher_form.html`, `templates/tenant/content_page_form.html`, `apps/catalog/views.py`, `apps/events/views.py`, `apps/core/content_page_views.py` | `static/css/app.css` | 0 | |
| N7 | N5 | `apps/tenants/demo_kits.py`, `apps/tenants/demo_fingerprint.py`, `+scripts/fb33_m6_stack19_stand.py` | — | 0 | |

Плюс у N5 — файлы, которые создаст S6 (на диске их ещё нет, поэтому с «+»).

**Цепочки (T-17):**
- `apps/core/object_structure.py`: S1 → S3 → N1. Весь чистый слой (формат, `candidate`, `project`,
  `lift`, реестр, охрана `save`, `write`, `walk`, `clone`, `counts`) — в S1; S3 дописывает только то,
  что нужно черновику (`losses`, поправка счёта, `shop_state`). S2, S4, S5, S6, S8 файл не правят —
  только зовут. Находка ревью в этом файле во время волны 2 — `plan_check.py --add` и правка в S3.
- `apps/core/site_schema.py`: S3 → S7 → N4. `apps/core/aufbau_draft.py`: S3 → N4.
- `apps/tenants/templatetags/siteui.py`: S2 → N3. `apps/core/detail_parts.py`: S2 → N1.
- `apps/promotions/public_views.py`, `apps/events/public_views.py`: S2 (→ N2 у событий).
- `apps/catalog/views.py`, `apps/events/views.py`: S8 → N6. `apps/core/content_page_views.py`: N3 → N6.
- `scripts/deploy.sh`, ядро переноса: S6 → N5. Сидеры: S10 → N7.
- `apps/tenants/siteconfig.py` в стопке 18 **не правится** (структура идёт через существующий
  `normalize` на проекции); первый раз — N1 (хост `textseite`).

**Волны** (вывод `plan_check`): P0, S1 · S2, S4, S5 · S3, S6 · S7, S8, S10 · N0 · N1 · N2, N3, N4 ·
N5, N6 · N7.

**Сессии (T-19: стопка длиннее трёх волн — остаток новой сессии):**
- 18a — волны 1–3 (P0, S1 · S2, S4, S5 · S3, S6); ветка стопки в `main` не вливается;
- 18b — волна 4 (S7, S8, S10), стенды, обход владельца, свод, замер миграций, `--dry-run`, деплой;
- 19a — N0, N1, N2 / N3 / N4; 19b — N5, N6, N7, обход, деплой.

`object_structure.py` (15 импортёров), `detail_parts.py`, `site_schema.py`, `siteui.py` —
`preflight --slice` возьмёт широкий набор: исполнитель не ждёт дольше пары минут, полный прогон — CI
ветки среза (T-16).

## 13. Что делает каждый срез стопки 18 и какие старые тесты он переписывает

- **P0** (координатор): план в `docs/`, ID в `docs/task-catalog.md`, строки карты `docs/fb33-map.md`,
  все msgid §10.3 в пять `.po`.
- **S1 «хранилище и чистое ядро»**: миксин, шесть миграций, `PromoGroupPage`, реестр `KINDS`,
  формат v1, `candidate / project / lift / state / write / walk / clone / counts`, запись поля в карту
  `media_registry` (сторож `test_media_registry_map_covers_known_fields`). Старые тесты:
  `apps/core/tests/test_fb29_object_structure.py`, `test_fb29_object_kinds.py` (списки видов → реестр).
- **S2 «читатель витрины»**: `bind` в детальных вьюхах, проекция в `raw_config`, сброс памяток,
  `place_banners` берёт хост страницы у `object_structure`, `_page_blocks.html` без `data-pb-host` на
  своей структуре, `lmiv_info_audit` читает через `object_structure`. Старые тесты — без правок
  (старый путь байт-в-байт): `test_fb31p5_object_golden.py`, `test_fb29_object_blocks.py`,
  `test_fb29_tour_blocks.py`, `apps/catalog/tests/golden_fb3016`, `apps/promotions/tests/golden_fb31p3`.
- **S4 «прочие писатели и обходчики»**: `clone` вместо `copy_blocks` у наследника акции, замок на
  клон серии, фильтр `structure == {}` в `page_axes_objects`, обходчики + `walk`, слаг категории.
  Старые тесты: `test_fb317_b1b2_migrate.py` (наследник: хост → структура),
  `test_fb3016_r5_all_categories.py` (`_pin_own_categories`).
- **S5 «Студия не правит»**: отказ хостам объекта / категории / группы / страницы в `add_block`,
  `use_block_template`, Save; такие хосты не рисуются в форме Студии. Старые тесты:
  `test_fb31p6_studio_writers.py`, `apps/catalog/tests/test_category_page_2026_08_26.py`,
  `apps/core/tests/test_main_list_marker.py`.
- **S3 «писатель и черновик»**: A2, сброс, отпечаток, права, строки схемы состояний A и B,
  `setting_codes` у кода объекта, группа через `PromoGroupPage`, категория без `adopt`. Старые тесты:
  `test_fb31p5_object_schema.py` (самый большой), `test_fb27_r7_category.py`,
  `test_fb33_m3_1b_window_cancel.py`, `test_fb33_m2b2b_window.py`, `test_fb33_m2g_events.py`.
- **S6 «перенос»**: ядро, команда, шаг `deploy.sh`, `--dry-run / --residue / --undo`.
- **S7 «интерфейс „Seitenaufbau“»**: плашки, окно и страница сброса, живая область, 🔒 / ⠿, список
  «… mit eigener Struktur», стенд. Эталоны — 2 (§15.1).
- **S8 «форма объекта»**: «Seite im Shop» в шести формах и форме категории, снятие вкладки,
  `apply_post` и сентинела. Старые тесты: `apps/catalog/tests/test_fb29_structure_tab.py`,
  `apps/booking/tests/test_fb29_structure_tab.py`, `apps/events/tests/test_fb33_e4_details_base.py`,
  `apps/core/tests/test_fb29_leftovers.py`, `apps/imports/tests/test_cscart.py` (упоминает вкладку).
- **S10 «сидеры»**: кит после сборки конфига прогоняет функцию переноса, `SEEDER_VERSION` 25.

## 14. Замки первого коммита (красный = strict xfail; номер — вопрос чеклиста)

Файлы — `apps/core/tests/test_fb33_m6_<срез>.py`, если не указано иное.

**S1**
- №1 `test_m6_structure_single_writer`, `test_m6_structure_single_reader`
- №1 `test_m6_full_save_keeps_structure[<модель>]` (устаревший экземпляр, полный `save()`)
- №2 `test_m6_kind_registry_is_single_source`
- №3 `test_m6_copy_keys_come_from_registries` (ключи `sections / flags / settings` — из реестров, не по префиксу)
- №5 `test_m6_host_prefix_exact_match` (`promo:` против `promo_group:`, `product:` против `product_detail`)
- №12 `test_m6_translations_follow_blocks_on_copy` (слияние общих и своих блоков, коллизия `pb-kit-1`)
- №16 `test_m6_kind_labels_lazy`
- №26 `test_m6_structure_caps_enforced_with_message` (30 блоков, `STRUCTURE_MAX_BYTES`)
- №32 `test_m6_migrations_additive_db_default` (только `AddField` / `CreateModel`, `db_default`)
- `test_m6_project_lift_roundtrip[<вид>]`, `test_m6_unknown_version_reads_as_inherit`

**S2**
- №40 `test_m6_candidate_renders_like_legacy[<случай golden_fb31p5>]` — образец «до» — существующий
  файл эталона; после `candidate` + проекции HTML равен ему с точностью до `data-pb-host`
- №6 `test_m6_broken_structure_renders_shared_200`
- №8 `test_m6_bind_failure_logs_and_falls_back`
- №3 `test_m6_bind_one_projection_per_request`, `test_m6_bind_after_early_raw_config`
- №31 `test_m6_detail_query_budget` (не больше +1 запроса на деталь)
- `test_m6_inherit_ignores_legacy_host_and_override`, `test_m6_lmiv_info_cannot_be_hidden_in_copy`,
  `test_m6_new_registry_section_appears_in_old_copy`, `test_m6_banner_place_block_seen_in_copy`,
  `test_m6_own_page_has_no_pb_host`

**S4**
- `test_m6_promo_heir_gets_structure_not_host`, `test_m6_series_clone_copies_structure`
- `test_m6_materialize_axes_skips_marked_objects`, `test_m6_pin_own_categories_skips_marked`
- №10 `test_m6_banner_delete_cleans_pick_in_structures`
- №4 `test_m6_walkers_cover_structures` (список обходчиков §4.3: каждый зовёт `walk` либо стоит в
  списке «не нужно» с причиной)

**S5**
- №28 `test_m6_studio_rejects_object_hosts[add_block, use_block_template, save]`
- `test_m6_studio_form_hides_object_hosts`, `test_m6_version_restore_keeps_structures`

**S3**
- №9 `test_m6_write_rechecks_fingerprint_under_lock`
- №10 `test_m6_conflict_before_any_write`, `test_m6_reset_drops_block_translations`
- №11 `test_m6_old_object_draft_is_dropped_with_conflict`
- №13 `test_m6_write_bumps_storefront_cache_on_commit`
- №17 `test_m6_german_edit_drops_translation_in_structure`
- №28 `test_m6_object_right_required_for_copy_and_reset[<вид>]`, `test_m6_names_hidden_without_view_right`
- №31 `test_m6_counts_query_budget`
- №33 `test_m6_reset_double_submit_idempotent`
- №37 `test_m6_structure_overlay_uses_realign_only`
- №6 `test_m6_soft_deleted_object_code_404`
- `test_m6_reset_never_resurrects_legacy[materialize, pin, restore, remigrate, heir]`
- `test_m6_first_edit_makes_copy`, `test_m6_fixed_order_sections_do_not_move[product, stay]`,
  `test_m6_reset_keeps_banner_places_card_style_faq`, `test_m6_group_page_survives_last_promo`

**S6** (`test_fb33_m6_migrate.py`)
- №8 `test_m6_migrate_reports_every_skip`
- `test_m6_migrate_idempotent`, `test_m6_migrate_dry_run_writes_nothing`,
  `test_m6_migrate_no_difference_means_inherit`, `test_m6_migrate_skips_on_view_mismatch`,
  `test_m6_migrate_undo_only_untouched`, `test_m6_migrate_no_post_save_no_updated_at`,
  `test_m6_migrate_category_four_states`, `test_m6_migrate_reports_ghost_and_overflow_hosts`,
  `test_deploy_sh_runs_migrate_structures_last`

**S7**
- №19 `test_m6_reset_without_js_page` (GET не меняет, POST с CSRF, неизвестный код — 404)
- №22 `test_m6_lock_and_grip_hidden_label_is_text`
- №34 `test_m6_live_region_outside_swapped_fragment`
- №35 `test_m6_describedby_targets_unique`
- №36 `test_m6_object_names_lang_attr`
- №25 `test_m6_reset_dialog_no_hidden_display_clash`
- №15 `test_m6_schema_goldens_changed_only_product` (список изменившихся эталонов = 2 файла)
- `test_m6_count_phrase_n1_and_n` (решение 16)
- стенд `scripts/fb33_m6_struktur_stand.py`: №20, №21, №24, №33 (фокус, подмена фрагмента, 390 × 844
  и 844 × 390, двойной клик, зависший ответ)

**S8**
- №4 `test_m6_removed_tab_leaves_no_callers_or_msgids`
- `test_m6_form_save_never_writes_structure[<форма>]`, `test_m6_shop_row_states`,
  `test_m6_kartenform_field_still_saved`

**S10**
- `test_m6_kit_seed_produces_structures_not_hosts`, сторож `SEEDER_VERSION`

**Стопка 19 (имена на план стопки 19):** `test_m6_versand_cost_pinned` (№29, PAngV),
`test_m6_about_contact_pinned`, `test_m6_legal_pages_have_no_blocks`, `test_m6_textseite_starts_text_only`,
`test_m6_page_with_blocks_becomes_own`, `test_m6_teacher_page_renders_shared_blocks`,
`test_m6_combo_and_page_sections_movable`.

Итого по стопке 18: 31 ответ «риск есть» чеклиста → 73 замка поимённо (параметризованные считаются
по одному) плюс два стенда.

## 15. Эталоны, стенды, исполнители

### 15.1. Прогноз эталонов (grep по всем 24 каталогам `golden*`)
```
G=$(find apps -type d -name 'golden*')        # 24 каталога
grep -rl 'data-pb-host="\(product\|service\|stay\|event\|promo\|tour\):' $G | wc -l   # 30 (все в golden_fb31p5)
grep -rl 'schema-row' $G | wc -l              # 33: page_nojs 31, wie_nojs 2
ls apps/core/tests/golden_fb33m3/page_nojs | grep -c '^product'     # 2
ls apps/core/tests/golden_fb33m3/page_nojs | grep -c '^text'        # 5
grep -rl 'page_override_present\|ps_layout\|Zurück zum Standard\|Auf allen Seiten dieser Art' $G | wc -l   # 0
grep -rl '@\(product\|service\|stay\|event\|promo\|tour\):' $G | wc -l   # 0 — страниц-объектов в эталонах окна нет
grep -rl 'catalog:[a-z0-9-]' $G | wc -l       # 1 (golden_fb33m5d2/registry.json)
```
- **S1 — 0**: ключей `site_config` не добавляем, `apps/tenants/tests/test_normalize_golden.py` не задет.
- **S2 — 0**: 30 файлов `golden_fb31p5` со своими хостами объектов рисуются старым путём
  (`structure == {}`); `_page_blocks.html` меняется только у привязанной страницы.
- **S3 — 0**: в эталонах окна нет ни одной страницы-объекта (0 совпадений кода `kind@kind:`).
- **S4, S5, S6, S8, S10 — 0**: формы объектов и Студия в эталонах не сняты (0 совпадений).
  `golden_fb33m5d2/registry.json` — реестр источников «Inhalt», переносом не меняется.
- **S7 — 2**: `golden_fb33m3/page_nojs/product___kauf.html`, `product_related.html` — общая страница
  «Produktseite»: строки разделов получают «Reihenfolge fest», появляется «Gilt für … Produkten.».
  Остальные 29 файлов `page_nojs` — другие типы (корзина, каталог, подтверждение, главная, 404,
  акции-обзор, текст): плашки у них нет, строка «Kopf und Fuß …» рисуется только у страниц объектов.
  Эталон хранит прежнюю подпись «feste Position» у разделов товара — срез её меняет осознанно.
- **N4 — 5** (предварительно): `golden_fb33m3/page_nojs/text_*.html` — раскреплённые разделы и плашка
  наследования у текстовой страницы. **N1, N2, N3, N5, N6, N7 — 0** (предварительно; 6 файлов
  `golden_fb32s6` с `data-pb-host="info" / "versand" / "seite:` должны остаться байт-в-байт — сторож
  переноса стопки 19).
- Свои эталоны переснимает исполнитель в своей ветке со свежими `.mo` (`FB33_M3_REGEN=1`), список
  изменившихся — в отчёт.

### 15.2. Стенды (на `scripts/standlib.py`; 1440 / 390, 390 × 844 и 844 × 390, de / ru, с JS и без)
- `scripts/fb33_m6_struktur_stand.py` (S7): A → первая правка → B → «Speichern» → витрина; сброс с JS
  и без; фокус и живая область; права (сотрудник без `sortiment.edit`); виды: товар, услуга, номер,
  событие, тур, акция, категория, группа; негативный контроль — общая правка после копии на странице
  не видна.
- `scripts/fb33_m6_form_stand.py` (S8): шесть форм и форма категории — строка «Seite im Shop» в обоих
  состояниях, сохранение формы не меняет структуру.
- Обход владельца `scripts/fb33_m3_9_owner_stand.py` — база до стопки и верхушка; новых ✗ нет.
- Перенос: `migrate_object_structures --dry-run` на стенд-БД с китами до и после, отчёт — в итог плана.

### 15.3. Исполнители (T-16; не больше трёх одновременно; срез — свежий исполнитель)
- У каждого: свой worktree, своя тест-БД `platform_s18_<срез>`, для стендовых срезов — копия
  стенд-БД и свой порт / номер базы Redis (таблица — в плане стопки 18 при раздаче).
- S1 и S6 — с `--create-db` (миграции). `PREFLIGHT_BASE` — коммит P0 либо верхушка после свода
  предшественников.
- Бриф: цитаты §10 дословно, справка `uv run python scripts/codemap.py --plan <план>` по файлам
  среза, список «не трогать» (файлы чужих строк), замки §14 первым коммитом.
- `preflight.py --slice` → пуш `claude/fb33-stack-18-<срез>` → конец хода; полный прогон — CI ветки.
- Координатор на верхушке: `.po`, `static/css/app.css`, полный `preflight`, `plan_check --verify`.

## 16. ECC-прогоны

| Шаг | Скиллы до кода | Агенты |
|---|---|---|
| План | `sa-increment`, `sa-block-editor`, `sa-storefront`, `sa-i18n`, `sa-cabinet-screen`, `database-migrations`, `accessibility` | `architect`, `database-reviewer`, `a11y-architect`, `security-reviewer` — ревью плана до кода, каждый с `docs/review-checklist.md` |
| S1 | `sa-storefront`, `database-migrations`, `postgres-patterns`, `django-patterns`, `django-tdd` | `django-reviewer`; `database-reviewer` (шесть миграций, блокировки, `lock_timeout`); `silent-failure-hunter` (охрана `save`, незнакомая версия) |
| S2 | `sa-storefront`, `django-tdd`, `seo` | `django-reviewer`; `silent-failure-hunter` (откат на общую при битой структуре); `security-reviewer` (превью черновика, `_may_preview`) |
| S4 | `sa-block-editor`, `django-celery` | `django-reviewer`; `silent-failure-hunter` (наследник акции, обходчики) |
| S5 | `sa-block-editor`, `django-security` | `django-reviewer`; `security-reviewer` (хост из запроса) |
| S3 | `sa-block-editor`, `sa-i18n`, `sa-cabinet-screen`, `django-security`, `django-tdd` | `django-reviewer`; `security-reviewer` (права, IDOR, код страницы); `silent-failure-hunter` (конфликты, гонки, блокировки); `database-reviewer` (счёт «Gilt für», N+1) |
| S6 | `sa-increment`, `database-migrations`, `deployment-patterns`, `error-handling` | `django-reviewer`; `database-reviewer` (обход 136 схем, блокировки строк); `silent-failure-hunter` (пропуски, отчёт) |
| S7 | `sa-block-editor`, `sa-stand`, `sa-i18n`, `e2e-testing`, `accessibility` | `django-reviewer`; `a11y-architect` (плашка, окно сброса, живая область); `e2e-runner` |
| S8 | `sa-cabinet-screen`, `sa-i18n`, `django-patterns` | `django-reviewer`; `a11y-architect` (`fieldset`, ссылки) |
| S10 | `sa-storefront` | `django-reviewer` |
| Стопка | `sa-increment` | `code-reviewer` перед FF; стенды §15.2; `doc-updater` в конце |

Ревьюеру в промпт — «пройди `docs/review-checklist.md` по каждому вопросу» и грабли `sa-block-editor`
/ `sa-storefront`. Находки круга — одной пачкой; находка — строка в `docs/skill-feedback.md` и замок
в том же коммите. До мержа все пункты закрыты.

## 17. 25 ловушек инвентаря (§10) — ответ на каждую

| № | Ловушка | Ответ |
|---|---|---|
| 10.1 | «наивный перенос» отвязывает объекты с пустяком в `page_override` | копия пишется только при **действующем** отличии (`candidate` ≠ общая); иначе `{"v": 1}`. `--dry-run` на копии прода до выката, число «своих» и серий — владельцу. Замок `test_m6_migrate_no_difference_means_inherit` |
| 10.2 | копия ≠ то, что видит посетитель | `candidate` повторяет правило показа (`detail_parts.flow`), сверка подписи вида на каждом объекте, HTML выборочно; расхождение — объект не трогается. Замки `test_m6_candidate_renders_like_legacy`, `test_m6_migrate_skips_on_view_mismatch` |
| 10.3 | настройки типа остаются общими | `flags` и `settings` — часть структуры, набор ключей из реестров; проекция кладёт их на ключи конфига, все читатели видят копию. Общие «Design» — осознанно общие. Замок `test_m6_copy_keys_come_from_registries` |
| 10.4 | у категории три независимых «своих» состояния | один признак — `Category.structure`; четыре сочетания сводит `candidate`; место баннеров не трогаем (решение 8), проверку блока «Banner» ведёт `place_banners` по хосту проекции. Замок `test_m6_migrate_category_four_states` |
| 10.5 | Студия — второй писатель и второй черновик | (а) хосты объектов Студия не рисует и не пишет (S5); (б) восстановление версии возвращает хосты в конфиг, но у объекта с `v` они не читаются; (в) перенос берёт только `structure == {}`; (г) история не откатывает страницы объектов — следствие решения 10, вопрос №5; (д) `structure_hash` и не должен: у структуры свой отпечаток |
| 10.6 | полный `save()` затирает поле | миксин исключает `structure` из полного `save()` существующей строки (образец `Tenant.save`), писатель — `QuerySet.update`; читатель берёт поле по pk. Замки `test_m6_full_save_keeps_structure`, `test_m6_form_save_never_writes_structure` |
| 10.7 | потолки теряют данные молча | новые структуры хостов не создают — потолок их не касается; перенос отчитывается «хост без живого объекта», «хост сверх потолка», «группа без ключа». Замок `test_m6_migrate_reports_ghost_and_overflow_hosts` |
| 10.8 | ежедневные акции съедают потолок | `clone` копирует структуру в наследника, хост не создаётся; старый объект `{}` с хостом у наследника становится структурой. Замок `test_m6_promo_heir_gets_structure_not_host` |
| 10.9 | `id` блоков не уникальны между хостами | структуры вне `site_config` — Студия по `pb_page_<id>` их не находит; внутри копии коллизия снимается суффиксом, перевод едет парой. Замок `test_m6_translations_follow_blocks_on_copy` |
| 10.10 | переводы живут не в блоке | оверлей — часть структуры (`i18n`), формат прежний; `localize / realign / split_translation / block_i18n` работают на проекции без второй реализации. Замки `test_m6_structure_overlay_uses_realign_only`, `test_m6_german_edit_drops_translation_in_structure` |
| 10.11 | обходчики конфига не видят блоки объектов | `object_structure.walk()` + список обходчиков под замком `test_m6_walkers_cover_structures`; будущий разовый перенос формата блоков обязан пройти и `walk` — строка в `sa-block-editor` |
| 10.12 | `normalize` — единственный валидатор | структура чистится тем же `siteconfig.normalize` на проекции под ключом своего / общего хоста (правила хоста действуют); вне `normalize` не хранится ничего. Замок `test_m6_project_lift_roundtrip` |
| 10.13 | правовые и «нескрываемые» инварианты | читатели те же (проекция), писатель повторяет фильтр; новый раздел реестра — в конец видимым. Замки `test_m6_lmiv_info_cannot_be_hidden_in_copy`, `test_m6_new_registry_section_appears_in_old_copy` |
| 10.14 | сохранение объекта не бесплатное | писатель и перенос — `update` без `post_save`; перенос не меняет `updated_at`. Замок `test_m6_migrate_no_post_save_no_updated_at` |
| 10.15 | кэш главной | `write` зовёт `bump_storefront_cache` в `on_commit`. Замок `test_m6_write_bumps_storefront_cache_on_commit` |
| 10.16 | права меняют смысл | решение 11: `website.edit` + право объекта из реестра (акция и группа — `marketing.edit`); на операцию и на запись. Замок `test_m6_object_right_required_for_copy_and_reset` |
| 10.17 | группа акций — не объект | `PromoGroupPage`: ключ байт-в-байт, `host` по md5, `view` вместо `promo_groups[key]`, цепочку наследования сводит `candidate`; страница переживает последнюю акцию (решение 15). Смена `Promotion.group` страницу не переносит — как сегодня, но страница остаётся видимой в списке |
| 10.18 | общего типа «Textseite» нет, системные страницы — не строки | стопка 19: хост `textseite`; «Über uns» и «Versand» держат свою структуру в фикс-хосте; правовые — без блоков (§11) |
| 10.19 | Teacher, Combo, BlogPost | стопка 19: сначала общий тип «Lehrer», затем вид в реестре; адрес блога по слагу — поле реестра «адрес превью» |
| 10.20 | `materialize_page_axes` и откаты | фильтр `structure == {}` в `page_axes_objects.build_index`; порядок шагов §6.2; истина — поле объекта. Замки `test_m6_materialize_axes_skips_marked_objects`, `test_m6_pin_own_categories_skips_marked` |
| 10.21 | окно деплоя | перенос после подъёма web; до него объект читается старым путём; старые данные не меняются; старый черновик снимается с сообщением (§5.4, §6.3). Замок `test_m6_old_object_draft_is_dropped_with_conflict` |
| 10.22 | размер строки в горячих запросах | у подавляющего большинства строк поле `{}`; большие значения Postgres хранит вне строки; потолок `STRUCTURE_MAX_BYTES`. Замер на стенде (5 000 товаров, 200 структур) — если список товаров заметно тяжелеет, `defer("structure")` в запросах списков — отдельной строкой roadmap. Менеджер по умолчанию не трогаем: отложенное поле ломает клон `pk = None` |
| 10.23 | адресация завязана на строку-хост | имена хостов остаются виртуальными (код страницы, черновик, `?seite=`, `von`, ⚙); `is_page_block_host` не сужается; разбор — `ref_for_host`. Замок `test_m6_host_prefix_exact_match` |
| 10.24 | сброс сегодня неполный | новый сброс — целиком (`{"v": 1}`); вкладка, её тексты и тесты снимаются в S8; «Kartenform» сброс больше не трогает. Замки `test_m6_reset_keeps_banner_places_card_style_faq`, `test_m6_removed_tab_leaves_no_callers_or_msgids` |
| 10.25 | мелкое | удалённый объект — отказ целиком, без частичной записи; структура категории живёт в строке, новый слаг чужого не получит; `site_schema.apply` для кодов объектов отказывает. Замок `test_m6_soft_deleted_object_code_404` |

## 18. Чеклист ревью — 40 ответов по плану

| № | Ответ | Замок / основание |
|---|---|---|
| 1 | риск есть: у структуры новый писатель, старые пути записи рядом | `test_m6_structure_single_writer`, `test_m6_full_save_keeps_structure` |
| 2 | риск есть: шесть списков видов | `test_m6_kind_registry_is_single_source` |
| 3 | риск есть: набор ключей копии, повторный разбор конфига | `test_m6_copy_keys_come_from_registries`, `test_m6_bind_one_projection_per_request` |
| 4 | риск есть: снимается вкладка, `apply_post`, `copy_blocks`, строки | `test_m6_removed_tab_leaves_no_callers_or_msgids`, `test_m6_walkers_cover_structures`; до снятия — `codemap` и grep вызовов |
| 5 | риск есть: префиксы хостов; `plan_check` — пройден; карта `fb33-map` — P0 | `test_m6_host_prefix_exact_match` |
| 6 | риск есть: битая структура, удалённый объект, незнакомая версия | `test_m6_broken_structure_renders_shared_200`, `test_m6_soft_deleted_object_code_404`, `test_m6_unknown_version_reads_as_inherit` |
| 7 | чисто: внешних действий нет, запись одной транзакцией | — |
| 8 | риск есть: откат на общую и пропуски переноса | `test_m6_bind_failure_logs_and_falls_back`, `test_m6_migrate_reports_every_skip` |
| 9 | риск есть | `test_m6_write_rechecks_fingerprint_under_lock` |
| 10 | риск есть | `test_m6_conflict_before_any_write`, `test_m6_reset_drops_block_translations`, `test_m6_banner_delete_cleans_pick_in_structures` |
| 11 | риск есть: отпечаток черновика объекта меняется | `test_m6_old_object_draft_is_dropped_with_conflict` |
| 12 | риск есть: позиционный оверлей | `test_m6_translations_follow_blocks_on_copy`, `test_m6_structure_overlay_uses_realign_only` |
| 13 | риск есть: кэш главной, языки сайта | `test_m6_write_bumps_storefront_cache_on_commit` |
| 14 | чисто: правило стопки — strict xfail первым коммитом | — |
| 15 | риск есть: 2 эталона у S7 | `test_m6_schema_goldens_changed_only_product` |
| 16 | риск есть: подписи видов в реестре, ≈ 70 msgid | `test_m6_kind_labels_lazy`, гейт `i18n_quickcheck` |
| 17 | риск есть | `test_m6_german_edit_drops_translation_in_structure` |
| 18 | чисто: новых `title` нет, имена — текстом | — |
| 19 | риск есть: сброс без JS | `test_m6_reset_without_js_page` |
| 20 | риск есть: фрагмент схемы подменяется | стенд `fb33_m6_struktur_stand.py` |
| 21 | риск есть: фокус в окне сброса и после | стенд `fb33_m6_struktur_stand.py` |
| 22 | риск есть: 🔒 и ⠿ | `test_m6_lock_and_grip_hidden_label_is_text` |
| 23 | чисто: движения нет | — |
| 24 | риск есть: окно сброса на 390 × 844 и 844 × 390 | стенд `fb33_m6_struktur_stand.py` |
| 25 | риск есть | `test_m6_reset_dialog_no_hidden_display_clash` |
| 26 | риск есть: размер структуры | `test_m6_structure_caps_enforced_with_message` |
| 27 | чисто: писем нет | — |
| 28 | риск есть | `test_m6_object_right_required_for_copy_and_reset`, `test_m6_names_hidden_without_view_right`, `test_m6_studio_rejects_object_hosts` |
| 29 | чисто в стопке 18; стопка 19 — стоимость «Versand» закреплена | `test_m6_versand_cost_pinned` (19) |
| 30 | чисто: внешних адресов нет | — |
| 31 | риск есть | `test_m6_detail_query_budget`, `test_m6_counts_query_budget` |
| 32 | риск есть: шесть миграций на ≈ 136 схем; перенос — шагом `deploy.sh` | `test_m6_migrations_additive_db_default`, замер на стенде (решение 12) |
| 33 | риск есть: сброс и «Speichern» из `aufbau.js` | `test_m6_reset_double_submit_idempotent`, стенд |
| 34 | риск есть | `test_m6_live_region_outside_swapped_fragment`, стенд |
| 35 | риск есть: `aria-describedby` у каждой ⚙ | `test_m6_describedby_targets_unique` |
| 36 | риск есть: имена объектов бизнеса в интерфейсе | `test_m6_object_names_lang_attr` |
| 37 | риск есть: переводы блоков копии | `test_m6_structure_overlay_uses_realign_only` |
| 38 | чисто: SEO страницы и `<title>` витрины не трогаем | — |
| 39 | сделано: §15.1, команды и числа по всем 24 каталогам | — |
| 40 | риск есть: образец «до» — существующие файлы `golden_fb31p5`, не рендер нового кода | `test_m6_candidate_renders_like_legacy` |

«Риск есть» — 31; «чисто» — 9 (№7, 14, 18, 23, 27, 29, 30, 38, 39).

## 19. Отложенное в `docs/roadmap-next-sprints.md`

| ID | Что с ним |
|---|---|
| S14-E4-route-fp (`:566`) | половина «разделы» закрывается: форма структуру не пишет (S8), полный `save()` поле не трогает (S1). Маршрут тура — остаётся |
| S14-E1-L6 (`:575`) | закрывается для страниц объектов: ⚙ и окно «Seite» правят настройки этой страницы (S3). Для общих страниц — без изменений |
| S15-von (`:562`) | не закрывается в 18; в 19 разбор текстовой страницы идёт через `ref_for_host` — закрыть там |
| S16-realign-dup (`:663`) | задевается: копия сохраняет `id`, коллизия внутри копии снимается суффиксом; общий дефект `realign` остаётся |
| S15-draft-fp (`:555`) | не задевается: Студия структуры не видит |
| S16-hreflang (`:662`) | не задевается: `seo.pages` остаётся в `site_config` |
| S14-E2-ghost, S14-E1-text, S15-versand, S15-versand-gear, S15-upper-slug, S14-E8-cleanup | инварианты сохраняются: существование — через `host_for`, один регэксп хоста страницы, два хоста «Versand» (стопка 19 — сторожа) |

Новые строки в «Отложено» (P0): `M6-defer` (замер списков товаров), `M6-list-link` (ссылка в строке
списка кабинета), `M6-cleanup` (стопка 20: состав уборки, §11), `M6-group-rename` (смена
`Promotion.group` не переносит страницу группы).

## 20. Риски
- **Проекция в `raw_config` — новый общий путь витрины.** Ошибка в ней видна на всех страницах со
  своей структурой. Защита: чистые функции, откат на общую при любой ошибке с логом, старый путь у
  `{}` не меняется (30 эталонов), стенд по восьми видам.
- **Тег или вьюха читает конфиг мимо `raw_config`** (`tenant.site_config` напрямую) — на своей
  странице покажет общую. Предпосылка — проверить в срезе S2: grep прямых чтений в
  `templates/storefront/` и тегах; найденное — через `raw_config`.
- **`save` с полным списком `update_fields`.** Приёмники, для которых `update_fields is None`
  значит «полное сохранение»: у Product и Category поведение то же (§1). Предпосылка — проверить в
  срезе S1 остальные приёмники девяти моделей и `Product.save` (`apps/catalog/models.py:362-375`).
- **Событийные серии.** Повторы с одинаковыми отличиями станут отдельными копиями (N повторов — N
  копий). Число — в отчёте `--dry-run`, вопрос №7.
- **Права.** Сотрудники с `website.edit` без права объекта теряют правку блоков объектов (решение 11).
- **Старые хосты до стопки 20** продолжают занимать потолок и читаться `normalize` на каждом запросе
  — не хуже сегодняшнего; у объектов с `v` они мёртвые. В кабинете «где показан баннер» старые
  хосты перенесённых объектов скрывает один предикат `object_structure`.
- **Миграции на ≈ 136 схем**: очередь блокировок за долгой транзакцией. `lock_timeout`, повтор по
  схеме, деплой вне пика, замер на стенде.
- **Объём S1 и S3.** Самые большие срезы; оба — цепочкой, не параллельно друг другу; S3 — отдельной
  волной с одним соседом.
- **Рассмотрено и отклонено**: одна отдельная таблица структур вместо поля у каждой модели (сняла бы
  охрану `save`, шесть миграций и вопрос размера строки) — противоречит решениям 3 и 8; вернуться,
  только если замер на стенде покажет проблему.

## 21. Вопросы владельцу (только то, чего нет в решениях 1–16)
1. **«Ähnliche Produkte» у товара.** На артборде у строки стоит ⠿ и нет 🔒, а порядок разделов товара
   закреплён (решение 1), и в коде это раздел. Рекомендация: 🔒 «Reihenfolge fest», без ⠿.
2. **Ссылка «Im Seitenaufbau ansehen →» в строке списка товаров.** Рекомендация: в стопке 18 не
   делать (путь «список → форма → „Seite im Shop“»), вынести в отложенное `M6-list-link`.
3. **Свои вопросы FAQ объекта при сбросе.** Рекомендация: это содержимое объекта, как фото и
   «Kartenform», — сброс их не трогает и в список потерь не включает.
4. **Поля `structure` для Kombi, блога, учителя и своей страницы — уже в миграциях стопки 18**, чтобы
   проход по всем схемам был один. Рекомендация: да.
5. **«Version wiederherstellen» в Студии не откатывает свои структуры объектов** (следствие решения
   10). Рекомендация: принять; подсказку в Студии не добавлять.
6. **Слова для остальных видов** в фразах «Wie alle …seiten», «gilt für … Produkte», «Gilt für … von
   … Produkten.», «… mit eigener Struktur», «Für alle …», «Anderes … öffnen». Предложение:
   Leistungen, Zimmer, Veranstaltungen (у общего типа событий и туров — «Veranstaltungen und Touren»),
   Angebote, Kategorien, Angebotsgruppen; в стопке 19 — Kombis, Blogbeiträge, Lehrer, Seiten.
7. **Серии событий.** Повторы с одинаковыми отличиями переносятся каждый своей копией, новый клон
   серии получает копию исходного. Рекомендация: так и оставить; число — в отчёте `--dry-run`.
8. **Блок «＋ Block» и метки правки Студии на странице со своей структурой** не показываются (Студия
   её не правит). Рекомендация: принять; ⚙ Студии ведёт в «Seitenaufbau» этой страницы.
