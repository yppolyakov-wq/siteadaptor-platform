# W10 — Verkäufe единственной операционной поверхностью продаж

Дата: 2026-08-05. Родитель: `cabinet-unification-plan-2026-08-05.md §2.4` (решение
Р-4: Reservierungen — в Verkäufe). Все инкременты БЕЗ миграций БД.

## §1. Цель

Одна страница `/dashboard/verkaeufe/` отвечает на все операционные вопросы продаж
(«что сегодня», «что нового», «где заказ X»), легаси-страницы становятся
редиректами — но СТРОГО после паритета функций (аудит-урок: «тонкая обёртка
оказалась богаче единой страницы»).

## §2. Разведка-сводка (что уже закрыто, что осталось)

Закрыто W7c (2026-08-05): next=-провод действий встроенных календарей;
shipped_at/резерв-таймстемпы в FSM; is_delivery-фильтр доски; гейт вкладки по
модулю; Liste по дате события. Закрыто W9-8: «⚙️ Abläufe» на Verkäufe; панели
статусов больше не только на легаси-страницах.

Остаток по аудиту (audit-sales.md):
- reservation вырезан из Verkäufe всегда (`sales_page.py`), заявки клиентов
  спрятаны в Marketing/Erweitert — Р-4 требует вкладку.
- Две несовместимые модели переключения видов: persist `sales_views[kind]`
  (Verkäufe) против «персист удалён» (сегмент ST-5b `orders_view`); плюс
  `verkaeufe_view_set` редиректит на голый `?tab=`, теряя `?von=/?tag=/?q=`.
- Liste заказов беднее `/dashboard/orders/`: нет фильтра статуса, KDS/Table-QR.
- Нет kind-агностичного «Heute»; deep-link «Abholbereit» ведёт на легаси.
- events:list/jobs:list вне Verkäufe; hub_tabs["board"]-огрызок (Tickets/Aufträge).
- «＋» (создать) доступен не из всех видов.
- «Versendet» с доски: shipped_at теперь ставится (W7c), но ввода трек-номера
  с канбан-карточки нет — письмо уходит без Sendungsnummer.
- Три поверхности доски дают три ответа «сколько заказов» (limit'ы 20/50/200 при
  честных счётчиках — визуальное расхождение).

## §3. Инкременты (порядок — механика → функции → поглощение)

- **W10-1 Виды: одна модель переключения + GET-сохранение.** `verkaeufe_view_set`
  редиректит на полный исходный путь (next= с carry GET); сегмент ST-5b
  `orders_view` умирает (страницы уже под Verkäufe; `entry_url_name` остаётся
  для якоря) — одна модель памяти видов (persist per-kind), замки ST-5b снимаются
  осознанно.
- **W10-2 Reservierungen-вкладка (Р-4).** `sales_page`: kind reservation
  показывается при primary promotions ИЛИ существующих резервах (exists-гейт как
  у прочих); тело — Board/Liste теми же механиками (FSM резервов уже в
  transactions). Вход из Marketing остаётся (дубль допустим до W11).
- **W10-3 Liste-паритет + входы вкладок.** Вкладка order: фильтр статуса + поиск
  `?q=` (код/имя/email) + кнопки KDS/Table-QR; события/заявки: `events:list`/
  `jobs:list` встраиваются вкладками (ticket/job уже в kinds — добавить
  недостающие тела), hub_tabs["board"]-огрызок умирает; «＋» доступен из любого
  вида (кнопка у переключателя, per-kind цель создания).
- **W10-4 «Heute»-вид** (kind-агностичный, НОВЫЙ, четвёртым в переключателе):
  заезды/выезды сегодня (stays), записи сегодня (booking), заказы к выдаче
  (ready) и к доставке — колонками; поглощает `stays:today`-ссылки и deep-link
  виджета «Abholbereit» главной.
- **W10-5 apply_action.** `transactions.apply_action(kind, obj, target, actor,
  extra)` — единая точка: письма/таймстемпы/спец-поля (tracking_code) для ВСЕХ
  поверхностей; канбан-карточка заказа-доставки при «Versendet» запрашивает
  трек-номер (мини-форма на карточке); kanban_action/per-app вьюхи делегируют.
- **W10-6 Легаси-редиректы.** `/dashboard/orders|booking|stays` списки/календари
  и `events:list`/`jobs:list` → 302 на соответствующую вкладку Verkäufe
  С СОХРАНЕНИЕМ GET; deep-links (`?status=ready`, `?von=`, `?tag=`) обязаны
  работать на цели ДО включения редиректа. «Alte Ansicht»-ссылки умирают.
  Board `/dashboard/board/` остаётся (вид доски = ссылка «Full view» главной).

Каждый инкремент — свой батч: локальный гейт (ruff+targeted pytest) → push →
CI → FF-merge. Характеризационные замки ДО переносов (урок UB1-3).

## §4. Статус

- **W10-1 ✅** (2026-08-05): одна модель переключения видов. `verkaeufe_view_set`
  возвращает на полный исходный путь (next=, только внутренний) — переключение
  вида больше не сбрасывает `?von=/?tag=/?q=/?buchung=`. Сегмент ST-5b удалён
  целиком (тег `orders_view_switch` + партиал + `switch_options`/`create_option`);
  5 легаси-страниц несут мостик «Alte Ansicht · Alles auf einer Seite»;
  `orders_view.py` сведён к resolve_view (главная) + entry_url_name (якорь).
  Создание броней не потеряно: walk-in формы живут в телах календарей.
  test_orders_view переписан (8), замок «API удалён, не забыт».
- **W10-2 ✅** (2026-08-05, Р-4): reservation подчиняется общему правилу «вкладка
  с первой продажей» (`visible_kinds` перестал вырезать kind; тело Board/Liste
  уже было generic — kod вьюхи не менялся). Вход из Marketing остаётся дублем
  до W11. Замок переписан: появление вкладки с первым резервом.
- **W10-3a ✅** (2026-08-05): паритет order-Liste + «＋». Вкладка order на
  Verkäufe: фильтр статуса + поиск `?q=` (код/имя/email через FK customer) +
  входы KDS/Table-QR; «＋» в шапке из любого вида (stay → stay-new, booking →
  `?tab=booking&view=kalender#neu`; у заказов owner-create флоу нет — кнопки
  нет); deep-link «Abholbereit» главной → `verkaeufe?tab=order&status=ready`.
  Урок: замки по URL, не по подписи — de.po переводит английские msgid
  («Kitchen Display» → «Küchenанzeige»). 1 msgid × 5 .po.
- **W10-3b ✅** (2026-08-05): огрызок `hub_tabs "board"` (Tickets/Aufträge) снят
  со всех 6 страниц (board/order_list/booking-календарь/jobs/events/stays-today);
  реестр board-хаба ЖИВ осознанно — питает палитру Ctrl+K и якорь подсветки.
  Страницы без мостика (jobs/events/today) получили «Alte Ansicht · Alles auf
  einer Seite»; вкладки ticket/job на Verkäufe получили вход в полные
  управляющие экраны (events:list/jobs:list). Замки: «ни один шаблон не рендерит
  board-бар» (скан) + входы с вкладок. W10-3 закрыт целиком.
