# A4 — iframe-виджет брони стола/записи (Termin) · план

Создан 2026-06-30. **Цель:** ресторан/Friseur встраивает форму записи (Termin) на свой
сайт через `<iframe>`, как у отеля (G10). **Email-reminder уже есть** — beat
`send_booking_reminders` (BOOKING_REMINDER_HOURS) уведомляет о любой брони, включая стол.
Значит A4 = только embed-режим витрины записи (по образцу stays).

## Источник для зеркала (stays G10 — уже работает)
- `apps/stays/public_views.py`: `_is_embed(request)`, `_render_embed(request, template, ctx, embed)`
  — ставит `embed`, `embed_qs="&embed=1"`, `base_template="storefront/_embed_base.html"`,
  `resp.xframe_options_exempt = True`.
- `templates/storefront/_embed_base.html` — минимальный layout (без шапки/футера) — **готов, реюз**.
- Виджет-сниппет в кабинете: `templates/stays/units.html` §G10 (textarea с `<iframe src="{{ embed_url }}">`).

## Что менять (booking)
**Вьюхи `apps/booking/public_views.py`:**
1. Добавить `_is_embed(request)` (копия из stays).
2. `termin_index` / `service_index` / `termin_slots` / `service_slots` — рендерить через
   общий `_render_embed`-аналог (или вручную добавить `embed`/`embed_qs`/`base_template` +
   `xframe_options_exempt` при embed).
3. POST `termin_book` / `service_book` / `karte_kaufen`: пробрасывать `embed` (из POST) во
   все `redirect(...)` (успех/ошибка/Stripe ok/cancel) — `?embed=1`, чтобы флоу не вышел из
   iframe. Stripe success/cancel URL — с `&embed=1` (как stays).
4. `termin_confirmation` — embed-aware.
5. Редирект одиночного ресурса (`termin_index` при 1 ресурсе) — сохранять `embed`.

**Шаблоны (5):** `booking_index`, `service_index`, `booking_slots`, `service_slots`,
`booking_confirmation` — заменить `{% extends "storefront/_base.html" %}` на
`{% extends base_template|default:"storefront/_base.html" %}`. Пробросить `{{ embed_qs }}` во
**ВСЕ** внутренние ссылки и `action` форм:
- back-ссылки (← All services / Back),
- день-нав prev/next (`?tag=…{{ embed_qs }}`),
- **календарь A3** `_booking_calendar.html` — уже принимает `cal_qs`; добавить `embed_qs` в
  `?tag=`/`?cal=` ссылки (либо включить embed в `cal_qs`),
- слот-ссылки (`?tag=…&slot=…{{ embed_qs }}`),
- пикер мастера (service_slots, `&resource=…{{ embed_qs }}`),
- `action="{% url 'storefront-termin-book' … %}"` + скрытый `<input name="embed" value="1">` при embed,
- ссылки на абонементы (`storefront-karten`) — опц.

**Кабинет:** сниппет `<iframe>` на странице booking-кабинета (`/dashboard/booking/` или рядом),
`embed_url = request.build_absolute_uri(reverse('storefront-termin')) + '?embed=1'`.

## Тесты
- `_is_embed` true/false; embed-страница использует `_embed_base.html` + `xframe_options_exempt`;
  все ссылки/форма несут `embed=1`; POST с `embed=1` редиректит на `…?embed=1`; конфирм embed.
- Риск-чек: ни одна ссылка во флоу записи не теряет `embed` (иначе iframe «вываливается»).

## Без миграции, без нового JS. Browser-verify желателен (iframe-флоу), но т.к. чистый
## server-render по образцу рабочего stays — достаточно тестов на присутствие `embed=1` во
## всех ссылках/форме (как у stays).
