# W9: Settings-хаб — «базовые + по типам в табах» + Team & Zugriff + Integrationen

Дата 2026-08-05. Семейство W-v3; предшественники W7/W-CL/W8 ✅ (все в main).
Цель — формулировка владельца: «выделить базовые настройки, а дополнительные по
типам разделить и поместить в табы». Целевая структура — `cabinet-unification-plan
§2.3`; разведка (полный инвентарь вьюх/save-механик/рисков/замков) — фоновый
агент 2026-08-05, ключевые факты вшиты сюда.

## §0. Принципы исполнения

- **Запрещённый паттерн:** `siteconfig.normalize(полный конфиг)` в save-путях
  настроек. Два нарушителя (seo_settings_view, finder_settings) чинятся ДО их
  переноса в хаб (W9-3).
- **Инвариант W0:** скрытие полей — CSS; при разрезании формы `settings_view`
  на табы — сентинелы `sec_*` (эталон `_payment_fields.html`) либо per-таб
  `update_fields`.
- **Мастер онбординга** делит партиалы/хелперы с настройками
  (`_payment_fields`/`_payment_connect`, `save_payment_settings`,
  `save_languages`, семантика legal_docs) и держит `tile_url` по именам маршрутов
  — имена полей/сентинелов/URL НЕ переименовывать.
- Новые nav_key (`ablaeufe`, `team`) обязаны попасть в `nav_registry` (иначе
  красный инвариант-замок W8). Новые лейблы — msgid × 5 .po.

## §1. Целевые табы хаба Einstellungen

Базовые (всегда): **Mein Geschäft** (контакты/адрес/часы-слитые/логотип/presence)
· **Sprachen** (витрина + язык кабинета рядом) · **Recht & Steuern** (LegalDoc —
единственный редактор; плоские поля Tenant → read-only плашка; vat/small_business)
· **Zahlung & Lieferung** (существующий эталон + статус Stripe-Connect;
billing/payments → read-only статус).

По типам (гейт модулей): **Benachrichtigungen & Kanäle** (матрица с 3 пресетами +
owner-каналы + Telegram-бот блоком; publishing/OTA — ссылки) · **Abläufe** (НОВЫЙ
агрегатор: колонки доски + имена статусов + правила переходов + свои статусы, с
селектором kind; эндпоинты переиспользуются as-is через `next=`) ·
**Website & Domains** (домены + SEO-блок + мостики в Studio) · **Abo & Rechnung**
(billing, только лейбл). Плюс **Integrationen** (Р-3: таб со СТАТУСАМИ
подключений — Stripe 4 состояния, TelegramBot, owner_chat_id, publishing.Channel,
stays.Channel c last_status, CustomDomain.status, e-mail-режим; данные уже
вычисляются — вкладка read-only) и **Team & Zugriff** (Р-7).

Erweitert: Funktionen · Medien · Zusatzleistungen (CRUD — как есть) · Finder
(переезд из marketing) · Hilfe.

## §2. Team & Zugriff — вывод разведки

Модель готова: `core.Membership` (OneToOne User, role owner/admin/staff),
`roles.py`, fail-closed middleware, User — per-tenant схема, allauth login/reset
работают (саморегистрация закрыта), magic-link паттерн готов (Redis, образец
`apps/account/auth.py`), AuditEvent для журнала. **Миграция НЕ нужна**:
приглашение = Redis-токен → создание User+Membership (или User с unusable
password + штатный password-reset).

**Критично:** роль сегодня ничего не гейтит — staff получил бы права владельца.
W9-10 обязан включить per-роль-гейт минимум на billing/Stripe-Connect/правовые
тексты/Team (is_owner), иначе «пригласить сотрудника» = «отдать бизнес».
Замки: «staff не открывает billing», «нельзя удалить последнее owner-членство»,
«инвайт-токен одноразовый/TTL».

## §3. Инкременты (порядок безопасности; каждый — батч с локальным гейтом)

- **W9-1 каркас:** перегруппировка ENTRIES settings-хаба под целевой порядок +
  общий партиал `_settings_page.html` (шапка+messages+Save) вместо 8 копий.
  Ноль save-путей. Навигационные замки обновляются осознанно.
- **W9-2 Zahlung & Lieferung:** статус-блок Connect в таб; billing/payments →
  read-only; лейбл «Abo & Rechnung».
- **W9-3 предохранитель:** seo_settings_view + finder_settings → targeted-write
  (без normalize полного конфига) + замки соседних ключей.
- **W9-4 Website & Domains:** таб (домены as-is + SEO-блок + мостики Studio).
- **W9-5 Recht & Steuern:** LegalDoc — единственный редактор, плоские поля
  read-only, налоговые поля сюда (самый рискованный перенос — после обкатки).
- **W9-6 Mein Geschäft:** разрез settings_view (сентинелы/update_fields per-таб;
  часы структурные+текст слиты).
- **W9-7 Benachrichtigungen & Kanäle:** пресеты Alles/Nur Wichtiges/Eigene +
  Telegram-бот блоком; owner_digest сюда.
- **W9-8 Abläufe:** экран-агрегатор (nav "ablaeufe" в реестр), переиспользование
  4 писателей через next=; ссылки «⚙️ Abläufe» на операционных страницах
  (включая Verkäufe); копия формы имен статусов из order_list + её ветка в
  orders:order-settings — удаляются; мёртвый контекст stays чинится.
- **W9-9 Integrationen-таб (Р-3):** статусы §1; якорь integrations уходит из
  сайдбара → карта якорей/замки согласованно.
- **W9-10 Team & Zugriff (Р-7):** экран членств + роль + отзыв + инвайт
  (Redis-токен) + per-роль-гейты + AuditEvent. Последним — цена ошибки высшая.
- **W9-11 Erweitert:** Finder из marketing-хаба сюда; site_seo получает hub_tabs.

## §4. Статус
- **W9-1a ✅** (2026-08-05): реестр перегруппирован «базовые + по типам»; Finder →
  Einstellungen/Erweitert; 4 msgid × 5 .po; замки обновлены осознанно.
- **W9-1b ✅**: единый партиал `_settings_messages.html` вместо копипасты в 9 шаблонах.
- **W9-2 ✅ прежней работой**: статус Stripe-Connect уже в табе Zahlung & Lieferung
  (`_payment_connect.html` включён в payment_settings); /dashboard/billing/payments/
  уже read-only статус+OAuth+ссылка (W7a убрал форму); лейбл «Abo & Rechnung» — W9-1a.
- **W9-3 ✅**: seo_settings_view и finder_settings — targeted-write своего узла
  (normalize_seo/normalize_finder на узел; пересборка полного конфига из save-путей
  настроек исключена) + 2 замка «соседние ключи целы».
- **W9-4 ✅**: таб «Website & Domains» (domains-экран + мостики SEO/Studio/Medien;
  site_seo получил hub_tabs — тупик закрыт; Domains из Erweitert в прямые).
- **W9-5 ✅**: «Recht & Steuern» — LegalDoc единственный редактор; налоговые
  реквизиты (vat/tax/§19/Register/V.i.S.d.P.) переехали из «Mein Geschäft» на
  правовой экран отдельной секцией со СВОИМ save (sec_steuer + update_fields);
  из BusinessSettingsForm поля изъяты целиком (один писатель; плоские правовые
  тексты редактируются только как LegalDoc-фолбэк). settings_view.update_fields
  сузился автоматически (*Meta.fields).
- **W9-6 ✅ прежней работой (W4-1)**: fieldset «Öffnungszeiten» в settings.html уже
  сводит структурные времена (oh_*) и свободный текст в один блок — делать нечего.
- **W9-7 ✅**: пресеты над матрицей клиента — «Alle Kanäle aktivieren» / «Nur E-Mail»
  (JS проставляет чекбоксы, сохранение прежнее). Отклонение от плана: флага
  «важное событие» в реестре prefs нет → пресет «Nur Wichtiges» был бы враньём,
  не делаем (кандидат при появлении флага). + read-only статус бизнес-бота
  (active_bot: @username + ссылка «Bot verwalten» → telegram-settings).
- **W9-8 ✅**: экран `/dashboard/ablaeufe/` (nav "ablaeufe" в реестре, прямой таб
  settings-хаба) — kind-селектор (order/booking/stay по активным модулям) +
  панели `_status_labels_panel`/`_transition_rules_panel` + W5-панель колонок
  доски (общий билдер `_board_stage_rows`) + вход в status-manager; сохранение —
  прежние эндпоинты через next= (board_settings научился next, локальный путь).
  Легаси-копия формы статусов в order_list удалена (мостик «Abläufe»), ветка
  status_labels в orders:order-settings удалена (no-op редирект), мёртвые
  status_label_rows/transition_rows из контекста stays-календаря сняты.
  Панели booking/resources оставлены (живая настройка booking; свод — W10/W11).
- Очередь: W9-9 (Integrationen-таб) → W9-10 (Team) → W9-11 хвост (Finder
  перенесён в W9-1a, site_seo hub_tabs в W9-4 — осталась только сверка).
