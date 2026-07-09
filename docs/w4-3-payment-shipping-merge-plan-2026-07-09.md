# W4-3 — единый экран «Zahlung & Versand» (физический свод, план 2026-07-09)

Решение владельца (2026-07-09): **физический свод** — все настройки оплаты/доставки на
ОДНОМ экране, одна форма/Save. Карта дублей — `docs/admin-global-audit` + Explore-агент
(см. `w4-settings-simplification-plan §W4-3`). Риск: поля кормят checkout → максимум
осторожности (переиспользуем существующую логику записи, характеризационные замки ДО правок).

## Что сводим (сейчас размазано по 3 экранам)
| Секция | Поля Tenant | Сейчас пишет | Хелперы |
|---|---|---|---|
| Stripe-Zahlarten | `stripe_payment_methods` | `billing.payments_methods` (`views.py:104`) | `STRIPE_METHOD_CHOICES` |
| Abholung/Prepay | `orders_prepay`, `pickup_min_cents`, `pickup_locations` | `orders.order_settings` (else / delivery) | `_parse_pickup_locations` |
| Vorkasse/Bank | `vorkasse_enabled`, `bank_holder/iban/bic` | `orders.order_settings` (form=vorkasse) | — |
| Lieferung/Versand | `delivery_enabled`, `delivery_fee/free/min_cents`, `delivery_area`, `delivery_restrict_to_zones`, `delivery_zones` | `orders.order_settings` (form=delivery) | `_eur_to_cents`, `_parse_delivery_zones`, `_zone_rows`, `ZONE_ROWS=6` |
| Stripe-Connect (статус/OAuth) | `stripe_connect_id`, `payments_enabled` | `payments_connect/callback` (OAuth) | connect.* |

## Архитектура свода (низкий риск)
**Принцип: НЕ переписываем логику записи — извлекаем её в переиспользуемые хелперы,
старые экраны продолжают звать те же хелперы. Единый экран зовёт все.**

1. **Извлечь save-хелперы** (тот же код, без изменения семантики):
   - `apps/orders/views.py`: `save_delivery(tenant, request)`, `save_vorkasse(tenant, request)`,
     `save_prepay(tenant, request)` — тела из `order_settings`; сам `order_settings` теперь
     диспатчит на них (поведение старого экрана байт-в-байт).
   - `apps/billing/views.py`: `save_stripe_methods(tenant, request)` — тело из `payments_methods`;
     `payments_methods` зовёт его.
2. **Гейт по СЕНТИНЕЛУ секции (ключевой guard от потери данных):** единый POST-обработчик
   сохраняет секцию ТОЛЬКО если пришёл её скрытый сентинел (`sec_stripe`/`sec_prepay`/
   `sec_vorkasse`/`sec_delivery`). Сентинел рендерится ТОЛЬКО когда секция показана (гейт по
   модулю). Секция скрыта (не в DOM) → нет сентинела → save пропущен → данные целы. Это НАДЁЖНЕЕ
   «всё в DOM + CSS-hide» для большой мульти-секционной формы (нельзя случайно затереть delivery,
   сохраняя vorkasse).
3. **Новый экран** `apps/core/views.py::payment_settings` (GET рендер + POST диспатч):
   - GET: контекст = все текущие значения + `method_choices`/`selected_methods` (billing) +
     `zone_rows`/`pickup_locations`/EUR-строки (orders) + connect-статус.
   - POST: `if sec_stripe: billing.save_stripe_methods(...)` … и т.д.; один `messages.success`;
     redirect на себя (`payment-settings`).
   - URL `dashboard/settings/payments/` name `payment-settings`.
4. **Хаб**: вкладка «Zahlung & Versand» в `HUB_TABS["settings"]` (nav_key `payments`, module_key
   None — видна всегда; секции внутри гейтятся). Старые экраны billing-payments/orders-settings
   ОСТАЮТСЯ рабочими (не ломаем закладки/ссылки), но нав ведёт на новый единый экран.
5. **Гейт секций по модулю:** Stripe — если `connect.is_connect_configured()`; Abholung/Vorkasse/
   Lieferung — если активен `orders`. Connect-кнопка (OAuth) — ссылками на существующий флоу
   (не переносим OAuth).

## Замки (характеризационные — ДО рефактора)
- `save_delivery/vorkasse/prepay/stripe_methods` пишут ровно те же поля, что старые обработчики
  (тест: POST → значения на Tenant; зоны/pickup JSON; IBAN нормализация upper/без пробелов;
  eur→cents). Снять на ТЕКУЩЕМ коде (через `order_settings`/`payments_methods`), затем refactor
  обязан их сохранить.
- Единый экран: (а) сохраняет каждую секцию по сентинелу; (б) секция без сентинела НЕ трогает
  свои поля (guard потери); (в) все поля показанных секций в DOM.
- `order_settings`/`payments_methods` старые тесты — зелёные после рефактора (делегируют хелперам).

## Порядок (батч, отдельные коммиты)
1. Характеризационные тесты текущего поведения (orders + billing).
2. Извлечь хелперы (orders, billing) — старые вьюхи делегируют; прогнать замки (без изменений).
3. Новый `payment_settings` + шаблон `tenant/payment_settings.html` + URL + хаб-вкладка + тесты.
4. Нав/дискаверабилити: вкладка в хабе; опц. редирект-подсказки со старых экранов.
5. Гейт локально: orders+billing+core+tenants (settings/nav) + ruff + build:css + template_comments.
Затем чекпоинт с владельцем (показать экран), опц. деплой.
