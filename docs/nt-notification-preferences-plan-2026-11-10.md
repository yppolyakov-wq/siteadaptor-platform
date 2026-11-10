# NT «Benachrichtigungen nach Wahl» — центр подписок портала (A) и темы рассылки магазина (B)

План от 2026-11-10. Запрос владельца: «полноценная система подписок на уведомления, настраиваемая
только из выбранных категорий, или отмена — частично или всех»; решения: **оба контура** (портал
города + Newsletter магазина), **бот портала тоже**; дополнение владельца — «для подписки нужны
опции, как в фильтре (vegan, halal…), и марка, если появится»; остальное — по рекомендации
(Р-NT1…Р-NT7 приняты). Разведка — агент `planner` (ECC).

## 0. Что есть

- Портал: `FollowSubscription` (`aggregator/models.py`, виды business/section/district/query,
  уникальность `(user, kind, key, city, channel)`), DOI подписанным токеном (до клика в БД ничего),
  `parse_target` сворачивает категорию в раздел (Р-1b T-8.7), лимит 20 (10 поисков), сводка
  `follow_digest.build_digest` (дедуп `seen`), страница управления `follow_manage` (по одной / все),
  `follow_unsubscribe` (RFC 8058), бот `portal_bot.py` (`fk:`→`fy:`, список `u:<pk>`, «все» нет).
- Фильтры выдачи: `listings_for(city_category=…, city_tag=…)`, марка — `brand__iexact` (T-8.10d);
  признаки — `city_categories.TAGS` (+ `TAGS_BY_SECTION`).
- Магазин: `Customer.marketing_opt_in/unsubscribed/unsubscribe_token`, `NewsletterCampaign`,
  `CouponCampaign`, `promotions/newsletter.py` (`consented_customers`, `segment_customers` с
  `annotate`), витрина `newsletter_signup`/`newsletter_confirm`/`unsubscribe`. Тем нет.

## 1. Решения

- **Р-NT1** Категория — свой вид цели `category`; «Folgen» на странице категории подписывает на
  неё, переключатель «Nur <Kategorie> / Ganzer Bereich».
- **Р-NT2** Раздел покрывает свои категории: в центре хранится раздел ИЛИ его категории; все
  категории раздела отмечены → один раздел. В письме позиция не повторяется (`seen`), узкое первым:
  business 0 · query 1 · category/tag/brand 2 · section/district 3.
- **Р-NT3** Лимит 20 → 40 (`max_follows`), поиски 10; в письмо — все подписки, но ≤ 60 позиций.
  Сохранение сверх лимита отклоняется целиком с подсказкой «Bereich statt einzelner Kategorien».
- **Р-NT4** Подписки-поиски из ОДНОГО условия `kat=<категория>` / `merkmal=<признак>` /
  `marke=<марка>` переносятся в новые виды (data-миграция; дубль сливается, `confirmed_at` —
  более ранний).
- **Р-NT5** Магазин: без выбора тем = все темы (и будущие); кампания без темы — всем согласившимся;
  тему с кампаниями не удалить (PROTECT), только выключить.
- **Р-NT6** Бот: категории раздела переключателями ☐/✅ → «Speichern (N)» → согласие «Ja, folgen»;
  список подписок страницами + «🗑 Alle beenden» с подтверждением (email-подписки не трогает).
- **Р-NT7 (владелец)** Признаки и марки — тоже цели подписки: вид `tag` (ключ из `TAGS`: vegan,
  halal, bio…) и вид `brand` (ключ — марка, нормализованная `search.clean_brand`, сравнение без
  регистра). В центре — блоки «Merkmale» (все признаки реестра; на тематическом портале — только
  его) и «Marken» (только марки, которые реально есть в каталоге области, одним агрегатом;
  блок скрыт, пока марок нет). Признак/марка — самостоятельная подписка (OR с категориями, как
  отдельные «интересы»). Сочетание «категория И признак» («Bäckereien, nur vegan») — подписка на
  поиск (уже есть, T-8.10d); в центре — ссылка «Kombination als Suche speichern».

## 2. Портал (A)

### A1 — новые виды целей (⚠️ `aggregator/0040` choices, `0041` перенос данных)
- `TARGETS += category, tag, brand` (instant только у бизнеса — ограничение не трогаем).
- `follow.py`: `Target.label`/`as_params` (`bereich`, `merkmal`, `marke`), `parse_target`
  (категория → category, `?umfang=bereich` → section; `?merkmal=` → tag; `?marke=` → brand),
  `items_for` (category: `city_category`; tag: `city_tag`; brand: `brand__iexact` — товары и акции
  на товар), `scope_url` (`kat`/`merkmal`/`marke` + `neu=1`).
- `follow_query.legacy`: одно условие `kat=<кат.>`/`merkmal`/`marke` → новая цель.
- `follow_digest`: порядок Р-NT2, константы из `_cfg`, потолок позиций на письмо.
- `0041`: перенос query-строк из одного условия (Р-NT4), идемпотентно, обратный ход noop.
- Замки ДО кода (`test_follow_kinds.py`): парсинг; `items_for` ⊆ «Alle anzeigen»; одна позиция
  под category и section — один раз, под категорией; перенос + слияние дубля; два условия
  остаются query; лимит письма ≥ лимита подписок.

### A2 — центр «Benachrichtigungen auswählen» (без миграций)
- `apps/aggregator/follow_center.py`: `tree(portal)` (разделы → непустые категории области, одним
  агрегатом; тема портала), `tags(portal)`, `brands(portal)`, `state(user, city, channel)`,
  `normalize(...)` (только ключи реестра; категории под отмеченным разделом убираются; все
  категории → раздел; районы через `districts.normalize`), `apply(user, desired, *, frequency,
  portal, source_host, channel, mode="set"|"add")` — одна транзакция под блокировкой жителя, diff
  по видам section/category/district/tag/brand этого канала и города (business/query не трогает),
  лимит по ИТОГОВОМУ множеству, `mode="add"` (DOI) никогда не удаляет.
- Вьюха `follow_center` (`folgen/auswahl/` в `urls_portal` и `urls_public`): вошедший — GET/POST
  (PRG), аноним — та же форма + e-mail + honeypot/метка времени/лимиты `follow_page` → одно DOI-письмо
  (токен v2 со списком целей, ≤ 40 ключей, сжатый); `follow_confirm` различает v2: GET показывает
  список, POST — `apply(mode="add")`; ключи перепроверяются.
- Входы: `/konto/`, страница управления, подвал портала, страница раздела.
- Партиал `_follow_tree.html`: fieldset/legend на раздел, чекбоксы; без JS работает (сервер
  нормализует), с JS — раздел отмечает и блокирует категории, `indeterminate`.
- Замки: diff; раздел+категория → раздел; все категории → раздел; лимит без частичной записи;
  DOI v2 GET без эффектов / POST только добавляет / мусор отброшен; одинаковый ответ анонима;
  тема портала; каналы не смешиваются; марки только существующие.

### A3 — частичная и полная отписка (без миграций)
- `follow_manage`: чекбокс у каждой строки, «Ausgewählte abbestellen» + «Alle abbestellen».
- Страница из письма (`follow_unsubscribe`): GET — все подписки, отписываемая отмечена; POST с
  `subs` — частично, без `subs` — прежний one-click (RFC 8058 паритет). Чужие токены игнорируются.
- Подвал сводки: «Diese abbestellen · Verwalten · Alle abbestellen».

### A4 — бот (без миграций)
- `kc:<раздел>` категории ☐/✅ (`edit_message_reply_markup`, состояние в кэше), `ks:` сохранить →
  согласие → `fy:` → `follow_center.apply(scope=раздел, channel=telegram)`; признаки — кнопкой
  «🏷 Merkmale» тем же переключателем; список страницами по 10 + «🗑 Alle beenden» (`ua`/`uy:`).
- Нажатия ≤ 64 байт, nonce одноразовый, все строки на 5 языках.

## 3. Магазин (B)

- **B1** (⚠️ `promotions/0036`): `NewsletterTopic` (name + i18n, position, is_active, category FK
  null) + `CustomerNewsletterTopic` (customer, topic, confirmed_at, source) + `topic` у
  `NewsletterCampaign`/`CouponCampaign` (PROTECT). Фильтр получателей ТОЛЬКО через `Exists`
  (`segment_customers` агрегирует — JOIN удвоил бы LTV). `set_topics` — единственный писатель.
- **B2** форма витрины с темами (без выбора = все) + DOI v2 (старые токены-строки работают).
- **B3** страница `newsletter/einstellungen/<token>/` — сузить темы / отписаться от всех;
  расширение у отписавшегося — только новым DOI; подвал писем «Themen wählen».
- **B4** кабинет: экран тем (шторка, переводы), тема кампании + число получателей, темы в CRM
  (только при уже данном согласии).
- **B5** ЛК клиента, DSGVO (экспорт/удаление), демо `cafe`.

## 4. Порядок
A1 → A2 (вошедший) → A2 (аноним, DOI v2) → A3 → A4 → B1 → B2 → B3 → B4 → B5. Каждый шаг: замки ДО
кода → ветка → зелёный CI → FF в `main`.

## 5. Право
UWG §7: каждая новая цель/тема — только после клика из письма или кнопки согласия в боте; страница
настроек из письма только сужает. DSGVO Art. 7: `confirmed_at` + `source_host`/`source` у каждой
строки. RFC 8058 one-click не меняется. Абзацы Datenschutz — на юридическую вычитку владельцу.

## 6. Риски
Лимит 40 → больше запросов в сводке (замерить на демо Solingen); смена Р-1b (старые ссылки
`?bereich=<кат.>` теперь подписывают на категорию — отметить в build-log); перенос данных — сливать
дубли до UPDATE; `editMessageReplyMarkup` падает на старом сообщении → новое сообщение; поля дерева
не делать `required` в скрытом блоке; дерево обязано работать без JS.

## 7. ECC-прогоны
Скиллы до кода: `django-patterns`, `django-tdd` (все), `database-migrations` + `postgres-patterns`
(A1, B1), `django-security` (A2/A3/B2/B3), `accessibility` (A2, B4), `e2e-testing` (A2, A4).
Агенты: `django-reviewer` перед каждым мержем; `security-reviewer` — DOI v2, частичная отписка по
токену, nonce бота, совместимость DOI магазина; `database-reviewer` — `0040`/`0041`/`0036`;
`silent-failure-hunter` — сводка (выпадающие подписки) и фильтр получателей; `a11y-architect` —
дерево чекбоксов и страница тем; Playwright-стенд — дерево (JS/без JS, 390/1440, de/ru), отписка из
письма, форма тем магазина.
