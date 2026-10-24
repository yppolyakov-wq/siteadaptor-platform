# KA-12 · Счёт из брутто-сделки: НДС «из брутто» (Bruttomethode) — план, 2026-10-24

План — агент `planner` по коду `main`. Найдено золотым путём E11.1: счёт из записи на 45,00 € @19 %
выходит на 45,01 € (нетто в центах 37,82 → НДС 7,19; 37,81 → 44,99). Замок —
`apps/booking/tests/test_golden_termine.py::test_invoice_gross_equals_deal_total_exactly` (xfail strict).

## 0. Разведка
- Сделки УЖЕ считают «из брутто»: `apps/orders/totals.py::split_gross` (net = round(G/(1+r)), vat = G − net)
  — его же используют `order_totals`, `core/vat.py::deal_vat`. Расходится только счёт:
  `finance/services.py::compute_totals` (quantize(net группы) → vat = round(net·r)).
- Режим «брутто» считать через `split_gross` — разбивка счёта совпадёт с разбивкой сделки по построению.
- Сметы `Job` считаются в нетто (`jobs/totals.py::quote_totals`) → счёт заявки остаётся нетто.
- УСт-срез/DATEV читают журнал выручки (не счета) — не затронуты; `ustva.py` (оплаченные предоплаты) читает
  `Invoice.gross` — станет точным.
- Пересчёт групп ставок продублирован 4 раза: `_invoice_gross_by_rate`, `reverse_job_credit`,
  `pdf._rate_rows` (фолбэк «одна ставка»), `advance.deduction_rows` («deduction drift»).
- E-Rechnung (EN 16931) в коде нет — при её появлении перепроверить (допуск ±0,01).

## 1. Вызовы `compute_totals` → режим
| Место | Что | Режим |
|---|---|---|
| `fit_gross` (2 вызова) | подгонка | только net; для gross не вызывается |
| `create_credit` | Rechnungskorrektur | как у оригинала |
| `invoice_from_stay` / `invoice_from_booking` / `invoice_from_order` | счёт из сделки | **gross** |
| `advance.create_advance_invoice` | Anzahlungsrechnung | **gross** |
| `finance/views.py` ручной счёт | владелец вводит нетто | net |
| `jobs/services.py` (Rabatt-подгонка, `quote_to_invoice`) | смета | net |
`create_storno` копирует суммы (GoBD) — копирует и режим.

## 2. Хранение режима
`Invoice.price_basis` (`net` | `gross`, default `net`, db_default) — миграция `finance/0018`, аддитивная,
мгновенная в каждой схеме. Все существующие счета = `net` → суммы/разбивка/PDF не меняются (GoBD:
выставленный документ не пересчитываем). Отвергнуто: выводить из сделки (у заказа и заявки один
`deal_kind`, режимы разные); признак в строках (истина размазана по строкам).
Строка gross: `{"text","qty","unit_gross","unit_price"(производное нетто, 4 знака — обратная
совместимость),"vat_rate"(обязательна)}`.

## 3. Арифметика — одна функция
`apps/finance/totals.py::rate_groups(lines, vat_rate, *, small_business, basis)` → `[(rate, net, vat,
gross)]`; net — нынешняя арифметика байт-в-байт; gross — G группы = quantize(Σ unit_gross·qty) →
`split_gross`. `compute_totals(..., basis="net")` — обёртка той же сигнатуры. `fit_gross` при gross —
no-op. Все 4 копии пересчёта → `rate_groups(..., basis=invoice.price_basis)`.

## 4. Согласованность документов
Сторно копирует `price_basis`; корректура gross-счёта — строка на ставку с `unit_gross=доля`, qty −1,
без `fit_gross`; предоплата gross (`advance_lines` с `unit_gross`), вычет по режиму предоплаты;
журнал заявок учитывает режим; PDF gross — «Einzelpreis (brutto)», блок Netto·USt·Brutto по ставкам
(§ 14 Abs. 4 Nr. 7/8 UStG), «Gesamtbetrag inkl. USt»; net — без изменений (замок). `money_contract`,
Offene Posten, Mahnung читают `Invoice.gross` — правок не нужно.

## 5. Тесты (красные первыми) — `apps/finance/tests/test_bruttomethode.py`
Снять xfail E11.1 · перебор брутто 1…20 000 ¢ × 19/7/0 × qty 1/2 — gross == итог сделки и группы ==
`split_gross` · смешанный заказ 7/19 + акция + доставка + Rabatt — разбивка == `order_totals` полями ·
номер (Kurtaxe 0 %, питание, допы, Rabatt, сертификат) · caplog: нет «rounding residual»/«deduction
drift» в gross · сторно/корректура gross · предоплата 45,00 → итоговый счёт без drift ·
`_invoice_gross_by_rate`/`reverse_job_credit` на gross · **байтовое совпадение net-счетов** (ручной,
заявки, старые) — существующие тесты без правок · миграция: старые строки `net` · сверка банка на 45,00.

## 6. Законность (подтвердить у Steuerberater)
Метод округления UStG не предписывает; выделение налога из брутто — обычная практика (касса,
§ 33 UStDV). Вопросы: формат «брутто-строки + блок по ставкам» для счетов фирмам; округление по группе
ставок; § 14c (показанный = уплаченный); совместимость с E-Rechnung B2B; «inkl. USt» на
Anzahlungsrechnung. Фича только убирает цент расхождения — за флагом держать не обязательно.

## 7. Инкременты
G-0 красные тесты (xfail strict) + замки байтового совпадения · G-1 (отдельно, рефактор):
`finance/0018`, `totals.py`, `basis`, 4 копии на `rate_groups`, net байт-в-байт · **G-2+G-3+G-4 одним
батчем**: построители gross + снять xfail · сторно/корректура · PDF и `invoice_detail.html` + msgid ×5 ·
G-5 документация. Вне объёма: остаток Rabatt в сметах, переключатель «Preise inkl. MwSt.» ручного счёта.

## 8. Риски
Черновики до деплоя остаются net (при выпуске сумма не пересчитывается) — предложить «пересоздать
черновик», решение владельца · читатели `unit_price` (сохраняем производным) · строка без `vat_rate`
в gross — построитель обязан ставить, защита + замок · отрицательные группы (Rabatt) — прежний фолбэк ·
смешение: итоговый gross + старая оплаченная предоплата net (вычет — снимок) — тест.

## 9. ECC-прогоны
| Когда | Что |
|---|---|
| До кода | `django-tdd`, `python-testing`, `error-handling`, `database-migrations`, `postgres-patterns`, `django-patterns`; `pitfalls.md` §1 |
| После G-0 | `tdd-guide` (опц.) — полнота перебора |
| После G-1 | `database-reviewer` (ADD COLUMN, db_default, migrate_schemas), `django-reviewer` |
| После G-2…G-4 | `django-reviewer` + **`silent-failure-hunter`** (деньги: тихие фолбэки в `rate_groups`/`_rate_rows`/`deduction_rows`), `code-reviewer` (PDF) |
| Не нужно | `security-reviewer` (нет нового ввода), Playwright (JS не меняется; PDF — текстом в pytest) |
| Перед пушем | ruff целиком, `i18n_quickcheck`, `test_template_comments`, pytest finance/booking/orders/stays/jobs/core (`--create-db` после миграции) |
