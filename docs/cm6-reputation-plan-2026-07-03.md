# CM-6 — Репутационный модуль (план, 2026-07-03)

ID — каталог §3 (CM-6.1–6.4). Разведка агентом (file:line в транскрипте).
Факты: кабинетной работы с отзывами НЕТ (ни views/urls у apps.reviews, ни
admin); `is_published` переключать негде; ответов владельца не существует;
пост-визитные просьбы есть у booking/stays/events, у orders — нет.
Портальные BusinessReview (SHARED, про бизнес целиком, модерация
super-admin) — ВНЕ CM-6 (отдельный контур).

## Слайсы

- **CM-6.1 (S) — кабинет «Bewertungen».** Новые apps/reviews/views.py +
  urls.py: список отзывов тенанта (фильтр kind/статус) + POST-toggle
  `is_published` (скрыть/показать). Резолвер имени сущности по kind
  (bulk, fail-soft: удалённая → «—»). Новый ModuleSpec("reviews", ⭐
  «Bewertungen», recommended_for=ВСЕ типы — урок default_disabled_for),
  url_prefixes /dashboard/reviews/. Замки: список/скрытие (пропадает с
  витрины), гейт модуля, test_modules += reviews осознанно.
- **CM-6.2 (S/M) — ответы владельца.** Review += reply_text/replied_at
  (миграция reviews/0003, 1:1 — отдельная модель избыточна); reply-форма
  в кабинете; витрина: блок «Antwort des Betreibers» в ДВУХ местах —
  `_entity_reviews.html` (service/stay/event) и инлайн-секции
  product_detail.html.
- **CM-6.3 (S) — сводка.** services.owner_overview(): avg/count по
  тенанту + разбивка по kind + счётчики скрытых/без ответа; KPI-строка
  в шапке списка CM-6.1.
- **CM-6.4 (S) — product post-purchase просьба об отзыве.**
  Order.post_purchase_sent_at (миграция orders/0013) + письмо
  `order_post_purchase` (ссылки на /sortiment/<pk>/bewerten/ по товарам
  заказа) + beat-задача по образцу booking post_visit (окно от
  picked_up/shipped); verifier has_purchased уже есть.

Порядок: 6.1 (+6.3 в ту же страницу) → 6.2 → 6.4.
