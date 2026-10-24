# KA-12 W3 B2-8 — Anzahlungsrechnung / Schlussrechnung (§ 14 Abs. 5 UStG) + режим Soll/Ist

План — агент planner, 2026-10-24. Решения владельца: T-1 (Soll/Ist/Kleinunternehmer, дефолт Soll),
T-2 (кнопкой, B2B автоматически), T-3 (вариант A: одна предоплата, модель — на N этапов).

## 0. Факты из кода
- `Invoice.kind` = invoice|storno|credit, constraint `finance_invoice_kind_links`.
- Предоплаты: stay/booking/job (`deposit_cents`, `payment_state`); у билета `deposit_cents` есть,
  но билдера счёта нет; у заказа предоплаты нет.
- `_prepaid_from_payment_state` считает депозит уже полученным; `_refresh_prepaid` обновляет при выпуске.
- `journal_invoice_revenue` проводит выручку для ЛЮБОГО счёта `deal_kind="job"` — счёт на
  предоплату заявки стал бы выручкой (дефект, закрыть гардом `kind == invoice`).
- Срез UStVA считается только из журнала `RevenueEntry` по дате, режима нет.
- `DealPayment.created_at` = дата поступления; у возврата даты нет.

## 1. Модель
- **Tenant** (SHARED, `tenants/0039`): `tax_regime` soll|ist (дефолт soll); Kleinunternehmer —
  существующий `small_business`; в UI одна радио-группа из трёх вариантов.
- **finance/0017**: `KIND_ADVANCE="advance"` («Anzahlungsrechnung») + расширение constraint;
  таблица `InvoiceDeduction(final, advance, vat_rate, net, vat, gross)` (unique final+advance+rate) —
  снимок вычета по ставкам в итоговом счёте; допускает N этапов без переделки (T-3).

## 2. Сервисы (`apps/finance/advance.py`)
- `advance_rows` — разбивка предоплаты по ставкам сделки (`deal_vat`), остаток округления в последнюю.
- `create_advance_invoice(kind, obj, tenant)` — stay/booking/job, под блокировкой, одна живая на
  сделку, выпуск через `issue_invoice`; если деньги уже получены — `prepaid_cents`.
- Оплата депозита (`folio.record`/`settle_payment`) переводит счёт на предоплату в paid.
- Итоговый счёт при выпуске: брутто = вся услуга (журнал по ставкам не меняется), строки вычета
  из оплаченных предоплат, `open_amount` = скорректированное брутто − вычет − прочее полученное;
  `_refresh_prepaid` вычитает уже вычтенное (иначе депозит дважды).
- Сторно предоплаты — только если не вычтена; сторно итогового освобождает вычет.
- Предоплата — НЕ выручка (MC-D1); время НДС решает срез UStVA.
- B2B: автоматически при подтверждении сделки с `customer_type=company` и депозитом.

## 3. UStVA по режиму (`apps/finance/ustva.py`)
- **Ist:** НДС по датам поступления (`DealPayment`) за вычетом возвратов + не-сделочные источники.
- **Soll:** НДС журнала за период + НДС предоплат, полученных до исполнения (Mindest-Ist,
  § 13 Abs. 1 Nr. 1a S. 4) − то же при исполнении; непривязанные записи — пометка.
- **Kleinunternehmer:** USt 0 с примечанием § 19. Подпись «срез, не декларация».

## 4. UI
- Кнопка «Anzahlungsrechnung erstellen» на карточке сделки (stay/booking/job), владелец/админ;
  приёмник `deal-advance-invoice/<kind>/<pk>/` (EXPECTED_UNLISTED).
- PDF: заголовок «Anzahlungsrechnung»; в итоговом — блок «Abzüglich Anzahlung RE-… vom …» по
  ставкам и «Noch zu zahlen».
- Offene Posten: счета на предоплату — открытые позиции; строка сделки скрыта при выставленной
  предоплате; аннотация вычета без N+1.

## 5. Инкременты
- **B2-8a** (`tenants/0039`): режим + UI + `ustva.py`, `ergebnis` на нём.
- **B2-8b** (`finance/0017`): вид advance + таблица вычетов (пустая), выпуск, кнопка, PDF,
  гарды журнала, Offene Posten, синк оплаты.
- **B2-8c:** вычеты в итоговом счёте, правка prepaid, блок PDF, сторно неоплаченной предоплаты.
- **B2-8d:** авто-счёт B2B с письмом.
- v2: предоплата билета, несколько этапов.

## 6. Замки (до кода)
Предоплата заявки не создаёт `RevenueEntry`; разбивка по ставкам = депозит (Kurtaxe 0 %);
повтор клика — тот же документ; итоговый счёт не вычитает депозит дважды; сторно вычтенной
предоплаты — отказ; Offene Posten по шагам; UStVA Soll/Ist/§19 на примерах; сотрудник — 403/404.

## 7. Риски
Двойной вычет · предоплата в выручке · точность Ist для легаси (`opening` датирован созданием
фолио, у возвратов нет даты) · привязка записей журнала к сделке · GoBD · смена constraint.

## 8. Вопросы владельцу
- **Q-1** Предоплата билета — в v2? (рекомендация: да)
- **Q-2** Неоплаченная предоплата при выпуске итогового счёта: автоматическое сторно (рекомендация)
  или отказ выпускать?
- **Q-3** Счёт на предоплату частному клиенту ДО поступления денег (кнопкой)? (рекомендация: да)
- **Q-4** Для Ist учитывать дату возврата — `DealPayment.refunded_at`, аддитивно в B2-8a
  (рекомендация: да)
- **Q-5** Подпись PDF для счёта после поступления («bereits bezahlt») — сверить со Steuerberater.

## 9. Детальный план B2-8b (planner, 2026-10-24)
- **Флаг `ADVANCE_INVOICES_ENABLED` (env, default False)** до B2-8c: без блока «Abzüglich
  Anzahlung» итоговый счёт повторил бы НДС предоплаты (§ 14c UStG).
- `finance/0017`: `KIND_ADVANCE` + расширение `finance_invoice_kind_links` + частичный
  unique «одна живая предоплата на сделку» + таблица `InvoiceDeduction` (пустая в 8b).
- `apps/finance/advance.py`: `advance_rows` (депозит по ставкам `deal_vat`, остаток в
  последнюю), `create_advance_invoice` (блокировка сделки, повтор = тот же документ, отказ
  без депозита/отменённой/с итоговым счётом; `invoice_id` сделки НЕ ставится),
  `sync_advance_paid` (депозит получен → advance paid), `on_advance_paid` (оплата advance →
  депозит на сделке, НЕ полная оплата).
- Гарды: журнал/сторно журнала/`_refresh_prepaid` пропускают advance; сторно advance с
  вычетом — отказ; `InvoiceSM` paid у advance → `on_advance_paid`; Offene Posten: advance —
  позиция, строка сделки/депозита скрыта; банк/Mahnung принимают advance.
- UI: кнопка на карточках stay/booking/job (владелец/админ), PDF «Anzahlungsrechnung».
