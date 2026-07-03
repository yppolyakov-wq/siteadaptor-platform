# Идея D3 — партнёрка веб-студий/фрилансеров (план, 2026-07-03)

ID — каталог §3 (D3.1–D3.5). Решения владельца (2026-07-03): **делаем**;
вознаграждение — «несколько вариантов» (per-partner конфиг); v1-кабинет —
**read-only список клиентов**; **этап 2 — вход в кабинеты клиентов**.
Разведка агентом: auth per-схемный (`auth_user` в каждой схеме),
`core.Membership` OneToOne (1 юзер = 1 тенант) — потому партнёрская учётка
живёт на PUBLIC-домене (allauth там уже смонтирован, своя `auth_user`);
referral-механизма нет; поля «кто привёл» на Tenant нет; скидок в
подписочном Checkout нет.

## Дизайн

**`apps.partners` (SHARED, по образцу apps.support):** модель `Partner` —
`user` OneToOne на public-`auth_user`, `name`, `code` (SlugField unique —
реф-код), `contact_email`, `is_active`, конфиг вознаграждения:
`reward_kind` ∈ {"" нет, client_discount, revshare} + `discount_percent`
(справочно; сам купон — `stripe_coupon_id`) + `revshare_percent`.
Wholesale (партнёр платит оптом) — ⏸ отложено: ломает «1 Stripe-customer =
1 тенант».

**`Tenant.partner`** — FK SET_NULL (`tenants/0023`), related_name="tenants".

**Атрибуция:** `?ref=<code>` на странице регистрации → session
(`partner_ref`) → kwarg `partner_code` в `start_business_provisioning`/
`create_business` → `_new_tenant` резолвит активного партнёра
(неизвестный/выключенный код тихо игнорируется).

**Кабинет `/partner/` (urls_public, login_required):** для юзера без
Partner-профиля — вежливый отказ; для партнёра — реф-ссылка
(`https://<base>/?ref=<code>`), список его тенантов (name/type/city/
created_at/subscription_status — всё из public-схемы, прецедент
admin_dashboard), счётчики (всего/активных/на триале), при
reward_kind=revshare — живая сводка «активные × 39 € × %/мес».

**Деньги (варианты, per-partner):** client_discount →
`create_checkout_session` подписки получает `discounts=[{"coupon":
partner.stripe_coupon_id}]` (купон владелец заводит в Stripe Dashboard,
id — в админке партнёра); revshare → сводка в кабинете партнёра +
админ-список (выплата вне Stripe, банковский перевод). Оба механизма
сосуществуют, выбирается на партнёре.

**Админ:** Partner в unfold-админке (list: name/code/reward/тенантов) +
пункт UNFOLD-навигации; партнёр создаётся суперадмином (v1 — без
self-signup партнёров).

## Слайсы

- **D3.1 (M)** — apps.partners + Partner + `Tenant.partner`
  (миграции `partners/0001` + `tenants/0023`) + админ + UNFOLD nav.
- **D3.2 (S)** — атрибуция `?ref=` (session → services kwarg → FK),
  fail-safe.
- **D3.3 (M)** — кабинет `/partner/` read-only + реф-ссылка + счётчики +
  revshare-сводка.
- **D3.4 (S)** — шов скидки: `discounts=[{coupon}]` в подписочном
  Checkout при client_discount (fail-safe: пустой coupon = как раньше).
- **D3.5 (⏭ этап 2, решение владельца «делаем + вход»)** — вход партнёра
  в кабинеты клиентов: кросс-схемный провижининг Membership + refactor
  OneToOne→multi-tenant. Отдельный план-док перед стартом (крупный
  refactor auth).

Замки: атрибуция не ломает онбординг при любом мусоре в `?ref=`;
Checkout без купона байт-в-байт прежний (паритет); кабинет партнёра
не отдаёт чужих тенантов; Partner неактивен → код не атрибуцирует и
кабинет закрыт.

## Пост-ревью (2026-07-03, адверсариальный воркфлоу, 4 находки)

Исправлено: (1) savepoint в `_resolve_partner` (except внутри atomic
отравлял транзакцию при DB-ошибке — окно «код раньше миграции»);
(2) `partner_ref` одноразовый (pop); (3) протухший Stripe-купон →
ретрай Checkout без скидки (best-effort); (4) N+1 в админ-списке
(annotate). **Осознанно принятый риск:** реф-коды — человекочитаемые
слаги, задаются админом; подбор кода даёт чужую скидку (эквивалент
«реф-ссылка публична by design», оракула валидности нет — проверка
стоит полной регистрации). Рекомендация админу: код с энтропийным
суффиксом (studio-x7k2). Rate-limit — при появлении злоупотреблений.
