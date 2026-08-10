# SM: один функционал для всех + Verkäufe по модулям (план)

Запрос владельца (2026-08-10): «Убираем переключатель Простой/Эксперт совсем,
для всех один функционал. В продажах верхний уровень — тип архетипа/модуля
(бронирования, услуги, продажи); модули проработать: какие настройки доступны
какому направлению; каждый модуль отображается в присущих ему видах —
календарь, список и/или канбан».

## SM-1. Снос режима Простой/Эксперт

История механизма: S5 (`ui_mode`/`is_simple`, тумблер) → S6b (скрытие по
архетипу) → W4-fix (тумблер в шапке) → W12 (экран «Ansicht», ось в ModuleSpec).
Теперь владелец решает: режима нет, функционал один. Сносим ЦЕЛИКОМ, как
classic_ui в волне W-CL (прецедент: normalize ДРОПАЕТ ключ, замки снимаются
осознанно).

### Карта удаления (разведано по коду, не по памяти)

**Ядро** — `apps/core/modules.py`:
- `ui_mode()`, `is_simple()`, `_simple_hidden_for_type()`,
  `simple_hidden_modules()`, `simple_hidden_labels()`;
- поля `ModuleSpec.simple_hidden` / `simple_hidden_for` + проставления у спек
  (catalog:107, analytics:316, finance:444).

**Потребители:**
- `apps/core/views.py`: POST-ветка `ui_mode` в modules_view (2818-2826),
  `ui_simple` в контексте (2890), `set_ui_mode_view` (2897), `ansicht_view`
  (3432), упоминание в комменте (3243);
- `apps/core/context.py`: `ui_simple` (349), `ui_simple_hidden` (352);
- `apps/core/dashboard.py`: гейты `simple_hidden_modules` у плиток (25) и
  виджетов (122) — показываем всем;
- `apps/core/templatetags/cabinet.py`: гейт табов хаба (57, 83) и ветка
  «Erweitert свёрнут в Простом» (72);
- `apps/catalog/views.py:52`: `ui_simple` формы товара (W2) — все табы всем;
- `apps/tenants/siteconfig.py:2257`: passthrough `ui_mode` в normalize —
  УДАЛЯЕМ: ключ у существующих тенантов выпадет при следующем сохранении
  (прецедент W-CL с classic_ui);
- `config/urls_tenant.py`: роуты `dashboard/ansicht/`, `dashboard/ui-mode/`;
- `apps/core/nav_registry.py:303`: запись «Ansicht» (уходит и из палитры Ctrl+K).

**Шаблоны:**
- `tenant/_base_dashboard.html` — тумблер Einfach/Experte из шапки;
- `tenant/settings.html` — гейт «Betrieb» (54-57): секция видна всем;
- `tenant/modules.html` — карточка «Ansicht» (14-21);
- `catalog/product_form.html` — `ui_simple`-гейты табов (55, 58-59);
- `tenant/ansicht.html` — удалить файл.

**Тесты:** `test_ui_mode.py`, `test_w12_modes.py` — удалить; правки в
test_board_settings / test_home_builder / test_presence / test_st4_home /
test_w6_theme / test_product_form_w2 / test_cabinet (orders) / test_settings /
test_onboarding_wizard / test_looks (там ui_mode — лишь пример «чужого ключа»,
заменить на другой живой ключ, например `board`).

### Что НЕ трогаем (и почему)

**Einfach/Experte в редакторе Studio** (`data-expert` в site_home.html /
_cb_row.html, UC6-10) — это НЕ гейт функционала кабинета, а свёртка продвинутых
настроек одного блока на канве («простой блок = 2 узкие строки», фидбэк
владельца). Функционал у всех одинаковый — режим лишь про плотность ленты.
Если владелец имел в виду и его — снести отдельным инкрементом (вопрос задан).

**msgid** убираемых строк остаются в .po мёртвым грузом — гейт i18n_gap
проверяет код→po, обратное направление не ломает CI. Не чистим (правка .po —
шумный дифф).

### Порядок

Один связный инкремент: ядро → потребители → шаблоны/роуты → тесты → полный
локальный гейт → push → зелёный CI → мерж. Без миграций.

## SM-2. Verkäufe: верхний уровень по модулям (анализ ДЛЯ ОБСУЖДЕНИЯ)

### Что уже есть (W10, работает в проде)

Единая страница `/dashboard/verkaeufe/` УЖЕ устроена почти как просит владелец:

| Вкладка (kind) | Модуль | Доступные виды (KIND_VIEWS) | Дефолт |
|---|---|---|---|
| Bestellungen (order) | catalog/orders | Board · Liste · Kalender (Auftragsbuch по дате выдачи) | Liste (гастро — Board/KDS) |
| Termine (booking) | booking | **Kalender** (Tagesplan+месяц) · Board · Liste | Kalender |
| Buchungen (stay) | stays | **Kalender** (Belegungsplan) · Board · Liste | Kalender |
| Aufträge (job) | jobs | Board · Liste | Board |
| Tickets (ticket) | events | Liste · Board | Liste |
| Reservierungen (reservation) | promotions | Liste · Board | Liste |

Плюс kind-агностичный вид «📆 Heute» (Anreisen/Abreisen/Im Haus/Termine/
Abholbereit/Lieferungen). Выбор вида запоминается per-kind (`sales_views`).

### Настройки по направлению (что где живёт сейчас)

| Настройка | order | booking | stay | job | ticket | reservation |
|---|---|---|---|---|---|---|
| Свои ИМЕНА статусов (FB-4) | ✅ | ✅ | ✅ | — | — | — |
| Правила ПЕРЕХОДОВ (FB-3 A) | ✅ | ✅ | ✅ | — | — | — |
| Свои НОВЫЕ статусы (FB-3 B) | ✅ | ✅ | ✅ | — | — | — |
| Колонки доски (W5: имена/порядок/скрытие) | ✅ все kind через `board` | ✅ | ✅ | ✅ | ✅ | ✅ |
| Вид по умолчанию (sales_views) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Спец: KDS/QR | ✅ | — | — | — | — | — |
| Спец: комнаты/хаускипинг | — | — | ✅ | — | — | — |

Все входы собраны на «Abläufe» (W9-8, `/dashboard/ablaeufe/`).

### Расхождения с формулировкой владельца — вопросы

1. **Вкладки появляются «с первой продажей»** (кроме primary). Альтернатива:
   вкладка на КАЖДЫЙ активный модуль сразу (пустая — с пустым состоянием
   «пока нет продаж» + CTA настроить). Что выбираем?
2. **«Heute»** — оставить первым «верхним уровнем» рядом с модулями?
3. **job/ticket/reservation без настроек статусов** — доводить их до паритета
   (имена статусов + правила переходов), или им хватает колонок доски?

## Гейт

`ruff` целиком + затронутые модули + broad-прогон apps/core+apps/tenants+
apps/catalog+apps/orders; стенд кабинета (шапка без тумблера, Funktionen без
карточки Ansicht, форма товара со всеми табами). CI → FF-мерж.
