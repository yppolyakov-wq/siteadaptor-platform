# KA-12 W3 B5 = E4.2b «Tagesplan: ресурс × время + drag-and-drop» — план, 2026-10-24

План — агент `planner` по коду HEAD (после E4.4b). **Без миграций.**

## 0. Как сейчас
- `apps/booking/views.py::calendar_context` отдаёт брони дня плоским списком (шаблон
  `booking/_tagesplan_body.html`); встроен во вкладку Verkäufe и в карточку сделки (compact).
- `services.move(booking, *, start, end, override_hours=False)`: блокирует ТОЛЬКО ресурс брони,
  **сменить ресурс нельзя, статус не проверяется**; закрытие → `ResourceClosed`, вне часов →
  `OutsideHours` (обход `override_hours`), буфер/пересечение/ёмкость → `SlotTaken`.
- `booking_action` (`action=move`) — только redirect+messages, без fetch-ответов и без `resource`.
- Образец DnD — Belegungsplan отеля (`stays/_belegungsplan_body.html`): делегирование на
  `document`, grab-offset, fetch с CSRF, 204 → reload, 409 → toast.

## 1. Что делаем
1. **`services.move(..., resource=None)`**: целевой ресурс; блокировать ОБА ресурса в порядке pk
   (как `resync_occupancy` — без дедлока); все проверки по целевому; `NotMovable`, если статус не
   в `status_registry.active_statuses_for("booking")` (закрывает дыру: POST руками двигал
   выполненные/отменённые); неактивный ресурс → отказ; письмо «verschoben» — только при смене
   ВРЕМЕНИ (смена мастера без смены времени — без письма, Р-2 ниже).
2. **`apps/booking/tagesplan.py`** (чистые функции): границы дня из `day_windows` всех активных
   ресурсов (+ расширение до броней вне часов, фолбэк 08–20), шаг 15…60, геометрия блоков
   (ряд/охват, хвост буфера `occupied_until`), нерабочие клетки, закрытый день = серая колонка,
   под-дорожки для `capacity > 1` (≤ 4).
3. **`calendar_context`** += `grid` (ресурсы с `prefetch_related("rules")`, брони
   `select_related("service")` — без N+1).
4. **`booking_action` move**: `resource` (404 на чужой/неактивный), fetch-ответы
   204 / 409 JSON `{code, message}` (`outside_hours|slot_taken|closed|not_movable|invalid`);
   навык — не отказ, а flash-предупреждение (паритет ручной записи E4.2a); `next` усилить до
   `url_has_allowed_host_and_scheme` + отбой `\`. Хелперы — ВЫШЕ декораторов.
5. **Шаблон**: сетка `_tagesplan_grid.html` на `md+` (CSS grid, позиции inline-стилем), список с
   формой переноса остаётся в DOM (W0, мобильный вид и путь без JS) + `<select name="resource">`
   в форме строки (клавиатурная альтернатива DnD). В compact-режиме карточки сделки сетка без DnD.
6. **JS** (делегирование, guard повторной привязки): grab-offset по времени, оптимистичная
   перестановка, 204 → reload, 409 `outside_hours` → `confirm` → повтор с `override_hours=1`,
   прочее → snap-back + toast; время клетки — строкой с сервера (без `Date()` браузера);
   клавиатура Enter/стрелки/Esc + `aria-live`; флаг `inflight`.

## 2. Решения (по рекомендации)
- **Р-1:** без навыка — перенос разрешён с предупреждением (как ручная запись).
- **Р-2:** письмо клиенту только при смене времени; смена мастера без смены времени — без письма.
- **Р-3:** группа HF-6c двигается по одной записи (значок 🔗), групповой перенос — позже.
- **Р-4:** через полночь сетка не тянется (v1).

## 3. Замки (красные до кода) — `apps/booking/tests/test_e42b_tagesplan_grid.py`
Сервис: смена ресурса + буфер · занятый целевой (с буфером чужого) · ёмкость/`counts_party_size`
целевого · закрытие целевого даже с override · вне часов → `OutsideHours`, с override проходит ·
`NotMovable` для fulfilled/no_show/cancelled, кастом-active двигается · смена только мастера —
без письма. Вьюха: fetch 204 · 409 JSON по кодам · override → 204 · чужой/неактивный/мусорный
ресурс → 404 · без навыка → 204 + flash · аноним 302 / GET 405 / без CSRF 403 · без fetch —
прежний redirect · `next=/\evil.com` игнор. Рендер: колонки = активные ресурсы, геометрия
`grid-row`, буферная полоса; W0 — форма переноса в DOM; compact без `draggable="true"`;
`django_assert_max_num_queries` (5 ресурсов × 20 броней); `grid_rows` фолбэки.

## 4. ECC-прогоны
| Когда | Что |
|---|---|
| До кода | скиллы `django-patterns`, `django-tdd`, `postgres-patterns` (порядок блокировок), `django-security`, `accessibility`, `e2e-testing`; `docs/pitfalls.md` §3, §5 |
| После плана | `a11y-architect` — модель доступности сетки и клавиатурный путь (до вёрстки) |
| После сервиса+вьюхи | `django-reviewer`, `security-reviewer` (CSRF, 404 на чужие pk, `next`, тело 409) |
| После JS | `silent-failure-hunter` (catch/snap-back, «тихий» неуспех), Playwright-стенд 1440/390 + compact |
| Перед мержем | повторный `django-reviewer` по ветке; гейт: ruff целиком, `test_template_comments`, `test_orphan_decorators`, `i18n_quickcheck`, `npm run build:css` при новых классах |

## 5. Риски
Дедлок двух ресурсов (порядок pk) · TZ браузера (время строкой) · скрипт в перерисовываемой зоне
(делегирование) · Tailwind-классы (inline-стили или пересборка `app.css`) · кэш шаблонов в DEBUG
перед стендом · многострочный `{# #}`.

## 6. Поправки по ревью доступности (`a11y-architect`, до вёрстки)
- **Модель — НЕ `role=grid`:** колонка = `<section aria-labelledby>` (h3 = ресурс) + `<ul>` блоков
  по времени; блок = `<li>` со ссылкой на карточку брони; фон часов/штриховка — `aria-hidden`.
  Порядок DOM = порядок чтения (ресурс → время), пустые слоты не фокусируются.
- **Альтернатива перетаскиванию (2.5.7):** на КАЖДОМ блоке «⇄ Verschieben» (≥ 24 px) раскрывает
  `<details>` с той же формой переноса (время + `<select name="resource">` с видимым `<label>` +
  «Trotzdem eintragen» + Move). Перемещение стрелками в v1 НЕ делаем (не требуется для AA).
- **Фокус после reload:** перед reload — `sessionStorage` pk брони, после загрузки фокус на её
  ссылку; при snap-back фокус возвращается на блок. Постоянный `#tp-live` (`role=status`,
  `aria-live=polite`, `aria-atomic`) для текста результата/ошибки по коду 409.
- **Размер и цвет:** `min-height: 24px` у блока; статус — текстовый бейдж; буфер — штриховка +
  sr-only «Puffer bis HH:MM»; закрытая колонка — sr-only «geschlossen»; у блоков рамка 1 px
  (forced-colors), контраст текста ≥ 4.5:1.
- `confirm()` для `outside_hours` допустим (нативный).
