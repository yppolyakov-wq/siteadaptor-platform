# AIS-W W4-0 — единый реестр готовности `apps/core/readiness.py` (2026-11-05)

План — агент ECC `planner` (2026-11-05) поверх `ais-modules-directions-assistant-plan-2026-11-05.md`
§5.1 п.4–6, §5.3, §5.7 и T-8.32 §3–§4. Кода нет. Без миграций.

## 1. Пункт

`Item(key, directions, level must|nice, check(tenant, facts), url_name, label, hint, applies_when)`.
`Facts` — ленивый мемо на `tenant._readiness_facts` (как `_nav_has_products`), один запрос на факт.

| Пункт | Ур. | Предикат |
|---|---|---|
| Контакты (адрес, телефон, e-mail) | must база | новый (сейчас `_check_company` — ИЛИ) |
| E-mail подтверждён | must база | `Tenant.email_pending` |
| Impressum полный | must база | `lite_cabinet.impressum_missing` |
| Datenschutz | must база | генерируется всегда → фактически True (так и записать) |
| Часы работы | nice база / must Termine | `setup_checklist` hours |
| Баннер/фото, «О нас» | nice | `_check_home`, `_check_about` |
| Waren: ≥ 1 товар с ценой и НДС | must | новый агрегат |
| Waren: Grundpreis весовых | must (applies_when) | новый, на `Product.grundpreis` |
| Waren: способ получения | must | новый (`orders/delivery_choice.py`) |
| Waren: способ оплаты | must | ⚠️ ON_SITE есть всегда → вопрос владельцу (§6) |
| Waren: AGB / Widerruf при доставке | must | `agb_present` → функция в `apps/core/legal`; LegalDoc widerruf |
| Lebensmittel: аллергены | must (applies_when food) | новый |
| Termine: услуга (длительность, цена/ab), ресурс «Ich» | must | новый |
| Termine: правила отмены | must | `Service.cancel_policy` (после `booking/0039` — фактически True) |
| Zimmer: номер с ценой, вместимостью и фото | must | новый (фото — решение §5.7) |
| Zimmer: Kurtaxe | nice | 0 = не взимается — законно |
| Tickets: событие + правила возврата | must | новый (`Event.cancel_fee_steps`) |
| Anfragen: форма заявки, НДС сметы | must | `normalize_anfrage` + новый |
| Speisekarte | только nice | — |

## 2. API

`items_for(tenant, *, direction=None, level=None)`, `missing(...)`, `sell_ready(tenant, direction)`,
`sell_allowed(tenant, direction)` (флаг off → True). Мемо только на объекте тенанта, бюджет ≤ 3
запросов на направление, чтение TENANT-моделей только в своей схеме (иначе «unknown»), ошибка БД →
выполнено (fail-open), в отчёте — «error». Из хрома кабинета не вызывается (замок).

## 3. Потребители

W4-0, байт-в-байт: `lite_home.next_step` (impressum), `setup_checklist` hours. **Одно изменение
поведения:** шаг «Recht» мастера → `impressum_missing` вместо `LegalDoc.exists()` (§ 5 DDG).
Позже: `completeness` legal (W4-1), `_check_company/home/about` (W4-1/2), экран «Laden eröffnen» и
шторка помощника (W4-5/A-0). Гейты доступности модулей (`gift_purchase_active`,
`promotions.response.can_buy`) в реестр не сводятся — помощник зовёт их как есть.

## 4. Гейт и отчёт

`READINESS_SELL_GATE` (default False). Исключение работающим магазинам —
`site_config["readiness"]["exempt"]` (presence-minimal + passthrough в `normalize`), ставит только
`readiness_report --stamp-exempt --apply` (продажи за 90 дней, не демо). Точки вызова в кассе — в
W4-5, в W4-0 только хелпер. `readiness_report [--tenant] [--json] [--stamp-exempt [--apply]]` —
зеркало `package_report`: итог «реальных бизнесов, которым закрылась бы касса: N».

## 5. Замки (до кода)

Реестр согласован с `directions` и reverse'ится · паритет `next_step` · три случая шага «Recht» ·
`django_assert_max_num_queries(3)` на направление, повтор — 0 · вне схемы не читает и не роняет
транзакцию · `sell_allowed` при флаге off/on/exempt · `normalize` хранит exempt (golden целы) ·
скан «не из хрома» · отчёт без `--apply` не пишет, демо не считаются · i18n msgid в 5 `.po`.

## 6. Риски и вопрос владельцу

**Решено владельцем 2026-11-05:** при доставке требовать способ оплаты кроме «на месте»
(карта или Vorkasse) — пункт `waren.prepay`; работающие магазины получают исключение.


- **Оплата:** «на месте» доступна всегда, поэтому пункт «способ оплаты» всегда выполнен. Для
  ДОСТАВКИ нужен способ, отличный от «на месте» (иначе продавать с доставкой можно без оплаты)?
  Если да — магазины с доставкой без Stripe/Vorkasse попадут под гейт (они получат исключение).
- Шаг «Recht» сдвигает рельсу части живых тенантов (`completed` не понижается).
- Дорогие предикаты на больших каталогах — только агрегат/`exists()` нарушителя.

## 7. ECC-прогоны

До кода: скиллы `django-patterns`, `django-tdd`, `postgres-patterns`, `django-security`. После плана —
`architect`. Перед мержем: `django-reviewer`, `database-reviewer`, `silent-failure-hunter`,
`security-reviewer`. Playwright не нужен (UI нет).
