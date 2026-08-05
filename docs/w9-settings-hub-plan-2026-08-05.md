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
- W9-1 … W9-11 — очередь; статусы вести здесь + build-log.
