# Сверка отложенного FB-33 (roadmap-next-sprints.md стр. 476–610), стопки 2026-11-20, 2, 3, 4, 5, 6
Сверено 2026-11-24 по рабочему дереву ветки `claude/fb33-stack-12-098ih4` (клон shallow — 98 коммитов, `git log -S` по старым правкам не работает; факты — код, тесты, build-log, fb33-next §3/§5-old.6).

Итого дел: 104 · ✅ 27 · ⏳ 57 · ❓ 17 · 🔁 3

| # | Блок | Дело | Статус | Доказательство | Класс |
|---|---|---|---|---|---|
| 4.1a | ст.4 | M3-5c: переводы USP (полоса доверия) в окне | ⏳ | `templates/tenant/_bw_usp.html` — только `_schema_usp.html`, языковых полей нет; `block_i18n.py` usp не знает | код-редактор |
| 4.1b | ст.4 | M3-5c: переводы SEO страницы в окне | ⏳ | `_bw_seo.html` без языков; `block_i18n.py` seo не знает | код-редактор |
| 4.2 | ст.4 | «Deutsch (Grundtext)» / язык бизнеса первым во «Felder» | ⏳ | только `block_i18n.py:787`; в `form_spec.py`/`_bw_formfields.html` нет `default_locale`/`first_note` | код-редактор |
| 4.3 | ст.4 | Перевод вопроса при «Trotzdem speichern» не применяется (лог) | ✅ | строки лога `window translations not applied` нет; `faq_content.py:168-171` — `explicit`/`explicit_src` ложатся поверх «(ревью M1: «Trotzdem speichern» не теряет набранное)» | — |
| 4.4 | ст.4 | У нового C-блока поля перевода сразу, позиция — при записи | ✅ | заметка о поведении, не долг — снять строку | — |
| 4.5 | ст.4 | «🌐 Übersetzen» для «Texte» + единственный `id="i18n-ai-note"` | ⏳ | кнопки во «Texte» нет; `_bw_formfields_ai.html:2,4` уже принимает `note_id` (заготовка) | код-редактор |
| 4.6 | ст.4 | Перевод формы заявки частями (>60 текстов/6000 знаков) | ⏳ | `i18n_translate.py:36,38,155` — `MAX_ITEMS=60`, `TOTAL_MAX=6000` → `BadRequest("too_large")` | код-редактор |
| 4.7 | ст.4 | Лимит `max` для меток ≤500 | ✅ | клиент берёт `maxlength` (`_i18n_translate_js.html:109`), у полей 120/60 (`_bw_formfields.html:28,35,48,58`) — условие ≤500 выполнено (одно значение — нет, 60 у вариантов события) | — |
| 4.8 | ст.4 | M4: «Speichern und öffnen» у ⚙ Студии | ⏳ | строки нет в шаблонах | решение владельца |
| 4.9 | ст.4 | M4b: снять дубли старой панели Студии | ✅ | стопка 5, fb33-next §3 «M4b ✅», `test_fb33_m4b_studio_dupes.py` | — |
| 4.10 | ст.4 | `aufbau_url` в контексте Студии — убрать | ⏳ | `apps/core/views.py:3540` `"aufbau_url": site_schema.url_for_path(`; шаблоны не читают | уборка-мёртвый-код |
| 4.11 | ст.4 | «Auf der Seite bearbeiten» → образец типа, а не объект | ⏳ | `site_schema_views.py:696-699` `preview_url = current.preview_url` | код-редактор |
| 4.12 | ст.4 | «Seitenaufbau öffnen» у баннера не на главной — голый экран | ⏳ | `_cb_row.html:196` `{% if pb_page %}{% url 'site-schema' %}` | код-редактор |
| 4.13 | ст.4 | «Grundtext» → «Ausgangstext»? | ⏳ | `project-memory.md:115` «решение владельца открыто» | решение владельца |
| 5.1a | ст.5 | M3-7: якоря `data-sf-section` у разделов детали товара | ⏳ | `product_detail.html:21,175` — только общий `product_detail`; в `sections/detail/` нет `_product_*` | код-витрина |
| 5.1b | ст.5 | M3-7: якоря у корзины | ⏳ | `cart.html` — 0 `data-sf-section` | код-витрина |
| 5.1c | ст.5 | M3-7: якоря у подтверждения | ⏳ | `confirmation.html`/`order_confirmation.html` — 0 | код-витрина |
| 5.1d | ст.5 | M3-7: «у подтверждения адреса Vorschau нет» | ❓ | адрес есть: `urls_tenant.py:985` `bestaetigung/vorschau/` (M2h-5), `studio_pages.py:737`; нужен стенд — видимо, не хватает только якорей | стенды-процесс |
| 5.2 | ст.5 | `allow-scripts` в кадре «Vorschau» | ⏳ | `aufbau_preview.js:140` `sandbox="allow-same-origin"` (без скриптов — рекомендация) | решение владельца |
| 5.3 | ст.5 | M2i-34: ответы на вопросы, удалённые до POST, теряются молча | ⏳ | `form_answers.py:161-168` `collect` — только текущие вопросы, без лога | код-витрина |
| 5.4 | ст.5 | KDS: расшифровка `custom_answers` на каждый поллинг, без лимита | ⏳ | `orders/views.py:132-149` — все активные, без среза | код-витрина |
| 5.5 | ст.5 | `Notification.payload` с ответами — в DSGVO-карту (ретеншн) | ⏳ | ретеншн 30 дн. есть (`notifications/tasks.py:136-151`, SEC-G7), но `dsgvo-review.md:13` — только `recipient` | данные-ПДн |
| 5.6 | ст.5 | «Name *» без sr-only «(Pflichtfeld)» | ⏳ | `storefront/cart.html:129` `{% trans "Name" %} *</label>` | a11y |
| 5.7 | ст.5 | ЛК (konto) не гонялся стендом | ❓ | нужен вход magic-link на стенде | стенды-процесс |
| 5.8 | ст.5 | Подсказка «Felder» корзины про e-mail при онлайн-оплате | ✅ | C5, стопка 6 (`test_fb33_m2i34_c5_window.py` 1b/1d) | — |
| 5.9 | ст.5 | M4b: пустой темп «Liste» не очищается | ✅ | «принято как есть» — закрыто решением | — |
| 5.10 | ст.5 | Ссылка «Liste» блока страницы (не главной) на окно | ⏳ | `_cb_row.html:154-155` `{% if not pb_page %}` (та же причина, что 4.12) | код-редактор |
| 5.11 | ст.5 | Мёртвый JS «Liste» | ⏳ | частично снят (`SL_DATA_FIELDS`, `_save_builtin_list_data`, `data-lb-scope-btn` — нет); остался `site_home.html:2869-2870` `[data-lb-source]` | уборка-мёртвый-код |
| 5.12 | ст.5 | «Im Kabinett ändern» / «🖼 Manage slides» — старые области Студии | ⏳ | `site_home.html:313` «Manage slides»; `_stu19_summary.html:9` «Im Kabinett ändern» | уборка-мёртвый-код |
| 6.1 | ст.6 | C5: «Übernehmen» без JS 44 px | ✅ | уже отмечено (M3-9c) | — |
| 6.2 | ст.6 | C5: строка cart/form в матрицу M3-0 (`panel.json`) | ✅ | `test_fb33_m3_window_before.py:60` `("cart","form")` «стопка 8»; `golden_fb33m3/panel.json` — `cart\|form` | — |
| 6.3 | ст.6 | C5: подсказка про Stripe стендом не проверена | ❓ | нужен стенд со Stripe (тестами 1b/1d покрыто) | стенды-процесс |
| 6.4 | ст.6 | C5: строка про столик у любого бизнеса с `orders` — печатал ли QR | ❓ | вопрос владельцу | решение владельца |
| 6.5 | ст.6 | M2i-7: брошенный онлайн-заказ держит склад | ✅ | M2i-7.1 (стопка 7, `ORDERS_ABANDONED_HOURS`, `test_fb33_m2i71_abandoned.py`) | — |
| 6.6 | ст.6 | M2i-7b: остальные онлайн-оплаты требуют e-mail до оплаты | ⏳ | `booking/public_views.py:257-263` — e-mail обязателен; `_adopt_payer_email` только в `orders/payments.py:208`; fb33-next §5.2 — решение владельца | решение владельца |
| 6.7 | ст.6 | Принятый риск: непроверенный адрес из Stripe / «старейший клиент» | ⏳ | предложена отдельная задача — за владельцем | решение владельца |
| 6.8a | ст.6 | ratelimit писем | ❓ | формулировка без адреса в коде; не проверить чтением | код-витрина |
| 6.8b | ст.6 | `mark_order_paid` → False = 200 без заказа | ⏳ | `billing/webhooks.py:217-219` warning + `return` | код-витрина |
| 6.8c | ст.6 | `folio.record_online` без общей atomic | ✅ | теперь внутри `with transaction.atomic()` `orders/payments.py:361…389` (M2i-7.1) | — |
| 6.9 | ст.6 | M3-9 №1 превью «Kategorie» 404 | ✅ | M3-9a; `site_schema.py:615` `("storefront-category","slug")`; `test_fb33_m39a_links.py:39` | — |
| 6.10 | ст.6 | №2 «Team» без команды | ✅ | `page_settings.py:552-557`; `test_fb33_m39a_links.py:54` | — |
| 6.11 | ст.6 | №3 «Versand» без заказов | ✅ | `test_fb33_m39a_links.py:73,80` | — |
| 6.12 | ст.6 | №4 кнопки без JS 40 px | ✅ | уже отмечено | — |
| 6.13 | ст.6 | №5 `/p/<uuid>/` ru 390 скролл 28 px | ✅ | M3-9a `min-w-0`; `test_fb33_m39a_links.py:130` | — |
| 6.14 | ст.6 | №6 мелкие цели | ✅ | уже отмечено | — |
| 6.15 | ст.6 | №7 «Button-Lösung» в ru | ✅ | `test_fb33_m39a_links.py:109` | — |
| 6.16 | ст.6 | №8 `blocks_for(summaries=False)` combos | ✅ | `test_fb33_m39a_links.py:96` | — |
| 6.17a | ст.6 | ~80 видов блоков без окна | ⏳ | частично: M5d закрыл G1–G4 (стопки 11–12, `scripts/fb33_m5d_inventory.py`); остаток вне M5d — главная, листинги, категории (fb33-next §5.1 п.2) | код-редактор |
| 6.17b | ст.6 | Правило `__page` → `site_schema.page_row_ref` | ✅ | M5b-1 (стопка 9, `test_fb33_m5b_page_row.py`) | — |
| 6.18a | ст.6 | Защита от одновременного деплоя и пересева | ✅ | M3-9b `ops_lock`/`run_locked` (`test_ops_lock.py`) | — |
| 6.18b | ст.6 | Автоочистка образов Docker в `deploy.sh` | ✅ | M3-9b | — |
| 6.18c | ст.6 | Лишний лог и запрос на повтор вебхука | ⏳ | fb33-next §5-old.6: «`catch_up` при «same»» — не исправлено | код-витрина |
| 3.1 | ст.3 | Путаница «Kompakt mit Foto» (форма) и «Kompakte Zeilen» (вид) | ⏳ | `card_forms.py:34` «Compact with photo» vs `siteconfig.py:4807` `"rows": _("Kompakte Zeilen")` | решение владельца |
| 3.2 | ст.3 | Форма «Nur Text» (строка без фото) | ⏳ | в `card_forms.CARD_FORMS` нет; макет за владельцем | решение владельца |
| 3.3 | ст.3 | Мёртвые msgid «Kompakte Zeile», «Preis-Etikett» ×5 | ⏳ | `locale/ru/LC_MESSAGES/django.po:12930,21718`; в коде не используются | уборка-мёртвый-код |
| 3.4 | ст.3 | Форма события/тура перезаписывает ключи `details` | ⏳ | в `apps/events/views.py` нет отпечатка `details` | код-редактор |
| 3.5 | ст.3 | «Überschrift» блока FAQ в окне | ⏳ | `_bw_faq.html` без поля заголовка; `section_titles` черновик не держит | код-редактор |
| 3.6 | ст.3 | Переводы своих вопросов объекта в окне | ⏳ | `_bw_faq.html:45` «Übersetzungen ändern Sie im Formular des Angebots.» | код-редактор |
| 3.7 | ст.3 | `aufbau_draft.info` не показывает конфликт своих вопросов | ⏳ | `aufbau_draft.py:772-777` — нет `ofaq` в `conflict` | код-редактор |
| 3.8 | ст.3 | Ссылки на формы на общем хосте — первые 8 без поиска | ⏳ | `object_faq.py:645` `LINKS_MAX = 8` | код-редактор |
| 3.9 | ст.3 | Общий хост: «Eigene Fragen jeder Seite» без правки списка | ❓ | `object_faq.py:1023`; поведение — стендом | код-редактор |
| 3.10 | ст.3 | Ось «Breite der Seite» на одну страницу | ⏳ | `_schema_settings.html:58` «wie Design: {{ value }}» | код-редактор |
| 3.11 | ст.3 | Виды мест «Katalog»/«Seite» и «Wo zeigen» у слайдера | ⏳ | `window_banner.py:6-7` «только когда в блоке ОДИН баннер (у слайдера — ссылка …)» | код-редактор |
| 3.12 | ст.3 | Снимок `show_on` общий — «Abbrechen» вернёт места второго баннер-блока | ⏳ | `aufbau_draft.py:890-892` копия всей части `show_on` | код-редактор |
| 3.13 | ст.3 | «N Seiten» считает и текущий блок | ❓ | `window_banner.py:135`; нужен сценарий/стенд | код-редактор |
| 3.14 | ст.3 | Тексты итога корзины (Überschrift / Zeile für die Summe / Hinweis) | ⏳ | строк «Zeile für die Summe» нет в коде | код-редактор |
| 3.15 | ст.3 | Свой вид товаров одной категории в окне (плитки) | ❓ | строка наследования есть (`page_window.py:293-316`, M3-6), плиток вида у ★ категории — проверить стендом | код-редактор |
| 3.16 | ст.3 | `category_page_style` виден в «Seite» у category@… | ❓ | `page_window.py:301` читает; показ — стендом | код-редактор |
| 3.17 | ст.3 | Подтвердить текст плашки «Kaufen» | ❓ | вопрос владельцу | решение владельца |
| 3.18 | ст.3 | `lock_timeout` для `migrate_schemas` | ⏳ | Postgres `lock_timeout` не ставится; `run_locked.py:48` — таймаут ops-блокировки, не БД | ops-сервер |
| 3.19 | ст.3 | database-reviewer по catalog/0046, stays/0049 | ❓ | отчёта в build-log/skill-feedback не найдено; замки `test_fb33_m2b2b_migrations.py` есть | стенды-процесс |
| 2.1 | ст.2 | Подписи форм карточек по M0-2 | ✅ | M3-4b (стопка 3, `test_fb33_m3_4b_card_labels.py`) | — |
| 2.2 | ст.2 | Форма «Nur Text» | 🔁 | = 3.2 | — |
| 2.3 | ст.2 | Явный «Standard» поверх формы из Design | ⏳ | `block_card.py:143-147` первая плитка = «как в Design», value "" | код-редактор |
| 2.4 | ст.2 | Значок ✓ на выбранной плитке | ⏳ | `_view_tiles.html:6,8` — выбор только рамкой | код-редактор |
| 2.5 | ст.2 | Асимметрия смены вида (Liste сбрасывает форму, встроенный — нет) | ❓ | нужен сценарий | код-редактор |
| 2.6 | ст.2 | ★-строка каталога (форма), related/upsell, «Karte (bei Kacheln)» категорий | ❓ | «bei Kacheln» в коде нет; ★ каталога/related — стендом | код-редактор |
| 2.7 | ст.2 | Мёртвая ветка `f.name == "card"` | ⏳ | `_schema_list_field.html:3,14` | уборка-мёртвый-код |
| 2.8 | ст.2 | a11y: две группы радио одного имени | ❓ | нужен прогон a11y-architect | a11y |
| 2.9 | ст.2 | «Wie anordnen» без JS — две формы, набранное теряется | ⏳ | `_block_window.html:8` подсказка «Erst „Übernehmen“ …» | код-редактор |
| 2.10 | ст.2 | После отказа (небезопасная ссылка) без JS введённое не возвращается | ❓ | стендом без JS | код-редактор |
| 2.11 | ст.2 | M3-5c переводы текстов блока в окне | ✅ | стопка 4 (`test_fb33_m35c_*`) | — |
| 2.12 | ст.2 | Переводы вопросов FAQ и подписей плашек | ✅ | `block_i18n.py:17`, `:770-775` (`label.<key>`, часть `tiles`) | — |
| 2.13 | ст.2 | M3-5b «Überschrift» FAQ в окне | 🔁 | = 3.5 | — |
| 2.14 | ст.2 | Канва Студии не шлёт `faq_base` | ❓ | форма Студии шлёт (`_section_fields.html:50`, `views.py:3031`); живой кадр канвы — стендом | код-редактор |
| 2.15 | ст.2 | Контраст `text-amber-600` | ⏳ | `sections/_hero_tiles.html:11`, `_hero_widget.html` | a11y |
| 2.16 | ст.2 | Стенд `fb33_m3_window_stand.py`: `&tab=wie`, ожидание ответа | ✅ | `fb33_m3_window_stand.py:351,355-357` `expect_response` | — |
| 1.1 | ст.11-20 | Снять позиционный `legacy_event_i18n` после `form_i18n_realign` (до 2026-12-15) | ⏳ | `siteconfig.py:5688`, `form_spec.py:848`, `jobs/views.py:195`, `demo_i18n.py:289-290` | ops-сервер |
| 1.2 | ст.11-20 | M2i-5c «Übersetzen» во «Felder» | ✅ | стопка 4 (`test_fb33_m2i5c_translate.py`) | — |
| 1.3a | ст.11-20 | Перевод закреплённых подписей («What do you need?», «Name») | ⏳ | `_anfrage_form.html:10` хардкод `{% trans "What do you need?" %}` | код-витрина |
| 1.3b | ст.11-20 | Полоса главной: textarea однострочно, choice/bool не рисует | ⏳ | `sections/_anfrage.html:41` `type=number/date/text` | код-витрина |
| 1.3c | ст.11-20 | Новый вопрос — поля перевода только после «Übernehmen» | ❓ | описание поведения; стендом | код-редактор |
| 1.4 | ст.11-20 | `role=status` сброшенного перевода | ✅ | M3-5a: `_bw_formfields.html:12` `role="status" data-form-status`, build-log 24422-24423 | — |
| 1.5 | ст.11-20 | Видимый фокус `<summary>` FAQ | ⏳ | `sections/_faq.html:56`, `_faq_own.html:50` — без `focus-visible` | a11y |
| 1.6a | ст.11-20 | Старый конструктор подписывает виды FAQ по `SECTION_STYLE_LABELS` | ⏳ | `siteconfig.py:4766` «Offene Liste»; `site_home.html` не знает `faq_views` | уборка-мёртвый-код |
| 1.6b | ст.11-20 | Свой заголовок блока FAQ | 🔁 | = 3.5 | — |
| 1.6c | ст.11-20 | «Erste Frage geöffnet» | ⏳ | строки нет в коде | код-редактор |
| 1.7 | ст.11-20 | Новые виды Team/Galerie (M0-9), «Fotos zeigen», «Abstand» | ⏳ | `_style_thumb.html` team/gallery — прежние ключи | решение владельца |
| 1.8 | ст.11-20 | M3-3a плитки вида у about/process/cta/testimonials/trust/reviews/contact | ⏳ | `_style_thumb.html` — `src` только card/family/faq/gallery/team | код-редактор |
| 1.9 | ст.11-20 | M3-3c одна группа «Darstellung» | ⏳ | две оси: `_schema_list_field.html:3` поле `out` отдельно от вида | код-редактор |
| 1.10 | ст.11-20 | Подсказка «Regale» у «Liste» source=categories | ⏳ | `block_views.py:173-178` — только секция `categories` и каталог | код-редактор |
| 1.11 | ст.11-20 | `_schema_catalog_view.html`: рамка `border-gray-200`, устаревший текст | ⏳ | `_schema_catalog_view.html:12,21` | a11y |
| 1.12 | ст.11-20 | `media_registry` не учитывает фото блоков | ⏳ | в `media_registry.py` нет `page_blocks`/`INACTIVE_FIELDS` (условное — при сборке мусора) | уборка-мёртвый-код |
| 1.13 | ст.11-20 | Плитки вида в две колонки (макет — три) | ⏳ | `_view_tiles.html:4` `grid-cols-2` | код-редактор |

## ✅, не отмеченные в roadmap
4.3, 4.4 (заметка), 4.7, 4.9, 5.8, 5.9 (принято), 6.2, 6.5, 6.8c, 6.9, 6.10, 6.11, 6.13, 6.15, 6.16, 6.17b, 6.18a, 6.18b, 2.1, 2.11, 2.12, 2.16, 1.2, 1.4 (24 шт.)
