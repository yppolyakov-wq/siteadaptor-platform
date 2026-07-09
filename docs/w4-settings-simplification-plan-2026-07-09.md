# W4 — упрощение настроек (план, 2026-07-09)

Волна аудита `docs/admin-global-audit-2026-07-09.md` §9, шаг W4. Порядок: W3 ✅ →
**W4** → W5 (Kanban-доска) → W6 (тема). Владелец: «максимально упростить, скрыть
ненужное по архетипам, визуал очень простой». Развивает S1–S6 + W2 (форма товара).

## Проблема (что видит владелец на `/dashboard/settings/`)
`templates/tenant/settings.html` = одна длинная форма из 4 fieldset'ов, все раскрыты:
1. **Contact & hours** — name/address/city/email/phone/website_url/**opening_hours (free-text)**/map_url/auto_redeem_on_scan
2. **Opening hours (structured)** — 7 строк time-inputs (`oh_<wd>_open/close`) → `opening_hours_structured`
3. **Legal** — vat_id/tax_number/small_business/register_entry/legal_responsible/impressum/privacy_policy/withdrawal_policy
4. **Operations & delivery** — service_area_plz/service_area_note/owner_digest_enabled/voucher_max_percent

Боли:
- **Дубль «часы»**: fieldset 1 (free-text `opening_hours`) + fieldset 2 (структурные). Оба про часы,
  в разных местах. Не редундантны по смыслу (free-text → витрина/футер/подтверждения; structured →
  бейдж «Открыто сейчас»), но в UI выглядят как дубль.
- **Дубль «право»**: impressum/privacy_policy/withdrawal_policy тут (плоские поля) И в отдельной
  вкладке «Rechtstexte» (LegalDoc per-locale; резолвер legal.py: LegalDoc→плоское→генерённое).
- **Всё раскрыто** → простыня; нерелевантные архетипу поля (service_area у пекарни, voucher/
  auto_redeem без loyalty) показаны всем.

## Ключевой инвариант (урок W0/W2 — НЕ повторять баг потери полей)
`settings_view` — ModelForm(`BusinessSettingsForm`). Поле, НЕ выведенное в шаблоне, при Save
затирается (Boolean→False, прочее→""). Поэтому **скрытие — ТОЛЬКО CSS (`hidden`/`<details>`),
поля ВСЕГДА в DOM**. Ни аккордеон, ни Простой-режим, ни архетип-гейт не должны `{% if %}`-опускать
поле. Замок-тест: «все 21 поля present в HTML при любом режиме/архетипе» (как `test_settings.py` W0 +
`test_product_form_w2`).

## Слайсы

### W4-1 — аккордеоны + Простой/Эксперт + свод часов (одна страница, main-win)
Файл: `templates/tenant/settings.html` (+ `settings_view` контекст — `ui_simple` уже в
context-processor; добавить флаги гейта).
- **Секции-аккордеоны** (как W2, `<details>`): ① «Kontakt & Standort» — ВСЕГДА открыт (name/address/
  city/email/phone/map_url/website_url). ② «Öffnungszeiten» — структурный редактор + free-text
  `opening_hours` под ним как «Anzeigetext (optional)» (свод обоих часов в ОДИН блок). ③ «Recht &
  Steuer» (collapsible) — vat/tax/small_business/register/legal_responsible + правовые textarea.
  ④ «Betrieb & Extras» (collapsible) — service_area_*/owner_digest/voucher_max/auto_redeem.
- **Простой/Эксперт**: в Простом — ③④ свёрнуты и помечены Erweitert (обёртка `{% if ui_simple %}`-класс,
  НЕ omit). Базовые (①②) всегда. `ui_simple` из контекста.
- **Свод часов**: два fieldset'а → один аккордеон «Öffnungszeiten».
- Партиал поля `_settings_field.html` (label+render_field+help+errors) — как `_pf_field.html` W2.

### W4-2 — гейт нерелевантных полей по архетипу/модулю (CSS-hide, НЕ omit)
- `service_area_plz/note` — только если активен delivery-контекст (jobs/handwerker ИЛИ orders с
  доставкой). Иначе — обёртка `hidden` (в DOM!).
- `voucher_max_percent`, `auto_redeem_on_scan` — только если активен `loyalty`. Иначе `hidden`.
- Флаги из `settings_view` (modules.is_module_active) → в шаблон; замок «поля в DOM при любом гейте».

### W4-3 — свод Zahlung/Versand (кросс-экранный) — карта Explore-агента ГОТОВА
Факты (агент a5e852d): оплата/доставка НЕ под хабом «Einstellungen», а размазаны:
- **Zahlung** на ДВУХ экранах: Stripe-методы (`stripe_payment_methods`) → `billing-payments`
  «Zahlarten» (`apps/billing/views.py:104`, кастомный POST); Vorkasse/банк+prepay
  (`vorkasse_enabled/bank_holder/bank_iban/bank_bic/orders_prepay`) → `orders:order-settings`
  (`apps/orders/views.py:276`, кастомный POST, рендерится на СТРАНИЦЕ СПИСКА заказов).
- **Versand/Lieferung + Abholung** целиком на orders-list (`delivery_*`, `pickup_*`, зоны PLZ).
- settings.html fieldset «Operations & delivery» = **вводящий в заблуждение лейбл**: доставки там нет
  (только `service_area_*` + owner_digest + voucher). → в W4-1 переименовать в «Betrieb & Extras».
- Смешанные паттерны записи: settings = ModelForm; billing/orders/legal = кастомный POST.

**Решение W4-3 (низкий риск, БЕЗ переписывания checkout):** НЕ сливать физически кастомные POST-экраны
(риск оплаты). Вместо — **дискаверабилити**: в хаб «Einstellungen» добавить секцию/вкладку «Zahlung &
Versand» = карточки-ссылки на существующие экраны (billing-payments «Zahlarten & Stripe», orders-settings
«Vorkasse & Lieferung»), гейтнутые по активным модулям (orders/billing). Один вход, физика не тронута.
**Отдельный слайс + чекпоинт с владельцем** (развилка: cross-links [реком.] vs физический свод).
Legal-дубль (плоские поля vs LegalDoc) — заметка: в Простом прятать правовые textarea из settings
(есть вкладка «Rechtstexte»); плоские поля оставить как фолбэк (не удалять — резолвер legal.py).

## Порядок и гейты
W4-1+W4-2 — один батч (тот же файл settings.html), локальный гейт: `test_settings.py` (расширить
«все поля в DOM» + новые флаги), ruff, `npm run build:css` (новые классы аккордеонов), template_comments.
Затем чекпоинт. W4-3 — отдельно после карты.

## Замки (обязательные)
- Все 21 поля BusinessSettingsForm present в HTML: (а) Эксперт, (б) Простой, (в) без loyalty,
  (г) без delivery. Скрытие только CSS.
- Round-trip Save (как W0 `test_settings_roundtrip`): значение не теряется после Save в Простом/
  гейт-режиме.
- Структурные часы сохраняются (существующий тест).
