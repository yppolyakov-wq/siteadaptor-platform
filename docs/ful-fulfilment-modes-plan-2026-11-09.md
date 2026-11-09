# FUL — «Waren» + способы получения (Abholung · Lieferung · Versand) — 2026-11-09

Фидбэк владельца (скриншот регистрации): чипы «Waren im Laden & zum Abholen» и «Online-Shop mit
Lieferung & Versand» — одно и то же и вводят в заблуждение («онлайн-магазин без самовывоза»).
По сути это способ получения товара. Просьба — проверить всю стратегию (ECC: `architect`).

## 1. Что нашла проверка (architect, файлы:строки — в отчёте сессии)

| # | Проблема | Где |
|---|---|---|
| A | Чип «Online-Shop … Lieferung & Versand» НЕ включает доставку: бизнес стартует только с самовывозом | `signup_directions.py:119-138`, `services.py:94-98` |
| B | Чип «online» почти ничего не делает: `orders` и так рекомендован всем товарным типам | `modules.py:225` |
| C | Самовывоз выключить НЕЛЬЗЯ: чистый онлайн-магазин без лавки всё равно предлагает «Abholung im Geschäft» (а тип обещает «ohne Ladengeschäft») | `delivery_choice.py:42-45`, `_fulfillment_choice.html:11,31`, `onboarding.py:346` |
| D | Курьер по городу и посылка по Германии — один флаг `delivery_enabled` (зоны по PLZ — модель курьера; посылке нужна ставка по стране) | `tenants/models.py:133-149`, `orders/services.py:213-234` |
| E | ⚖️ Widerruf показывается только при доставке, но онлайн-заказ с самовывозом обычно тоже Fernabsatz (§ 312c BGB) — **к юристу** | `tenants/models.py:699-707`, `promotions/public_views.py:3205` |
| F | «Verkauf öffnen» спрашивает только «Liefern Sie auch?» (да/нет) | `sell_questions.py:89-102` |
| G | «zzgl. Versand» и при курьере; портал и Google local feed не знают способа получения | `product_detail.html:60`, `catalog/feed.py:72,242` |

Направление «Waren» в реестре одно — это верно; ошибка в регистрации и в модели данных.

## 2. Целевая модель
Одно направление **«Waren verkaufen»** + вопрос **«Wie bekommen Kunden die Ware?»** —
три независимых способа:

| Способ | Хранение |
|---|---|
| Abholung im Geschäft | новый `Tenant.pickup_enabled` (default True = как сейчас) |
| Lieferung vor Ort (курьер) | существующий `delivery_enabled` + зоны/сбор/минимум |
| Versand (посылка) | новые `Tenant.shipping_enabled`, `shipping_fee_cents`, `shipping_free_cents` |

Один читатель `apps/orders/fulfilment.py::modes(tenant)` и один писатель `set_modes` (запрет
«всё выключено» при активных заказах). Корзина показывает только включённые способы (один —
без выбора); самовывоз выключен → POST `fulfillment=pickup` отклоняется. Одна миграция
`tenants/00xx` (SHARED, аддитивная + данные: всем `pickup_enabled=True`).

## 3. Инкременты (замки до кода)
- **F-0** (без миграции): чип «online» включает доставку (A); тексты чипов.
- **F-1** миграция + `fulfilment.modes()` + корзина/резолвер fail-closed; паритет «по умолчанию байт-в-байт».
- **F-2** «Verkauf öffnen» — те же три галочки, тот же писатель.
- **F-3** регистрация: один чип + три галочки (у `online_shop` предвыбран Versand); старые
  заявки с «online» = Waren + Versand (алиас на релиз).
- **F-4** `shipping_quote`, PAngV-нота по способу («zzgl. Versand» / «zzgl. Liefergebühr» / ничего), readiness.
- **F-5** ⚖️ Widerruf по «онлайн-заказ возможен» — за флагом, после юриста.
- **F-6** Google local feed только с самовывозом; метки портала «Liefert»/«Versand» (SHARED-миграция).
- **F-7** отчёт `fulfilment_report` по существующим бизнесам (кто с доставкой = посылка) + демо-киты.

ECC: `django-reviewer` каждый шаг; `database-reviewer` F-1/F-6; `security-reviewer` F-1
(fail-closed POST); `a11y-architect` F-3 (новые контролы регистрации); Playwright-стенд регистрации и корзины.

## 4. Решения владельца (нужны до F-1)
- Р-1: три способа (Abholung · Lieferung vor Ort · Versand) — да / два (Abholung · Lieferung)?
- Р-2: у курьера и посылки разные тарифы (зоны PLZ vs ставка по стране) — да?
- Р-3: Widerruf при онлайн-заказе с самовывозом — отдать юристу (F-5 за флагом)?
- Р-4: существующие бизнесы с доставкой — посылку включать только после подтверждения владельцем (отчёт), без тихой смены.
