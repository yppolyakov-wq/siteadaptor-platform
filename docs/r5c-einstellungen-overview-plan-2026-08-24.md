# R5c — обзорный экран «Einstellungen» (утверждённый артборд Einstellungen.dc)

Дата: 2026-08-24. Волна R5 плана `redesign-b-implementation-plan-2026-08-24.md`;
отмашка владельца «Делай» (макет утверждён в составе канваса: «структура ок ·
стиль B · ок по экранам»). Артборд обещает: «Alles an einem Ort — keine
Untermenüs» — группированный СПИСОК-ОБЗОР со строками «название + живая
подпись + шеврон», три группы (Geschäft / Verkauf / System).

## 1. Решение (по прецедентам, без новых механизмов)

Обзор — **лендинг якоря**, ровно как «Marketing» (`marketing-home`, ST-6a) и
«Website» (`site-home`, W11-5):

- НОВАЯ вьюха `einstellungen_home` + шаблон `tenant/einstellungen_home.html`
  + роут `dashboard/einstellungen/` (name=`einstellungen-home`).
- Якорь сайдбара «Einstellungen»: `url_name` `settings` → `einstellungen-home`;
  `nav_key="settings"` НЕ меняется — подсветка всех 14 страниц настроек цела.
  Прецедент: W11-5 так же перенацелил якорь Website на site-home.
- `/dashboard/settings/` (форма «Mein Geschäft», settings_view, POST с
  update_fields W7a) НЕ трогается — ни один тест формы не задет.
- Таб-бары X5 на 14 под-страницах остаются (быстрый переход на десктопе);
  обзор — вход с сайдбара, главный на мобильном.

## 2. Состав строк — из nav_registry (единый источник W8)

Вьюха идёт по `nav_registry.legacy_hub_tabs()["settings"]` с ТЕМИ ЖЕ гейтами,
что `hub_tabs` (module_key активен · owner_only скрыт сотруднику ·
allowed_for_business · `palette_only` пропускается). В обзоре advanced-состав
ВИДЕН (обзор = «всё в одном месте»; на страницах его снял R2).

Группы обзора ≠ группы X5-таб-бара (тех две, в макете три) — локальная карта
во вьюхе, фолбэк «Weitere»:

- **Geschäft**: Mein Geschäft (`settings`) · Team & Zugriff · Sprachen
- **Verkauf**: Zahlung & Lieferung · Recht & Steuern · Benachrichtigungen ·
  Abläufe (в макете нет — добавлена: настройка процессов относится к продаже)
- **System**: Integrationen · Funktionen (`modules`) · Abo & Rechnung
- **Weitere**: Zusatzleistungen · Finder · Hilfe (advanced-остаток)

## 3. Живые подписи строк (fail-safe, паттерн digest._safe)

v1 — только дешёвые источники; всё прочее — статичные описания (msgid):

- Sprachen: `tenant.active_locales()` (поле) → «Deutsch + N weitere»
- Team: `Membership.objects.count()` (1 запрос, _safe)
- Funktionen: число активных модулей (вычисление в памяти)
- Остальные: статичная подпись («Adresse, Öffnungszeiten, Kontakt» и т.п.)

Статусы Integrationen со светофорами (как в макете) — v2 по спросу
(реюз контекста integrations_home, там запросы дороже).

## 4. Замки — осознанные правки

- `test_x0_x7_locks.py::test_sidebar_anchor_composition_is_frozen` — кортеж
  якоря settings: url_name → einstellungen-home (осознанно, прецедент
  site-home; состав/порядок якорей НЕ меняется — мораторий X7.1 цел).
- `test_w8_nav_registry.py::test_settings_subpage_highlights_settings_anchor`
  — href якоря станет `/dashboard/einstellungen/` (подсветка та же).
- Палитра: якорь больше не дедупит запись «Mein Geschäft» (url_name разошлись)
  → «Mein Geschäft» появляется в палитре отдельной строкой (это плюс).
- Новые замки: обзор рендерит группы и гейтит (owner-only строки скрыты
  сотруднику; module-строки — по активности; заголовок «Mein Geschäft»
  ведёт на /dashboard/settings/).

## 5. Не делаем (границы v1)

- Свод ФОРМ в один экран — нет: макет показывает обзор-хаб, формы остаются
  своими страницами (safe-пути W7a/W9 целы).
- Светофоры интеграций, счётчики на каждой строке — v2.
- Убийство таб-баров под-страниц — нет.

## 6. ИТОГ (2026-08-24, после волны R7): план ОТМЕНЁН — поглощён R7-1

Фидбэк владельца тем же днём («по-прежнему на страницах дубль меню; клик по
разделу должен открывать подменю, и в нём уже всё») снёс таб-бары целиком и
сделал подменю раздела ЕДИНСТВЕННОЙ поверхностью состава — раздел
«Einstellungen» теперь раскрывает полный список экранов настроек прямо в
сайдбаре. Отдельная страница-обзор в этой IA — ровно тот «дубль меню»,
который владелец просил убрать; обещание макета «alles an einem Ort» несёт
подменю. Живые подписи-статусы строк (Deutsch + 2 weitere и т.п.) — идея на
будущее для подменю, не для отдельной страницы. Разведка (воркфлоу
wf_dcceb5ee) сохранена выше — карта входов url 'settings' пригодится любому
будущему рефактору настроек.
