# B4/CM-9 — купоны-триггеры / кампании по сегментам (план, 2026-07-03)

ID — каталог §3 (B4.1–B4.4). Идея B4 (`feature-ideas-2026-07-02.md`) + CM-9
(`market-content-analysis-2026-07-02.md`) — один трек: персональные купоны
сегменту CRM-базы, рассылка ТОЛЬКО opt-in (UWG §7). Разведка агентом
2026-07-03 (карта file:line в транскрипте).

## Что уже есть (переиспользуем, не строим)

- UWG-гейт: `consented_customers()` (`promotions/newsletter.py:46`) —
  opt-in + не отписан + email; DOI, one-click unsubscribe, List-Unsubscribe
  (RFC 8058) — всё в `send_campaign` (`newsletter.py:68-92`), идемпотентно
  по `campaign:{id}:{customer.id}`.
- Генератор кодов: `generate_vouchers(customer=…)`
  (`promotions/services.py:173`); гашение атомарно, `used_count` инкрементится
  в `redeem_voucher`/`spend_voucher` → аналитика «погашено» бесплатна.
- LTV/последняя покупка: `finance.RevenueEntry.customer`
  (`related_name="revenue_entries"`, наполняют все 5 FSM-доменов); паттерн
  annotate-выборки — `purge_due_customers` (`promotions/tasks.py:201`).

Гэпы: (1) метка кампании на `Voucher`; (2) функция сегмент-выборки;
(3) связка «код-на-клиента → письмо»; (4) авто-триггер.

## Дизайн

**Модель `CouponCampaign`** (promotions, TENANT; рядом с NewsletterCampaign):
`name`, сегмент — `tag` (blank), `inactive_days` (null), `top_ltv` (null),
комбинируются AND; параметры кода — `discount_percent`/`discount_cents`/
`min_order_cents`/`valid_days` (срок жизни кода от выдачи); письмо —
`subject`/`body` (DE, авторский текст владельца, как newsletter; код и
условия дописываем сами); `kind` — `manual`|`auto_winback`; `status` —
draft|sent (manual) / active|paused (auto); `sent_at`, `recipient_count`.

**`Voucher.campaign`** — FK SET_NULL на `promotions.CouponCampaign`
(loyalty-миграция; код переживает удаление кампании). Аналитика:
выдано = `campaign.vouchers.count()`, погашено = `Sum("used_count")`.

**`segment_customers(tag=…, inactive_days=…, top_ltv=…)`** в `newsletter.py`
поверх `consented_customers()`: tag → `tags__contains=[tag.lower()]`;
inactive_days → `annotate(Max("revenue_entries__date")) < cutoff` (клиенты
БЕЗ покупок отсекаются NULL-ом — win-back целит бывших покупателей, это
осознанно); top_ltv → `annotate(Sum(amount)).order_by("-ltv")[:N]`
(слайс — последним).

**`send_coupon_campaign(campaign, base_url)`** — клон `send_campaign`:
по сегменту, на клиента get-or-create персонального кода
(`filter(campaign, customer).first()` — повторный прогон не дублирует коды),
письмо `notify(dedupe_key=f"coupon:{campaign.id}:{customer.id}", headers=
List-Unsubscribe)`. Sent-гейт как у newsletter.

**v2 авто-win-back БЕЗ Tenant-миграции:** настройки живут на самой
кампании `kind=auto_winback` (get_or_create, та же модель: inactive_days +
discount + valid_days; toggle active/paused на странице). Beat-задача
daily по схемам: активные auto-кампании → сегмент → дедуп «клиенту уже
выдавали auto-код в окне inactive_days» (`vouchers.filter(customer,
created_at__gte=cutoff)`) → код+письмо (dedupe_key с датой выдачи).

## Слайсы

- **B4.1 (S) — модель+сегменты.** `CouponCampaign` (миграция promotions) +
  `Voucher.campaign` (миграция loyalty) + `segment_customers()` + тесты
  (гейт opt-in внутри, tag/inactive/top-LTV, NULL-семантика).
- **B4.2 (M) — кампания end-to-end.** `send_coupon_campaign` + страница
  `/promotions/kampagnen/` (`promotions:coupon-campaigns`): список,
  создание (live-счётчик получателей по сегменту), отправка, удаление
  draft, аналитика выдано/погашено. Ссылки со страниц vouchers/newsletter.
  Тесты: идемпотентность (коды не дублируются, письма дедупятся),
  не-opt-in не получает, sent-гейт.
- **B4.3 (S) — вход из CRM.** `customer_list`: кнопка «Kampagne für diese
  Auswahl» (при активном фильтре) → форма кампании с prefill `?tag=`.
- **B4.4 (M) — v2 авто-триггер.** Кампания `auto_winback` + beat
  `send_winback_coupons` (86400, `@idempotent_task`, `_iter_tenant_schemas`)
  + дедуп-окно + toggle в UI. Тесты: окно не дублирует, paused/выкл. молчит,
  только consented.

Замки: письма только `consented_customers` (сегмент строится ПОВЕРХ гейта —
не-opt-in недостижим по построению); повторная отправка кампании — no-op;
код клиента одноразовый (`max_uses=1`), срок из `valid_days`; beat не шлёт
дважды в окне. «Первый заказ −10 %» и Happy-Hour (авто-применение на
чекауте, другая механика) — НЕ в этом треке, roadmap §Отложено.
