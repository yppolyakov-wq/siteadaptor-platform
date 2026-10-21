# T-8.30e «Касса в Mini App» — план (2026-10-21)

Продолжение T-8.30 (`t8-30-miniapp-plan-2026-10-20.md`, решение Q2 «экраны кассы — отдельно»).
Разведка — агент planner; решения E-1…E-5 приняты по рекомендации.

## Цель
Владелец у прилавка в Telegram Mini App: видит отложенное («Zurückgelegt»), выдаёт его,
гасит купон/резерв по QR или коду. Сейчас эти ссылки в Telegram ведут на «nur per E-Mail».

## Решения
| # | Вопрос | Решение |
|---|---|---|
| E-1 | Чем сканировать в Telegram | нативное окно Telegram (`web_app_open_scan_qr_popup` через мост, без SDK); ручной ввод — всегда; камера страницы — только в обычном браузере |
| E-2 | Куда ведёт плитка «Zurückgelegt» | фильтр `?status=offen` (pending+confirmed) по сроку — совпадает со счётчиком |
| E-3 | Сотрудники в Mini App | нет (сессия Telegram — только владелец, как в T-8.30) |
| E-4 | Автопогашение при скане | прежнее — настройка бизнеса |
| E-5 | Плитки на «Start» | «Zurückgelegt N offen» + «Code scannen» (тот же партиал, что на экране акций) |

## Найдено разведкой и закрывается здесь
1. Сканер страницы делал `location.href = val` для ЛЮБОГО http(s) из QR — открытый переход.
   Теперь общий разбор: голый код или путь `/promotions/redeem/<code>/` (хост любой — QR мог
   выпустить свой домен владельца) → переход на СВОЙ адрес; прочее — «Unbekannter QR-Code».
2. Счётчик «N offen» считал pending+confirmed, а ссылка вела на `?status=pending`.
3. В списке у pending не было «Ausgeben» — продавцу два нажатия, хотя `services.fulfill`
   с T-8.2 сам подтверждает неподтверждённую бронь. Лёгкая карточка pending получает
   «Ausgeben» сразу; сервер не меняется.

## Инкремент
- Белый список `TG_LITE_VIEWS` += reservation-list/-action, redeem/-detail/-action.
- `reservation_list`: `?status=offen`, `lite`, лёгкая вёрстка карточками (телефон), полный
  кабинет — прежняя таблица.
- `redeem.html`: ветка Telegram (кнопка `data-tg-scan`), безопасный разбор в обеих ветках.
- Мост `_tg_shim.html` → `window.saTgBridge = {post, on}` (приём событий через
  `Telegram.WebView.receiveEvent`, прежний обработчик сохраняется).
- Плитки — общий партиал `promotions/_lite_counter_tiles.html` (экран акций + «Start»).

## Известный долг (не в объёме)
`redeem_detail` при `auto_redeem_on_scan` гасит на GET (так было и раньше). Перенос на POST —
отдельная задача; prefetch этого адреса не добавлять.

## Проверка
Замки до кода (`test_t830e_counter.py`, `test_t830_tg_session.py`) → стенд Playwright 390 px
с эмуляцией моста (`TelegramWebviewProxy` + вызов `Telegram.WebView.receiveEvent`) →
django-reviewer + security-reviewer → CI → FF в `main`. Нативное окно на настоящих iOS/Android —
проверка владельцем.
