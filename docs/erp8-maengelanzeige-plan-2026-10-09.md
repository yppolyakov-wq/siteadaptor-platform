# ERP-8 «Mängelanzeige» — рекламация поставщику (§ 377 HGB)

> Статус: **ERP-8a/b/c ✅ (2026-10-09)** — отмашка владельца «делаем ERP-8». Решения владельца из
> каталога задач (2026-09-09): полный цикл — фиксация + PDF-бланк + возврат через ERP-5.
> Источник — бумажный бланк владельца: виды дефектов, Liefer-/Prüfdatum, Frachtführer,
> Prüfergebnis, решение (принять со скидкой / замена / возврат), подпись.

## 1. Зачем и что говорит закон

Между коммерсантами (§ 377 HGB, Rügepflicht) покупатель обязан проверить поставку
«unverzüglich» и так же незамедлительно заявить о дефекте; кто промолчал, тот принял
товар («Genehmigungsfiktion»), скрытый дефект — заявить сразу после обнаружения. Поэтому
у рекламации важны **даты** (Lieferdatum, Prüfdatum, дата отправки поставщику) и
**документ**, который можно отправить и хранить. Сейчас в «Einkauf» есть только возврат
(ERP-5) без фиксации причины, дат и без бланка.

## 2. Разведка (факты кода)

* `apps/inventory/models.py`: `Lieferant`, `Bestellung` (`BE-XXXXXX`, статусы draft/
  ordered/received/cancelled — простое поле, не FSM), `BestellPosition` (`qty`,
  `qty_received`, `qty_returned`, `unit_cost`-снимок; `qty_open`, `qty_returnable`,
  `is_fully_received`).
* `apps/inventory/purchasing.py`: `receive_po_line` (складской путь + `ExpenseEntry` с
  ключом `<строка>:<накопл. qty_received>`), `return_po_line` (ERP-5: движение
  `return_supplier`, FEFO, сторно-расход `<строка>:ret:<накопл. qty_returned>`).
* Кабинет — один экран `/dashboard/purchasing/` (`views_purchasing.py`, action-POST,
  `?po=<pk>` — деталь заказа), шаблон `templates/inventory/purchasing.html`.
* PDF — reportlab поверх `apps/core/documents.py` (язык `document_language`, шрифт
  `fonts()`, форматы `doc_date`/`money`/`qty`); образец — `orders/pdf.py` (Lieferschein).
* Письмо с вложением — `notifications.services.notify(attachments=[(имя, bytes, mime)])`,
  язык письма — `email_locale()` (образец — счёт юрлицу SH-23b).
* Демо — `_seed_demo_purchasing` (киты с `enable_lots`: received-заказ + ordered).

## 3. Решения

**Р-1. Одна рекламация на поставку, строки внутри.** Бумажный бланк — на ПОСТАВКУ, в нём
несколько артикулов. Модели: `Maengelanzeige` (шапка, FK `Bestellung`) + `Mangel` (строка,
FK `BestellPosition`). Отдельной сущности «поставка» нет — поставка = заказ `BE-…`.

**Р-2. Виды дефектов — реестр, хранение списком кодов.** `DEFECT_TYPES`: `packaging`
(Verpackungsschaden) · `wrong_item` (Artmangel/Falschlieferung) · `quantity`
(Quantitätsmangel/falsche Menge) · `quality` (Qualitätsmangel) · `other` (Sonstiges).
`Mangel.defect_types` — JSON-список (несколько галок, как на бланке); мусор отбрасывается.

**Р-3. Решение — на строке, применяется один раз.** Три решения владельца:
* `discount` — **принять со скидкой**: товар остаётся, сумма скидки — сторно-расход
  (`ExpenseEntry`, отрицательная сумма, ключ `<строка>:mangel:<pk>`). Склад не трогаем.
* `return` — **возврат**: `return_po_line(qty)` (ERP-5 целиком: движение, FEFO, сторно).
* `replacement` — **замена**: возврат дефектных (`return_po_line`) + строка снова ждёт
  столько же штук: новое поле `BestellPosition.qty_replacement`, `qty_open = qty +
  qty_replacement − qty_received`. Деньги сходятся без новой логики: приёмка +N,
  сторно −N, приёмка замены +N = заплатили один раз. Заказ из `received` возвращается в
  `ordered` (иначе форма приёмки не покажется), `received_at` сбрасывается.
  `is_fully_received` = «открытого нет» — без замены совпадает с прежним `qty_received ≥ qty`.

  `resolved_at` + `resolved_qty` (сколько фактически вернулось — кламп ERP-5 по остатку)
  делают применение идемпотентным: повторный POST ничего не двигает. Пустое решение =
  рекламация «открыта» (поставщик ещё не ответил).

**Р-4. Шапка — поля бланка.** `reference` (`MA-XXXXXX`), `delivery_date` (Lieferdatum),
`inspected_at` (Prüfdatum), `carrier` (Frachtführer), `delivery_note_ref`
(Lieferschein-Nr.), `result` (Prüfergebnis, текст), `inspected_by` (кто проверял —
подпись на бланке; по умолчанию пользователь), `notified_at` (когда заявлено поставщику).
Подпись — строка подписи в PDF + имя; «рисованной» подписи нет (v1).

**Р-5. Строки рекламации — из принятого.** `Mangel.qty` ≤ `qty_received` строки
(Quantitätsmangel без приёмки — тоже строка: `qty` = недостача, решение не обязательно;
кламп по `max(qty_received, qty)` позиции заказа). Создаётся только строка с `qty > 0`.

**Р-6. PDF-бланк «Mängelanzeige».** Отправитель (тенант) → получатель (поставщик, адрес,
Kundennummer) → заголовок `Mängelanzeige MA-…` + дата → реквизиты (Bestellung,
Lieferschein-Nr., Lieferdatum, Prüfdatum, Frachtführer) → таблица строк (артикул +
Art.-Nr., количество, отмеченные виды дефектов, описание, требуемое решение) →
Prüfergebnis → правовая фраза («Hiermit zeigen wir gemäß § 377 HGB folgende Mängel an …
Wir behalten uns sämtliche Rechte vor.») → строка подписи «Ort, Datum / Name». Язык —
`document_language` (как Rechnung); правовая фраза — немецкий msgid с переводами.

**Р-7. Отправка поставщику.** Кнопка «Per E-Mail an Lieferanten» (если у поставщика есть
e-mail): `notify` с PDF-вложением, dedupe `<schema>:maengel:<pk>:<n-я отправка>` — повтор
после правки разрешён, двойной клик — нет; ставит `notified_at`. Без e-mail — кнопка
«Als angezeigt markieren» (ставит `notified_at` вручную: бланк ушёл факсом/почтой).

**Р-8. Кабинет — тот же экран «Einkauf».** На детали заказа (`?po=`) — секция
«⚠ Mängelanzeigen»: список рекламаций (MA-код, дата, статус offen/erledigt, PDF),
форма «Mängelanzeige erstellen» в `<details>` (шапка + по строке заказа: кол-во, галки
видов, описание), у каждой строки — форма решения (селект + сумма скидки для `discount`).
В списке заказов — бейдж «⚠ N offen». PDF — `/dashboard/purchasing/maengel/<pk>.pdf`
(с параметром → вне замка X7 «беспараметрный экран»).

**Р-9. Без FSM.** Статус рекламации производный: `open`, пока есть строка без решения;
иначе `done`. Отдельного поля статуса нет — нечего рассинхронизировать.

## 4. Миграция

`inventory/0006` — аддитивная: `BestellPosition.qty_replacement` (default 0) + модели
`Maengelanzeige`, `Mangel`. Бэкфилла нет.

## 5. Замки до кода (`apps/inventory/tests/test_erp8_maengel.py`)

1. Реестр видов: мусор в `defect_types` отбрасывается, порядок реестра.
2. `create_anzeige`: MA-код уникален, строки только с `qty > 0`, кламп по принятому.
3. `discount`: сторно-расход ровно на сумму, склад не тронут, повтор — без второй записи.
4. `return`: вызывает ERP-5 (движение `return_supplier`, сторно `…:ret:…`), `resolved_qty`
   = фактически возвращённое (кламп по остатку), повтор — ничего.
5. `replacement`: возврат + `qty_open` снова N, заказ `received → ordered`, приёмка замены
   книжит +N и расход; итог денег = одна оплата; заказ снова `received`.
6. Статус рекламации производный (open/done); бейдж открытых в списке заказов.
7. PDF: строится на de и ru (шрифт), содержит MA-код, BE-код, § 377 HGB, виды дефектов.
8. Отправка: письмо с вложением на e-mail поставщика, `notified_at`, двойной клик — одно
   письмо; без e-mail — ручная отметка.
9. Кабинет: создать → решить → PDF через вьюху (login_required), чужой pk → 404.
10. Демо: у кита с закупками есть закрытая (скидка) и открытая рекламация.

## 6. Инкременты

* **ERP-8a** — модель + миграция + сервис `apps/inventory/maengel.py` + замки 1–6.
* **ERP-8b** — кабинет (секция, формы, бейдж) + PDF + отправка + замки 7–9 + i18n.
* **ERP-8c** — демо + стенд Playwright (de/ru, 1440/390) + доки.

## 7. Сделано (2026-10-09)

ERP-8a/b/c одним батчем, миграция `inventory/0006` (аддитивная). Отличия от плана:

* **Ключ сторно скидки** — `mangel:<pk строки>`, а не `<строка>:mangel:<pk>`: `source_ref`
  у расхода 64 символа, два UUID не влезают (та же грабля, что в MX).
* **Блокировки** — `select_for_update` на строке при решении (двойной клик не применит
  его дважды) и `of=("self",)` на рекламации при отправке: поставщик — nullable join,
  его FOR UPDATE Postgres не берёт.
* **Демо** — решение пишется полями без проводок (как и демо-приёмка): сторно-расход без
  расхода приёмки исказил бы Ergebnis.

**Стенд** (пекарня, Playwright: бейдж → деталь → PDF → «Ersatzlieferung» → приёмка замены
→ отправка → новая рекламация формой; de/ru × 1440/390) нашёл два дефекта, невидимых
серверным замкам: (1) омоним — «offen» уже занят «Offene Posten» (ru «не оплачено»), у
статуса рекламации свой контекст перевода `complaint` + замок; (2) в ru-бланке
«Количество» налезало на «Товар» — колонка количества теперь по ширине подписи. Бланк
отрисован (pymupdf) на de и ru и проверен глазами.

**Фидбэк владельца (той же датой): «не только булочной — всем, где продаются товары».**
Функция кабинета от типа бизнеса не зависела (экран «Einkauf» — у любого тенанта с
каталогом), ограничение было в ДЕМО: закупки сеялись только китам с партиями. Теперь —
всем товарным типам (`PURCHASING_DEMO_TYPES`), поставщик и тексты дефектов под жанр,
строка заказа у товара с вариантами — вариант; гастро-киты осознанно вне (их закупки —
сырьё, которого в каталоге нет). Замок `test_every_goods_kit_gets_the_purchasing_demo`.
