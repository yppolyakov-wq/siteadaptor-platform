# PH-14 — панель выдачи в одну строку (вариант A) — 2026-11-09

Решение владельца: «Делай A с элементами из фото» (макет — артефакт «Suchleiste in einer Zeile»,
`claude.ai/artifact/9nN6tVK7JMqWqdcRU2aAxw`; элементы со скриншота: «⇅ Relevanz ▾» и сегмент
Kacheln · Liste · Karte).

## Что было
Над выдачей поиска/раздела пять строк: вкладки вида · пилюли фильтров (Bereich/Stadtteil/Preis/
Merkmale/Jetzt geöffnet + снятые фильтры) · «N Treffer» + сортировка с «OK» · «Benachrichtigen» ·
Liste/Karte + «In meiner Nähe». Первая карточка ≈ 330 px ниже начала панели.

## Что делаем (только при `flt` — выдача/раздел/район)
1. **Строка заголовка:** h1 + «N Treffer» (`data-hit-count`, role=status) + колокольчик подписки
   (`_search_follow.html` компактом: значок 44 px, sr-only имя). Интро портала при поиске скрыто.
2. **Одна строка инструментов** (`_portal_filter_bar.html`): «Filter · N» · вкладки вида сегментом
   (`_portal_tabs.html` уходит в строку) · «Stadtteil ▾» · «Jetzt geöffnet» · пусто · «⇅ Сортировка ▾»
   · сегмент Kacheln/Liste/Karte. На телефоне строка листается вбок (как и сейчас).
3. **Bereich / Preis / Merkmale** — только в шторке/колонке фильтра (поповеры из строки сняты).
4. **Снятые фильтры** — метками с ✕ строкой ПОД панелью, только когда они есть.
5. **Сортировка** срабатывает сразу при JS (кнопка «OK» прячется скриптом; без JS форма с «OK»).
   «In der Nähe» — пункт сортировки всегда: без точки JS берёт геолокацию и дописывает lat/lng;
   без JS/без разрешения сервер «naehe» без точки игнорирует (`search.parse`).
6. **Вид:** `?ansicht=` ∈ {"" Kacheln, `liste`, `karte`}. Новый `liste` — строки на всех ширинах
   (`_cards.html` layout `rows`); `karte` — как прежде (карта над карточками). Ссылки вида —
   `rel=nofollow` (query-вариации noindex), `aria-current`. `liste` переносится как `karte`
   (`portal_filter_ui` carry, `portal_views` keep-список).
7. `_map.html` при `flt` не рисует свою строку переключателя и «In meiner Nähe» (они в панели).

## Инварианты
P0-1 (никаких персональных данных/CSRF в кэшируемом HTML; всё — ссылки и GET-формы) · без JS всё
работает (сорт с «OK», шторка noscript, ссылки вида) · W0 (ничего не теряется: Bereich/Preis/
Merkmale доступны в фильтре) · лимит запросов поиска не растёт (`test_unified_search` cap).

## ECC-прогоны
- Скиллы до кода: django-patterns, django-tdd, accessibility, e2e-testing.
- Замки ДО правок: строка — одна (`data-flt-bar` содержит фильтр, сегмент вида, сорт, вид);
  Bereich/Preis/Merkmale-поповеров в строке нет; count в строке заголовка; bell — значок с именем;
  `ansicht=liste` → `data-card-rows`, переносится фильтрами; сорт без «OK» при JS (атрибут для JS).
- После кода: `django-reviewer` + `a11y-architect` (новые контролы); Playwright-стенд 390/1440 ×
  de/ru + без JS; замер «до первой карточки».
