# Упрощение кабинета «анти-Битрикс v2» — ПОЛНОЕ ТЗ + HANDOFF (2026-07-08)

Самодостаточный документ для продолжения в НОВОЙ сессии. Читать вместе с
`docs/admin-simplification-exec-plan-2026-07-08.md` (пошаговый план S1..S7) и
`docs/admin-simplification-analysis-2026-07-08.md` (аудит + §7 решения владельца).

**Ветка разработки:** `claude/unified-order-kanban-stock-af3pl7`.
**Состояние на 2026-07-08:** S1–S4 закрыты и в `main` (без миграций, деплой НЕ нужен).
Следующий шаг — **S5** (режим Простой/Эксперт), затем **S6** (реальные архетипы, миграция).

---

## 0. Задача от владельца (дословный смысл)
Функционал платформы обширен и «похож на Битрикс». Цель — **максимально упростить**
создание/настройку/ведение бизнеса. По архетипам скрывать ненужный/отключать функционал,
чтобы админка была простой. Где можно — управлять из витрины / добавлять данные проще.
Пошаговые настройки при необходимости. **Визуал очень важен и должен быть очень простым.**
Утверждён визуальный макет (Artifact) + план S1–S7. Решения владельца:
- Режим «Простой/Эксперт» — **переключаемый на странице «Модули» (Funktionen)**, зонтик на весь кабинет.
- Длинные страницы — прятать под табами. Родственные страницы — объединять в хабы.
- Реальные архетипы — **вводить через миграцию**. Набор: **friseur/handwerker/werkstatt/events
  + оставить текущие** (добавить к существующим 10 типам, НЕ заменять). (Ответ 2026-07-08.)
- S5-дефолт режима владельцем НЕ зафиксирован явно → взят **безопасный дефолт «Эксперт»**
  (никого не ломает; «Простой» — опциональный тумблер). Если владелец захочет «Простой» из
  коробки — сменить дефолт в одном хелпере (см. §4 S5).

---

## 1. МЕХАНИКА ХАБОВ (готова, переиспользуемая) — как устроено

### 1.1 Реестр вкладок — `apps/core/templatetags/cabinet.py`
```python
HUB_TABS = { "<hub_key>": ( (url_name, label, nav_key, module_key, advanced), ... ) }
```
- **url_name** — Django url-имя под-страницы (reverse в теге).
- **label** — метка вкладки (gettext `_()`).
- **nav_key** — для подсветки активной вкладки (сравнивается с `context["nav"]`).
- **module_key** — `None` = вкладка видна всегда (под-страница core-модуля); иначе видна
  ТОЛЬКО если `modules.is_module_active(tenant, module_key)` (архетип-гейт).
- **advanced** — `True` → вкладка уходит в свёрнутый ящик **«Erweitert ▾»** (реже нужное).

Тег `{% hub_tabs "<hub>" %}` (inclusion, `takes_context`): читает `nav` из контекста,
`tenant` из `request.tenant` (fail-open, если request/tenant нет — простой тест-рендер).
Возвращает `{tabs, more_tabs, more_active}` (прямые / advanced / активна ли advanced-вкладка).

### 1.2 Партиал — `templates/tenant/_hub_tabs.html`
Рендерит tab-bar: прямые вкладки в scroll-контейнере (`overflow-x-auto`) + опциональный
`<details>` «Erweitert» СПРАВА, ВНЕ scroll-контейнера (чтобы выпадашка не обрезалась);
`<details open>` когда активна advanced-вкладка. Переиспользует существующие Tailwind-классы —
**CSS не пересобирается** при добавлении новых хабов.

### 1.3 Паттерн свода пункта сайдбара → хаб
1. У модуля(ей) `nav_items=()` (или свести к 1 якорю-пункту). **url_prefixes НЕ трогать** —
   `ModuleGatingMiddleware` продолжает гейтить пути, под-страницы доступны через табы.
2. Метка якоря — `modules.NAV_TASK_LABELS[nav_key]` (язык задач, DE).
3. В шаблон каждой под-страницы после `{% block dash_content %}` добавить `{% hub_tabs "<hub>" %}`
   и в строку `{% load i18n %}` дописать `cabinet`.
4. Тесты: свод nav_items + рендер вкладок + гейт по модулю + (для Erweitert) open-состояние.

### 1.4 Сайдбар — `templates/tenant/_base_dashboard.html`
Рендерит `nav_groups` (из `modules.grouped_active_modules`), внутри `{% for module in group.modules %}
{% for item in module.nav_items %}`. Модуль с пустыми nav_items не даёт пункта (сирот нет).
Метка — `{% nav_task_label item.nav_key %}`. Бейдж непрочитанного inbox (M22b) — на пункте
`crm:customer-list` (перенесён в S4b, т.к. inbox стал вкладкой хаба «Kunden»).

---

## 2. СДЕЛАНО — S1–S4 (всё в `main`, миграций нет)

| Инкремент | Хаб | Свод | Коммит(ы) |
|---|---|---|---|
| **S1** | **Sortiment** (catalog) | Produkte/Kategorien/Lager/Kombi/Import 5→1 | `a10da9c` |
| **S2** | **Verkäufe** (board) | Board+Bestellungen/Termine/Übernachtungen/Tickets/Aufträge 6→1; вкладки гейтятся по модулю | `cfef40e` + fix `a68c5bd` |
| **S3** | **Einstellungen** (settings) | 10→2 (Website отдельно + хаб); ящик «Erweitert»; кортеж расширен до 5 (`advanced`) | `a8cee5b` + fix `1d2c43d` |
| **S4a** | **Marketing** (promotions-якорь) | promotions×3/reviews/loyalty×2/publishing×2 + Kampagnen(из CRM) → хаб; Erweitert | `c181f58` |
| **S4b** | **Kunden** (crm-якорь) | Kontakte/Nachrichten/Telegram; бейдж непрочитанного → на «Kunden» | `050c1ee` |

**Итог сайдбара:** ~25 пунктов → ~8 (Dashboard, Sortiment, Verkäufe, Marketing, Kunden,
Einstellungen, Website, Finanzen/Abrechnung). Всё внутри — под таб-барами; вкладки скрываются
по архетипу. Проверено рендером на реальном тенанте (schema `shop`) + тестами.

### Хабы и их вкладки (текущее состояние HUB_TABS)
- **catalog:** Produkte / Kategorien / Lager / Kombi / Import (все `module_key=None`).
- **board:** Board(board) / Bestellungen(orders) / Termine(booking) / Übernachtungen(stays) /
  Tickets(events) / Aufträge(jobs) — гейт по одноимённому модулю.
- **settings:** прямые Einstellungen(settings)/Benachrichtigungen(notifications)/Rechtstexte(legal-docs)/
  Zusatzleistungen(extras); Erweitert Sprachen(languages)/Medien(media)/Domains(domains)/
  Funktionen(modules)/Hilfe(support). Все `module_key=None` (settings — core).
- **marketing:** прямые Aktionen(promotions)/Bewertungen(reviews)/Kampagnen(crm)/Gutscheine(loyalty);
  Erweitert Reservierungen(promotions)/Einlösen(promotions)/Treuepunkte(loyalty)/Kanäle(publishing)/
  Beiträge(publishing).
- **kunden:** Kontakte(crm)/Nachrichten(inbox)/Telegram(telegram).

### Файлы механики (точки изменения)
- `apps/core/templatetags/cabinet.py` — HUB_TABS + тег `hub_tabs`.
- `templates/tenant/_hub_tabs.html` — партиал tab-bar + Erweitert.
- `apps/core/modules.py` — своды `nav_items`, `NAV_TASK_LABELS`, `NAV_GROUPS`,
  `grouped_active_modules`, `is_module_active`.
- `apps/core/tests/test_hub_tabs.py` — 20+ тестов (свод/рендер/гейт/Erweitert по каждому хабу).
- `apps/core/tests/test_cabinet_nav.py` — характеризационный тест сайдбара.
- `templates/tenant/_base_dashboard.html` — рендер сайдбара + бейдж.
- Под-страницы с `{% hub_tabs %}`: каталог(5) / продажи(6) / настройки(9) / marketing(9) / kunden(3).

### ⚠️ Известное ограничение (краевое сиротство) — кандидат на полиш «группа=хаб»
Хаб-якорь сидит на конкретном модуле (Marketing→promotions, Kunden→crm). Если якорный
модуль ВЫКЛЮЧЕН, а зависимая вкладка активна (напр. promotions off, reviews on) — пункт-хаб
исчезает из сайдбара, а страница доступна только по URL. Редкий случай (осознанное
выключение). Чистое устранение — механика «группа=хаб» в `grouped_active_modules`
(синтетический пункт по группе, ссылка на первую активную под-страницу). Отложено; см.
`scratchpad/s4-marketing-kunden-design.md` (вариант «группа=хаб»).

---

## 3. S5 — режим «Простой / Эксперт» (СЛЕДУЮЩИЙ ИНКРЕМЕНТ) — полное ТЗ

**Цель:** зонтик на весь кабинет. «Простой» скрывает продвинутое; «Эксперт» — всё.
**Дефолт:** `expert` (безопасно, не ломает существующих). Тумблер на «Funktionen».

### Шаги реализации
1. **Хелпер** (в `apps/core/modules.py` или новый `apps/core/ui_mode.py`):
   ```python
   def ui_mode(tenant) -> str:          # "simple" | "expert"
       cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
       return "simple" if cfg.get("ui_mode") == "simple" else "expert"
   def is_simple(tenant) -> bool: return ui_mode(tenant) == "simple"
   ```
   (Чтобы дефолт «Простой» из коробки — вернуть "simple" при отсутствии ключа.)
2. **normalize ДОЛЖЕН сохранять ui_mode** (иначе сохранение билдера его сотрёт —
   `siteconfig.normalize` дропает неизвестные ключи; ср. как сохранены `seo`/`page_blocks`):
   в `apps/tenants/siteconfig.py::normalize` добавить (conditional, чтобы golden-паритет):
   ```python
   if config.get("ui_mode") == "simple":
       normalized["ui_mode"] = "simple"
   ```
   (Дефолт expert → ключ не материализуется → паритет старых конфигов сохранён.)
3. **Тумблер** на странице «Funktionen» (`apps/core/views.py::modules_view`,
   `templates/tenant/modules.html`): POST-поле `ui_mode`; в POST-ветке — прочитать
   `tenant.site_config` (dict), выставить/убрать `ui_mode`, `normalize`, сохранить
   `site_config`. ВНИМАНИЕ: `modules_view` сейчас сохраняет только `disabled_modules` —
   добавить сохранение `site_config` тем же POST (или отдельной формой на странице).
4. **Контекст сайдбара**: контекст-процессор, дающий `nav_groups` (искать `modules_nav`
   в `apps/core/context.py` / `context_processors`), добавляет `ui_simple` (bool). Сайдбар
   `_base_dashboard.html` в Простом скрывает пункты с продвинутым nav_key.
5. **Что прятать в Простом (v1, консервативно, расширяемо):** набор
   `ADVANCED_NAV = {"finance", "analytics"}` (продвинутые отчёты). Расширять по фидбэку.
   Хаб-табы: Erweitert-ящик УЖЕ прячет редкое — в Простом можно дополнительно не рендерить
   Erweitert вовсе (опция; в v1 не обязательно).
6. **Гейт (уроки §5):** `grep` импортёров изменённых реестров; прогнать `apps/core`+`apps/tenants`
   ПОЛНОСТЬЮ + рендер сайдбара в обоих режимах; `test_cabinet_nav` дополнить кейсом Простого.

---

## 4. S6 — реальные архетипы через миграцию — полное ТЗ

**Решение владельца:** добавить `friseur / handwerker / werkstatt / events` **к текущим**
(не заменять). Требует МИГРАЦИЮ (deploy владельцем).

### Шаги
1. **`Tenant.BUSINESS_TYPES`** (`apps/tenants/models.py`): добавить 4 choice-пары к 10 текущим.
   Миграция — `AlterField(choices=...)` на SHARED-модели Tenant (public). Только choices, данные
   не трогает. (⚠️ django-tenants: Tenant/billing — SHARED; миграция в public-схему.)
2. **demo_kits** (`apps/tenants/demo_kits.py`): у китов friseur/handwerker/werkstatt/events
   выставлять `business_type` = новый тип (сейчас маппятся в `"other"`; найти где `business_type=`
   в китах и заменить). Проверить `apply_business_type`/`load_demo`.
3. **recommended_for / suited_for** (`apps/core/modules.py`): добавить новые типы к релевантным
   модулям — booking→friseur (Termine), jobs→handwerker+werkstatt (Aufträge/Angebote),
   events→events (Tickets), reviews/gift/crm→все. Свериться с `market-gap-*` доками.
4. **default_disabled_for(business_type)** (`apps/core/modules.py`): пресеты выключенного для
   новых типов (Friseur без stays/events по умолчанию и т.п.).
5. **Скрытие по архетипу в Простом (S5+S6)**: в Простом прятать нерелевантные ХАБЫ по
   `business_type` — Friseur без Sortiment/Lager (каталог не primary), Hotel без корзины и т.д.
   Поверх готового `recommended_for`/middleware-гейта + `is_simple`.
6. **Гейт:** `apps/tenants` (миграция+demo) + `apps/core` полностью; проверить `--create-db`
   локально (изменилась миграция!); демо-сиды новых китов.
7. **⚠️ После мержа — деплой владельцем:** `git pull origin main && ./scripts/deploy.sh single`
   (миграция Tenant choices). Обновить строку «Миграции» в CLAUDE.md §3.

---

## 5. УРОКИ (критично — стоили 2 красных CI в S2/S3)
1. **Правка ФОРМЫ общего реестра** (HUB_TABS кортеж/NAV_GROUPS/modules) →
   `grep -rn "HUB_TABS\|NAV_GROUPS" apps/` и прогнать ВСЕ приложения-импортёры, не только
   `apps/core`. (S3: расширение кортежа 4→5 сломало `apps/orders/tests/test_cabinet.py`.)
   В тестах читать кортеж по индексу `t[0]`, не распаковкой по длине.
2. **Свод nav → рендер сайдбара на ВСЕХ дашборд-страницах** → характеризационные тесты
   (`test_cabinet_nav`) ломаются, если проверяли старую метку. Обновлять их в том же инкременте.
3. **Полный локальный прогон затронутых приложений** перед пушем (крупный nav-инкремент):
   `uv run pytest <app1> <app2> ... -n auto --dist loadscope --reuse-db`.
4. **`msgfmt`/gettext локально НЕТ** → `apps/promotions/tests/test_email_i18n.py` (2 теста)
   падают ЛОКАЛЬНО, зелёные на CI (там `compilemessages`). НЕ блокер, не связаны с nav.
5. **`siteconfig.normalize` ДРОПАЕТ неизвестные ключи** → новый ключ site_config (ui_mode)
   сохранять в `normalize` (conditional, для golden-паритета), иначе билдер-сохранение сотрёт.
6. **CI ~11–13 мин** (медленный shared-раннер; тесты `-n auto --dist loadscope`). Батч-режим:
   гейтить локально, пушить стопкой, один CI на верхушке, **FF-merge в `main` по зелёному**
   (main не защищён; владелец разрешил). `concurrency: cancel-in-progress` на ветке.
7. **Рендер-проверка на реальном тенанте** (schema `shop` в dev-БД): `schema_context('shop')`
   + `RequestFactory` + прямой вызов вьюхи → извлечь tab-bar/сайдбар из HTML (см. как делалось
   для settings/marketing/kunden в этой сессии).

---

## 6. Очередь после программы упрощения
- **S3b** (отложено) — табификация длинной `settings.html` (form-секции Kontakt/Zeiten/
  Zahlungen/Versand в in-page табы). Отдельный инкремент, трогает форму.
- **«группа=хаб»** (отложено) — устранить краевое сиротство (§2). Полиш-рефактор `grouped_active_modules`.
- **S7** — витрина-first ввод (L2) + простой мастер онбординга (L3).
- Далее по владельцу: **T-1** (массовый de.po хрома) → **Волна «Склад-2»** (Chargen/MHD,
  мультисклад, закупки M12).

## 7. Как продолжить в новой сессии (чек-лист старта)
1. `git checkout claude/unified-order-kanban-stock-af3pl7 && git pull origin main` (ветка = main на 050c1ee).
2. Прочитать этот файл + `admin-simplification-exec-plan-2026-07-08.md` + CLAUDE.md §3/§7.
3. Реализовать **S5** по §3 (флаг+тумблер+скрытие advanced, дефолт expert).
4. Затем **S6** по §4 (миграция choices + demo + recommended_for + скрытие по архетипу).
5. Гейт по §5. Чекпоинт с владельцем после S5 и перед деплоем S6.
