# Оглавление ядра `apps/core` — что уже есть (T-15.3)

Собирается командой `uv run python scripts/codemap.py --core-index`; руками не править.
Нужен, чтобы найти готовый модуль, а не завести второй. Назначение — первая строка описания
модуля; подробности и «единственные писатели» — `docs/project-memory.md` §3. Связи одного файла —
`uv run python scripts/codemap.py <файл>`. Числа обновляются при пересборке; замок сверяет только
то, что каждый модуль ядра здесь есть (`apps/core/tests/test_codemap.py`). Команды управления и
шаблонные теги зовутся по имени, а не импортом — нули в их строках не значат «не используется».

| Модуль | Назначение | Файлов-импортёров | Приложений | Кто зовёт (до шести) |
|---|---|---|---|---|
| `admin.py` | Чистка платформенной админки (public-схема). | 1 | 0 |  |
| `admin_dashboard.py` | KPI-дашборд платформенной админки (unfold DASHBOARD_CALLBACK). | 0 | 0 |  |
| `apps.py` | — описания нет | 0 | 0 |  |
| `archetypes.py` | M20U: «главный товар» по архетипу — primary_item registry. | 26 | 6 | aggregator, booking, catalog, inventory, promotions, tenants |
| `assistant.py` | AIS-A A-0: ядро шторки «✨ Assistent» — без ИИ, только чтение. | 6 | 0 |  |
| `assistant_actions.py` | AIS A-4a: «KI-Aktionen» — пакет «создать» из помощника с предпросмотром и откатом. | 7 | 0 |  |
| `assistant_ai.py` | AIS A-2: ИИ-ответ на свободный вопрос в шторке «✨ Assistent». | 8 | 1 | scripts |
| `assistant_ai_actions.py` | AIS A-4e: ИИ-задача `assistant_actions` — фраза, которую не поймали правила, → пакет | 4 | 0 |  |
| `assistant_bulk.py` | AIS A-4d: «alle Kuchen 10 % teurer / скрой все товары категории Торты» — массовое изменение | 4 | 0 |  |
| `assistant_changes.py` | AIS A-4b: «измени цену / скрой / перенеси» — пункты пакета для СУЩЕСТВУЮЩИХ объектов. | 9 | 0 |  |
| `assistant_clarify.py` | AIS A-5b: уточняющий вопрос помощника вместо тупикового «bitte genauer». | 5 | 0 |  |
| `assistant_escalate.py` | AIS A-5d: «Das funktioniert nicht / ich brauche einen Menschen» — из поля помощника прямо в | 2 | 0 |  |
| `assistant_followup.py` | AIS A-5c: «und den Käsekuchen auch» — продолжение прошлого хода помощника. | 1 | 0 |  |
| `assistant_history.py` | AIS A-3d: история переписки с помощником — единственный писатель `AssistantTurn`. | 5 | 0 |  |
| `assistant_pages.py` | AIS A-4c: «покажи товары списком / 4 в ряд / шаблон Kompakt» — пункт пакета для настройки | 3 | 0 |  |
| `assistant_panel.py` | AIS A-3c: плавающая панель «✨ Assistent» — вкладки KI · Support · Kunden в шторке. | 2 | 0 |  |
| `assistant_phrases.py` | AIS A-6a: эталонные фразы помощника (5 языков кабинета × каждый обработчик роутера). | 1 | 0 |  |
| `assistant_quality.py` | AIS A-6b: отчёт качества помощника — только для команды `assistant_report` (оператор платформы | 1 | 0 |  |
| `assistant_router.py` | AIS A-5a: один «мозг» помощника — реестр обработчиков фразы вместо цепочки if/elif во вьюхе. | 3 | 0 |  |
| `assistant_stats.py` | AIS A-6b: счётчики исходов помощника по дням — только КОДЫ, без текста фраз. | 4 | 0 |  |
| `assistant_views.py` | AIS-A A-0: шторка «✨ Assistent» (GET, без ИИ, ничего не пишет). | 1 | 1 | config |
| `attribution.py` | В5 V5-5: откуда пришла сделка — канал (`ch`) и карточка каталога города (`cl`). | 10 | 8 | aggregator, booking, events, inbox, jobs, orders |
| `audit.py` | Совместимость: FSM (apps/core/fsm.py) импортирует audit_event отсюда. | 13 | 5 | events, jobs, promotions, publishing, stays |
| `aufbau_draft.py` | FB-27 R2: черновик экрана «Seitenaufbau» — правки копятся и попадают на сайт | 11 | 0 |  |
| `balance_pay.py` | KA-12 B2-5 (E1.11): онлайн-оплата ОСТАТКА после Anzahlung. | 8 | 4 | billing, booking, events, stays |
| `bank_notify.py` | KA-H2: письмо владельцу о смене банковских реквизитов Vorkasse. | 1 | 1 | orders |
| `banner_views.py` | FB-29.2 S2: кабинет «Website › Banner» — библиотека баннеров. | 1 | 1 | config |
| `banners.py` | FB-29.2: библиотека баннеров — единственный писатель и читатель модели `Banner`. | 13 | 4 | catalog, imports, promotions, tenants |
| `block_card.py` | FB-33 M3-4: вкладка «Karte» окна блока (макет M0-2). | 1 | 0 |  |
| `block_catalog.py` | FB-33 M2a: каталог блоков — какие блоки одна СЕМЬЯ и как они выглядят в библиотеке. | 5 | 1 | tenants |
| `block_i18n.py` | FB-33 M3-5c: переводы текстов блока в окне «Seitenaufbau» — единственный писатель. | 3 | 0 |  |
| `block_views.py` | FB-32 S5a: один реестр видов блока «Kategorien» для главной и каталога (решение владельца | 3 | 0 |  |
| `block_window.py` | FB-33 M3-1: окно блока — вкладки панели «Seitenaufbau». | 3 | 0 |  |
| `bots.py` | В5: «это не человек» — для счётчиков, а не для защиты. | 1 | 1 | aggregator |
| `bulk_actions.py` | KA-12 E2.1: массовая смена статуса сделок из списка продаж. | 3 | 1 | orders |
| `business_card.py` | T-8.1b: карточка «So finden Sie uns» на странице акции (план | 4 | 3 | aggregator, promotions, tenants |
| `cachescan.py` | Удаление ключей кэша по шаблону (DSGVO: данные со случайными ключами — черновики, | 1 | 1 | platform_bot |
| `card_forms.py` | DL-19: реестр ФОРМ карточки товара и акции (план | 14 | 4 | booking, catalog, promotions, tenants |
| `checkout_window.py` | FB-33 C5: вкладка «Felder» у строки формы корзины (`cart/form`) в окне блока. | 1 | 0 |  |
| `checks.py` | Security-check: инварианты изоляции сессий между схемами тенантов (HIGH-10). | 1 | 0 |  |
| `cities.py` | FB-19: поле «Stadt» — подсказки городов и каноническое написание. | 5 | 1 | tenants |
| `city_categories.py` | T-8.13a: единые категории каталога города — справочник платформы. | 35 | 5 | aggregator, catalog, platform_bot, promotions, tenants |
| `closures.py` | KA-12 E4.1a: Betriebsferien — закрытие всего бизнеса на дни (отпуск, праздники). | 14 | 5 | aggregator, booking, orders, promotions, tenants |
| `colors.py` | Цвета и контраст WCAG 2.x — общий слой витрины и городского портала (PH-12b). | 2 | 1 | aggregator |
| `compositions.py` | LAY-2: ЕДИНЫЙ реестр композиций страницы («шаблонов вывода структуры»). | 9 | 3 | catalog, promotions, tenants |
| `config_migration.py` | Общая механика переноса настроек сайта (`Tenant.site_config`) командами деплоя. | 3 | 0 |  |
| `confirmation_page.py` | FB-33 M2h: страница подтверждения — один хост блоков `confirmation` на заказ, запись, номер, | 7 | 1 | tenants |
| `confirmation_views.py` | FB-33 M2h-5: превью страницы подтверждения для «Seitenaufbau». | 1 | 1 | config |
| `contact_access.py` | KA-12 E6.7g: ДОСТУП к контактам клиентов (e-mail, телефон) — по праву «Kontaktdaten der Kunden | 9 | 5 | crm, events, inbox, jobs, stays |
| `contacts.py` | KA-12 E6.6: сравнение контактов клиента. | 2 | 2 | orders, promotions |
| `content_page_views.py` | M21.6: свои страницы сайта — витрина ``/seite/<slug>/`` и кабинет «Website › Seiten». | 1 | 1 | config |
| `content_pages.py` | M21.6: свои страницы сайта (`core.ContentPage`) — единственное место правил. | 12 | 5 | catalog, imports, orders, promotions, tenants |
| `context.py` | Context processor: активные модули для навигации кабинета (Track D / D0a). | 1 | 1 | tenants |
| `context_processors.py` | SEO-1: context processor витрины — резолвит title/description из движка | 0 | 0 |  |
| `csrf.py` | Диагностическая страница ошибки CSRF (403). | 0 | 0 |  |
| `csv_safe.py` | Нейтрализация CSV formula/DDE-инъекции при экспорте (MEDIUM). | 6 | 5 | crm, events, finance, inventory, stays |
| `dashboard.py` | Виджеты и хаб-плитки главной кабинета `/dashboard/`. | 3 | 2 | aggregator, billing |
| `day_home.py` | UX-D D8.1: главная = сводка дня у ВСЕХ видов продаж (не только у отеля). | 1 | 0 |  |
| `deal_card.py` | DC-1: единый скелет карточки сделки (ТЗ владельца 2026-08-25). | 5 | 5 | booking, events, jobs, orders, stays |
| `deal_discount.py` | DC-5: скидка владельца на карточке ЛЮБОЙ сделки (ТЗ владельца 2026-08-25). | 3 | 1 | orders |
| `deal_invoice.py` | DC-6: счёт из сделки — одна точка для всех поверхностей. | 2 | 1 | stays |
| `deal_lines.py` | DF-4: состав сделки СТРОКАМИ — как на утверждённом макете. | 2 | 1 | inbox |
| `deal_links.py` | VS-3: сервис связей «якорь + прикреплённые сделки» (план | 8 | 6 | booking, events, jobs, orders, stays, tenants |
| `demo_switch.py` | DL-8e: смена шаблона НА ДЕМО-ВИТРИНЕ без входа в кабинет. | 3 | 2 | config, promotions |
| `design_page.py` | DL-7b: экран «Design» кабинета — переключатель шаблонов вне Studio. | 1 | 1 | config |
| `design_samples.py` | FB-29.8b: товары-примеры для предпросмотра дизайна на пустом магазине. | 5 | 4 | booking, events, promotions, stays |
| `detail_parts.py` | FB-31 P5: детальная страница — разделы и свои блоки одной схемой | 21 | 7 | booking, events, orders, promotions, scripts, stays |
| `detail_sections.py` | UA4-1 (U-A): единый реестр секций детальной страницы — KEYS + подписи (LABELS) | 10 | 5 | booking, events, scripts, stays, tenants |
| `diagnoses.py` | AIS-A A-0: реестр диагнозов помощника — «почему не работает» без ИИ. | 3 | 0 |  |
| `digest.py` | C1: утренний дайджест владельцу — сбор метрик ТЕКУЩЕЙ схемы тенанта. | 4 | 1 | stays |
| `directions.py` | AIS-M M-0: направления продаж — единственный ответ на «как продаёт этот бизнес». | 15 | 2 | booking, tenants |
| `directions_screen.py` | AIS-M M-1c: экран «Richtungen & Funktionen» (`/dashboard/modules/`). | 1 | 0 |  |
| `districts.py` | T-8.17: реестр районов городов (план docs/t8-15-districts-portal-plan-2026-10-09.md). | 26 | 3 | aggregator, platform_bot, tenants |
| `documents.py` | I18N-7b: общий слой печатных документов (PDF) — язык, шрифт, форматы. | 21 | 8 | catalog, events, finance, inventory, jobs, orders |
| `drawer.py` | UX-D D1: шторка кабинета — серверная половина. | 16 | 8 | booking, collections, finance, inventory, orders, promotions |
| `extras.py` | Универсальный движок Extras (#7): доп-услуги к брони на все архетипы. | 11 | 5 | booking, events, finance, stays, tenants |
| `extras_pages.py` | UX-D D6.1: «Zusatzleistungen» — список строками, «＋ Zusatzleistung» шторкой и страница | 2 | 1 | config |
| `facets.py` | UB2-1: протокол `FacetProvider` — единый интерфейс фасетов листингов витрины. | 15 | 6 | booking, catalog, events, promotions, stays, tenants |
| `faq_content.py` | FB-33 M3-5b: вопросы FAQ сайта — один писатель (`site_config["faq"]` и его переводы). | 6 | 0 |  |
| `faq_views.py` | FB-33 M2b-2a: виды блока FAQ — ЕДИНСТВЕННЫЙ список видов FAQ на всех страницах. | 5 | 1 | tenants |
| `finder.py` | FD-1: Finder «вопросы → 3 предложения» — rule-based guided selling. | 5 | 2 | promotions, tenants |
| `folio.py` | KA-12 B2-3: фолио платежей сделки (`core.DealPayment`). | 15 | 6 | booking, events, finance, jobs, orders, stays |
| `form_answers.py` | FB-33 M2i: свои вопросы формы и ответы на них — чистое ядро (без моделей и site_config). | 11 | 3 | account, jobs, orders |
| `form_fields.py` | KA-M2: денежное поле, которое понимает «12,50» на любом языке кабинета. | 6 | 3 | catalog, events, promotions |
| `form_spec.py` | FB-33 M2i: «Поля форм» — какие поля формы заявки и оформления спрашивать и какие обязательны. | 11 | 3 | jobs, orders, tenants |
| `freshness.py` | Г3: «срок свежести» товаров и услуг в каталоге города. | 10 | 4 | aggregator, booking, catalog, imports |
| `fsm.py` | Декларативная машина состояний. Спецификация: docs/references/patterns/state-machine.md. | 36 | 13 | account, billing, booking, events, finance, inbox |
| `funnels.py` | E5 «задача-первым»: реестр шагов воронок покупки для прогресс-степпера. | 1 | 1 | tenants |
| `grid_filler.py` | DL-11 «Volle Reihen»: плитка-подсказка для неполного последнего ряда листинга. | 1 | 1 | promotions |
| `health.py` | Health / readiness endpoints. | 3 | 1 | config |
| `help_articles.py` | AIS A-1: статьи справки шторки «✨ Assistent» — реестр в коде, поиск без ИИ. | 3 | 0 |  |
| `hero_tiles.py` | Первый экран «ловит направления» (фидбэк владельца 2026-07-30): плитки-входы | 7 | 1 | tenants |
| `i18n_cabinet.py` | T1 (FB-12): язык КАБИНЕТА (админ-панели) — отдельно от языка витрины. | 7 | 2 | platform_bot, tenants |
| `i18n_input.py` | L3d: per-locale ввод для моделей с overlay-семантикой i18n. | 23 | 6 | booking, catalog, collections, events, promotions, stays |
| `i18n_json.py` | Overlay-переводы для ВЛОЖЕННОГО JSON (аудит переводов демо 2026-08-13). | 2 | 2 | events, tenants |
| `i18n_seq.py` | Overlay-переводы для СПИСОЧНЫХ полей (план i18n-owner-content-2026-08-01). | 3 | 2 | booking, events |
| `i18n_translate.py` | AIS-5: «🌐 Übersetzen» — перевод базового текста в ПУСТЫЕ поля языка ввода. | 4 | 0 |  |
| `iban.py` | KA-H2: проверка и маскирование IBAN (ISO 13616, контрольная сумма mod-97). | 3 | 1 | orders |
| `inline_edit.py` | UC2-4: единый диспетчер инлайн-правки канвы витрины. | 5 | 5 | booking, catalog, events, promotions, stays |
| `integration_status.py` | Статусы подключений (read-only) — общие для «Integrationen» и «Sichtbarkeit» (T-8.31c). | 2 | 0 |  |
| `jobs.py` | Идемпотентные Celery-задачи. Спецификация: docs/references/patterns/notification-dedupe.md. | 13 | 12 | account, aggregator, ai, audit, billing, crm |
| `labels.py` | FB-20: метки («Neu», «Beliebt», …) — один реестр для всех продаваемых сущностей. | 10 | 5 | booking, catalog, events, promotions, stays |
| `langs.py` | Короткие ярлыки локалей для пилюль переключателей языка. | 4 | 1 | tenants |
| `legacy_redirects.py` | M21.1: переадресации со старых адресов (переезд с другой платформы). | 3 | 1 | imports |
| `legal.py` | L5/E-2: резолвер правовых текстов витрины. | 3 | 2 | promotions, tenants |
| `legal_buttons.py` | FB-33 M3-6 (макет M0-10): закреплённые правовые строки «Seitenaufbau» и подписи их кнопок. | 2 | 0 |  |
| `list_blocks.py` | LB-1: блок «Liste» — выборка источника и действующий вид. | 10 | 2 | promotions, tenants |
| `list_filters.py` | FLT-4b: строка фильтров списка кабинета — поиск, «Filter · N», сортировка, пилюли, шторка. | 4 | 2 | finance, promotions |
| `list_panel.py` | FB-27 R3b-2: настройки блока «Liste» в панели «Seitenaufbau» — | 3 | 0 |  |
| `listing_composition.py` | STU-18d: композиция ЛИСТИНГА — одна точка сборки контекста для девяти страниц. | 7 | 6 | booking, collections, events, orders, promotions, stays |
| `listing_parts.py` | FB-31 P4: девять страниц-списков, «Team» и «Galerie» — оси блоков вместо кода шаблона | 8 | 3 | events, promotions, tenants |
| `lite_cabinet.py` | T-8.23c: лёгкий кабинет для магазинов «Nur Aktionen» (план | 11 | 2 | config, promotions |
| `lite_home.py` | T-8.31a: «Start» лёгкого кабинета (план docs/t8-31-mein-laden-plan-2026-10-20.md §2). | 1 | 0 |  |
| `machine_http.py` | T-8.8: HTTP-обвязка машинных ресурсов (фид, sitemap): условный GET + Cache-Control. | 2 | 1 | aggregator |
| `management/commands/assistant_eval.py` | AIS A-6a: точность помощника на эталонных фразах (5 языков × каждый обработчик). | 0 | 0 |  |
| `management/commands/assistant_report.py` | AIS A-6b: отчёт качества помощника по бизнесам — только коды и числа. | 0 | 0 |  |
| `management/commands/backfill_media_registry.py` | CM-4: идемпотентный засев реестра MediaAsset из существующих FileRef-копий. | 0 | 0 |  |
| `management/commands/detach_quick_links.py` | FB-33 M2c-2: «Быстрые ссылки» из баннера главной — в отдельный блок (шаг `deploy.sh`). | 0 | 0 |  |
| `management/commands/form_i18n_realign.py` | FB-33 M2i-5b: старые позиционные переводы вариантов «Art der Veranstaltung» — ключом по | 0 | 0 |  |
| `management/commands/import_banners.py` | FB-29.2: перенос прежних слайдов баннера главной в библиотеку «Website › Banner». | 0 | 0 |  |
| `management/commands/materialize_page_axes.py` | FB-31.7: перенос прежних кодов шаблонов страниц в строки-оси «Seitenaufbau». | 0 | 0 |  |
| `management/commands/migration_state.py` | Сверка применённых миграций по ВСЕМ схемам (2026-08-01). | 0 | 0 |  |
| `management/commands/pilot_report.py` | KA-12 E11.5: отчёт пилота по бизнесам — только чтение, без персональных данных. | 0 | 0 |  |
| `management/commands/readiness_report.py` | AIS-W W4-0: кому закрылась бы касса при включённом гейте готовности — до включения. | 0 | 0 |  |
| `management/commands/run_locked.py` | FB-33 M3-9b: `manage.py run_locked <команда> [аргументы…]` — команда под общей | 0 | 0 |  |
| `marketing_home.py` | ST-6a: Marketing-центр — данные лендинга /dashboard/marketing/. | 0 | 0 |  |
| `media_places.py` | FB-21: формат фото по МЕСТАМ витрины (карточки товаров, акций, услуг, …). | 3 | 1 | tenants |
| `media_registry.py` | CM-4: карта мест хранения FileRef-медиа + операции реестра. | 4 | 0 |  |
| `media_views.py` | P0-2 (аудит 2026-09-03 §9.3): раздача /media/ с deny-list'ом приватных префиксов. | 4 | 1 | config |
| `middleware.py` | Гейтинг модулей кабинета (Track D / D0a): неактивный модуль → 404. | 1 | 0 |  |
| `models.py` | Базовые абстрактные модели и миксины для всех TENANT-приложений. | 88 | 25 | aggregator, booking, catalog, collections, community, crm |
| `module_presets.py` | AIS-M M-1: замороженные исторические пресеты модулей по типу бизнеса. | 1 | 0 |  |
| `module_report.py` | AIS-M M-1e: какие живые бизнесы держат исторический пресет модулей. | 1 | 1 | tenants |
| `modules.py` | Реестр модулей кабинета (Track D / D0a) — только код, без таблиц. | 32 | 5 | crm, imports, orders, promotions, tenants |
| `money.py` | KA-M2: разбор суммы, введённой человеком, независимо от языка интерфейса. | 25 | 9 | booking, catalog, events, finance, inventory, jobs |
| `money_contract.py` | KA-MC: денежный контракт сделки — единое чтение «сколько стоит / оплачено / | 27 | 7 | booking, events, finance, jobs, orders, stays |
| `nav_registry.py` | W8: ЕДИНЫЙ реестр навигации кабинета (план w8-nav-registry-plan-2026-08-05.md). | 10 | 1 | tenants |
| `next_steps.py` | AIS W4-5c: карточки «Nächster Schritt» на главной кабинета (мастер v4). | 1 | 0 |  |
| `not_found_page.py` | FB-33 M5a: страница 404 витрины — хост блоков `not_found` (решение владельца K4, | 2 | 1 | tenants |
| `not_found_views.py` | FB-33 M5a: страница 404 витрины с блоками владельца и её превью для «Seitenaufbau». | 1 | 1 | config |
| `object_faq.py` | FB-33 M2b-2b: свои вопросы FAQ у объекта (услуга, товар, номер, событие, тур). | 12 | 5 | booking, catalog, events, stays, tenants |
| `object_structure.py` | FB-29.4b: своя структура страницы у объекта (товар, услуга) поверх общей. | 15 | 6 | booking, catalog, events, promotions, stays, tenants |
| `offer_batch.py` | AIS-W W4-2: «Übernehmen» шага «Angebot prüfen» — создание пачки позиций. | 3 | 0 |  |
| `offer_examples.py` | AIS-W W4-2: образцы для кнопки «Beispiele einfügen» шага «Angebot prüfen». | 3 | 0 |  |
| `offer_lines.py` | AIS-W W4-2: разбор строк «Name — Preis» шага мастера «Angebot prüfen» (без ИИ, без БД). | 6 | 0 |  |
| `offer_pdf.py` | AIS-4: PDF Speisekarte/Preisliste → строки шага «Angebot prüfen». | 3 | 0 |  |
| `offer_photo.py` | AIS-W W4-4: «Foto der Speisekarte / Preisliste» → строки шага «Angebot prüfen». | 6 | 1 | scripts |
| `offer_sentence.py` | AIS-2: «Beschreiben Sie Ihr Geschäft in einem Satz» → строки для «Angebot prüfen». | 2 | 1 | tenants |
| `ops_lock.py` | FB-33 M3-9b: одна блокировка на операции над схемами, которые нельзя вести одновременно. | 2 | 1 | tenants |
| `option_trackers.py` | MX-2e: enforcement трекеров опций — пул и склад (план mx-followups-plan-2026-08-21.md). | 13 | 3 | booking, events, stays |
| `orders_view.py` | ST-5b → W10-1: архетип-дефолт представления продаж (для главной кабинета). | 0 | 0 |  |
| `owner_login.py` | T-8.5: вход владельца без пароля + подтверждение почты лёгкой регистрации. | 34 | 17 | aggregator, booking, catalog, collections, config, finance |
| `packages.py` | T-8.32a: пакет бизнеса по направлению — одна точка истины «что ему доступно». | 15 | 2 | jobs, tenants |
| `page_axes_migration.py` | FB-31.7: перенос прежних кодов шаблонов страниц в строки-оси схемы «Seitenaufbau» | 12 | 3 | catalog, promotions, tenants |
| `page_axes_objects.py` | FB-31.7 B1b-2b: свои шаблоны ОБЪЕКТОВ → строки своих хостов (план | 5 | 1 | tenants |
| `page_axes_residue.py` | FB-31.7 B3a: остаток перед снятием чтения старых кодов шаблонов (`materialize_page_axes | 1 | 0 |  |
| `page_images.py` | M21.11: кадрирование картинки страницы (редактор «Seiten»). | 1 | 0 |  |
| `page_parts.py` | FB-31: шаблон страницы → блоки страницы, общее ядро (стратегия §5). | 10 | 2 | promotions, tenants |
| `page_presets.py` | ST-2 «Шаблоны всех страниц»: реестр пресетов НЕ-home страниц (уровень L2). | 4 | 1 | tenants |
| `page_settings.py` | STU-19a: one service that describes, validates and writes page settings. | 20 | 7 | booking, collections, events, orders, promotions, stays |
| `page_starters.py` | M21.11 P4: заготовки для «＋ Neue Seite». | 1 | 0 |  |
| `page_templates.py` | «Seitenvorlagen» (STU-19b) — экран снесён в FB-27 R4 (решение владельца 2026-11-11: | 6 | 1 | config |
| `page_title.py` | FB-33 M2d: «Seitentitel» — свой заголовок и вступление страниц-списков и форм. | 9 | 1 | tenants |
| `page_window.py` | FB-33 M3-6 (макет M0-11): «Einstellungen der Seite» окном с вкладкой «Seite». | 3 | 0 |  |
| `pagecache.py` | Кэш публичных анонимных страниц (P2.2b) — выдача агрегатора/порталов. | 18 | 8 | aggregator, booking, catalog, events, promotions, publishing |
| `pagination.py` | Keyset (cursor) пагинация. Спецификация: docs/references/patterns/cursor-pagination.md. | 18 | 9 | aggregator, crm, events, finance, inbox, orders |
| `palette_search.py` | X8: поиск по ДАННЫМ для палитры Ctrl+K (план x8-palette-data-plan-2026-08-19). | 3 | 1 | finance |
| `payment_cards.py` | FB-30.12b: вкладка «Zahlung» карточками (макет 7, `docs/fb30-plan-2026-11-15.md` §12b). | 1 | 0 |  |
| `payment_holds.py` | SH-23d (решение владельца Р-4): удержание места без оплаты. | 10 | 6 | billing, booking, events, finance, orders, stays |
| `payment_methods.py` | SH-23 (фидбэк владельца 2026-09-03): «для каждого типа заказа всех архетипов | 23 | 7 | booking, events, finance, jobs, orders, promotions |
| `payments_page.py` | R7-3: «Zahlungen» — отдельная поверхность оплат (фидбэк владельца 2026-08-24 | 1 | 0 |  |
| `perm_grants.py` | KA-12 E6.7c-2: единственный писатель прав и ролей команды. | 2 | 0 |  |
| `perm_ui.py` | KA-12 E6.7d: экран выдачи прав — подписи и построение формы (только чтение). | 1 | 0 |  |
| `permissions.py` | KA-12 E6.7: права сотрудников — единый реестр и проверка. | 41 | 8 | aggregator, booking, events, finance, orders, promotions |
| `personal_channels.py` | Личные каналы связи с клиентом (фидбэк владельца 2026-08-25). | 1 | 1 | publishing |
| `pii.py` | Минимизация персональных данных в свободном тексте (DSGVO). | 7 | 2 | aggregator, ai |
| `pipeline.py` | U-D2: единый «конвейер» транзакции — статус → стадия доски (Kanban). | 5 | 0 |  |
| `presence.py` | LS-2 «Jetzt erreichbar»: живое присутствие бизнеса для мгновенного видео-звонка. | 2 | 1 | tenants |
| `price_conditions.py` | В2: условие цены акции — «2. Stück −50 %», «2 für 1», «ab 3 Stück −20 %». | 6 | 3 | aggregator, promotions, tenants |
| `quick_links_migration.py` | FB-33 M2c-2: перенос «Быстрых ссылок» из баннера главной в отдельный блок. | 3 | 1 | tenants |
| `ratelimit.py` | Rate-limit публичных эндпоинтов (Hardening H8). | 60 | 17 | account, aggregator, booking, community, events, finance |
| `readiness.py` | AIS-W W4-0: единый реестр готовности — «что обязательно и что желательно заполнить». | 18 | 7 | booking, events, loyalty, orders, promotions, stays |
| `redirects_views.py` | M21.1: экран «Weiterleitungen» (Website → старые адреса после переезда). | 1 | 1 | config |
| `refunds.py` | KA-H4 (2026-10-23): возврат оплаты при отмене — одна точка для всех поверхностей. | 19 | 6 | booking, events, finance, jobs, orders, stays |
| `richtext.py` | SR-3: ограниченный rich-text для описаний (визуальный редактор кабинета). | 20 | 7 | aggregator, booking, catalog, events, imports, publishing |
| `role_templates.py` | KA-12 E6.7f: шаблоны ролей (Rollenvorlagen) — именованные наборы прав по архетипу. | 3 | 0 |  |
| `roles.py` | Роли пользователя в тенанте (M6 / master-plan §7, шов multi-user). | 18 | 9 | catalog, community, crm, documents, events, finance |
| `sales_export.py` | KA-12 E2.2: CSV продаж — заказы, брони номеров, записи, билеты, заявки. | 1 | 0 |  |
| `sales_page.py` | Единая страница продаж «Verkäufe» — вкладки по kind + виды (2026-08-03). | 12 | 5 | booking, jobs, orders, stays, tenants |
| `schema_migrations.py` | Какие миграции не применены в схеме (T-10, 2026-10-20). | 2 | 1 | tenants |
| `sell_questions.py` | AIS W4-5a: «Verkauf öffnen» — короткие вопросы по направлению вместо форм. | 2 | 0 |  |
| `sellable.py` | Контракт `SellableEntity` (U-A / UA1-3): единое представление любой продаваемой | 9 | 6 | aggregator, booking, events, inbox, promotions, stays |
| `sellable_manage.py` | FB-8: единый кабинетный список продаваемых сущностей (товар/услуга/номер/событие/ | 4 | 2 | catalog, inbox |
| `seo.py` | schema.org JSON-LD для локального SEO витрины (Track B5). | 9 | 3 | aggregator, jobs, promotions |
| `seo_meta.py` | SEO-1: движок мета-заготовок (title/description) с плейсхолдерами. | 4 | 1 | tenants |
| `session_schema.py` | HIGH-10: привязка Django-сессии к схеме тенанта, в которой создан логин. | 3 | 1 | scripts |
| `settings_hints.py` | SR-5 (R5c A+B, решение владельца «делаем оба»): живые подписи экранов | 2 | 0 |  |
| `settings_home.py` | SR-5 (вариант Б, реанимация плана r5c-einstellungen-overview §1-3): страница- | 1 | 1 | config |
| `setup_assistant.py` | STU-19c: "Was möchten Sie anlegen?" — a plan for creating things, never an action. | 17 | 4 | booking, events, promotions, stays |
| `setup_google.py` | AIS W4-3: «Bei Google suchen» в шаге «Firma» мастера v4. | 3 | 1 | config |
| `setup_steps.py` | AB6.1: handler'ы шагов Onboarding-мастера — по одному на слайд. | 1 | 0 |  |
| `share_links.py` | Кнопка «поделиться» с выбором канала (фидбэк владельца 2026-08-25). | 4 | 2 | events, promotions |
| `site_schema.py` | FB-25: «Website › Seitenaufbau» — схема блоков каждого типа страницы витрины. | 23 | 4 | catalog, jobs, scripts, tenants |
| `site_schema_views.py` | FB-25 / FB-27: экран «Website › Seitenaufbau» — схема страницы рядами и её правка. | 1 | 1 | config |
| `social_proof.py` | «Verkauft N diese Woche» — честный social-proof (LS-4 v2, одобрен 2026-07-19). | 1 | 1 | tenants |
| `ssrf.py` | Защита от SSRF для URL, задаваемых владельцем (iCal-фиды, будущий отправитель | 5 | 2 | imports, stays |
| `status_effects.py` | FB-3 Вариант B Phase 2: эффекты статусов по РОЛИ (для КАСТОМ-статусов). | 1 | 0 |  |
| `status_labels.py` | FB-4a/FB-4b: свои имена статусов (кабинет-отображение) — generic по kind. | 7 | 1 | crm |
| `status_registry.py` | FB-3 Вариант B, Phase 0: реестр дескрипторов статусов (роль + флаги). | 60 | 13 | account, booking, catalog, community, crm, documents |
| `storefront_profile.py` | T-8.1: профиль витрины «Nur Aktionen» (план docs/t8-1-aktion-demos-plan-2026-10-09.md). | 17 | 5 | aggregator, config, imports, promotions, tenants |
| `storefront_state.py` | Почему витрина бизнеса сейчас закрыта для гостя («bald online», AIS-A A-0). | 13 | 5 | aggregator, booking, orders, promotions, stays |
| `studio_pages.py` | STU-1: единый реестр «тип страницы витрины → её настройки» для Studio. | 8 | 0 |  |
| `tasks.py` | C1: beat-задача утреннего дайджеста владельцу. | 7 | 1 | scripts |
| `team.py` | W9-10 (Р-7, аудит 2026-08-05): «Team & Zugriff» — членства/роли + инвайт. | 1 | 1 | config |
| `templatetags/attribution.py` | В5 V5-5: `{% portal_attribution_fields %}` — канал и карточку каталога города несут | 0 | 0 |  |
| `templatetags/block_window_ui.py` | FB-33 M3-5a: окно блока в шаблонах — форма, которую применяют кнопки вкладок, и контракт | 0 | 0 |  |
| `templatetags/cabinet.py` | Шаблонные теги кабинета (AB1 язык задач + анти-Битрикс v2 хаб-табы). | 6 | 2 | promotions, stays |
| `templatetags/deal_pay.py` | KA-12 B2-5 (E1.11): «Restbetrag online bezahlen» на подтверждении брони/записи/билета. | 0 | 0 |  |
| `templatetags/form_a11y.py` | KA-12 E9.4c: доступность полей форм. | 0 | 0 |  |
| `templatetags/richtext.py` | SR-3: шаблонные фильтры ограниченного rich-text (описания). | 0 | 0 |  |
| `templatetags/sellable_ui.py` | UB1-2: единая карточка продаваемой сущности (услуга/номер) — листинги + home-секции. | 0 | 0 |  |
| `templatetags/seo.py` | Шаблонные теги SEO: LocalBusiness JSON-LD в <head> витрины (Track B5). | 2 | 2 | promotions, tenants |
| `templatetags/sf_map.py` | В3: `{% sf_map_loader %}` — общий загрузчик подложки карт (Leaflet + MapLibre GL + | 0 | 0 |  |
| `templatetags/workflow.py` | U-D2: шаблонные теги конвейера — действия FSM для строк/карточек. | 0 | 0 |  |
| `tenant_iter.py` | SM11: фоновый обход всех бизнесов — один бизнес не обрывает остальных. | 9 | 8 | aggregator, booking, documents, events, orders, promotions |
| `text_check.py` | T-8.10e (D2a-1): «Text-Check» — детерминированные правила текста акции без ИИ. | 10 | 4 | aggregator, ai, inbox, promotions |
| `text_draft.py` | AIS-7: «✨ Text vorschlagen» — текст описания/«Über uns»/баннера из сохранённых фактов. | 4 | 0 |  |
| `text_facts.py` | AIS-7: доверенные факты для «✨ Text vorschlagen» — только из СОХРАНЁННЫХ данных. | 2 | 0 |  |
| `tg_login.py` | T-8.30: вход в «Mein Laden» из Telegram Mini App — сессия ТОЛЬКО в лёгкие экраны. | 13 | 2 | config, platform_bot |
| `transactions.py` | U-D1: единый протокол `Transaction` над 6 доменными транзакциями. | 37 | 9 | account, booking, events, finance, inbox, jobs |
| `transition_rules.py` | FB-3: правила переходов статусов (кабинет-конфигуратор поверх FSM). | 8 | 1 | orders |
| `translate_views.py` | AIS-5: эндпоинты «🌐 Übersetzen» (план docs/ais-5-translate-plan-2026-11-06.md). | 2 | 1 | config |
| `vat.py` | DC-8: честная разбивка НДС у брони номера, записи услуги и билета. | 12 | 6 | booking, catalog, events, finance, jobs, stays |
| `view_perms.py` | KA-12 E6.7b: какое право нужно каждому экрану кабинета. | 20 | 5 | booking, crm, events, finance, stays |
| `views.py` | Общие tenant-facing вьюхи (живут в схеме арендатора). | 7 | 1 | config |
| `whatsapp.py` | LS-1: единый строитель wa.me-ссылок (WhatsApp — 94 % DACH). | 5 | 3 | booking, inbox, tenants |
| `window_banner.py` | FB-33 M3-6 (макет M0-7): окно блока «Banner» — подписи плиток и «Wo zeigen». | 2 | 0 |  |
| `window_link_views.py` | FB-33 M4: ⚙ Студии → окно блока «Seitenaufbau» (GET, только 302, ничего не пишет). | 1 | 1 | config |
| `window_links.py` | FB-33 M4: адреса окна блока «Seitenaufbau» — для ⚙ Студии и ссылок в кабинете. | 4 | 0 |  |
| `window_parts.py` | FB-33 M3-5b: части окна блока «Seitenaufbau» — вопросы FAQ («Texte») и плашки | 1 | 0 |  |
| `zusatz.py` | MX-2c: сводный учёт ДОП-ПРОДАЖ — проданные опции по всем направлениям. | 1 | 0 |  |
