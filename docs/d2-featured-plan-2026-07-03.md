# Идея D2 — self-serve featured + Anzeige: докрутка (план, 2026-07-03)

ID — каталог §3 (D2.1–D2.5). Разведка агентом 2026-07-03. Главный вывод:
**ядро D2 уже готово** — P2.4b (self-serve покупка продвижения акции:
`AggregatorListing.featured_until`+`featured_payment_ref`, планы 7/14/30 дней
в `billing/featured.py` c env-оверрайдом, платформенный Stripe `mode=payment`
+ webhook `kind=featured` c двойной идемпотентностью, `split_featured` сверху
первой страницы, «★ Anzeige» на карточках `_cards.html`) и бизнес-страница на
главном `/entdecken` (E-2 слайс 2). D2 = закрыть гэпы self-serve. Полный E-11
(claim-your-business, featured уровня бизнеса) — отдельно, позже (L).

## Гэпы (verified)

1. Anzeige НЕ на карте: `_map.html` строит map_points без featured-флага
   (UWG-риск: рекламная позиция без пометки на одной из поверхностей).
2. Точка входа — только карточка на форме акции (`promotion_form.html`);
   из списка акций «продвинуть» не видно.
3. Цены — hardcode+env; кабинет/админ-настройки нет (ОК для v1, владелец
   задаёт env; отложить).
4. Owner-аналитики показов/кликов featured нет — владелец не видит эффект.
5. Self-serve покупки для stays/events нет (механика featured_until общая).

## Слайсы

- **D2.1 (S) — Anzeige на карте.** Пробросить `featured` в map_points +
  бейдж «Anzeige» в попапе/маркере `_map.html`. Замыкает «Anzeige на всех
  поверхностях». Заодно перепроверить экранирование (аудит 2026-07-01
  находил 2×XSS в карте).
- **D2.2 (S) — вход из списка акций.** В `promotion_list` на active-акциях
  бейдж «beworben bis …» / ссылка «Bewerben ★» → `promotions:promotion-feature`
  (гейт `featured_enabled`).
- **D2.3 (M) — owner-аналитика featured.** Счётчики показов/кликов на
  `AggregatorListing` (impressions_count/clicks_count, F+update без гонок;
  инкремент показов — в местах рендера split_featured, кликов — редирект-
  счётчик или клик-параметр) + блок «Bisher: X Aufrufe · Y Klicks» на
  `promotion_feature.html`. Дёшево и закрывает «не вижу эффекта».
- **D2.4 (M) — self-serve featured для stays/events.** Реюз флоу: generic
  вью поверх `AggregatorListing` (kind любой) или зеркала в booking/events.
  Решить при реализации — предпочтительно generic в promotions → перенос
  URL в нейтральный неймспейс не делаем (ссылки уже живут).
- **D2.5 (⏸ отложено) — цены в кабинете/суперадмине.** env-оверрайда
  достаточно; вернуться при спросе.

Замки: featured-выдача без изменений (split_featured не трогаем в D2.1/2.2);
Anzeige-пометка обязана быть везде, где позиция оплачена (UWG §5a); счётчики
не ломают keyset-пагинацию и кэш витрины.
