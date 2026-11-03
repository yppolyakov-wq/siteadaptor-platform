# UX-D · D2 — «Leistungen» (услуги): список строками + страница с вкладками (план, 2026-11-03)

Основание: `ux-declutter-analysis-2026-11-03.md` §D2, утверждённые макеты Services/ServiceEdit.
План составлен агентом ECC `planner`; миграций нет.

## Разведка — что определяет решения
- `services_view` (`apps/booking/views.py` ~1347) обслуживает и список, и страницу (`pk`); POST
  `create/update/toggle/season_add/season_delete/variant_*`. **`update` всегда перезаписывает
  duration/price/description**, остальное — по сентинелам `*_present` → вкладки «Grundlagen /
  Buchungsregeln / Beschreibung & FAQ» — ОДНА форма (разбивка по формам обнулила бы цену из
  вкладки правил — класс W0). Сезоны и варианты — свои мини-формы → вкладка «Preise & Varianten»
  вне главной формы (приём `catalog/product_form.html`).
- `_photo_add_tile.html` несёт inline `<script>` — в шторке создания фото нет; после «Anlegen» —
  страница услуги.
- Тесты `no_show_rule_save`/`termin_manage` зовут `__wrapped__` — декораторы этих вьюх не трогаем;
  приёмник шторки — новая вьюха.
- Табы — `_i18n_switch.html` (`data-pf-tab/panel`, раскрытие скрытого поля при `invalid`); активную
  вкладку рисует сервер (`?tab=`).
- Общего «окна отмены по умолчанию» нет — `cancel_window_hours` у каждой услуги (B6).

## Инкременты
- **D2.1 — экран «Buchungsregeln» в Einstellungen.** Новая GET-вьюха `booking_rules_view`
  (`leistungen/regeln/`… `booking-rules`), карточка «Anzahlung nach Nichterscheinen» переносится
  1:1 партиалом, `no_show_rule_save` возвращает туда; таблица «Stornofrist je Leistung» (только
  чтение, ссылки `?tab=regeln`); nav_registry (settings, группа termine), view_perms `_r(CFG, CFGE)`,
  правка — `preise.edit`. Чеклист `cabinet-screen-dod.md`.
- **D2.2 — «＋ Leistung» в шторке.** `_create_service(request)` выделяется из `action=create`;
  новая `service_new` (`leistungen/neu/`, `@drawer_aware` внутренним): фрагмент Name/Dauer/Preis/
  MwSt/Preis gilt/Anzahlung, ошибка у поля с сохранением ввода, успех → `navigate` на страницу
  услуги; `?neu=1` → 302; входы `sellable_manage`, `setup_assistant` → `service-new`.
- **D2.3 — список строками.** Строка: миниатюра · Leistung · Dauer · Preis («ab» при вариантах) ·
  Wer bietet an · чип Status (toggle — только hidden) · ›; шапка: число, /termin/, Kollektionen,
  Öffnungszeiten & Ressourcen, «＋ Leistung» (шторка); подвал — «Regeln für alle Leistungen →».
  Список не строит i18n/FAQ-контекст, `prefetch_related` (нет N+1).
- **D2.4 — страница услуги с вкладками** `service_page.html`: шапка (← Alle Leistungen, имя,
  «29,00 € · 480 min · кто», статус, «Auf der Website ansehen»), вкладки Grundlagen · Preise &
  Varianten · N · Buchungsregeln · Beschreibung & FAQ; одна `#svc-form` (все сентинелы), сезоны/
  варианты вне неё; `?tab=` по белому списку, POST возвращает на свою вкладку; липкий «Speichern».
- **D2.5 — стенд, i18n, доки.** Playwright friseur/hotel/restaurant 1600/390, замер «полей до/после».

## Замки (до кода) — по инкрементам
D2.1: карточка на экране; у сотрудника нет формы; POST → 302 на booking-rules; пункт меню по модулю;
nav_title = h1; вход есть (X7); на списке нет формы no-show-rule. D2.2: фрагмент помечен/без
кэша/без скриптов; префилл; чужой `next`; JSON `navigate`; без JS 302; пустое имя → фрагмент с
`role=alert`; `?neu=1` → 302. D2.3: в строках нет редактируемых полей; ссылка на страницу у каждой
строки; бюджет запросов при 10 услугах. D2.4: все поля старой формы внутри `#svc-form`; нет
вложенных форм; **round-trip W0** (POST из отрендеренной формы без правок не меняет модель);
`?tab=` и мусорный tab; `season_add` → `?tab=preise`.

Переписываются осознанно: `test_x6_mechanics` (service-часть «＋», `?neu=1`), `test_stu19g_setup_v2`,
`test_stu19i_miniapp`, `test_service_rich_editing` (GET с pk), `test_deal_card_shell:718`.

## ECC-прогоны
| Когда | Что |
|---|---|
| до кода | скиллы `django-patterns`, `django-tdd`, `django-security`, `accessibility`, `e2e-testing` |
| после плана | `django-reviewer` — ревью плана (одна форма vs формы по вкладкам, шторка) |
| D2.1 | `django-reviewer`, `security-reviewer` (права, staff только чтение) |
| D2.2 | `django-reviewer`, `security-reviewer` (ввод, next, drawer_aware), `a11y-architect` |
| D2.3 | `django-reviewer`, `database-reviewer` (prefetch, бюджет запросов) |
| D2.4 | `django-reviewer`, `a11y-architect` (вкладки, липкий Save), `silent-failure-hunter` (W0) |
| D2.5 | `e2e-runner` (Python-Playwright стенд) |

## Вопросы владельцу
1. Общая «Standard-Stornofrist für neue Leistungen» (ключ `site_config["booking"]`)? Без неё подвал
   упоминает только правило неявок.
2. Anzahlung услуги — редактируемой во вкладке «Buchungsregeln» (сентинел, только `preise.edit`)?
