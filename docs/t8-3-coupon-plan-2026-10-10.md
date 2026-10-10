# T-8.3 «Coupon holen» — купон акции с погашением сканером (2026-10-10)

Пункт 4 общего плана `t8-roadmap-2026-10-10.md`. Решение владельца Р-2 «купон да»;
анализ лёгкой версии §3 (вид отклика «Coupon»): клиент получает код и QR, бизнес гасит тем
же экраном «Einlösen»; лимит штук и «1 на человека»; счётчики «получено / погашено».

## 0. Факты (разведка 2026-10-10)

- `loyalty.Voucher` (TENANT, таблица `promotions_voucher`): `code` unique(12), `max_uses`,
  `used_count`, `expires_at`, `customer` FK (nullable), скидка %/€/мин. заказ, `campaign` FK.
  Связи с `Promotion` НЕТ. Коды `V-XXXXXX` (`services._unique_voucher_code`, алфавит без
  0/O/1/I). Погашение `redeem_voucher` (atomic, select_for_update), откат `unredeem_voucher`.
- `spend_voucher` — единая точка онлайн-оплаты кодом (orders/booking/jobs): любой активный
  Voucher со скидкой уходит в чекаут. Купон акции туда попадать НЕ должен.
- Сканер «Einlösen» (`redeem_home/detail/action`) знает только `Reservation.reference_code`
  (`R-…`); JS сканера открывает абсолютный URL из QR как есть.
- Движок резерва: anti-oversell conditional UPDATE по `available_quantity`, honeypot,
  `ratelimit.hit`, `form_token` в кэше, `_get_or_create_customer` (имя обязательно).
- Идентичности устройства (cookie) в проекте нет.
- Отклик акции — `promotions/response.py` (T-8.2); buy-box и CTA ветвятся по нему.

## 1. Решение

**Модель (⚠️ миграция `loyalty/0006`, аддитивная):** `Voucher.promotion` — nullable FK на
`promotions.Promotion` (`related_name="coupons"`, SET_NULL). Купон = Voucher с `promotion`,
`max_uses=1`, `expires_at = promotion.ends_at`, БЕЗ скидочных полей (скидку описывает сама
акция). Код `C-XXXXXX` тем же генератором (префикс параметром).

**Онлайн-оплата:** `spend_voucher` отбивает купоны акций (`promotion_id is not null` →
`not_found`) — код живёт только на кассе. Замок.

**Выдача** `services.issue_coupon(promo, *, name, email, phone, device_key)`:
- акция active; отклик `coupon`;
- «1 на человека»: тот же `device_key` (подписанная кука `sa_cp`, без трекинга — одна
  случайная строка на браузер, только для этой проверки) ИЛИ тот же e-mail/телефон →
  возвращается уже выданный купон (идемпотентно, не новый);
- лимит: `available_quantity` списывается тем же conditional UPDATE (`OutOfStock` → «Alle
  Coupons sind vergeben»);
- контакт необязателен; клиент создаётся только при e-mail/телефоне (CRM, UWG-гейт не трогаем).

**Витрина:** отклик `COUPON` («Coupon holen») в реестре; кнопка на странице акции → форма
(имя/e-mail/телефон необязательны + honeypot/ratelimit/form_token) → страница купона
`/coupon/<code>/`: крупный код, QR, срок, условия, «An der Kasse zeigen». QR кодирует
адрес сканера `promotions:redeem-detail` (как у резерва). Повторный заход с той же кукой —
сразу тот же купон.

**Сканер:** `redeem_detail` при `C-…` ищет купон; карточка «Coupon · <акция> · gültig bis»
+ кнопка «Einlösen» (`redeem_voucher`); `auto_redeem_on_scan` уважается; погашенный —
«bereits eingelöst am …».

**Кабинет:** выбор отклика «Coupon holen» в форме акции и в ассистенте T-8.4; счётчики в
списке «Coupons N · eingelöst M»; флаер T-8.9 — призыв «Scannen & Coupon holen».

**Демо:** у кафе и мода-лавки лёгких китов по одной купон-акции.

## 2. Замки (до правок)

- выдача: код `C-`, срок = конец акции, лимит списан; повтор с той же кукой / тем же
  e-mail → тот же купон, лимит не тронут; лимит исчерпан → отказ без купона;
- купон не проходит `spend_voucher` (чекаут) и не выдаётся у неактивной акции;
- сканер находит купон, гасит один раз, второй раз — «bereits eingelöst»;
- витрина: отклик coupon рисует форму на `/coupon/`-приёмник без полей доставки/оплаты;
  страница купона показывает код и QR;
- счётчики в списке без N+1 (`distinct=True`);
- отклик `coupon` проходит форму акции, ассистент и флаер.

## 3. Вне объёма

Персональная скидка купона в онлайн-корзине (купон — касса), push-напоминание о сроке,
Wallet-пасс (P2.8), купон без акции (это кампании B4).
