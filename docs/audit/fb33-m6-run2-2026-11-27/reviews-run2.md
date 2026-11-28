# architect (прогон 2) — 19 находок: CRITICAL 1, HIGH 4. Оценка: три состояния одного поля и один писатель — верная основа; «читатели не меняются» кодом не подтверждается; до кода нужны правки 1–5.
1 CRITICAL проекция «свой виртуальный хост» идёт через normalize, тот режет хосты по алфавиту (siteconfig.py:1985-2003): у сайта у потолка хост редактора выпадает → редактор пусто → «Speichern» пишет пустую структуру; object_hosts_full (aufbau_draft.py:1198-1210) откажет A2 — test_m6_projection_survives_full_host_caps
2 HIGH проекция в raw_config, а товар/категория читают preview_raw напрямую (promotions/public_views.py:2438,1628; context.py:332) — test_m6_no_preview_raw_bypass
3 HIGH commit пишет весь конфиг locked.site_config=normalize(config) (aufbau_draft.py:1548-1549; store_items :1457; apply_many :1547) → проекция утечёт в site_config и на ключи ТИПА — test_m6_object_commit_leaves_site_config_equal_except
4 HIGH обходы видят мёртвый старый хост: except→tenant.site_config в тегах (siteui.py:370,543,565,599,635,658,1605), object_blocks (:628-645), _raw(obj) без request 5 раз на деталь (events/public_views.py:353-409) → состояние с экземпляра; функции сами возвращают пусто при v — test_m6_marked_object_ignores_legacy_without_projection
5 HIGH превью ОБЩЕГО типа берёт первый объект по pk (site_schema.py:111) — если у него своя, превью врёт; ?tpl=; черновик X на адресе Y — test_m6_type_preview_uses_inheriting_sample
6 MED normalize зависит от ключа хоста (siteconfig.py:1708-1713,1766-1792): строки осей под <kind>:<hex> срежутся — roundtrip-замок
7 MED кандидат до 60 блоков, normalize режет до 30 (siteconfig.py:2108) → отказ, не обрезка
8 MED settings «всё, кроме…»: ключи по умолчанию отсутствуют в копии → поздняя общая правка протечёт → материализовать каждый ключ — test_m6_copy_materializes_every_key
9 MED i18n в структуре позиционный; обходчики через write без realign → хранить по id блока
10 MED --undo и {"v":1} без src; клон серии увозит src
11 MED откат кода: старый код читает черновик новой формы → новый ключ сессии для черновиков — test_m6_new_drafts_use_new_session_key
12 MED новый код пишет старое хранилище для {} (_pin_own_categories page_settings.py:837-847; восстановление версии views.py:2583); новая категория подхватит мёртвый catalog:<slug> → новые объекты рождаются {"v":1} (Python-default), db_default={} для старого web — test_m6_new_object_born_inherit, test_m6_slug_reuse_ignores_dead_host
13 MED группа: «у наследующей строки нет» противоречит сбросу (siteui.py:568) → строку не удалять — test_m6_group_reset_keeps_row
14 MED объект, пропущенный переносом (расхождение подписи), при A2 копируется тем же candidate → предупреждение — test_m6_a2_on_skipped_object_warns
15 MED перенос без блокировки Tenant/сверки хэша при поднятом web
16 MED срезы: S8 без object_structure.py; сквозные замки не в том срезе; S1 широк
17 MED сторож «до» только golden_fb31p5 (5 видов) → добавить golden_fb3016, golden_fb31p3; битый i18n структуры гасит переводы страницы
18 LOW охрана save: отложенные поля, исчезнувшая строка
19 LOW список обходчиков руками, page_blocks трогают 36 модулей → замок от grep
# database (прогон 2) — 19 находок, HIGH 2. Подтверждено: номера миграций; ADD COLUMN jsonb DEFAULT '{}' NOT NULL на PG16 без переписи; охрана save по образцу Tenant.save (tenants/models.py:447-455) приёмники не ломает; путей «объект→Tenant» нет.
1 HIGH §3.3 несколько AddField на разные таблицы в одной миграции = несколько ACCESS EXCLUSIVE в одной транзакции → deadlock с JOIN витрины → одна таблица на файл миграции — test_m6_migrations_one_table_each
2 HIGH §6.1 candidate() по конфигу вне блокировки, копия включает общие строки → устаревшая копия при правке общей во время переноса → сверка/рендер вне блокировки, короткая транзакция на объект: config_migration.lock (config_migration.py:47-52) → сверка config_hash → блокировка объекта → повторная проверка → update — test_m6_migrate_rechecks_config_and_object_under_lock
3 MED lock_timeout не RunSQL в миграции, а PGOPTIONS="-c lock_timeout=3000" у шагов [6b] deploy.sh — test_deploy_sh_tenant_migrate_has_lock_timeout
4 MED deploy.sh:206-214: после сбоя один последовательный проход по всем схемам, второй отказ — exit до [7]; таймаут 2–3 с
5 MED перенос «без отличий» пишет {"v":1} без src → --undo не отличит от сброса владельца → {"v":1,"src":"migrate"} — test_m6_migrate_undo_restores_inherit_marked
6 MED src:"migrate" уезжает в клон серии (events/services.py:530-537) и наследника акции → срезать src — test_m6_clone_drops_migrate_marker
7 MED откат кода: старый web пишет page_override/хосты объектам с v → теряются → строка в --residue + предупреждение — test_m6_residue_reports_legacy_edits_on_marked
8 MED _pin_own_categories (page_settings.py:837-847) и materialize_page_axes после выката создают catalog:<slug> категориям с {}; мёртвые хосты занимают потолок 120 → писать через write; в потолке не считать хосты объектов с v — test_m6_pin_writes_structure_not_host, test_m6_dead_hosts_do_not_count_in_cap
9 MED кандидаты all_objects, а хост категории по слагу, слаг при мягком удалении освобождается (catalog/forms.py:165-178) → категории только живые; мягко удалённые — в отчёт, не переносить (restore() никто не зовёт) — test_m6_migrate_category_slug_reuse_goes_to_alive
10 MED state(ref) по pk в списках = N+1 → states(kind,pks) — test_m6_page_picker_query_budget
11 MED bind — отдельное чтение по pk на детальной → брать с экземпляра, бюджет «+0» — test_m6_detail_query_budget
12 MED TOAST разворачивается без defer → defer("structure") в массовых читателях в S2; обосновать потолок — test_m6_bulk_readers_defer_structure
13 MED поля стопки 19 в 18 — ок по БД, но миксин меняет save() у 4 моделей → замок по всем наследникам — test_m6_full_save_keeps_structure[12 моделей]
14 MED охрана save с update_fields: сохранение жёстко удалённой строки → DatabaseError; клон pk=None без _state.adding — test_m6_save_of_deleted_row_is_handled, test_m6_clone_requires_state_adding
15 MED порядок Tenant→объект для Category/Promotion/PromoGroupPage — AST-замок; get_or_create группы только в write — test_m6_lock_order_tenant_then_object, test_m6_group_page_create_race
16 LOW шаг [8] без run_locked — test_deploy_sh_migrate_structures_locked
17 LOW update не шлёт post_save; сегодня _commit_object save(update_fields=[…, updated_at]) «sitemap, портал» (aufbau_draft.py:1624-1626) — test_m6_user_write_portal_lastmod
18 LOW индексов нет, порог пересмотра
19 LOW pytest: TENANT как SHARED → прогон на стенде ≥2 схем обязательным пунктом
# security (прогон 2) — 12 находок, HIGH 3. Подтверждено: один маршрут site-schema с CSRF; ассистент хосты и page_override не пишет; CS-Cart только info; rich-text в блоках нет (тексты плоские).
1 HIGH write: образец «if user is not None and not allowed» (aufbau_draft.py:1653), commit шлёт getattr(request,"user",None) (:1471) → None = отказ; системная запись — отдельный вход, белый список вызывающих; проверять ОБА права — test_m6_write_without_user_is_refused, test_m6_system_write_callers_whitelist
2 HIGH право объекта «на каждой операции» без замка: матрица op×8 видов (add/add_row/adopt/move/delete/update/pick_*/catview, setting+apply_all, revert, window_done, reset, save, force=1; site_schema_views.py:297-390); вид без маршрута права — отказ — test_m6_every_op_requires_object_right[op×kind], test_m6_force_does_not_skip_rights, test_m6_kind_without_edit_route_denies
3 HIGH подмена черновика в превью: ?aufbau=<код> без сверки со страницей (page_settings.py:1081-1086); проекция под ОБЩИЙ хост → черновик объекта A на странице B → bind только если код = объект вьюхи; ref из объекта, не из черновика — test_m6_preview_draft_of_other_object_not_projected, test_m6_write_ref_from_code_not_draft_host
4 MED «вся витрина читает raw_config» неверно: preview_raw напрямую (promotions/public_views.py:1628,2438; core/context.py:332) → проекция внутри preview_raw — test_m6_bound_views_have_single_config_reader
5 MED утечка в кэш 404: bind до Http404 → 404 по проекции в общий кэш (not_found_views.py:118, pagecache.py:115-148) → bind после проверок, storefront_404 снимает привязку — test_m6_404_after_bind_is_unprojected
6 MED валидация копии: оверлеи переводов normalize не чистит (siteconfig.py:4250-4278), потолки только в писателе окна (block_i18n.py:398-429); settings перепроверять (aufbau_draft.py:1543-1547); белый список верхних ключей — test_m6_write_validates_overlay_settings_top_keys
7 MED группа: host_for только живая группа (site_schema.py:1107-1111, первые 40 :844-849) → страница, пережившая последнюю акцию, не открывается и не сбрасывается (решение 15!) → второй источник PromoGroupPage по host; ключ не из POST; витрина без get_or_create — test_m6_orphan_group_page_resolvable_and_resettable, test_m6_public_group_never_creates_row
8 MED страница объекта по прямому коду при одном website.view: title, крошки, плашка, потери, фрагменты; _object_for отдаёт неактивные (:663); новый маршрут сброса — строка в view_perms → без права просмотра вида 404; GET сброса — право записи — test_m6_object_page_requires_view_right[page,reset-get,fragment]
9 MED команда: lock_timeout SET LOCAL в транзакции записи; try+savepoint на схему/объект; verify-render — новый запрос на рендер; без процессных кэшей; вывод без имён/ключей групп (md5); категории по слагу только живые (catalog/models.py:76-80); --schema public отказ — test_m6_migrate_schema_isolation_two_tenants, test_m6_migrate_output_has_no_business_text, test_m6_migrate_failure_does_not_poison_next_schema, test_m6_migrate_rejects_public
10 MED обход решений 10/11 у объектов {} до стопки 20: писатели site_config с website.edit шире — «Version wiederherstellen» (views.py:2578-2607), пресеты (page_presets.py:329-394), fetch add_block (views.py:2330-2337) → замок-перечень «конфиг не изменился байт-в-байт» — test_m6_no_config_writer_accepts_object_hosts[6 путей]
11 LOW размер черновика в сессии (кэш), до 10 копий — потолок — test_m6_draft_size_capped
12 LOW флаги черновика own/reset не основание записи; сброс по устаревшему черновику не стирает чужую свежую копию
# a11y (прогон 2) — 22 находки, HIGH 4
1 HIGH A→B с JS: правка в модальном окне, фон inert (aufbau.js:15-16, [data-bwin-msgs]) → текст A2 класть в область ОКНА и повторить после «Fertig» — test_m6_a2_notice_spoken_inside_window
2 HIGH в окне блока нет «для какой страницы правка»; с JS запись по change → имя страницы + подсказка A2 в шапке окна — test_m6_window_names_scope_in_state_a
3 HIGH losses(): правленый текст/перевод скопированного блока (тот же id) не в списке потерь → строка «geänderte Blöcke» (msgid, вопрос владельцу) — test_m6_losses_cover_edited_copied_blocks
4 HIGH на артбордах нет «⋯» (клавиатурная/сенсорная замена ⠿; на 390 нет ни ⠿ ни ⋯) → каждая двигаемая строка с «⋯» и в A — test_m6_every_movable_row_has_more_menu
5 MED кнопка плашки type=button без JS мертва → ссылка/GET-форма; с JS нативный <dialog> — test_m6_reset_without_js_page
6 MED страница без JS: нет «…zeigt danach wieder…» и «Wirksam erst…», порядок кнопок обратный → один партиал текста — test_m6_reset_page_and_dialog_same_text
7 MED aria-describedby окна на весь список → только первая фраза — test_m6_reset_dialog_description_short
8 MED losses: пустой список, блок без названия, 30 имён; %(names)s склейка — <li> на имя, lang, ветка «ничего не теряется» — test_m6_losses_empty_long_unnamed
9 MED отказ/таймаут сброса: aufbauFail ищет dialog.ui-bwin[open] [data-bwin-msgs] — контейнер в окне сброса, aria-disabled, итог при любом исходе — test_m6_reset_dialog_has_msgs_host
10 MED site_schema.html:47 уже есть role=status data-schema-live («Übernommen.») → одна область, один текст; смена разметки заденет 31 эталон page_nojs, не 2 — test_m6_single_live_region_single_text
11 MED отказ первой правки: текст A2 не звучит, черновик не создаётся; без права объекта — без подсказки и кнопки возврата — test_m6_no_a2_notice_on_refused_edit, test_m6_plate_readonly_without_object_right
12 MED aria-describedby у шести ⚙ — только фраза A2 отдельным id — test_m6_describedby_targets_unique
13 MED плашка A после сброса = плашка A (один партиал) — test_m6_plate_a_same_after_reset
14 MED «Reihenfolge fest» в schema-desc-<ref> + видимая подпись — test_m6_lock_and_grip_hidden_label_is_text
15 MED «nur hier» рамка = вид выбранной строки; рамки строк 1,2–1,5:1 → border-gray-500, метка+фон — test_m6_own_row_not_styled_as_selected
16 MED возврат фокуса по id schema-row-<ref> при смене хоста A→B, «＋ Block», удаление, «Verwerfen» — стенд, цель не body
17 MED липкий подвал на 844×390 и 400 % (320×256) — случаи стенда
18 MED список имён: «und N weitere», без права — текст без details, закрыт по умолчанию — test_m6_own_list_truncation_and_no_names
19 MED «Für alle Produkte 13» без единицы; метка «eigene Struktur» текстом <option> — test_m6_page_picker_marks_own_in_text
20 MED заголовок-цель фокуса на 390 (артборд A/390), один h2 с именем страницы — test_m6_focus_heading_present_in_both_states
21 LOW «Seite im Shop» у нового (без pk) и удалённого — не рисовать
22 LOW «Eigene Struktur verwerfen» vs «Verwerfen» (вопрос владельцу); крошки 24 px; ★ aria-hidden
