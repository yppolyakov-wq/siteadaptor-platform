# MX-2 — Опции с трекерами на все якоря (план-док перед кодом)

**Дата:** 2026-08-21 · родитель: `mx-execution-plan-2026-08-21.md` §MX-2
Решения владельца: §5b «опция = цена + трекер»; v1 = «надбавка + поставщик»,
ёмкостная/расходуемая — вторым слайсом; «Zusatzverkäufe» — вкладкой в Verkäufe.

## Слайс 2a — модель (миграция core, аддитивная)
`core.Extra` +=
- `entity_kind` CharField(20, blank) + `entity_id` CharField(64, blank) — адресность
  (пусто = scope-wide, поведение сегодня; строки, не FK — прецедент DealLink);
- `tracker` CharField(12, blank): "" надбавка · pool · stock · purchase (заявленный
  вид обработки; v1 сама обработка есть только у purchase-подсказки MX-4);
- `pool_size` PositiveSmallInteger(default 0) — размер собственного пула (v1
  информативно, enforcement — слайс 2e);
- `supplier` FK inventory.Lieferant SET_NULL — у закупаемой;
- `product` FK catalog.Product SET_NULL — у расходуемой (рецепт, слайс 2e);
- `vat_rate` Decimal(4,2) null — своя ставка НДС опции (пока справочно; в
  разбивку журнала — при MX-НДС).

## Слайс 2b — адресность на витрине (без миграций)
`extras.active_for(scope)` → `active_for(scope, entity_kind=None, entity_id=None)`:
scope-wide (entity_kind="") ∪ адресные этой сущности. Приёмники (4 колл-сайта
public_views + walk-in) передают сущность. `snapshot` — тот же фильтр (защита от
подмены формы). Кабинет `/dashboard/extras/`: колонка «Gilt für» + выбор сущности
(select по kind → поиск pk; v1 — простой select из активных сущностей kind).

## Слайс 2c — «Zusatzverkäufe» (вкладка Verkäufe)
Экран `/dashboard/verkaeufe/zusatz/`: строки проданных опций за период —
собираются по id из снимков: StayBooking.extras / Booking.extras / Ticket.extras
(+ OrderItem.modifiers с id). Python-скан за период (SME-объёмы; JSON-поля).
Строка: опция · сделка (код, ссылка) · день исполнения (arrival/start/starts_at/
pickup) · статус сделки · сумма. Фильтры: kind, день, опция. Сводка сверху:
Σ по опциям («Frühstück × 12»). Вкладка в ряду Verkäufe — гейт «есть активные
Extras или продажи с опциями»; nav_registry запись (hub board), палитра.
Активные статусы сделок — через status_registry (отменённые не считаем).
Кнопка у purchase-опции «→ Anbieter-Buchung» — заглушка до MX-4 (не рисуем).

## Слайс 2d — переквалификация демо moto (решение §3.1)
Кит moto: тиры заездов → «Eigenes Motorrad / Sozius» (категории УЧАСТИЯ, без
аренды), НОВАЯ адресная опция «Royal Enfield 411 mieten» (tracker=pool,
pool_size=6, supplier=Moto-Verleih Manali) на события туров. Демо-билеты
выбирают опцию → Zusatzverkäufe показывает «продано N аренд на заезд X».
ops: `seed_demo_tenants --kit moto --recreate`.

## Слайс 2e (отложен, отдельная отмашка) — enforcement
pool: подсчёт проданных опций пула на дату/заезд + отказ при переполнении
(в atomic брони); stock: списание product по рецепту при исполнении сделки.

## Замки
- адресная опция видна ТОЛЬКО у своей сущности (и в snapshot не проходит чужой);
- scope-wide поведение байт-в-байт (характеризация до правок);
- Zusatzverkäufe: строки трёх видов сделок + модификаторы заказа; отменённая
  сделка выпадает; счётчик Σ по опции;
- гейт вкладки; nav-замки (test_w8_nav_registry).

## Порядок: 2a → 2b → 2c → 2d (батч, один CI-прогон); 2e — после отмашки.
