# ERP-волна — план исполнения (отмашка владельца «Делай», 2026-08-21)

Источник: `erp-gap-analysis-2026-08-21.md` (Tier 1 целиком). Батчи через зелёный
CI → мерж; ERP-5..7 (возврат поставщику · часы Работы · производственный акт) —
за отдельной отмашкой (архетип-специфичны).

## ERP-1 — COGS-снимок + честная маржа (⚠️ миграция orders, аддитивная)
1. `OrderItem.cost_price` (Decimal, null=легаси) — снимок EK на момент продажи
   (как уже снимаются цена/НДС/артикул): variant.cost_value | product.cost_price.
   Точки: `create_order` (обычные+custom со складским товаром; наборы и свободные
   строки — без снимка) и `editing.add_line`.
2. Ergebnis: блок «Wareneinsatz (COGS)» + «Rohertrag» — по заказам, чья выручка
   записана в период (join RevenueEntry(source=order) за период → позиции;
   легаси-позиции без снимка → 0, честная пометка «teilweise ohne EK»).

## ERP-2 — Offene Posten + банковский импорт (⚠️ миграция finance, аддитивная)
1. Экран «Offene Posten»: неоплаченные сделки всех kind (payment unpaid/pending,
   не отменённые по реестру статусов) + выставленные неоплаченные Invoice; суммы,
   возраст долга.
2. `finance.BankTransaction`: date, amount, purpose (Verwendungszweck),
   counterparty, import-ref (дедуп повторного импорта), matched_kind/matched_id.
   CSV-импорт: авто-детект колонок по заголовкам DE-банков (Buchungstag|Datum,
   Betrag, Verwendungszweck, Beguenstigter/Auftraggeber|Name), `;`-CSV, запятая
   в сумме; кривой файл — честная ошибка.
3. Сопоставление: по reference_code в Verwendungszweck (Vorkasse E7 его пишет)
   и/или сумме → предложение; подтверждение кликом ставит оплату сделки
   (payment_state=paid / InvoiceSM paid) + помечает транзакцию.

## ERP-3 — Eingangsrechnung + Mahnwesen v1 (⚠️ миграции finance, аддитивные)
1. `ExpenseEntry` += supplier FK, due_date, paid_at, document FK
   (documents.SecureDocument — файл/фото счёта, приватная выдача уже есть).
   Экран Ausgaben: секция «Offene Eingangsrechnungen» (по due_date), кнопка
   «Bezahlt»; ручная форма += ставка НДС и срок.
2. Mahnwesen своих счетов: `Invoice` += mahn_level, mahned_at; из Offene Posten
   кнопка «Zahlungserinnerung/Mahnung» (письмо клиенту, уровень++, дедуп по дате).

## ERP-4 — UStVA/EÜR-срез + DATEV расходов (БЕЗ миграций)
1. Ergebnis: «USt aus Einnahmen − Vorsteuer aus Ausgaben = Zahllast» за период
   (налог из брутто: amount × rate/(100+rate)).
2. `exports.datev_expenses_csv` (Aufwandskonto по категории an Kasse) + кнопка
   на Ausgaben; выручка-экспорт не тронут.

i18n: msgid × 5 на каждый экран; nav-записи palette_only (мораторий сайдбара цел).
