# UX-D · D5 — Tagesplan: «＋ Neuer Termin» шторкой, свободное время → шторка, запись открывается шторкой (план, 2026-11-03)

Основание: `ux-declutter-analysis-2026-11-03.md` строка D5 (П1–П6). Механики из D1.2/D1.3: шторка
`apps/core/drawer.py` (контракт `references/patterns/drawer.md`), прецедент формы —
`stays/views.py:134-169` (`_clean_prefill`, `_new_booking_fragment`, `fail(msg, field)`). План —
агент ECC `planner`. **Миграций нет.**

**Решения (2026-11-03, по рекомендации; владелец может поменять):** строгий разбор — только в шторке
(легаси-путь Tischplan и POST без JS — без изменений); свободное время — клик по колонке скриптом +
«＋» в заголовке колонки (не ссылка на каждую строку); дата и время — раздельными полями; walk-in
Tischplan в шторку — позже; на телефоне (сетки нет) v1 — только «＋ Neuer Termin» с датой дня.

## Разведка (file:line)
- Форма записи всегда раскрыта: `templates/booking/_tagesplan_body.html:88-130` (`#neu`,
  `booking:booking-create`): `resource`, `start` (datetime-local), `minutes`, `service`
  (`<svc>`/`<svc>:<variant>`), `name`/`phone`/`email` без видимых подписей, `party_size`, `note`,
  `override_hours`. Мобильный якорь `data-skip-neu` — `:31`; раскладка SP-12 — `:20`, `:88`.
- Тело включают вкладка booking в Verkäufe и главная салона (`core/_sales_body.html:15`).
- Сетка рисуется только при записях (`:37-39`); свободное время — не ссылка
  (`_tagesplan_grid.html:24`); сетка `hidden md:block`; перенос — инлайн-скрипт, после 204 reload.
- Запись открывается полной карточкой (`booking_detail`, `views.py:203-251`, фрагмента нет).
- `booking_create` (`views.py:486-561`) без `drawer_aware`; мягкий разбор: мусор в `minutes` →
  «Invalid date.», в `party_size` молча → 1, устаревшая услуга → запись без услуги на 0 €.
- `services.create_manual` (`services.py:591-692`): часы, пул, места стола GA-3, навык, занятость;
  `ManualBookingRefused` без кода причины, один флажок на часы и места.
- «＋» Verkäufe → `?tab=booking&view=kalender#neu` (`sales_page.py:719`); `data-drawer` только у stay.
- Прочие клиенты `booking-create`: Tischplan (`tischplan.html:71`) и POST-тесты — легаси не трогаем.

## Инкременты
- **D5.0 — форма шторкой `booking:booking-new`** (`termin/neu/`): фрагмент/страница из одного
  партиала, дата+время раздельно (легаси `start` принимается), префилл `?resource=&start=`/`?tag=`,
  видимые подписи; `booking_create` + `@drawer_aware`; строгий разбор в шторке (ошибка у поля, ввод
  сохранён); `ManualBookingRefused(code=…)`; «Trotzdem eintragen» в шторке второй кнопкой
  `override_hours`; успех — `open_after(booking-detail)` без `navigate`.
- **D5.1 — клик по свободному времени**: сетка и в пустой день, `data-tp-new`/`data-tp-closed`,
  клик → шторка с ресурсом и временем; «＋» в заголовке колонки (клавиатура, без JS).
- **D5.2 — запись шторкой**: фрагмент `booking_detail` (сводка, статусы, перенос, оплата),
  `booking_action` + `@drawer_aware`, плашки и коды — `data-drawer`, область `tp-region`.
- **D5.3 — снять постоянную форму**: кнопка «＋ Neuer Termin» (`id="neu"`), create_target →
  `booking-new`, единый флаг шторки `sales_page.opens_in_drawer(url)`, `#neu` → открыть шторку.
- **D5.4 — стенд, i18n, доки**: friseur + restaurant + werkstatt × 1600/390.

## Замки — до кода
D5.0: ошибка у поля, ввод сохранён, ничего не создано; `outside_hours` → кнопка обхода; повтор с ней
создаёт запись; `closed`/`slot_taken` без обхода; успех = JSON `open` без `navigate`; без заголовка —
прежние редиректы; префилл чужого uuid → пустой выбор; фрагмент без `<script>`; видимые подписи.
D5.1: пустой день рисует сетку с `data-tp-new`; закрытая колонка `data-tp-closed`; без права — нет.
D5.2: фрагмент `data-drawer-title`, формы `data-drawer-form`, чужой uuid → 404, `tp-region`.
D5.3: в теле дня нет формы `booking-create`; create_target booking = booking-new с `data-drawer`.

**Переписать осознанно:** `test_e42b_tagesplan_grid.py:370-373`, `test_sp_a11y_review.py:36`,
`test_verkaeufe.py:245`, `test_e44b_variants_s3.py:95-107`, `test_ka_w2_tabbar.py:41`.

## ECC-прогоны
| Когда | Что |
|---|---|
| до кода | скиллы `django-patterns`, `django-tdd`, `django-security`, `accessibility`, `e2e-testing`; `docs/pitfalls.md` |
| D5.0 | `django-reviewer`, `security-reviewer`, `silent-failure-hunter` |
| D5.1 | `django-reviewer`, `a11y-architect`, `e2e-runner` |
| D5.2 | `django-reviewer`, `security-reviewer`, `silent-failure-hunter`, `a11y-architect` |
| D5.3 | `django-reviewer` |
| D5.4 | `e2e-runner`: friseur + restaurant + werkstatt × 1600/390, без JS |

## Риски
Клик после drag (флаг «только что тянули»); инлайн-скрипт сетки в обновляемой области больше не
выполняется — делегирование `__tpBound`; запись на другой день не видна в области (тост с датой);
без JS ошибка формы теряет ввод (личные данные в URL не кладём); время — только ISO `HH:MM`.
