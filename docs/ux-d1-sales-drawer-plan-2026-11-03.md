# UX-D · D1 — «Продажи отеля и главная без каши» (план, 2026-11-03)

Основание: `ux-declutter-analysis-2026-11-03.md` §4–7 (решения Р-1…Р-5) + утверждённые макеты
«Kabinett aufräumen (UX-D)». Миграций нет, новых URL нет: шторка грузит фрагменты существующих
страниц `stays:booking-detail?box=1` и `stays:stay-new?box=1`.

## Разведка — скрытые дефекты (закрываются в D1.2, замок «красный до правки» на каждый)
1. `mark_paid` с полной карточки брони → 404: `f"{back}&buchung=…"` при `next` без `?`
   (`stays/views.py` ~633, то же 656/665). Оплата при этом записывается.
2. Действие в панели под шахматкой (fetch `?buchung=&box=1`) берёт `next=request.get_full_path`
   с `&box=1` → после POST браузер открывает голый фрагмент без хрома.
3. Компактная шахматка карточки сделки шлёт fetch на `location.pathname` (= booking_detail,
   без поддержки `box`) → в панель вставляется целая страница.
Попутно: клетки `td[data-free]` с `role=button tabindex=0` не реагируют на Enter/Space;
`room_clean` и `stay_action update` игнорируют `next`.

## Инкременты
- **D1.1** Общая шторка: `core/_drawer.html` (один `<dialog>` на кабинет), `.ui-drawer` в
  `app.css` (справа 30rem, на телефоне весь экран, блок прокрутки фона, reduced-motion),
  раздел `cabinet.js` (делегированный `a[data-drawer]` → fetch `box=1` → `showModal`, фокус
  на заголовок / первое поле; Esc, ✕, клик по подложке; возврат фокуса; формы
  `data-drawer-form` → fetch POST с `X-Sf-Drawer`, JSON `{ok,messages,location}`;
  `sfRefreshRegions()` перерисовывает `[data-drawer-refresh]` с сохранением прокрутки;
  фолбэк — обычная навигация), `apps/core/drawer.py` (`is_drawer`, `drawer_next`,
  `drawer_aware`: редирект + messages → JSON).
- **D1.2** Клик по брони → шторка: `stays/_booking_drawer.html` (сводка + те же партиалы
  `_stay_edit/_payment/_meldeschein/_front_desk`, ссылка на полную карточку), `booking_detail`
  с `?box=1`, `next_url` в партиалах, `_with_param` вместо склейки URL, `#booking-panel`
  удаляется, регион `#bp-region data-drawer-refresh`, `?buchung=` → автооткрытие шторки.
- **D1.3** «Neue Buchung» шторкой: `stay_new?box=1` с предзаполнением (unit/arrival/departure/
  room, мусор игнорируется), форма по макету (основные поля + «Mehr», имена полей байт-в-байт),
  инлайн-JS формы → `cabinet.js`, свободная клетка = ссылка-шторка (+ Enter/Space), «＋» тулбара/
  FAB/таб-бара → шторка; форма под шахматкой удаляется.
- **D1.4** Главная отеля = сводка: `apps/stays/home_summary.py` (KPI выручка/занято x из y/
  заезды-выезды/неоплачено; «Heute» с Check-in/out и «Sauber»; «Braucht Aufmerksamkeit»; полосы
  7 дней из `occupancy_grid`), `stays/_hotel_home.html`, гейт `loop_kind == "stay"` в
  `core.views.dashboard`; остальные архетипы байт-в-байт. `room_clean` уважает `next`;
  колонка «Zu reinigen» в виде «Heute».
- **D1.5** Шахматка без второстепенного: уборка и Lücken-Deal уходят на главную (и «Heute»);
  узкие `max-w-*` навигации и поиска сняты.
- **D1.6** Демо hotel (грязная комната, бронь без номера, дыра, сообщение) + документы.

## Решения (по рекомендации владельца)
Р-D1-a KPI «Offene Zahlungen» без модуля Finanzen — без ссылки, с подсказкой включить ·
Р-D1-b Lücken-Deal на главной и «Was heute starten?» — оба · Р-D1-c сквозной `?box=1` на
главной снимается (2 замка переписываются осознанно).

## Риски
Перехват `_danger_confirm`/`_photo_shrink` (слушатель шторки — фаза всплытия +
`defaultPrevented`) · скрипты во фрагменте не исполняются (весь JS — в `cabinet.js`, замок
«нет `<script` во фрагментах») · CSRF при fetch (FormData несёт токен) · прокрутка и фокус при
перерисовке · деньги: логика apply/refund не трогается, только адрес возврата.

## ECC-прогоны
| Когда | Что |
|---|---|
| до кода | скиллы `accessibility`, `e2e-testing`, `django-patterns`, `django-tdd` |
| после D1.1+D1.2 | `django-reviewer`, `security-reviewer` (`next`, CSRF, JSON, права `box`), `silent-failure-hunter` (`stay_action`: оплата/возврат/отказы в JSON), `a11y-architect` (шторка) |
| после D1.3 | `django-reviewer`, `a11y-architect` (форма в шторке, ошибки `role=alert`) |
| после D1.4 | `django-reviewer` + `database-reviewer` (запросы главной, `assert_max_num_queries`), `a11y-architect` (KPI, полосы) |
| каждый инкремент | Playwright-стенд demo hotel 1440/390: шторка (фокус/Esc/прокрутка), оплата без перезагрузки, «Stornieren» поверх шторки, клетка → новая бронь, занятые даты → ошибка в шторке, телефон, компактная шахматка, без JS, главная, friseur/bakery без изменений, замер «поля/высота» до/после |
