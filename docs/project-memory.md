# Память проекта — решения, единые модули, открытое, ops

Собрано 2026-11-13 при сокращении `CLAUDE.md`: всё, что жило только в его истории (§3) и
нужно для будущей работы. Источник — дословный архив `docs/claude-md-archive-2026-11-11.md`,
разобранный восемью агентами ECC (`doc-updater`), пути модулей сверены с кодом.

**Как пользоваться.** Перед инкрементом — прочитать раздел своей области в §3 (какой модуль
уже отвечает за задачу) и поиск по §5 (что владелец уже решил). Правила и грабли — в
`docs/pitfalls.md`, хронология — в `docs/build-log.md`, очередь — в `docs/task-catalog.md`.
Новое решение владельца, новый «единственный писатель», новый ops-шаг — строкой сюда в том же
коммите. Закрытое из §1 и §2 убирать.

Содержание: 1. Открыто сейчас · 2. Ops владельцу · 3. Единые точки истины · 4. Сырые выписки
«открытое» и «ops» по периодам · 5. Решения владельца по периодам.

## 1. Открыто сейчас (сводка на 2026-11-13)

Идёт в работе:
- **FB-27** «Website: Seitenaufbau» — сделаны R0…R6 (настройки типа страницы в панели
  «★ Hauptliste» / «Einstellungen der Seite»; «Seitenvorlagen» снесены, адреса → 302; ручной
  состав «Einzeln»; блоки «Textseite» и «Kontakt», готовые строки; своя схема категории
  ЗАМЕНЯЕТ блоки каталога на её странице; R8a–c: «Speichern» Студии пишет только
  содержимое и вид — `site_schema.merge_structure`, контролы структуры в Студии скрыты,
  пункта «Studio» в меню нет, вход — кнопка «Auf der Seite bearbeiten»); R8d: сохранённые
  шаблоны блоков — в «+ Block», устаревшая вкладка Студии сохраняет текст; R9: обход
  `scripts/aufbau_owner_stand.py`). Программа «Seitenaufbau» закрыта; остаток — в
  `roadmap-next-sprints.md` (наборы блоков страницы акций и шаблоны страниц ещё в Студии).
  Экран «Seiten» сделан (список по S1/S3, вкладки Text · Blöcke · Suchmaschinen; SEO
  страницы — `site_config["seo"]["pages"][<хост>]`, писатель `content_pages.save_page_seo`).
  «Seitenaufbau» доведён до макета (V1–V4: шапка одной полосой, сводки и миниатюры строк,
  кнопки «Welche»/«Wie»/«Breite», одна «+ Block», лист на телефоне; правка в панели без
  «Übernehmen» — `static/js/aufbau.js` поверх формы). FB-28: пункты редактора меню
  сворачиваются. Дальше экран «Design». Планы `fb27-*-2026-11-1*.md`.
- **M21.11** P6 (таблица, видео/карта с согласием, PDF, оглавление, цвет из палитры, чеклист,
  счётчик, поиск/замена, Markdown, ИИ, оформление фото) → P7 история версий (⚠ миграция).
- **M21** прогон переезда haanerteeladen на сервере — владелец, runbook §7
  `m21-cscart-migration-plan-2026-10-31.md`.

Ждёт решения владельца:
- Pro-тариф D1 и тарифы T-8.32/33 (19/29 €, Profi-модули) — скрыты до объявления.
- UC2-3 вариант B (свои ДАННЫЕ секций на каждой странице).
- SHP: перевод существующих бизнесов на Paketdienst — после подтверждения владельцем по
  `shipping_report`.
- Перевод маркетинговой копии Branchen-лендингов (224 msgid в allowlist `i18n_gap`).
- Включение ИИ-поиска (`AI_SEARCH_ENABLED`) — по `search_log_report` + абзац в Datenschutz.
- F-6 оценка пилота MCP (после 4 недель данных).
- E6.4: поле аллергий с согласием, шифрование заметок мастера; свой статус неявки в счётчике.
- DL-21.3 идеи «Too Good To Go»; DS-трек видов вывода услуг/номеров/событий.
- D3.5 вход партнёра в кабинеты клиентов; T-8.12 порталы сторонних операторов (после пилота).
- Тёмная тема кабинета; E2.9b входящие в две панели; A-3b вид «Kalender» у заявок.

Ждёт юриста / Steuerberater:
- `ADVANCE_INVOICES_ENABLED` (формулировки PDF Anzahlungsrechnung), `QUOTE_WITHDRAWAL_ENABLED`
  (Widerruf и письмо-договор), T-6b § 25 UStG / Sicherungsschein, § 634a BGB (акты приёмки),
  Widerruf click&collect (SHP), `old_price` и лицензия открытого фида (T-8.8), абзацы
  Datenschutz (см. §2).

Внешние зависимости (`docs/external-integrations-backlog.md`): Stripe live, OTA-API G11c–e,
нативные PayPal/Klarna, SMS, Shopify/Woo, реклама M23c, PWA/push/Wallet, WhatsApp Business API,
LLM-режим Finder, SSE для чата.

Технический остаток: SEC вне волн (non-root в образе, фиксированные теги образов, wildcard-
сертификат DNS-01, SM11/SM15); дробление `RevenueEntry` по ставкам НДС; ERP-7 v2 (рецепты,
средневзвешенный EK); Склад-2 v2 (продажа с локации); DCC хвосты (фото `sg-*`,
`--refresh-events`); T-8.7 хвосты (bounce, ротация `follow_token`); правовые страницы
ПЛАТФОРМЫ с плейсхолдерами реквизитов; AIS-0 замер `onboarding_report`; AIS-1/8/9/10.

## 2. Ops владельцу (сводка; выполнено ли — не подтверждено, если не сказано иначе)

`.env.prod`:
- `STRIPE_WEBHOOK_SECRET` (без него вебхук отвечает 503), `STRIPE_CONNECT_WEBHOOK_SECRET`;
  в Stripe Dashboard — события `checkout.session.async_payment_succeeded` / `…_failed`.
- `SECRETS_ENCRYPTION_KEY` задан (деплой проходит); после него `rotate_secrets` и
  `cleanup_import_files` (dry-run → `--apply`); смена ключа — только через
  `SECRETS_ENCRYPTION_KEY_PREVIOUS`.
- `GOOGLE_PLACES_API_KEY` + квота (Google-рейтинг GK-11, «Bei Google suchen» W4-3).
- ИИ: `AI_ENABLED` + ключи маршрутов ЕС (`docs/ai-providers-setup-2026-10-16.md`),
  `AI_REQUIRE_EU` в проде не снимать; задачи включаются в админке «KI-Einstellungen»
  (`offer_photo_lines`, `offer_pdf_lines`, `assistant_answer`, `assistant_actions`,
  `i18n_translate`, `text_from_facts`, `search_query_expand`).
- Флаги, выключенные по умолчанию: `READINESS_SELL_GATE` (после `readiness_report
  --stamp-exempt --apply`), `AI_SEARCH_ENABLED`, `MCP_ENABLED` / `MCP_ACTIONS_ENABLED`,
  `ADVANCE_INVOICES_ENABLED`, `QUOTE_WITHDRAWAL_ENABLED`. Включены: `SETUP_WIZARD_V4`,
  `SIGNUP_EMAIL_CONFIRMATION`, `PANGV_PERISHABLE_EXEMPTION`, `TELEGRAM_WEBHOOK_LEGACY_HEADER`
  (выключить после `telegram_resync_webhooks --apply`).
- По желанию: `ADMIN_ALLOWED_NETWORKS`, `REDIS_PASSWORD`, `CSP_REPORT_URI`,
  `QUICK_START_HOURLY_CAP`, `LITE_FREE_ACTIVE_PROMOS`, `PLATFORM_CONTACT_EMAIL`,
  `MAP_STYLE_URL`, `PORTAL_DISTRICT_MIN_BUSINESSES`.

Админка и Telegram:
- «Telegram platform bot»: токен → включить → «Webhook setzen» (ставит команды и кнопку Mini
  App); «Portal bots»: токен → «Connect». Повторять после обновлений ботов.
- @BotFather: privacy mode **ВКЛ** у бота платформы и ботов портала; **ВЫКЛ** у своего бота
  бизнеса, если он работает мостом ленты поездки (MT-3).
- Пометить внутренний тенант «rest» как `is_internal`; `show_demo` у портала Solingen снять на
  запуске.

После деплоя: `migration_state` (печатает сам деплой) → `sync_aggregator` →
`rebuild_search_index` → `seed_demo_tenants --group all --changed --jobs 3` (один раз до этого
`--group all --stamp`). Отчёты с решением: `modules_report` → `--apply`, `shipping_report`,
`onboarding_report --compare <дата>`, `package_report`, `pilot_report`, `search_log_report`.

Разовое: cron бэкапа из шапки `scripts/backup.sh` + проверить восстановление;
`scripts/install-git-hooks.sh` на рабочей копии; при переезде Postgres — роль с правом
`CREATE EXTENSION` (`pg_trgm`).

Юридическая вычитка: Datenschutz бизнеса (§8/§8a боты, Mini App, ИИ, импорт с сайта, срок
3 года заметок мастера, подписки и темы рассылки), Datenschutz портала (статистика поиска,
«Folgen», Telegram-подписки, ИИ-поиск), уведомление «ИИ работает в США», правовые страницы
платформы (реквизиты вместо плейсхолдеров), AGB — внешний генератор.

## 3. Единые точки истины в коде

Модули, названные в истории «единственный источник / писатель», «одна точка истины», «реестр».
Существование каждого пути проверено 2026-11-13. Новый код обязан звать их, а не заводить
второй список или второй писатель.

### apps/core

- `legacy_role_gates.py` — (нет по пути `apps/core/`; pitfalls называет его замороженным эталоном — расположение не проверял).
- `apps/core/archetypes.py` — `primary_item`/`purchase_mode`/`purchase_label` архетипа.
- apps/core/assistant_actions.py — закрытый реестр действий ИИ-помощника «объект × действие» (A-4).
- `apps/core/balance_pay.py` — онлайн-доплата остатка после Anzahlung.
- `apps/core/business_card.py` — карточка «So finden Sie uns» (T-8.1).
- `apps/core/card_forms.py` — реестр форм карточки (товар/акция) и резолвер `card_form` «объект → категория → сайт → прежняя форма»; тег `{% card_form %}` в `apps/tenants/templatetags/siteui.py` (DL-19, STU-12j).
- `apps/core/card_forms.py` — общий резолвер формы карточки `card_form` (объект → категория → сайт) (LAY-4).
- `apps/core/city_categories.py` — справочник 15 разделов каталога города + признаки.
- `apps/core/closures.py` — Betriebsferien (витрина, слоты, «открыто сейчас», портал).
- apps/core/colors.py — чернила по контрасту, общий слой витрины и портала (PH-12).
- `apps/core/compositions.py` — единый реестр шаблонов (композиций) страниц: `SURFACES`/`LISTING_SURFACES`, гейты `requires`, `EXCLUDED_REASONS`, `PENDING_SURFACES` (сейчас пуст); прежние списки стилей — производные (LAY-2, STU-18).
- `apps/core/compositions.py` — общий реестр композиций страниц (источник для двух предыдущих).
- `apps/core/contact_access.py` — маскирование и запись контактов по праву `kunden.kontakte`.
- apps/core/day_home.py — сводка дня на главной для заказов/записей/заявок/билетов (D8).
- apps/core/deal_card.py + templates/core/deal_card_base.html, _deal_lines.html, _deal_totals.html — единая карточка сделки всех видов.
- apps/core/deal_discount.py — скидка сделки с пересчётом итога по доменам.
- apps/core/deal_links.py — связь сделок «якорь + спутники» (DealLink: attach/for_cards).
- apps/core/demo_switch.py — «Design testen» на демо-витрине.
- `apps/core/detail_sections.py` — реестр секций детали (упомянут как причина нижней оценки деривации).
- `apps/core/detail_sections.py` — реестр секций детальных страниц (порядок, подписи, скрытие).
- apps/core/directions.py — единственный источник «как продаёт бизнес» (направления); писатель `set_state` (M-0/M-1).
- `apps/core/districts.py` — реестр районов/городов (slug, алиасы, PLZ, `toponym_tokens`).
- `apps/core/districts.py` — реестр районов и соседей (`NEIGHBORS`).
- apps/core/documents.py — слой PDF-документов (язык/деньги); apps/catalog/pdf.py — `build_menu_pdf`.
- `apps/core/documents.py` — общий слой документов/PDF: язык, шрифт, деньги/даты по локали (I18N-7b)
- `apps/core/facets.py` — протокол `FacetProvider` + `provider_for(kind)`: фильтры, поиск, сортировка листингов.
- `apps/core/facets.py` — провайдеры фасетов/сортировок листингов (источник допустимых ключей сортировки).
- `apps/core/finder.py` — движок Finder витрины; `apps/aggregator/finder.py` — платформенный Finder (FD-1/FD-4)
- `apps/core/folio.py` — книга платежей `DealPayment`; деньги контракта читаются из неё.
- apps/core/fsm.py — `StateMachine.apply` блокирует строку, переход от статуса в БД (SEC волна 1).
- `apps/core/fsm.py` — StateMachine (`apply`).
- apps/core/grid_filler.py, scripts/gen_fill_rows_css.py, scripts/demo_rows_audit.py — полные ряды плиток.
- apps/core/help_articles.py — реестр статей справки (A-1).
- `apps/core/hero_tiles.py` — реестр плиток первого экрана по архетипам (2026-07-30)
- apps/core/hero_tiles.py — `HERO_TILE_SETS`, плитки первого экрана с гейтами.
- `apps/core/i18n_cabinet.py` + `CABINET_LANGUAGES` (`config/settings/base.py`) — язык кабинета, отдельный от витрины.
- `apps/core/i18n_input.py` + `templates/tenant/_i18n_switch.html` — per-language ввод в формах.
- apps/core/i18n_input.py — подписи per-locale полей (`format_lazy`).
- apps/core/i18n_json.py / apps/core/i18n_seq.py (+ `I18nMixin.get_overlay`) — три слоя оверлеев переводов (вложенный JSON / плоские списки / скаляры).
- `apps/core/i18n_seq.py` — поэлементный оверлей списков (`apply_seq_overlay`) (2026-08-01)
- `apps/core/inline_edit.py` — единый диспетчер инлайн-правки на канве.
- apps/core/labels.py — общий реестр меток «Neu/Beliebt/…» (FB-20).
- `apps/core/legal.py` — резолвер правовых текстов (LegalDoc[локаль] → дефолт → плоское поле → генерённый).
- apps/core/legal.py — `save_legal_doc`, писатель правовых текстов (M21.10).
- `apps/core/list_blocks.py` — блок «Liste»: реестр источников (10), выборки `resolve_for`/`resolve_section`, `apply_type_scope`, `library_presets` (LB-1…LB-4).
- apps/core/list_filters.py (+ `core/_list_filter_bar.html`) — общая строка фильтров списков кабинета (FLT-4).
- `apps/core/management/commands/migration_state.py` — сверка миграций по всем схемам (T-7)
- `apps/core/marketing_home.py` — состояние маркетинга (ST-6/W11-2)
- `apps/core/media_views.py` — единственный гейт отдачи медиа (P0-2).
- `apps/core/middleware.py` (`PackageScopeMiddleware`) — белый список адресов кабинета лёгкого пакета.
- apps/core/middleware.py (`StorefrontLocaleClampMiddleware`) — кламп языка витрины к локалям тенанта.
- apps/core/modules.py — `set_modules` единственный писатель модулей; `inactive_reason` — причина неактивности (M-1).
- `apps/core/modules.py` — реестр модулей (REGISTRY, recommended_for). (`apps/tenants/modules.py` — нет в коде.)
- apps/core/money.py — `parse_amount`, один разбор сумм во всех формах кабинета (D6.0b).
- `apps/core/money.py` — разбор сумм из форм (`MoneyField`).
- `apps/core/money_contract.py` — одно чтение денег сделки (итог, оплачено, возвращено, ждём, проведено), карты состояний оплаты, `settle_payment`.
- apps/core/nav_registry.py — единый реестр навигации кабинета (сайдбар, подпункты `sidebar_children`, палитра, подсветка, EXPECTED_UNLISTED-инвариант в apps/core/tests/test_x0_x7_locks.py).
- `apps/core/nav_registry.py` — единый реестр навигации; `HUB_TABS` в `apps/core/templatetags/cabinet.py` — производная. (`apps/tenants/cabinet.py` — нет в коде.)
- apps/core/offer_photo.py, apps/core/offer_sentence.py — пост-проверка строк из фото / из фразы (W4-4, AIS-2).
- apps/core/option_trackers.py — пулы/склад опций (Extra), `sync_options`, возвраты.
- `apps/core/orders_view.py` — выбор вида продаж (ST-5b; сегмент-контрол снят W10-1, проверить актуальность при чистке)
- apps/core/owner_login.py — `safe_next` (SEC батч 1); apps/core/ratelimit.py — `client_net` (/64), `refund`.
- `apps/core/page_presets.py` — реестр `PAGE_PRESETS`, `apply_page_preset` (ST-2)
- apps/core/page_settings.py — список вариантов и писатель настроек страниц (кабинет «Seitenvorlage», помощник A-4c).
- `apps/core/page_settings.py` — схема, проверка и запись одного ключа настроек страницы; `raw_config` для превью.
- `apps/core/pagination.py` — `paginate` (курсор) и `paginate_list` (offset, `?seite=`) (STU-18f).
- `apps/core/payment_methods.py` — реестр способов оплаты (on_site|stripe|vorkasse|invoice) + тип покупателя, правила для всех шести видов сделок (SH-23).
- apps/core/payments_page.py — слой чтения страницы «Zahlungen».
- `apps/core/perm_grants.py` — единственный писатель прав участника.
- `apps/core/perm_ui.py` — подписи и группы прав для экрана «Team & Zugriff».
- `apps/core/permissions.py` — реестр прав (`has_perm`, пресеты ролей).
- `apps/core/pipeline.py` — статус → стадия доски, `resolve_columns`.
- `apps/core/presence.py` — резолвер «Jetzt erreichbar»; `apps/core/whatsapp.py::wa_link` — единственный сборщик wa.me (LS-1/2)
- `apps/core/price_conditions.py` — условие цены акции («2. Stück −50 %»).
- apps/core/readiness.py — единый реестр «готово к продаже», `require_sell` — гейт касс (W4-0, W4-5d).
- `apps/core/refunds.py` — возврат оплаты при отмене с любой поверхности.
- apps/core/richtext.py — `editor_rules` (белый список редактора), `to_plain` (фид/PDF/JSON-LD) (M21.8/M21.10).
- apps/core/richtext.py — санитайз rich-text (nh3, allowlist).
- apps/core/sales_page.py — тело страницы Verkäufe и главной (`body_context`, `view_for_filters`); шаблон templates/core/_sales_body.html.
- `apps/core/sales_page.py` — страница Verkäufe, `legacy_redirect` (W10-6)
- `apps/core/sellable.py` — контракт `SellableEntity` (адаптеры товар/услуга/номер/событие/комбо; purchase_mode, цена, JSON-LD-поля).
- `apps/core/sellable_manage.py` — единый список продаваемых сущностей кабинета.
- `apps/core/sellable_manage.py` — пикер/список продаваемых сущностей кабинета
- `apps/core/seo.py::localbusiness_data` — публичные поля продавца для JSON-LD.
- `apps/core/seo.py` — JSON-LD сущностей (`entity_ld`).
- apps/core/seo_meta.py — DEFAULTS мета-заготовок (lazy-переводимые).
- `apps/core/seo_meta.py` — движок мета-заготовок title/description.
- `apps/core/setup_steps.py` — обработчики шагов мастера (HANDLERS).
- apps/core/share_links.py, apps/core/personal_channels.py — меню «поделиться», личные каналы.
- `apps/core/social_proof.py` — «Verkauft N» с порогом (LS-4 v2)
- `apps/core/ssrf.py` (`safe_fetch`) — исходящие запросы по адресам пользователя.
- `apps/core/status_effects.py` — эффекты статусов (ёмкость, деньги, склад по роли).
- `apps/core/status_labels.py` — свои имена статусов.
- apps/core/status_registry.py (+ status_effects.py) — статусы/роли всех 6 kind: `active_statuses_for`, `cancelled_statuses_for`, BUILTIN, подписи.
- `apps/core/status_registry.py` — роли статусов, `counted_statuses_for` (формула G9/кастом-статусы); эффекты — `apps/core/status_effects.py`
- `apps/core/storefront_profile.py` — профиль витрины «Nur Aktionen» (T-8.1).
- apps/core/storefront_state.py — состояние витрины (опубликована/скрыта) для диагнозов и гейтов (A-0).
- `apps/core/studio_pages.py` — реестр «тип страницы × настройки Студии», `PAGE_QUERY_KEYS` — единственный список параметров, задающих страницу (STU-1/7).
- `apps/core/studio_pages.py` — реестр типов страниц Студии (`PAGE_TYPES`).
- `apps/core/tasks.py::expire_payment_holds` — снятие неоплаченных удержаний через FSM (beat `expire-payment-holds` в `config/settings/base.py`).
- `apps/core/text_check.py` — правила Text-Check (UWG/PAngV/LMIV).
- `apps/core/tg_login.py` (`TG_LITE_VIEWS`) — белый список экранов Mini App и одноразовый вход.
- `apps/core/transactions.py` (`apply_action`) — смена статуса сделки с любой поверхности; здесь же проверка «возврат отменой — только владелец или бухгалтер».
- `apps/core/transactions.py` — `apply_action` (единая смена статуса сделки с любой поверхности), `kinds_with_sales` (W10-5, V1)
- `apps/core/transition_rules.py` — скрытие переходов владельцем.
- apps/core/vat.py (`parse_rate`, `parse_rate_optional`) — разбор ставки НДС из формы (локаль «19,00»).
- `apps/core/view_perms.py` — право каждого экрана кабинета; источник и для меню (`nav_registry.hidden_for`).
- `apps/core/views.py::_safe_preview_page` / `_hits_deny_zone` — единственный санитайзер адреса канвы.

### apps/tenants

- `apps/tenants/archetype_pages.py` — контент Branchen-страниц.
- `apps/tenants/demo_city/` — спека → `build_kit` демо-бизнесов города + валидатор (DCC).
- apps/tenants/demo_i18n.py — обход перевода демо, `PROPER_NAMES`; scripts/demo_i18n_gap.py — замер покрытия; scripts/i18n_quickcheck.py — локальный гейт i18n.
- apps/tenants/demo_images.py (`_PHOTO_ALIASES`) — резолвер демо-фото.
- `apps/tenants/feature_demos.py` — реестр «функция → страница живого демо»
- apps/tenants/feature_demos.py — «функция → живое демо».
- apps/tenants/google_places.py — Google-рейтинг (Places API).
- `apps/tenants/menu.py::target_sets()` / `target_options()` — реестр целей пунктов меню (один источник для Студии и «Menü-Generator») (STU-16d). `apps/core/menu.py` — (нет в коде).
- apps/tenants/menu.py — `resolve_menu`, `_PAGE_URL_NAMES`, `PAGE_TARGET_LABELS` (цели меню). (apps/core/menu.py — нет в коде)
- apps/tenants/onboarding.py — `set_had` единственный писатель `onboarding["had"]` (AIS-3). (apps/core/onboarding.py — нет в коде, модуль живёт в tenants.)
- `apps/tenants/onboarding.py::SETUP_STEPS` — единый реестр шагов мастера (рельса, чек-лист, бейджи) (AB6.1); обработчики — `apps/core/setup_steps.py`
- `apps/tenants/openinghours.py` — `open_status` (в записи назван без пути)
- `apps/tenants/schema_template.py` — создание схемы копией `_template`.
- `apps/tenants/signup.py` — регистрация с подтверждением почты (флаг `SIGNUP_EMAIL_CONFIRMATION`)
- `apps/tenants/siteconfig.py` — `OPTIONAL_PAGE_LAYOUTS` (сетки страниц без своего ключа), `TRANSLATABLE_KEYS`/`NON_TRANSLATABLE_FIELDS`/`split_translation` (что переводимо в site_config; общий реестр с обходом демо-переводов) (LAY-3a-2, LAY-6). В записи назван `siteconfig` без пути; `apps/core/siteconfig.py` — (нет в коде).
- `apps/tenants/siteconfig.py` (в записи назван `siteconfig`; `apps/core/siteconfig.py` — нет в коде) — normalize конфига сайта; `PAGE_BLOCK_HOSTS`, `detail_layout(cfg, kind)`, `listing_sort_keys`, `cblock_type` (легаси `promo_list` → `list`), `realign_block_overlays`, `LIST_STYLES`.
- apps/tenants/sitetemplates.py — `LOOK_FAMILIES`, `BUNDLES`, `COMPOSITIONS`, `templates_for`, `apply_preview_bundle` (в тексте записей путь указан без каталога; `apps/core/sitetemplates.py` — нет в коде).
- `apps/tenants/sitetemplates.py` — `LOOK_FAMILIES`, `ARCHETYPE_LOOK_ACCENTS`, `apply_look`/`looks_for`, общая `_apply`-база (ST-1)
- `apps/tenants/templatetags/siteui.py::sf_grid_attrs` — единственное место правила «раскладка владельца сильнее литерала» (LAY-7).
- apps/tenants/tests/test_demo_menus.py — замок «меню кита как данные»; apps/core/tests/test_nav_reachability.py — достижимость экранов.

### apps/catalog

- apps/catalog/bulk_price.py — одна формула массовой правки цен (экран «Sortiment» и помощник, A-4d).
- `apps/catalog/category_styles.py` — шаблоны страницы категории/корня каталога, `page_style(category, site_default)` (DL-20/21; сегодня производное от `apps/core/compositions.py`).
- apps/catalog/category_styles.py — шаблоны страницы категории (позже производное от apps/core/compositions.py).
- `apps/catalog/city.py` — резолвер категории города для категории товара (своё → родители → подсказка).
- apps/catalog/combos.py (`pool_products`) — пул свободной сборки (категория + прямые дети).
- apps/catalog/facets.py — `branch_ids`: товары всех уровней вложенности категории (M21.4).
- `apps/catalog/food.py` — реестры аллергенов/диет/Zusatzstoffe.
- `apps/catalog/google.py` — отбор товаров и id позиций для обоих фидов Merchant.
- `apps/catalog/merge.py` — «Als Varianten zusammenführen»
- apps/catalog/models.py `Product.get_absolute_url()` — единственная точка URL товара; apps/catalog/slugs.py — `unique_slug` (в записи назван `slugs.unique_slug`; apps/core/slugs.py — нет в коде).
- `apps/catalog/option_styles.py::COLOR_HEX` — общий словарь цветов (свотчи, фасет `?farbe=`, генератор фото одежды).
- `apps/catalog/option_styles.py` — реестр видов показа вариантов/модификаторов + словарь цветов (O-волна)
- apps/catalog/picker.py — пикер позиций (заказ, смета, наборы `k:<pk>`).
- `apps/catalog/prefetch.py` — предзагрузка карточек товаров.
- apps/catalog/wegweiser.py — композиция корня `/sortiment/` (2026-11-08).
- apps/catalog/writers.py, apps/booking/writers.py — писатели создания товара/категории/услуги, общие для экранов, мастера «Prüfen» и помощника (A-4a).

### apps/promotions

- `apps/promotions/ai_draft.py`, `apps/promotions/today.py` — черновик из фото; «Was heute starten?».
- `apps/promotions/city_fields.py` — общие поля «категория города + признаки» трёх форм акции (T-8.13a).
- `apps/promotions/facets.py` (`PromoFacets`) — одна точка фильтров акций, включая цель `ziel`, для блока, секции и `/aktionen/` (LB-4d-1).
- `apps/promotions/flyer.py` — PDF-флаер акции; `apps/core/documents.py` — общий слой PDF-документов.
- `apps/promotions/group_styles.py` — шаблоны страницы группы акций и обзора (`PROMO_PAGE_STYLES` = `compositions.styles_for("promos")`) (DL-20/21).
- `apps/promotions/group_styles.py` — `PROMOTION_DETAIL_STYLES` и стили групп (производные от compositions) (STU-15a).
- `apps/promotions/limits.py` — лимит активных акций бесплатной ступени (Р-5).
- `apps/promotions/message_parse.py` — разбор акции из сообщения правилами.
- `apps/promotions/models.py` (`Promotion.on_sale_q()`) — «акция в продаже» для витрины и слоя цены.
- apps/promotions/price_layer.py (`promo_line_price`) — цена акции «показано = списано»; apps/promotions/facets.py (`PromoFacets`) — фасеты /aktionen/; apps/catalog/price_history.py (`lowest_price_30d_bulk`) — §11 PAngV.
- `apps/promotions/price_layer.py` — ценовой слой акции, `deal_counts` (PL)
- `apps/promotions/promo_types.py` — реестр типов акций: свои рубрики + встроенные `sys:*`, один параметр `?gruppe=` (PT-1).
- `apps/promotions/quick.py` (`publish_built`) — публикация акции одной формой (веб-ассистент, Telegram, быстрый старт).
- `apps/promotions/quick.py` — ассистент «Schnell-Aktion», та же форма для `/aktion-starten/` (T-8.4/8.5).
- `apps/promotions/response.py` — одна точка истины отклика акции (booking/buy/reserve/inquire/show) (T-8.2).
- `apps/promotions/telegram_actions.py` — пауза/стоп акции из бота через FSM.
- `apps/promotions/where.py` — «Wo ist meine Aktion?».

### apps/orders

- `apps/orders/delivery_choice.py` — общий разбор «Abholung | Lieferung» для корзины, акции, предложения, заявки (SH-24).
- apps/orders/editing.py — правка состава/скидки/доставки/клиента заказа тем же складским движком, что создание/отмена.
- `apps/orders/offers.py` — Sofort-Angebot (LS-3)
- `apps/orders/pickup_slots.py` — окна и ёмкость самовывоза.
- apps/orders/shipping_admin.py — единственный писатель способов доставки (под advisory-блокировкой, SHP).
- apps/orders/totals.py — итоги заказа (брутто → НДС, скидка, доставка, §19).

### apps/booking

- `apps/booking/no_shows.py` — счётчик неявок из статусов.
- `apps/booking/occupancy.py` — область занятости и блокировки ресурсов (комбинации столов).
- `apps/booking/services.py::book_many` — групповая бронь «всё или ничего» (HF-6c)
- `apps/booking/services.py` (`create_manual`) — ядро ручной записи.

### apps/stays

- `apps/stays/capacity.py` — ёмкость не ниже проданного.
- `apps/stays/front_desk.py` (`today_lists`) — списки «Heute» и виджет.
- `apps/stays/night_rates.py` — единственный писатель `NightRate`.
- `apps/stays/pricing.py::auto_discount` — единый кандидат скидки номера (витрина = чекаут)
- `apps/stays/rate_plans.py` — применимость тарифа, `parse_uuid`.
- `apps/stays/services.py::free_rooms_for` / `assign_room` — назначение номера (PMS-R2)
- apps/stays/settings_actions.py — 15 настроечных действий номеров (D4.0).

### apps/events

- apps/events/itinerary.py — маршрут тура, серверный фильтр видимости `visible`; apps/events/landing.py — редактор богатых блоков события/тура; apps/events/logistics.py — `participant_view`.
- apps/events/registration.py — реестр анкеты участника.

### apps/jobs

- apps/jobs/services.py (`commit_stock`/`release_stock`) — резерв склада из сметы.
- apps/jobs/totals.py (`quote_totals`) — итоги сметы для карточки/PDF/публичной страницы/счёта.

### apps/finance

- apps/finance/bank.py — `deal_open_items`: строки Offene Posten (их же читает «Nicht bezahlt» главной отеля, D1.4).
- apps/finance/bank.py — импорт банка, открытые позиции (`_OPEN_PAYMENT_STATES`), сопоставление.
- apps/finance/services.py (`compute_totals`, `invoice_from_order|stay|booking`) — счёт из сделки, построчные ставки.
- `apps/finance/ustva.py` — срез UStVA по режиму Soll/Ist/§ 19.

### apps/inventory

- `apps/inventory/locations.py` — балансы по локациям, `transfer`.
- `apps/inventory/matrix.py` — матрица склада «размер × цвет»
- `apps/inventory/purchasing.py` — закупки; приёмка через складской путь.
- `apps/inventory/services.py` — единственный складской путь (`record_movement`, `log_catalog_change`, FEFO-партии; отдельного `lots.py` нет в коде).
- apps/inventory/services.py (`produce`) и apps/inventory/purchasing.py (`return_po_line`) — производство и возврат поставщику.

### apps/aggregator

- `apps/aggregator/ai_search.py`, `apps/aggregator/ai_expand.py` — ИИ-подсказки поиска (закрытый словарь, белый список фильтров).
- `apps/aggregator/category_facets.py` — чипы разделов/признаков портала.
- `apps/aggregator/district_liveness.py` — «живой» район и соседи.
- `apps/aggregator/featuring.py` — featured-checkout листингов.
- apps/aggregator/portal_facets.py, apps/aggregator/portal_filter_ui.py, static/js/portal.js — счётчики и UI фильтров портала; portal.js общий с витриной (FLT-1/3).
- `apps/aggregator/portal_home_blocks.py` — блоки главной портала (замок «блок ⊆ ленты»).
- `apps/aggregator/portal_scope.py` — охват портала (город, тип, демо, тема); AST-замок запрещает ручной охват.
- `apps/aggregator/search.py` — единый движок поиска портала и `/entdecken/`, `FILTER_PARAMS` — источник списка фильтров; `apps/aggregator/search_synonyms.py` — синонимы и `split_compound`; `apps/aggregator/query_intent.py` — парсер намерения запроса.
- `apps/aggregator/search_synonyms.py` (`CROSS_LANG`) — словарь основ поиска на 5 языках.
- apps/aggregator/views.py — `open_snapshot` («открыто сейчас» портала, PH).
- `apps/aggregator/visibility.py` — одна точка «бизнес годен к показу» (`listable`) + `AggregatorListing.objects.public()` на всех чтениях портала (T-8.6).
- apps/aggregator/visibility.py — `withheld_reasons`: почему бизнес не в каталоге города (A-0).

### apps/ai

- `apps/ai/config.py` — настройки ИИ (админка → `.env`; «Nur EU» из `.env` — пол).
- apps/ai/guard.py — общая пост-проверка/отсечение для ИИ-ответов (A-2).

### apps/billing

- `apps/billing/connect.py` — `checkout_session`, шов `payment_method_types` для всех продажных вызовов.

### apps/community

- apps/community/access.py — `role_of` (доступ к ленте поездки, fail-closed).

### apps/crm

- `apps/crm/dsgvo.py` — выгрузка и удаление данных клиента (общая с ЛК и CLI).

### apps/inbox

- apps/inbox/deal_threads.py (`find_thread`, `adopt_open_thread`) — тред сделки; канон `ref_id = reference_code`.

### apps/notifications

- apps/notifications/prefs.py (`muted`) — разовое подавление уведомлений; apps/notifications/services.py (`email_locale`) — язык писем.
- `apps/notifications/prefs.py` — реестр событий уведомлений + `channel_enabled` (хранение `site_config["notify"]`).

### apps/platform_bot

- `apps/platform_bot/links.py` — единственный писатель связей чат↔бизнес и их зеркал.
- `apps/platform_bot/rights.py` — права DSGVO Art. 15–21 в ботах.

### apps/publishing

- `apps/publishing/models.py` (`Channel.update_config`) — блокирующий писатель конфига канала.
- `apps/publishing/services.py::republish_promotion` — идемпотентная публикация акции по каналам (ST-6b)

### docs

- docs/cabinet-glossary.md (термины кабинета), docs/cabinet-screen-dod.md (чек-лист нового экрана).
- docs/references/patterns/drawer.md — контракт шторки кабинета (UX-D).

### scripts

- `scripts/fetch_cc0_photos.py`, `scripts/demo_photo_sheet.py`, `scripts/demo_photo_fetch.py`, `scripts/gen_demo_garments.py`, `static/demo/photos/SOURCES.md` — канал демо-фото и провенанс; `scripts/gen_demo_photos.py` — AI-канал, оставлен, но не используется.
- `scripts/golden_paths.py` — стенд золотых путей.
- `scripts/i18n_gap.py` — CI-гейт покрытия .po (I18N-9)
- scripts/i18n_untranslated.py + locale/i18n-untranslated-baseline.json, scripts/i18n_status.py, .claude/hooks/i18n-watch.sh, .githooks/pre-commit — сторож непереведённого.

### static

- `static/demo/photos/SOURCES.md` — провенанс демо-фото.

### templates

- `templates/core/_deal_lines.html`, `templates/core/_part_picker.html` — общая таблица позиций сделки и пикер позиций (SH-21).
- templates/core/_vat_select.html + тег `vat_select` — выбор ставки (три законные ставки).
- `templates/storefront/_buybox.html` — единый buy-box, диспатч по purchase_mode.
- `templates/storefront/_discount_display.html` — парты цены/условий акции (mystery не течёт) (DL-17/19).
- `templates/storefront/_discount_display.html` — единый показ цены/скидки акции.
- `templates/storefront/_sellable_card.html` (+ тег `sellable_card`) — единая карточка услуги/номера/события.
- `templates/storefront/_slider_script.html` — единственный слайдер-примитив `[data-sf-slider]` (DL-16.1).
- `templates/storefront/listing.html` — единый каркас всех листингов.
- `templates/tenant/_cb_row.html` — общая строка C-блока редактора (главная и страницы).
- Партиалы-единственные: templates/tenant/_i18n_switch.html (свитчер языка/вкладок + раскрытие invalid), templates/tenant/_status_manager_panel.html, templates/storefront/_combo_card.html, _category_tile.html, _anfrage_form.html, _message_form.html.
- `templates/tenant/_icons.html` + тег `{% icon %}` — SVG-спрайт кабинета

## 4. Сырые выписки по периодам: открытое и ops

Выписки агентов с их пометками уверенности («точно / вероятно открыто» — оценка агента от
2026-11-13, не подтверждение; ссылки «чанк», «строка „Миграции“» относятся к прежнему `CLAUDE.md`). Сводка выше собрана из них; при расхождении
верить сводке и `docs/task-catalog.md`.

### 4.1 Открытое

#### 2026-06-22 … 07-16
- G11c–e: реальные API Booking/Expedia/Airbnb для Channel Manager (партнёрство, шаг владельца) — точно открыто (2026-06, A5).
- Stage 2: P2.8 PWA/push/Wallet, M21 импорт Shopify/Woo, M23c платная реклама — точно открыто (external; M21 частично закрыт только для CS-Cart).
- Stage 3: маркетплейс-корзина M14, dropshipping M15, workflow-билдер M19 — точно открыто (не начато).
- Нативные PayPal/Klarna/SEPA — точно открыто, external-integrations-backlog (E-7, 2026-07-02).
- D1 Pro-тариф — «долгий ящик», ждёт прайсинг владельца — точно открыто (task-catalog: 🧊).
- D3.5 вход партнёра в кабинеты клиентов (этап 2) и wholesale-вариант партнёрки — точно открыто (task-catalog: ⏭ / ⏸).
- D2.5 цены featured-планов в кабинете — ⏸, env достаточно; E-11 claim-your-business «позже» — точно открыто.
- SMS-канал уведомлений (UD4-1) — точно открыто, external.
- Склад-2 v2: продажа с локации, `Lot.location`, демо мультисклада — точно открыто (task-catalog: «v2»).
- SEO v2: перевод листингов/деталей на движок мета-заготовок — «по спросу», вероятно открыто (в архиве позже не закрывалось).
- FB-9 (статичный календарь наличия номера — «уточнить») и FB-14 (внешняя ссылка «refused to connect», нужен репро) — вероятно открыто; FB-14 возможно снят фиксом `target="_top"` (2026-07-12).
- AB6: динамические слайды меню (v2) — вероятно неактуально (мастер v4 заменил слайды).

Закрыто позже, не включал: T-1 de.po, перевод меток вариантов/модификаторов (I18N-10), кастом-статусы для всех kind (SM-3), dedicated online_shop-кит, owner-письма DE-only (I18N-7a), E7-4 (SH-23), UC2-3(b), «10 видов на блок».

#### 2026-07-11 … 08-05
Закрыто позже и НЕ включено: ST-4b, «продано N», ST-7c, UC2-3(b) вар. A, I18N-7b, W11-5, ответ на BusinessReview, метки вариантов/опций (I18N-10), остаток демо-переводов (I18N-11/12), CO-1/CO-2, AB6 код, FD-3/FD-4, перевод attributes/faq.

- UC2-3 вариант B — per-page ДАННЫЕ секций (не ссылочные блоки) — за решением владельца (2026-07-20) — точно открыто (подтверждено §7 CLAUDE.md)
- Pro-тариф D1 — ждёт прайсинг владельца (2026-07-20) — точно открыто
- G11c–e реальные OTA-API (Booking/Expedia/Airbnb) — external, блокер владельца — точно открыто (external-integrations-backlog)
- LLM-режим Finder (v2), WhatsApp Business API — external-gated (2026-07-20) — точно открыто (task-catalog: «v2 = LLM-режим, external»)
- SSE для чата (M22b) — отложено (2026-08-01) — точно открыто (roadmap §Отложено, стр. 699)
- Перевод маркетинговой копии Branchen-лендингов (224 msgid в allowlist i18n_gap; рекомендация начать с en) — за решением владельца (I18N-9, 2026-07-31) — вероятно открыто (позднее закрытие не найдено)
- LS-4 v2: фото сотрудника в треде; LS-5 v2: поздравление с ДР (2026-07-19) — вероятно открыто (упоминаний закрытия нет)
- Мастер: динамические слайды меню per-страница (v2, AB6.0 2026-07-11) — вероятно открыто (мастер позже заменён v4 — возможно, неактуально)
- Studio ST-3: мобильная версия оболочки — «ограничение v1, desktop-first» (2026-07-19) — вероятно закрыто STU-12h (телефон bottom-sheet); проверить
- Корпоративный контур/цены конкурентов: дальнейшие шаги после CP-1 (CP-2+ в `pms-corporate-competitor-plans-2026-07-28.md`) — вероятно открыто (в task-catalog CP-2 не найден)
- «Де-факто новые экраны кабинета W9–W12 прогнать глазами на стенде» (2026-08-05) — вероятно закрыто последующими стендами программы «Кабинет-X»

#### 2026-08-06 … 08-20
- DS-трек: виды вывода услуг/номеров/событий (прайс-с-длительностью · пакеты-колонки · полоса-разворот · афиша) — «за отмашкой владельца» (2026-08-12); в task-catalog строка DS до сих пор «Дальше: … за отмашкой» — точно открыто (частично перекрыто MEN-18 прайс-виды услуг и волной LAY).
- VS-3 границы v1: связь сделок без витрины, без каскадов статусов, без слияния денег, без миграции Extras в DealLink (2026-08-20) — вероятно открыто (VS-4 в каталоге нет; адресные опции на витрине закрыла MX-2 другим механизмом).
- MT-F: у `FeedPost` (лента поездки) нет i18n-оверлея — демо-чат только на немецком (2026-08-14) — вероятно открыто.
- GK-8: блок newsletter v1 уводит на /newsletter/ (нет PRG/next возврата) (2026-08-11) — вероятно открыто.
- DS-3b: слайдер при hero_style=split не крутится (v1) (2026-08-12) — вероятно открыто.
- MT-D: `demo_photo_report` показывал 6 незакрытых фото-ключей у других китов (2026-08-14) — вероятно закрыто позже фото-волнами; проверять командой.
- Закрыто позже (не переносить): роли admin/staff идентичны (→ E6.7), I18N-11 остаток (→ I18N-12), GK-5..9, X2c, VS-3 как таковой.

#### 2026-08-20 … 09-02
- Дробление `RevenueEntry` по ставкам НДС (нужен гард от двойного учёта) — VAT, 2026-08-26. Вероятно открыто: в task-catalog и roadmap закрытия не нашёл; позже по ставкам считаются сторно и UStVA, но про журнал выручки записи нет.
- ERP-7 v2 «по спросу»: сохранённые рецепты производства, локации, средневзвешенный EK — 2026-08-21. Точно открыто (task-catalog так и пишет «v2 по спросу»).
- I18N-13: остаток 120 строк «без пути перевода» (контент тенанта, правовое платформы, admin, машинные форматы) — осознанно не переводится; вероятно открыто только «правовое платформы».
- Pranasy: 17 из 49 блюд без честного фото (плейсхолдер) — 2026-08-25/26. Вероятно открыто.
- DL-13 «хвосты v1» — список только в build-log 2026-09-02, в архиве и каталоге закрытия нет. Вероятно открыто.
- SF-4b «границы v1» (план `sparfuchs-ux-tz-plan-2026-08-31.md §SF-4b`) — вероятно открыто.
Проверено и закрыто позже (не включать): R5c/R6 (каталог RD: ✅ целиком), «карта узких страниц» (VF-24, затем D7), выручка заявок в журнале (finance/0014 SOURCE_JOB), MX follow-ups, «индексы promotions_spec» (цель акции по имени, STU-18h).

#### 2026-09-02 … 09-10
- DL-21.3 «Too Good To Go» — предложение владельцу (план `docs/dl21-root-and-overview-templates-plan-2026-09-03.md §4`, Р-9 «код — по решению»): отмена до N ч, «Bescheid geben, wenn es wieder Tüten gibt», post-pickup оценка, Impact, ежедневная повторяющаяся публикация, чекбокс-согласие «Inhalt nicht garantiert». В task-catalog отдельного закрытия нет; окно выдачи у акции позже сделано (KA-12 W1.3), подписки — волной NT/Folgen. — вероятно открыто (частично закрыто по кускам).
- DL-21.2 «Kopfbild v1 без своих текстов» у обзора акций (Р-8) — ограничение v1, закрытия не найдено — вероятно открыто.
- STU-17: `team`/`gallery` без своей оси сетки (берут раскладку одноимённой секции главной) — осознанное исключение, не долг; упоминаю как ограничение — точно так и осталось.
- Закрыто позже (не включаю): SH-22 (✅ `orders/0023`), A1 «Vorschau» и tabs-категория (DL-17/18), переработка Студии (STU), «Alle anzeigen»/перекос на ru (SF-5/6), демо-носитель формы карточки у полки (clothing «Taschen», 2026-11-08), LAY-остаток.

#### 2026-09-09 … 10-16
- T-8.12 «порталы сторонних операторов» (модель B «оператор-партнёр», после пилота) — в task-catalog по-прежнему «после пилота» — точно открыто (2026-10-09).
- `old_price` в открытом фиде (L2) + лицензия фида — «к юристу» (T-8.8, 2026-10-15) — вероятно открыто (закрытия не нашёл).
- DCC хвосты: фото-добор для плейсхолдеров `sg-*` (≈290 ключей), сводный стенд портала после пересева, `seed_demo_tenants --refresh-events` (события демо протухают) — в roadmap §Отложено — точно открыто (2026-10-16).
- T-8.7 хвосты: bounce-обработка писем (Resend webhook), ротация `follow_token`, «Folgen» на разделе/районе на `/entdecken/` — в roadmap — вероятно открыто (Telegram-канал подписки закрыт T-8.28).
- N+1 `Product.has_variants` на карточках (LB-1a, 2026-10-02) — запись в roadmap §Отложено осталась; позже E10 батч 1 ввёл `catalog/prefetch.py` (каталог 250 → 51 запрос) — вероятно закрыто, запись roadmap стоит сверить.
- LAY-1: «проверку отката формы карточки в браузере доиграть» — утратило смысл (пилюля охвата и `studio_scope` снесены STU-19f) — закрыто.
- Остаток волны LAY (LAY-3a-2, LAY-5, LAY-6), LB-3/LB-4, T-8.2…T-8.26 — закрыты позже (проверено по архиву).
- `show_demo` на портале Solingen снять на запуске; «rest» пометить `is_internal` — ops, см. D.

#### 2026-10-16 … 11-01
- **F-6 — оценка пилота MCP после 4 недель данных** (2026-10-19): точно открыто; в task-catalog T-8 стоит без отметки.
- **Включение D-2 и T-8.34d (`AI_SEARCH_ENABLED`)** — ждёт решения владельца по `search_log_report` (`d2_recommended`) и абзаца в Datenschutz: точно открыто (флаг `False` в base.py).
- **E2.9b — входящие в две панели** (2026-10-24): точно открыто (roadmap §Отложено, строка 549).
- **T-6b — § 25 UStG и Sicherungsschein для пакетных туров**, за Steuerberater'ом (2026-10-25): точно открыто (roadmap, строка 330).
- **A-3b (Anfragen) — вид «Kalender» у заявок** (2026-10-25): точно открыто (план anfragen: «отложено»).
- **E6.4 — вопросы владельцу В-4 (отдельное поле аллергий с согласием) и В-5 (шифрование текста заметок мастера)**: вероятно открыто (roadmap, строка 319); срок хранения закрыт E6.4d.
- **Свой статус неявки не учитывается счётчиком** (E6.4a): вероятно открыто (roadmap, строка 321).
- **MC-H6 — аванс заявки без Anzahlungsrechnung**: код есть (B2-8b/c/d), но за выключенным `ADVANCE_INVOICES_ENABLED`; вероятно открыто до решения Steuerberater'а. MC-E8/J1/T1/Z9 закрыты батчами 1–2.
- **Тёмная тема кабинета — «позже»** (E9, 2026-10-30): точно открыто, позже не упоминается.
- **Тарифы (19/29 €, Profi-модули) скрыты до объявления; T-8.33** (2026-10-22): вероятно открыто; T-8.33 в task-catalog и архиве не найден.
- **Пометить демо «rest» как intern и снять `show_demo` на запуске портала** (T-8.26, упомянуто в начале чанка косвенно): вероятно открыто — это ops.
- Закрыто позже, не включаю: E9.7 (build-log 2026-10-30), KA-5c…KA-11 (поглощены KA-12), E10.4, Д3 (D3-3/4a сняты владельцем).

#### 2026-10-31 … 11-11
- M21.11 P6 (таблица, видео/карта с согласием, PDF, оглавление, цвет из палитры, чеклист, счётчик, поиск/замена, Markdown, ИИ, оформление фото) → P7 история версий (⚠ миграция) — точно открыто (каталог: «P6/P7 дальше»; после 11.11 шли только M21.11-доводки и FB-27).
- M21: прогон переезда haanerteeladen на сервере владельцем (runbook §7 плана) — точно открыто (каталог: «⏳ прогон на сервере владельцем»).
- W4-5d: код готов, флаг `READINESS_SELL_GATE` выключен до `readiness_report --stamp-exempt --apply` — точно открыто (default=False в base.py; O-1 решён).
- M-1e: `modules_report` → показать владельцу → `--apply` — вероятно открыто (следов выполнения нет).
- AIS-0: замер базовой линии `onboarding_report` ≥ 2 недели после деплоя — вероятно открыто (по времени).
- AIS-1 (часы структурой), AIS-8 (Impressum на проверку), AIS-9/10 — в каталоге без ✅; вероятно открыто (AIS-1 частично покрыт «часы сеткой» в W4-1).
- SEC, остаток вне волн: non-root в образе и фиксированные теги образов (нужен chown тома media), SM11/SM15 (beat без изоляции схем, дедуп публикаций — по спросу), wildcard-сертификат через DNS-01 как настоящее решение квоты LE (B-H1, ops-решение владельца) — точно открыто (отчёт аудита §6). Django 5.1 EOL/Pillow — ЗАКРЫТО 2026-11-02 (Django 5.2 LTS), SEPA/FSM/нумерация/CSRF/kill-switch/шифрование — закрыты волнами 1–4.
- SHP: Widerruf для click&collect — юристу, за флагом; перевод существующих бизнесов на Paketdienst — после подтверждения по `shipping_report` — вероятно открыто.
- FB-27 (Website: Seitenaufbau/Seitenvorlagen/Seiten/Design) — идёт после чанка (в архиве нет, в каталоге «план на согласование», коммиты R3b-2) — точно открыто, в архив не попало.
- Закрыто по проверке, НЕ переносить: «EUR» вместо «€» (PH-11e), контраст цвета портала (PH-12), вопрос об оплате при доставке (решён 2026-11-05), O-1.
- Осознанно НЕ делаем (не открытое, но чтобы не возвращаться): PH-12e «Das Beste» без N параметров; контакты с картой и наборы без фото (SP-17).

### 4.2 Ops владельцу

#### 2026-06-22 … 07-16
- Правовые страницы ПЛАТФОРМЫ `/impressum/`, `/datenschutz/` (и AGB): в `templates/tenants/legal_impressum.html` и `legal_datenschutz.html` до сих пор стоят плейсхолдеры `[Name / Firma des Betreibers]`, `[Straße Hausnummer]`, `[PLZ Ort]`, `[Inhaber/in …]` — заполнить реквизитами + юр. вычитка (2026-07-13).
- Stripe live: ключи, Price 39 €, Connect, webhook; способы оплаты Stripe (`stripe_payment_methods`) включаются в Stripe Dashboard (E-7, 2026-07-02).
- Featured-планы: цены задаются env-оверрайдом (D2, 2026-07-03).
- Партнёрка D3: ревшара считается вручную; скидка клиенту — Stripe-купон, создаётся владельцем (2026-07-03).
- Правка переводов без кода: `/rosetta/` (только суперпользователь, public) — цикл «править в dev → коммит .po → деплой»; на проде правки не сохраняются (T1-c, 2026-07-10).
- После T-5: рестарт caddy (скорее выполнено).
- Демо-кнопки «Demo ansehen» появляются только при засеянных демо. Пересев: hotel, friseur, baeckerei, metzgerei, cafe, mode, touren, handwerker (+ общий `--recreate` для фото).
- Миграции этой части (collections/0001, booking/0013–0014, stays/0021, inventory/0001–0004, catalog/0012–0016, tenants/0020–0025 и др.) — по записи 2026-10-19/24 применены; действий нет.

#### 2026-07-11 … 08-05
- `SIGNUP_EMAIL_CONFIRMATION` (default on) — реальные письма подтверждения требуют `RESEND_API_KEY` (AB5.1, 2026-07-18); по §8 CLAUDE.md Resend в проде работает — вероятно выполнено
- Пересборка образа с `fonts-dejavu-core` для PDF на кириллице/турецком (I18N-7b, 2026-07-31) — в Dockerfile есть; выполнено деплоями
- Миграции записей (tenants/0026, orders/0015, booking/0017, tenants/0027, stays/0024–0027, 0030, 0031, catalog/0020–0023, collections/0002, booking/0020–0021, promotions/0024–0025, orders/0017, aggregator/0015) — закрыты общим деплоем 2026-10-24 («Всё применено»)
- Постоянное правило ops: очередь миграций сверять `python manage.py migration_state` (шаг встроен в deploy.sh, T-7)
- seed_demo_tenants --recreate: все киты (демо «новой идеологии», 2026-07-19; демо-стили опций 2026-08-01), отдельно hotel, aktionsmarkt, clothing, friseur
- Юр. вычитки, BotFather, cron в этой части — нет

#### 2026-08-06 … 08-20
- `GOOGLE_PLACES_API_KEY` (Places API New + billing) в .env.prod/secrets — без него Google-рейтинг (GK-11, 2026-08-11) и «Bei Google suchen» молчат; в task-catalog всё ещё помечено EXTERNAL.
- @BotFather: у СВОЕГО бота бизнеса, используемого для Telegram-моста ленты поездки (MT-3, 2026-08-13), privacy mode ВЫКЛЮЧИТЬ. Внимание: для общего бота платформы и ботов портала (T-8.10h/T-8.28) правило обратное — privacy mode ВКЛ; в коротком CLAUDE.md развести явно.
- Модули finance/analytics выключены по умолчанию у всех типов (карточка «Finanzen aktivieren») — включает владелец бизнеса (X3, 2026-08-19).
- Миграции этого периода (aggregator/0016, catalog/0024, jobs/0013, tenants/0028–0031, 9 миграций I18N-12, волна MT, reviews/0005, catalog/0027–0028, promotions/0026, core/0008) — по строке «Миграции» задеплоены 2026-10-19; проверка `python manage.py migration_state`.
- Пересев демо (`seed_demo_tenants --kit … --recreate`), упомянутые киты: все (после ST-8/I18N-11/I18N-12), catering, pranasy, restaurant, moto, hotel; пометка «мастер пройден» приезжает только с пересевом.
- Юр. вычитка/cron/флаги в этой части — нет.

#### 2026-08-20 … 09-02
- Миграции этого периода — в очереди, помеченной задеплоенной 2026-10-19; новых ключей/флагов в записях части 4 нет.
- `scripts/install-git-hooks.sh` — ручной разовый запуск на каждой рабочей копии (иначе pre-commit сторож i18n/CSS не работает) — I18N-13.
- Пересев демо: `seed_demo_tenants --recreate` для cafe, moto, stadtfuehrung, catering, pranasy, aktionsmarkt; после DL-11 — всех китов.
- Юридическая вычитка, BotFather, cron — в этой части нет.

#### 2026-09-02 … 09-10
- Ключей/флагов/юр-вычитки/BotFather/cron в этой части нет. Миграции части (`catalog/0032–0034`, `promotions/0027–0028`, `orders/0022–0024`, `jobs/0018–0020`, `tenants/0032`, `finance/0012`, `booking/0027`, `stays/0035`, `events/0030`) — задеплоены (отметка 2026-10-19).
- Справочно: ключа генеративной модели изображений в окружении нет (AMP/MODE) — это решение, а не задача (см. E).
- `seed_demo_tenants --recreate`: aktionsmarkt, clothing (mode), pranasy, online_shop, shop, outlet, stadtfuehrung.

#### 2026-09-09 … 10-16
- `.env.prod`: `SECRETS_ENCRYPTION_KEY` (без него или с негодным значением деплой останавливается на префлайте) → после деплоя `manage.py rotate_secrets` (dry-run → `--apply`) → `manage.py cleanup_import_files` (dry-run → `--apply`); при смене ключа — `SECRETS_ENCRYPTION_KEY_PREVIOUS` (P0, 2026-09-10). Деплой 2026-10-24 прошёл, значит ключ задан; выполнены ли `rotate_secrets`/`cleanup_import_files` — не подтверждено.
- Env: `LITE_FREE_ACTIVE_PROMOS` (лимит бесплатных акций, по умолчанию 5), `PLATFORM_CONTACT_EMAIL` (адрес «свяжитесь с нами») (T-8.4).
- `RESEND_API_KEY` — письма жителям (Folgen) и подтверждения (T-8.7); по §8 CLAUDE.md Resend в проде работает.
- Админка после деплоя T-8.26: пометить внутренний тенант «rest» как `is_internal`; `AggregatorPortal.show_demo` у `solingen.<base>` снять на запуске.
- Команды после деплоя: `sync_aggregator` → `rebuild_search_index` (T-8.8, T-8.26).
- Postgres: роль с правом `CREATE EXTENSION` (pg_trgm, T-8.20) — важно при переезде на внешний Postgres.
- Юр. вычитка/Datenschutz: строка о статистике поиска (T-8.21); строка о подписках «Folgen» (T-8.7); `old_price` и лицензия открытого фида (T-8.8).
- Пересев демо (`seed_demo_tenants … --recreate`): aktionsmarkt, hotel, friseur, retreat, moto, stadtfuehrung, shop, clothing, online_shop, outlet, tours, bakery, butcher, klingenbrot, ohligser_eck, walder_faden, wupperhof, brueckenblick, graefrather_markt; группа `--group solingen-dcc --jobs 3`. (Позже заменено на `--group all --changed`.)

#### 2026-10-16 … 11-01
**Ключи и флаги (все по умолчанию выключены в `base.py`):**
- `AI_ENABLED` плюс ключи провайдеров ЕС (Bedrock EU, Azure Data Zone EU, Mistral — `docs/ai-providers-setup-2026-10-16.md`); `AI_REQUIRE_EU` в проде не снимать; задачи включаются в админке «KI-Einstellungen»; `ai.W004` глушится через `SILENCED_SYSTEM_CHECKS` в `.env`.
- `AI_SEARCH_ENABLED` плюс задача `search_query_expand` — после `search_log_report` и абзаца в Datenschutz.
- ИИ-модерация каталога (D2b-2) — выключена до ключей ЕС.
- `MCP_ENABLED`, `MCP_ACTIONS_ENABLED` — второй требует настоящей почты (Resend или SMTP).
- `ADVANCE_INVOICES_ENABLED` — после подтверждения формулировок PDF Steuerberater'ом.
- `QUOTE_WITHDRAWAL_ENABLED` — после вычитки текстов Widerruf юристом.
- `PANGV_PERISHABLE_EXEMPTION` — включён; `False` это откат.
- `MAP_STYLE_URL` (OpenFreeMap по умолчанию), `PORTAL_DISTRICT_MIN_BUSINESSES` (10) — менять по желанию.
- `RESEND_API_KEY` — письма подтверждения бота (по CLAUDE.md §8 уже стоит).

**Ручные шаги в админке и BotFather:**
- «Telegram platform bot»: токен, включить, «Webhook setzen» (ставит команды и кнопку меню Mini App); повторить после H-7 и T-8.30.
- «Portal bots»: токен, «Connect» (вебхук и команды); повторить после H-7.
- @BotFather: privacy mode ВКЛ у бота платформы и ботов портала.
- `telegram_resync_webhooks`, затем `--apply` (после B-1).
- Пометить «rest» как intern (`tenants/0037`); снять `show_demo` на запуске.

**Команды после деплоя:**
- `sync_aggregator` → `rebuild_search_index` (T-8.26-Б, В2/В4, T-8.10d).
- `seed_demo_tenants --group all --stamp` один раз, далее `--group all --changed --jobs 3` (T-10).
- `package_report` перед включением гейта пакетов; `pilot_report`, `search_log_report`, `mcp_smoke`, `ai_smoke` — по мере надобности.
- `seed_demo_tenants --recreate`: все киты (новые адреса `example.com`, F-4e), любой кит Solingen (создаёт `gesund-solingen`), hotel (Z-7), restaurant (GA-7/GA-9).

**Юридическая вычитка:**
- Datenschutz бизнеса §8/§8a (общий бот, права в ботах), фраза о Mini App, абзац про ИИ (T-8.10g), строки об импорте с сайта (T-8.27), срок 3 года для заметок мастера.
- Datenschutz портала: Telegram-подписки, ИИ-поиск.
- Widerrufsbelehrung и письмо-договор (A-7).
- Основание § 634a BGB для хранения актов приёмки (A-5).
- PDF Anzahlungsrechnung — Steuerberater.
- § 25 UStG / Sicherungsschein (T-6b).
- AGB — внешний генератор (решение владельца).

**Cron:** в этой части новых нет; beat подхватывает задачи при рестарте.

#### 2026-10-31 … 11-11
- `.env.prod`: `STRIPE_WEBHOOK_SECRET` (`whsec_…`; без него вебхук отвечает 503, deploy-check `billing.E001`) и `STRIPE_CONNECT_WEBHOOK_SECRET` (секрет эндпоинта «Connected accounts», `billing.W002`, SEC-D7).
- Stripe Dashboard → Webhooks: добавить события `checkout.session.async_payment_succeeded` / `…_failed` (SEC волна 1).
- `python manage.py telegram_resync_webhooks --apply`, затем `TELEGRAM_WEBHOOK_LEGACY_HEADER=False` (сейчас default=True).
- Cron бэкапа из шапки `scripts/backup.sh` + один раз проверить восстановление.
- По желанию: `ADMIN_ALLOWED_NETWORKS`, `REDIS_PASSWORD` (+`REDIS_URL`), `CSP_REPORT_URI`, `QUICK_START_HOURLY_CAP`.
- `GOOGLE_PLACES_API_KEY` + квота (W4-3 «Bei Google suchen»; также GK-11).
- «KI-Einstellungen» в админке: включить задачи `offer_photo_lines`, `offer_pdf_lines`, `assistant_answer`, `assistant_actions` (тумблер выкл.), `i18n_translate`, `text_from_facts`; сам ИИ — `AI_ENABLED` (default False), прод-маршрут Claude — AWS Bedrock EU.
- Флаги, выключенные по умолчанию: `READINESS_SELL_GATE` (после `readiness_report --stamp-exempt --apply`), `AI_SEARCH_ENABLED`, `MCP_ENABLED`/`MCP_ACTIONS_ENABLED`, `ADVANCE_INVOICES_ENABLED` (после Steuerberater), `QUOTE_WITHDRAWAL_ENABLED` (после юриста). `SETUP_WIZARD_V4` включён; откат — `False` в `.env.prod`.
- Команды-отчёты с решением: `modules_report` → `--apply`; `shipping_report`; `onboarding_report` (`--compare <дата>`).
- Деплой очереди миграций (блок «⏳ К ДЕПЛОЮ» от `finance/0017` до `core/0019`; `events/0036` переписывает таблицу билетов каждой схемы) → `migration_state` → `sync_aggregator` (→ `rebuild_search_index`).
- Переезд магазина: `import_cscart` (`--apply`, `--replace-menu`, `--locales de`, `--cleanup`, `--codes`), `fix_impressum` — по runbook §7 `m21-cscart-migration-plan-2026-10-31.md`.
- Юридическая вычитка: абзацы Datenschutz о подписках/темах рассылки (NT), Widerruf click&collect (SHP), уведомление «ИИ работает в США».
- Пересев демо: `seed_demo_tenants --group all --changed`; `--recreate` для китов: cafe, outlet, online_shop (+ прежняя очередь из строки «Миграции»: moto, catering, pranasy).

## 5. Решения владельца по периодам

Позднее решение сильнее раннего. Пометки «позже снесено / отменено» оставлены намеренно —
чтобы снесённое не восстанавливали.

### 2026-06-22 … 07-16
- Модели продаваемых сущностей НЕ сливаем — единый слой через адаптер `SellableEntity`; отличается только buy-box (2026-06-30).
- Единый CRUD продаваемых сущностей не делаем: общий экран — обзор + переход в родную форму (FB-8 Вариант A, 2026-07-12).
- Хранение site_config ПЛОСКОЕ («виртуальный фасад» страниц); свод save-блоков билдера — WONT-FIX (UC2-1, UC2-4, 2026-07-08).
- Цвет текста C-блоков — только из палитры темы (UC6-2, 2026-07-06).
- Тема (цвет/шрифт/баннер) — один источник; второй экран её не пишет (W6, 2026-07-09).
- Склад: архитектура «счётчик = истина, леджер/партии/локации поверх»; движки заказов не переписываем; сразу полный FEFO (UD3 D1, Склад-2, 2026-07-16).
- KDS не трогаем при унификации доски (UD2 D2, 2026-07-07).
- Kanban = drag-drop; правила переходов: FSM — пол, владелец только скрывает; свои статусы — роль + флаги (FB-3 A+B, 2026-07-12).
- Свои имена статусов показываются в кабинете, НЕ в клиентском аккаунте (FB-4b, 2026-07-12).
- Пищевая маркировка — только гастро-типам (FB-1, 2026-07-12).
- Типы бизнеса добавляются к существующим, не заменяя («набор ок + текущие», S6, 2026-07-09).
- Язык кабинета отделён от языка витрины и от переводов контента; языки кабинета — de/en/tr/ru/uk; базовый msgid — немецкий (T1, 2026-07-10/11).
- Языки витрины: реестр 11 локалей, включает владелец бизнеса (L2, 2026-07-09).
- Правовое per-locale — модель `LegalDoc`; `/agb/` без текста = 404 (S-2b, L5, 2026-07-03).
- Vorkasse и пикер оплаты: показывается только при > 1 способа (E-7, 2026-07-02).
- Партнёрка v1 read-only, вознаграждение per-partner (скидка купоном или ревшара вручную) (D3, 2026-07-03).
- UWG: платное размещение всегда помечено «★ Anzeige» на всех поверхностях (D2/E-2, 2026-07-03).
- Демо-фото: только CC0/PDM с проверенной лицензией, без реальных лиц; AI-набор FLUX от 2026-07-10 позже отменён решением «только реальные CC0» (см. более поздние части).
- Главная платформы = `/branchen/`, регистрация — `/registrieren/` (2026-07-13).
- После зелёного CI — сразу FF-мерж в main; PR через API не создаём (2026-07-01, 2026-07-12).
- Режим Простой/Эксперт (S5) и хабы-таб-бары (S1–S4), введённые в этой части, позже снесены (SM-1, R7-1) — не восстанавливать.

### 2026-07-11 … 08-05
- classic_ui («Klassische Ansicht») УДАЛЁН целиком, normalize дропает ключ; правило «каждый редизайн уважает флаг» отменено (Р-1, W-CL, 2026-08-05)
- Verkäufe — единственная поверхность продаж; старые списки/календари = 302 на её вкладки (W10, 2026-08-05); вход «Verkäufe» отеля = Belegungsplan
- Marketing и Kunden — один хаб; Integrationen — не якорь сайдбара, а часть Einstellungen; Reservierungen — в Verkäufe; Newsletter — вкладкой (Р-2…Р-5, 2026-08-05)
- Навигация кабинета — только из единого реестра `nav_registry`; каждый nav-литерал обязан иметь якорь (замки W8)
- Акция = ценовой слой над базовой сущностью: закрывается штатным Order/Booking/Stay, зависит от реального наличия; kind `reservation` новый не порождается (легаси доживает); наборы — расширяем Combo (PL, 2026-08-03)
- Скидки номера не суммируются — берётся максимум (акция/G4/Lücken) (PL)
- Sofort-Angebot — отдельная лёгкая модель `orders.Offer`, jobs.Job не обобщаем (LS-3, 2026-07-19)
- Видео-консультация v1 = WhatsApp, без записи разговора (§201 StGB); номер — `Tenant.whatsapp_number` (LS-1)
- Finder — ОПЦИЯ (выкл по умолчанию), rule-based; в платформенном Finder featured НЕ поднимается, «★ Anzeige» обязательна (UWG §5a) (FD, 2026-07-18/20)
- UC2-3: секции на страницах — ссылочные блоки с ГЛОБАЛЬНЫМИ данными (вариант A); per-page данные — только отдельным решением (2026-07-20)
- «Verkauft N» и «Antwortet in ~N Min» — только с честным порогом (≥5 / ⌀ ≤ 2 ч) (2026-07-19/20)
- Регистрация: тенант не создаётся до подтверждения почты; allauth EmailAddress не используем (AB5.1, 2026-07-18)
- Кастомные вопросы/тексты владельца не переводятся автоматически (локализуются только пресеты); переводится ПОКАЗ, ключи фасетов (`?gruppe=`) остаются плоскими (I18N-6, 2026-08-01)
- Документы/PDF переводим полностью, КРОМЕ DATEV-экспорта и налоговых обозначений (решение «полный», I18N-7b, 2026-07-31)
- Маркетинговая копия Branchen-лендингов осознанно не переведена (allowlist) до решения владельца (I18N-9)
- Физические номера (`stays.Room`), корпоративный контур и «цены конкурентов» одобрены; CP-1 показывает позицию цены БЕЗ рекомендаций; правила продаж G12 гейтят ТОЛЬКО витрину, не стойку (PMS, 2026-07-27/28)
- Цвет кружка варианта — ТОЛЬКО по словарю (не произвольный hex владельца); свотчи управляют единственным `select name="variant"` (O-волна/M4-A, 2026-08-01)
- Merkzettel — в сессии, без модели/аккаунта (DSGVO-чисто) (M4-C, 2026-07-31)
- Индикатор «печатает» — кэш-флаг без модели, без новых запросов чтения; SSE не делаем (M22b, 2026-08-01)
- Режим Простой/Эксперт в этой части ещё существует (W12 «честные режимы», экран Ansicht) — позже снесён SM-1 (2026-08-10); из краткого CLAUDE.md W12-описание не переносить как действующее
- Правило процесса периода: автономные FF-мержи в main по зелёному CI; крупное — план-доком до кода (уже в §5)

### 2026-08-06 … 08-20
- Режим Простой/Эксперт КАБИНЕТА снесён целиком (ui_mode дропается normalize); Einfach/Experte РЕДАКТОРА блока тогда оставлен (SM-1, 2026-08-10; позже STU-16c снёс и его).
- Страница `/dashboard/site/` удалена — «Website» = только Studio (W11-5, 2026-08-06); легаси-доска `/dashboard/board/` и список `jobs:list` → 302 на Verkäufe; экран событий НЕ схлопывать (события — сущность Sortiment) (X2b/X2c, 2026-08-19).
- Verkäufe: вкладка на КАЖДЫЙ активный модуль сразу; исключение — `reservation` (легаси, видна только при записях); «Heute» живёт на главной (SM-2a 2026-08-10, VK п.8 2026-08-20). Reservierungen без дубля в Marketing (4а, 2026-08-06).
- Доска продаж: КОЛОНКА = СТАТУС, стадии — группы колонок; настройки W5 управляют группами (VS-2b, 2026-08-20).
- Главная кабинета = рабочая петля архетипа (вариант B) тем же телом, что Verkäufe (X3, 2026-08-19).
- Состав якорей сайдбара заморожен; каждый новый экран обязан иметь вход (X7, 2026-08-19); подпункты сайдбара = состав хабов из nav_registry (SM-4, 2026-08-11); глоссарий: «Angebote» → «Sortiment» (X4).
- Конвенция «＋» ведёт в форму создания (X6).
- Демо-киты пропускают мастер (`apply_kit` → `onboarding.mark_complete`) (2026-08-19).
- Категория = страница `/sortiment/<slug>/`; `/bereich/` и тумблер `category_landings` удалены; комбо = часть товара; «301 не нужен — не в проде»; выдача категории включает товары прямых детей (KAT, 2026-08-18; позже M21.4 — всех уровней).
- Товар: SEO-слаг, единственный URL — `get_absolute_url()`; POST-подпути на uuid (KAT-3).
- Заказ по акции = обычный Order; `Reservation` — легаси (VK п.8, подтверждение волны PL).
- Кастом-статусы на всех 6 направлениях; FSM — жёсткий пол, Вариант A прячет только builtin-цели (SM-3, 2026-08-10).
- Look = кожа; ВИД ВЫВОДА — per-модуль; в мастере — готовые СБОРКИ (DS, 2026-08-12).
- Страницы галереи/команды/отзывов — отдельные страницы, секции главной — тизеры; гейт по наличию контента (ST-8, 2026-08-06).
- У каждого демо-кита — акции всех стилей и меню с выходами во все наполненные модули (2026-08-06/07).
- Branchen: отраслево-нейтральные модули — среди прочих карточек, НЕ отдельным блоком (2026-08-07).
- Форма заявки (дата/гости/тип) — опция любого архетипа, наполняет владелец (AF, 2026-08-11); архетип Catering: jobs primary, Speisekarte browse-only (GK-1).
- Google-рейтинг в JSON-LD НЕ кладём (политика Google); показываем рядом с внутренним рейтингом (GK-11).
- Демо-фото: только CC0/PDM с проверкой лицензии по метаданным и просмотром каждого кадра, без узнаваемых лиц/водяных знаков, провенанс в SOURCES.md (MT-D, 2026-08-14).
- Маршрут тура = IP гида: видимость на каждой остановке, дефолт private (MT-1); ретеншн `TicketWaiver` осознанно НЕ вводим (срок исковой давности); досье участника — 90 дней после заезда (MT-2).
- Связь сделок создаёт владелец в кабинете; деньги не сливаются (VS-3, 2026-08-20).
- Роли admin/staff «оставить как есть» (2026-08-06) — отменено позже правами E6.7 (не переносить как действующее).
- CI ставит зависимости строго из `uv.lock` (лок в репо; обновление = осознанный `uv lock` в коммите) (5а, 2026-08-06).
- Правило процесса: ревью-находки перед починкой перепроверять разведкой, замки писать ДО правок (ревью Кабинет-X, 2026-08-19).

### 2026-08-20 … 09-02
- Вкладка «Kunden» в продажах — у ВСЕХ архетипов, но модуль CRM всем НЕ включаем (SH, 2026-08-20).
- Способ продажи — свойство КАРТОЧКИ; опция = цена + трекер (надбавка/пул/склад/закупка); 4 якоря по оси ёмкости (MX, 2026-08-21).
- Таб-бары хабов на страницах снесены: одно меню — сайдбар с подпунктами; ящик «Erweitert» со страниц снят (R2/R7-1, 2026-08-24).
- Все дизайны — через утверждение канваса; стиль кабинета B «Karten & Luft», мобильная в приоритете (2026-08-24).
- `/dashboard/angebote/` — единственная страница ассортимента; `/catalog/products/` только 302 (SR-1).
- Форма товара: правая колонка «Preis & Bestand» только на главной вкладке, у каждой вкладки своя раскладка (SR-2d).
- Смета = модель заказа: один селект каталога у «＋ Position», поле EK не показываем; закупка — раздел ERP (VF-9b, 2026-08-25).
- Кампании стоят рядом с акциями, но данные и экраны НЕ объединяем (VF-20b).
- Резерв склада по смете — при «Beauftragt», клампом, без блокировки (VF-13).
- Единая карточка сделки: статус в верхней строке, скидка между позициями и итогом, календарь под сеткой, «меняется один блок — меняются все» (DC/DF, 2026-08-25/26).
- KDS — только cafe/catering/restaurant; Tisch-QR — cafe/restaurant (VF-5).
- Генерации изображений в среде нет — только CC0/PDM с просмотром каждого кадра либо тематический плейсхолдер; у веган/вегетарианских демо в кадре нет мяса и рыбы (Pranasy).
- Демо Pranasy: ru-локаль = дословный текст PDF владельца, рецепты не «веганизируем», маркируем честно (2026-08-25).
- Корзина и quick-add продают по промо-цене (вариант A), лимит кампании клеймится на чекауте (SF-4b, 2026-08-31).
- Дил-сборки универсальны (видны всем типам), но чужие отраслевые Layout-Vorlagen скрыты; сборки обязаны отличаться композицией, а не только цветом (DL-7/DL-9).
- Ряды плиток всегда полные: дефолт листингов — «Verteilen» + авто-колонки; остаток по центру, одиночная карточка — широкая (вариант B+D); плитка-подсказка только режимом `fill`; «Alle anzeigen» только когда карточки реально скрыты (DL-11/14/15).
- Лимит акций на главной — 9; Grundpreis у акции (DL-12/13).
- Слайдеры без автопрокрутки на телефоне (DL-13.2).

### 2026-09-02 … 09-10
- AI-генерация фото отменена целиком — на витрине демо только реальные CC0/PDM (Openverse) с провенансом в `SOURCES.md`; для одежды допустимы детерминированные иллюстрации `gen_demo_garments.py` (AMP 2026-09-03, MODE 2026-09-04).
- В демо продуктового магазина нет непищевого ассортимента (туалетная бумага, бытовая химия) — замок (AMP).
- Форма карточки: выбор у объекта сильнее общего; порядок слоёв «товар/акция → категория → сайт» (DL-19 2026-09-03, STU-12j/F9).
- Шаблоны страниц: та же механика «реестр + два слоя, своё бьёт общее»; корень `/sortiment/` имеет свой ключ и НЕ наследует дефолт категорий (DL-20, DL-21 Р-2).
- Слайдеры: без автопрокрутки по умолчанию, стрелки только при наведении (hover-устройства); «Preis zuerst» — дефолт карточки акции в дил-сборках (DL-16).
- «Alle anzeigen» показывается только когда карточки реально скрыты (SF-5).
- Способы оплаты и Privat/Firma — на всех шести видах сделок; счёт юрлицу выпускается автоматически на чекауте; неоплаченное удержание снимается по сроку (SH-23, решения Р-1…Р-8 `order-feedback-plan-2026-09-03.md §9`).
- Студия: левая рейка убрана целиком, одна колонка справа без вкладок, всё через клик по канве/«+»/«Seite ▾»; глобальный дизайн и «Start» — на экране кабинета «Design des Shops», Студия эти ключи не пишет; `apply_look` меняет только кожу, композицию задаёт сборка (STU-12, 2026-09-08/09).
- Тумблер Einfach|Experte панели блока Студии снесён (STU-16c); дубль-радио «Header style» снят.
- Контрол «Darstellung der Gruppen» убран: «сетка или лента» — одна ось вывода, легаси `promo_layout` только читается (LAY-7c).
- Редактор работает в одном языке контента (язык канвы), без удвоения формы суффиксами локалей (LAY-6).
- Экран `/dashboard/site/pages/` снесён (302); `/dashboard/design/` оставлен осознанно (STU-5).
- Сначала варианты дизайна на утверждение (канвас), потом код — для переработок UI (запрос 2026-09-03, STU).
- Кастомный 404 витрины — standalone намеренно (SF-3, подтверждено STU-7).

### 2026-09-09 … 10-16
- Полная унификация видов вывода: три ортогональные оси — композиция · сетка · форма карточки; один реестр + гейт доступности; новый «вид» не заводить отдельным ключом (LAY, Р-1…Р-5, 2026-09-09).
- Пагинация — только каталог и `/aktionen/`; группы/секции не пагинируются (STU-18f, 2026-09-10).
- Тип акции ведётся одним параметром витрины `?gruppe=` (встроенные — с префиксом `sys:`); второй параметр не вводить (PT, 2026-10-01).
- Страница = упорядоченный список блоков; блок «Liste» = источник × фильтр × сортировка × лимит × вид; основной список — блок «Hauptliste»; списочные секции главной = блоки «Liste» с закреплённым источником (LB Р-1…Р-4, Р-6 → (б), 2026-10-02/04).
- Демо-фото — только реальные CC0-кадры фонда или тематические плейсхолдеры (инвариант AMP, подтверждён STU-18h и DCC).
- T-8 Р-1: «отложить» = старый движок Reservation · Р-2: купон да, онлайн-чекаут купон НЕ принимает · Р-3: поддомен сразу, каталог города — после подтверждения почты · Р-4: не второй кабинет, а пресет витрины + мобильный поток в том же кабинете · Р-5: бесплатно до 5 активных акций, дальше «свяжитесь с нами» · Р-6: пилот — весь Solingen (2026-10-09).
- ИИ: A-1 владельцу сильнейшая модель, поиск — после замеров · A-2 Telegram не главный вход, а вариант наравне с вебом · A-3 ИИ бесплатно в пилоте с мягким лимитом · всё работает и без ИИ, результаты только из БД (2026-10-09).
- Остальной функционал = ступени роста той же платформы (0 Aktion · 1 Sichtbar · 2 Website · 3 Verkaufen · 4 Betrieb); новые крупные модули на время пилота не начинаем (2026-10-09).
- Каталог города: О-1 единая система категорий платформы (15 разделов + признаки отдельной осью) · О-2 операторы порталов — модель B · О-3 пилот ведём сами · О-4 «срочное первым»; мерило успеха — визиты и выдачи, а не онлайн-оборот (2026-10-09).
- Демо-бизнесы не попадают в настоящие порталы (`Tenant.is_demo`, `show_demo` только на превью); превью-портал целиком noindex; фид и llms.txt — без демо всегда (T-8.15, T-8.26 п.2).
- Sitemap портала: страницы бизнесов входят, страницы предложений — нет (T-8.8 Р-1 A).
- Жалобы «Melden»: три разных голоса скрывают листинг (T-8.6).
- Подписка жителя «Folgen»: Double-Opt-In без pending-строк, пустых писем нет, кнопка — ссылка (кэш) (T-8.7, Р-1…Р-8).
- Хотфиксы прямо в `main` запрещены; каждый пункт — план → замки → ревью → зелёный CI → FF (2026-10-16).

### 2026-10-16 … 11-01
- ИИ в проде — только маршруты ЕС (Bedrock EU, Azure EU, Mistral); прямые Anthropic/OpenAI — только dev с демо-данными (Р-E, AI-0, 2026-10-16/17).
- ИИ никогда не заполняет цены, скидки и сроки и ничего не отправляет сам; автоскрытия по ИИ или правилам нет, машинная пометка — не голос (Д1/Д2, В-1…В-6, 2026-10-17).
- Text-Check только советует, ничего не блокирует (Д2, 2026-10-17).
- Google: данные идут только от нас в Google; импорт постов снят (Д3, 2026-10-18).
- Mystery-акция не трогает цену товара; исчерпанная по лимиту акция уходит с витрины, её страница остаётся (SF-9/SF-10, 2026-10-18).
- Демо на витрине — только плашка «Demo-Geschäft»; оплату и письма не трогаем (В1, 2026-10-16).
- Карты — бесплатные тайлы OpenFreeMap; htmx и карты отдаются со своего сервера (В3; KA-12 Волна 0).
- Аналитика портала — только агрегаты без персональных данных (В5).
- Чат Telegram становится владельцем бизнеса только после подтверждения почты; до 5 бизнесов на чат (H-5b, 2026-10-20).
- Свой бот не рвёт связь с общим; подключать и отключать бота — только владелец; `/eigener_bot` — только инструкция (T-8.29/T-8.31/H-7).
- Mini App — только лёгкие экраны; полный кабинет в Telegram тоже лёгкий, остальное «nur per E-Mail» (Р-5, T-8.30).
- Пакеты «Paket × Richtung», жёсткий гейт готовности, бесплатно только тест (5 акций / 50 товаров / немного ИИ), затем 19 или 29 €; склад и финансы — Profi-модули; тарифы скрыты до объявления (T-8.32, 2026-10-22).
- Каталог города — всегда; тумблера у бизнеса нет, снять может только оператор (пилот-батч A, 2026-10-23).
- Финансовые выгрузки — роль admin; CSV продаж — только владелец (батч A, E2.2).
- Возврат денег отменой — только владелец или бухгалтер (2026-10-24).
- IBAN Vorkasse меняет только владелец (KA-H2).
- Оплата «на месте» считается оплаченной при исполнении; выручка — при исполнении (X1, MC-D1, 2026-10-23).
- Онлайн-оплата держит место 24 ч; неподтверждённый резерв держит товар 4 ч (батч B, E6.6).
- Счета из сделок — Bruttomethode (`finance/0018`); старые остаются net.
- Право «Kontaktdaten sehen» по умолчанию у всей команды; у сотрудника по умолчанию нет Finanzen, «Abläufe ändern», Domains, Funktionen (E6.7f/g, 2026-10-25).
- Ролевые префиксы и декораторы сняты — права только через `view_perms` плюс пол владельца (E6.7c).
- Цены и ценообразующие правила номеров — только owner/admin (Z-3/Z-4).
- После ≥2 неявок онлайн-запись только с депозитом; без Stripe — просьба позвонить (E6.4c).
- Блог выключен по умолчанию; учёт товаров (Kategorien/Lager/Einkauf/Import) только у направления «Waren»; booking не у отеля (KA-12 W2).
- Кабинет владеет всеми настройками страниц («Seitenvorlage»); Студия — только порядок и видимость блоков, тексты, «＋»; пилюли «Nur hier» и `studio_scope` снесены (STU-19, 2026-11-01).
- Детали кабинета — только с префиксом `ui-`; тон статуса по роли; SVG в меню; тёмная тема кабинета — позже (E9, 2026-10-30).
- Один переключатель языка ввода — выпадашка с кодом; у ваучеров переводов нет (E9.10).
- MCP-сервер — свой слой без SDK; действия из ассистента только через письмо человеку со ссылкой (T-8.10f).
- Касса/TSE и чаевые — не в пилоте (KA-11 В-6).
- Программа KA: деньги, данные, закон — сразу хотфиксом; остальное — после плана (2026-10-22).

### 2026-10-31 … 11-11
- ИИ: один вход (плавающая ✨), «объект × действие», правила — основа, Claude — для формулировок; факты проверяет сервер; запретный список; массовые ≤ 50; названия магазина в промпт можно, данные клиентов — никогда; в проде Claude через AWS Bedrock EU; у ИИ-кнопок плашка «ИИ работает в США» (AIS §5.7, ai-strategy В-1…В-5, 2026-11-05/06).
- Мастер v4 включён по умолчанию; первый шаг «Was haben Sie schon?»; сайт скрыт до кнопки «Website veröffentlichen» (W4-1/W4-6, 2026-11-05/06).
- Zurücklegen/купон гейтом готовности НЕ закрываются (O-1, 2026-11-06); при доставке обязателен способ оплаты кроме «на месте» (2026-11-05).
- Регистрация: обязательный вопрос «Was verkaufen Sie?», ниша — по желанию; о доставке не спрашивает, чип «Online-Shop» слит с «Waren verkaufen» (FB-26a, SHP, 2026-11-08/09).
- Модули правятся экраном направлений, большого Save нет; акции у отеля/туров/ремесла — пункт меню только с первой акции (M-1, 2026-11-05).
- Доставка v1 — только Германия; один самовывоз со списком адресов (SHP, 2026-11-09).
- Шаблоны страниц — только в «Website › Seitenvorlagen» (Sortiment/Aktionen → 302) (FB-блок А, 2026-11-07).
- Меню сайта: виды A/B/C/D/G, подвал, до 3 уровней; один экран «Website › Menü» (FB-23, 2026-11-07).
- Текстовые страницы — один плоский список «Website › Seiten»; правит только владелец (право `seiten.edit` выдаётся в Team); один тип «Seite» в Studio; под правовыми страницами блоков нет, правовые не удаляются (M21.10/M21.11, 2026-11-11).
- Кабинет: одна шторка `<dialog>` на весь кабинет; списки — строки без редактируемых полей, создание — шторкой, правка — страницей с вкладками (UX-D Р-1…Р-5, 2026-11-03).
- Услуги: общей «стандартной» отмены нет; предоплату правит только право `preise.edit` (D2, 2026-11-03).
- Право «Hausordnung bearbeiten» отдельно от Kurtaxe (owner+admin по умолчанию) (D6.8).
- Портал и витрины — на всю ширину по умолчанию; бренд портала «<Город>Markt»; «Deal des Tages» органический, платное и показанное не повторяются, честные пороги блоков (PH-9/11, M21.5, 2026-11-06…10).
- Быстрая регистрация создаёт поддомен сразу (до подтверждения почты) — отступление от рекомендации аудита, защита лимитами (SEC B-H1, 2026-11-02).
- Рассылка магазина: без выбора тем = все темы; страница настроек подписчика только сужает (NT, 2026-11-10).
- Существующие коды ваучеров → combinable (`loyalty/0009`, `CLAUDE.md` §3 «Миграции к деплою»).

