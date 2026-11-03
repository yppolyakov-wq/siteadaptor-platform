# Шторка кабинета (drawer) — контракт

UX-D D1 (2026-11-03). Одна шторка `<dialog id="sf-drawer">` на весь кабинет
(`templates/core/_drawer.html`, подключена в `_base_dashboard.html`), JS — раздел
`// ---- core/_drawer.html ----` в `static/js/cabinet.js`, сервер — `apps/core/drawer.py`.
Цель: открыть объект (бронь, позже — новую бронь, услугу) справа, не уходя со страницы.
**Без JS всё работает как раньше:** ссылка ведёт на обычную страницу, форма — обычный POST.

## Открыть объект

```html
<a href="{% url 'stays:booking-detail' b.pk %}" data-drawer data-drawer-key="bar-{{ b.pk }}">…</a>
```

- Клиент берёт адрес ТОЛЬКО из `href` и только для страниц кабинета этого сайта
  (`cabinetUrl`), добавляет `box=1` и `next=<текущая страница>` (`fragmentUrl`).
- Вьюха отдаёт фрагмент, если `drawer.is_box(request)` (`?box=1` или GET с заголовком
  `X-Sf-Drawer: 1`), и оборачивает ответ в `drawer.fragment(...)`.
- `fragment()` ставит `X-Sf-Fragment: 1`, `Cache-Control: private, no-store`,
  `Vary: X-Sf-Drawer`. **Ответ без метки клиент не вставит** (страница входа, целая
  страница, чужой редирект) — уходит на обычную навигацию.
- Корень фрагмента: `data-drawer-title="…"` (заголовок шторки). Фокус — на заголовок или
  на `[data-drawer-autofocus]`.
- `data-drawer-key` — для возврата фокуса после перерисовки области (ссылка пересоздаётся).
- В адрес страницы пишется `?drawer=<путь>` (pushState) — «назад» закрывает шторку,
  перезагрузка/ссылка открывает её снова. Автооткрытие с сервера —
  `<div hidden data-drawer-autoopen="<url>">`.

## Формы внутри шторки

```html
<form method="post" action="…" data-drawer-form [data-drawer-after="close|reload"]>
  {% csrf_token %}<input type="hidden" name="next" value="{{ next_url }}">
```

- Клиент шлёт fetch с заголовком **только `X-Sf-Drawer: 1`** и `redirect: "manual"`.
  `X-Requested-With` НЕ шлём: часть вьюх отвечает на него своими кодами (перетаскивание
  броней, доска) — действие прошло бы, а шторка показала бы ошибку.
- `next` во фрагменте — `drawer.drawer_next(request, default)` (только локальный путь,
  `safe_next`); партиалы берут `{{ next_url|default:request.get_full_path }}` — без
  `box=1`, иначе после POST без JS браузер открыл бы голый фрагмент.
- Вьюха-приёмник: `@drawer.drawer_aware` — **ВНУТРЕННИЙ декоратор** (под
  `login_required`/`require_POST`), иначе редирект на вход превратился бы в JSON.
  Замок — `test_drawer_aware_is_the_innermost_decorator`.

### Ответы `drawer_aware` (только для запросов с заголовком)

| Ответ вьюхи | Что получает клиент |
|---|---|
| редирект | JSON `{ok, messages, navigate, open[, location]}`; сообщения сессии забраны |
| редирект НЕ туда, куда `next` формы (счёт, полная карточка) | `navigate: true` + `location` — клиент переходит |
| `drawer.open_after(request, url)` перед редиректом | `open: url` — клиент открывает этот объект в шторке |
| фрагмент (ошибки формы) / 403 / 404 / 409 | как есть; сообщения — в заголовке `X-Sf-Messages` (JSON) |

`ok` ложно, если среди сообщений есть `error`. Клиент после успеха перерисовывает области
страницы и перезагружает шторку; `data-drawer-after="close"` — закрыть с тостом.
Сетевая ошибка / неясный ответ → области и шторка перерисовываются, пользователь видит
«Status unklar — Ansicht aktualisiert…» (не повторять действие вслепую — деньги).

## Перерисовка страницы под шторкой

```html
<div id="bp-region" data-drawer-refresh> … <div class="overflow-x-auto" data-scroll-key="bp-grid"> …
```

- `sfRefreshRegions()` запрашивает текущую страницу (без `box/drawer/buchung`) с
  заголовком `X-Sf-Refresh: 1` и заменяет каждую `[data-drawer-refresh][id]` по id.
  **id обязателен** (замок `test_refresh_regions_have_ids`); области нет в ответе →
  полная перезагрузка.
- `data-scroll-key` сохраняет горизонтальную прокрутку (шахматка).
- После замены — событие `sf:region-updated` на `document`: обработчики, навешенные на
  элементы области (перетаскивание, подписи), переподключаются по нему. Весь JS — в
  `cabinet.js` на делегировании; `<script>` во фрагментах не исполняется и запрещён
  (замок `test_drawer_fragments_carry_no_inline_handlers_or_scripts`, `on…=` тоже).
- `X-Sf-Drawer`/`X-Sf-Refresh` глушат тосты страницы (триал в `billing/context.py`).

## Доступность

`<dialog>` + `showModal()` (фокус внутри, Esc закрывает), `aria-labelledby` на заголовок,
кнопка ✕ с `aria-label`, сообщения — `role=status` (polite) и `role=alert` (ошибки),
возврат фокуса к открывшей ссылке (или по `data-drawer-key`, или к области/`h1`), клик по
подложке закрывает только при mousedown+click на ней. Телефон — во весь экран с
safe-area, кнопки 44 px; анимация — только при `prefers-reduced-motion: no-preference`.
