# KA-12 E6.7e — навигация по правам (2026-10-25, без миграций)

Сегодня доступ держит middleware (`view_perms.allowed` в `process_view`), а навигация прячет
только owner-only экраны второй копией правил (`NavEntry.owner_only` → `owner_hidden_for`,
`_hide_owner_only` в палитре). Цель — скрывать ровно то, что запрещено, из ОДНОГО источника.

## 1. Один источник
- `nav_registry.entry_allowed(entry, user)` = `view_perms.allowed_quiet(user, entry.url_name, "GET")`
  (strict-режим `allowed` бросает на незарегистрированный экран — хром не должен падать; замок
  «каждый `entry.url_name` есть в RULES»). Аноним/None → True (доступ держит middleware).
- Вкладки-query (`verkaeufe?tab=kunden`, `?tab=job`, `?versand=1`): `view_perms.QUERY_RULES`
  {(url_name, query): key}; ту же карту проверяет `sales_page` (иначе скрытие косметика). Замок:
  каждая query-запись ENTRIES в `QUERY_RULES` или в явном списке «наследует правило экрана».
- `entry_visible(..., user=None)` += `entry_allowed`. `owner_only` выводится из FLOOR: сперва
  замок паритета `owner_only ⇔ RULES[url].read == FLOOR`, затем снос `owner_hidden_for` /
  `owner_only_url_names` / `_hide_owner_only`.

## 2. Разделы и цели
- `visible_children` уже фильтрует → скрытые подпункты пропадают.
- Якорь без разрешённых детей и без своего разрешённого экрана — скрыт.
- `anchor_target`: первая разрешённая цель → первый разрешённый ребёнок → `dashboard`. Лендинги
  `marketing_home`/`integrations_home` — через тот же `anchor_target(user)` (без 302→403).

## 3. Потребители
`nav_registry.py`, `view_perms.py`, `modules.py` (`sidebar_nav`, бейдж inbox при
`nachrichten.view`), `context.py` (таб-бар; «＋» только при write), `templatetags/cabinet.py`
(палитра + фильтр `perm_allowed` для кнопок), `settings_home.py`, `dashboard.py` (плитки/виджеты),
`lite_cabinet.py` + Mini App, `sales_page.py`, `palette_search.py` (каждая секция имеет право),
`views.py` (`marketing_home`). Прямые `{% url %}` на чужие экраны в шаблонах кабинета — обернуть
фильтром; таблицу приложить в build-log.

## 4. Производительность
`effective` мемоизирован, `allowed` — словарь: +0 запросов (замок `django_assert_max_num_queries`).

## 5. Замки (до кода) — `apps/core/tests/test_perm_nav_hiding.py`
1. Адверсариально: пресеты owner/admin/staff × дельты (снятие каждого ключа + seed-наборы) ×
   3–4 архетипа — каждая ссылка сайдбара/подпункта/цели якоря/таб-бара/палитры/плиток/обзора
   настроек проходит `allowed` (+QUERY_RULES); «＋» — write.
2. Staff без `kunden.view` не видит Kunden нигде; `verkaeufe?tab=kunden` вкладку не рендерит.
3. Пустой якорь скрыт; якорь с запрещённой первой целью ведёт на первый разрешённый подпункт.
4. Паритет `owner_only ⇔ FLOOR`, затем «`owner_only` в реестре нет».
5. X7/reachability идут от владельца (проверить явно); для staff — скрыто ТОЛЬКО запрещённое.
6. Поиск по данным: без `kunden.view` пусто в клиентах, без `verkaeufe.view` — в сделках.
7. Число запросов.

## ECC-прогоны
- До кода: скиллы django-patterns, django-tdd, django-security.
- После кода: `django-reviewer`; `security-reviewer` (вкладки, поиск по данным, лендинги).
- Стенд Python-Playwright: owner/admin/staff и staff без `kunden.view`, 390/1440, de/ru,
  3–4 архетипа; обход всех видимых ссылок — 0 ответов 403; лист «Mehr», Ctrl+K.

## Грабли
Декоратор, съеденный вставленным хелпером (`test_orphan_decorators`); переменная
контекст-процессора в аргументе фильтра; многострочный `{# #}`; i18n_quickcheck + `git add`;
app.css при новых классах; `ruff format --check .`; тест-тенант не на public-схеме; strict-`allowed`.

Мерж: два коммита (замки+`entry_allowed`+паритет; снос owner_hidden+потребители), один CI.
