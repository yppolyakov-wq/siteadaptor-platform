# UX-D · D3 — «Öffnungszeiten & Ressourcen»: список строками, страница ресурса, правила — в Einstellungen (план, 2026-11-03)

Основание: `ux-declutter-analysis-2026-11-03.md` §D3 (П1–П6). Механики из D2/D4: шторка
`apps/core/drawer.py` (контракт `docs/references/patterns/drawer.md`, `drawer_aware` — внутренний
декоратор), вкладки рисует сервер через `_i18n_switch.html` (`service_page.html` D2.4,
`unit_page.html` D4.6), экран-прецедент `booking_rules_view` (D2.1). План — агент ECC `planner`.
**Миграций нет.**

**Решения (2026-11-03, по рекомендации; владелец может поменять):** правило онлайн-брони столов и
виджет записи — карточками на «Buchungsregeln»; Anzahlung и Manual review ресурса — по праву цен
`preise.edit` (как предоплата услуги, D2), сотрудник видит значения текстом; тип ресурса после
создания — только чтение; форма «закрытых дней» снимается, вход — «Tage blockieren»
(`booking:availability`); имя ресурса становится редактируемым (сегодня — только переводы).

## Разведка
- `resources()` (`apps/booking/views.py:822-1051`) — один POST-диспетчер на 10 действий
  (`resource`, `i18n`, `rule`, `rules_from_hours`, `rule_delete`, `closed`, `toggle`,
  `resource_settings`, `resource_parts`, `resource_profile`); в конце `_back_to_resource`
  (`:800-813`) → `?open=<pk>#res-<pk>`.
- **W0:** `resource_settings` всегда пишет `deposit_cents`/`require_manual_confirm`/
  `counts_party_size` (места/зона/порядок/`min_seats`/`bookable_online` — по сентинелу
  `seats_present`); `resource_profile` всегда пишет `title`/`bio` → обе группы — ОДНА форма страницы.
- **Денежный дефект:** Anzahlung рисуется `{% widthratio r.deposit_cents 100 1 %}`
  (`resources.html:104`) — округление до евро: 5,50 € → «6», любое сохранение мест пишет 600;
  `_eur_to_cents` молча превращает мусор в 0.
- Ошибка комбинации столов (`:945-955`) уводит на голый список. `rule_delete` не сверяет ресурс.
- `table_rules_save` (`:1056`) требует `preise.edit`, форма видна всем → сотрудник получает 403.
- Статус-панели дублируют «Abläufe» (`ablaeufe_view`, kind booking, те же эндпоинты и права);
  в `calendar_context` (`views.py:143-151`) — мёртвый контекст `embed_url`/`status_label_rows`/
  `transition_rows`.
- Форма `closed` (один день бизнеса) дублирует «Tage blockieren» и Betriebsferien.
- Навыки мастеров (`Service.resources`) правятся на странице услуги — у ресурса только чтение.
- Входы на список остаются (`services.html`, `service_page.html`, `availability.html`,
  `tischplan.html`, `settings.html`, `jobs/detail.html`); `?open=`/`#res-` из закладок → 302.
- Замок `test_ga1_table_rules.py:207-220` разрешает `resource.require_manual_confirm` только в
  `booking/views*` → новый модуль `apps/booking/views_resources.py`.

## Инкременты
- **D3.0 — модуль действий + хотфикс депозита.** `views_resources.py`: 10 обработчиков 1:1,
  `ACTION_TAB`, `redirect_after`; Anzahlung — формат денег и `parse_money`, мусор → ошибка без
  записи.
- **D3.1 — страница ресурса** `booking:resource-edit` (`ressourcen/<uuid:pk>/`). Шапка со сводкой;
  вкладки `RESOURCE_TABS = basis, zeiten, buchung, tisch, profil` (tisch — у стола, profil — у
  мастера); ОДНА форма `#resource-form` (`resource_update`, сентинелы по группам, сначала проверка,
  потом одна запись); мини-формы правил времени и комбинации несут `tab`; «Bietet an» — чтение.
- **D3.2 — список строками + «＋ Ressource» шторкой + старые адреса.** Строка без полей; группы по
  типу; `booking:resource-new` (`ressourcen/neu/`, префилл `?type=table`); `?open=` → 302.
- **D3.3 — правило столов и виджет → «Buchungsregeln».** Карточка при столах, форма — по праву;
  виджет с копированием кнопкой.
- **D3.4 — уборка.** Статус-панели → ссылка на «Abläufe»; форма закрытых дней → карточка «Nächste
  geschlossene Tage» на чтение + «Tage blockieren»; мёртвый контекст из `calendar_context`.
- **D3.5 — стенд, i18n, доки.** friseur + restaurant + werkstatt × 1600/390.

## Замки — до кода
D3.0: каждое действие в одной записи `ACTION_TAB`; депозит 5,50 € переживает GET→POST без правок;
мусор не меняет депозит. D3.1: все поля в `#resource-form`, нет вложенных форм; round-trip W0
(стол, мастер); ошибка комбинации → `?tab=tisch`, ничего не сохранено; мини-формы → `?tab=`;
чужой uuid → 404; `rule_delete` чужого ресурса не удаляет. D3.2: в строке нет полей; фрагмент
шторки без скриптов; `navigate`; без JS → 302; `?open=` → 302; реестры прав/X7. D3.3: карточка
только при столах, у сотрудника без права формы нет. D3.4: панелей статусов и формы `closed` нет.

**Переписать осознанно:** `booking/tests/test_sp3_resources_compact.py:75-129`,
`booking/tests/test_cabinet.py:267-268`, `core/tests/test_sp_a11y_review.py:34`,
`core/tests/test_x0_x7_locks.py:61-80`. На легаси-диспетчере остаются зелёными:
`test_cabinet.py:243-355`, `test_ga3/ga4/ga5_*`, `test_e41b_hours_fallback.py`,
`core/tests/test_closures_owner_portal.py`.

## ECC-прогоны
| Когда | Что |
|---|---|
| до кода | скиллы `django-patterns`, `django-tdd`, `django-security`, `accessibility`, `e2e-testing` |
| D3.0 | `django-reviewer`, `silent-failure-hunter` (паритет, депозит, сообщения) |
| D3.1 | `django-reviewer`, `security-reviewer`, `silent-failure-hunter`, `a11y-architect` |
| D3.2 | `django-reviewer`, `security-reviewer`, `database-reviewer`, `a11y-architect` |
| D3.3 | `django-reviewer`, `security-reviewer`, `a11y-architect` |
| D3.4 | `django-reviewer` |
| D3.5 | `e2e-runner`: friseur + restaurant + werkstatt × 1600/390 |

## Риски
Немецкая локаль в числах (только `parse_money`/`_bounded_int`); комбинация и смена мест в одной
форме (проверка до записи); `_photo_add_tile.html` со скриптом — не в шторке; старые вкладки
браузера шлют POST в `resources()` — диспетчер принимает до конца волны; новые url-имена — в
`view_perms` и `EXPECTED_UNLISTED`; nav-литерал страницы — `booking-resources`.
