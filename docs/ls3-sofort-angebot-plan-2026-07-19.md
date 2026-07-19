# LS-3 «Sofort-Angebot» — план (2026-07-19)

Персональное предложение из чата → оплата в 1 клик. Пункт A1 ТЗ
`docs/next-gen-master-tz-2026-07-19.md §3`; план-док ОБЯЗАТЕЛЕН по §4.7
(развилка «обобщать jobs.Angebot vs новая модель»). Разведка кодовой базы —
фоновым Explore-агентом 2026-07-19 (jobs/inbox/orders/sellable_manage/письма);
ключевые факты ниже перепроверены чтением кода.

## 1. Развилка «модель предложения» — РЕШЕНИЕ: новая лёгкая модель в `apps/orders`

Варианты:

- **(a) Обобщить `jobs.Job`.** Отвергнут. Job — это весь жизненный цикл
  Handwerker (Anfrage→Angebot→Auftrag→Rechnung): vehicle-поля, `finance.
  compute_totals` (net/VAT), Rechnung/DATEV, свой FSM с commit_stock, оплата
  ТОЛЬКО частичная (Anzahlung-депозит), `customer` PROTECT, намеренно НЕ
  sellable (`sellable.py` докстринг). Обобщение = риск для живого архетипа A7
  ради чужого флоу. Jobs НЕ трогаем вообще → «паритет jobs-сметы байт-в-байт»
  выполняется тривиально (ни один файл jobs не меняется).
- **(b) Сразу создавать Order при отправке предложения.** Отвергнут:
  непринятое предложение засоряло бы канбан/статистику, «отклонение» пришлось
  бы моделировать отменой заказа, у анонимного треда нет name/email для
  Order.customer (PROTECT).
- **(c) ✅ Новая лёгкая модель `Offer`+`OfferLine` в `apps/orders`** (имена
  английские как Order/OrderItem; в UI — «Angebot». НЕ «Bestellung» — имя
  занято закупками inventory, и НЕ «Angebot»-класс — семантическая коллизия с
  jobs). Предложение живёт отдельно; **принятие конвертирует его в обычный
  Order**, дальше всё — существующими путями (оплата, канбан, статусы, письма
  заказа). Ключевой факт: `OrderItem.product` уже nullable +
  `unit_price`/`title_snapshot` обязательны (прецедент — комбо-позиции), т.е.
  заказ со свободными строками поддержан МОДЕЛЬЮ уже сейчас; нужен лишь новый
  параметр `custom_lines` в `create_order`.

## 2. Модель (⚠️ миграция `orders/00XX` — новая, аддитивная)

```python
class Offer(TimestampedModel):                 # apps/orders/models.py
    STATUSES = open / accepted / declined / cancelled   # + «истёк» — вычисляемо
    token = UUIDField(default=uuid4, unique=True)       # как jobs.public_token
    conversation = FK("inbox.Conversation", SET_NULL, null)  # строковый ref, без циклов
    customer = FK("promotions.Customer", SET_NULL, null)     # снимок из треда
    customer_name / customer_email                      # снапшоты (могут быть пустые)
    note = TextField(blank)                             # личное сообщение на странице
    valid_until = DateField(null, blank)                # пусто = бессрочно
    status = CharField(choices=STATUSES, default="open")
    order = FK(Order, SET_NULL, null)                   # созданный при принятии
    accepted_at / declined_at = DateTimeField(null)

class OfferLine(TimestampedModel):
    offer = FK(Offer, CASCADE, related_name="lines")
    kind = CharField(blank)      # ''=custom | product/service/stay/event/combo (провенанс)
    ref_id = IntegerField(null)  # pk источника (снимок, НЕ FK — цена/название заморожены)
    title = CharField(200); qty = PositiveIntegerField(default=1)
    unit_price = DecimalField(10,2)   # БРУТТО, как OrderItem (PAngV) — БЕЗ net/VAT-математики jobs
    position = PositiveIntegerField(default=0)
```

`Offer.total` = Σ qty×unit_price (property). `is_expired` = valid_until в
прошлом при status=open. FSM `OfferSM` (apps/orders/state_machine.py или рядом):
open→accepted/declined/cancelled, терминалы дальше не двигаются; смена статуса
только `.apply()` (конвенция). Хуки on_transition: письма + system-message в
тред (см. §4).

## 3. Сервис + расширение `create_order`

`apps/orders/offers.py` (новый модуль, чтобы не раздувать services.py):

- `send_offer(conversation, lines, valid_until, note, author)` → Offer+lines,
  снимок customer из треда, system-`Message` в тред («📄 Angebot über 45,00 € —
  gültig bis …»), письмо клиенту (если email известен) с ПРЯМОЙ ссылкой на
  `/o/<token>/` — паттерн jobs `quoted` (`_base_url + reverse`), dedupe
  `offer:<id>:sent`, locale тенанта (L4).
- `accept_offer(offer, name, email, phone, payment_method)` →
  `@transaction.atomic` + `select_for_update`: гейт open+не истёк (иначе
  Conflict), `create_order(custom_lines=..., payment_method=...,
  note=«Angebot <token>»)`, `OfferSM().apply(offer, "accepted")`,
  `offer.order=order`, `conversation.ref_kind/ref_id/ref_label → order` (шов
  inbox уже есть), письмо владельцу. Идемпотентность: повторный POST по
  принятому → редирект на существующий заказ, второго Order нет.
- `decline_offer(offer)` → apply declined + письмо владельцу + system-message.

Расширение `create_order` (обратная совместимость строго):
`custom_lines=()` — кортежи `(title, unit_price, qty, product=None,
variant=None)`. Правила:
- строки С product/variant → участвуют в `_reserve_stock` (тот же атомик,
  anti-oversell, леджер UD3 — «сток по существующим правилам»), но цена/название
  берутся ИЗ СТРОКИ (заморожены в предложении), не из товара;
- строки без product → `OrderItem(product=None, combo=None)` — склад не трогают;
- `EmptyOrder`-гейт и валидация qty≥1 учитывают custom_lines; currency-фолбэк
  "EUR" при заказе только из custom-строк.
При принятии предложения: line.kind=="product" и товар ещё существует/активен →
передаём product (сток списывается); иначе (service/stay/event/combo/custom
или товар удалён) → свободная строка. **v1-ограничение (зафиксировать):**
предложение по услуге/номеру принимает ОПЛАТУ заказом, но НЕ создаёт
ServiceBooking/StayBooking — слот/даты согласуются в том же чате (авто-создание
брони из предложения — v2 по спросу).

## 4. Кабинет (inbox) и публичная страница

**Кабинет:** в `templates/inbox/thread.html` кнопка «💶 Angebot senden» →
страница-композер `/dashboard/inbox/<pk>/angebot/` (server-rendered, без JS):
чекбоксы+qty по секциям `sellable_manage_sections_for(tenant)` (цены из
`display_fields` → price_value; редактируемая цена = поле ввода с префиллом) +
3 пустые свободные строки (title+price+qty) + valid_until + note → POST →
`send_offer` → назад в тред. Карточки предложений — блок в треде (кабинет:
статус/итог/строки/ссылка/«Zurückziehen» для open; отправка карточек В
timeline не требуется — system-message уже отмечает момент в ленте).

**Клиент:** та же карточка в публичном треде (`message_thread.html`, по
`conversation.offers`) + письмо. Публичная страница `/o/<uuid:token>/`
(короткий префикс — хаус-стиль /r/ /t/ /s/; `/angebot/` ЗАНЯТ jobs):
строки/итог/срок/note; при open+не истёк — форма «Annehmen & bezahlen»
(name/email/phone, префилл из снапшота; пикер способа оплаты как на checkout
при >1 способе — реюз `available_methods`) и «Ablehnen»; после accept —
маршрутизация КАК у orders-чекаута: stripe+total>0 → `order_checkout_url`
редирект (вебхук `order_payment` уже существует и НЕ меняется), vorkasse/
on_site → редирект на `/bestellung/<code>/` (реквизиты/Verwendungszweck там
уже есть, E7). Статусные страницы: accepted → ссылка на заказ; declined /
истёк / cancelled — честные состояния; неверный токен → 404.

## 5. Гейты и чего НЕ делаем

- Кнопка в треде — без модульного гейта (inbox сам хост; способ оплаты всегда
  ≥1 — on_site). Stripe не настроен → vorkasse/on_site, флоу цел.
- Ваучер-код на странице предложения — НЕ в v1 (персональная цена уже
  «скидка»); un-redeem при отмене заказа — существующие правила orders.
- jobs, golden normalize, site_config — НЕ трогаются (ни одного ключа).
- Канбан: заказ появляется обычной карточкой orders после принятия; связь
  «заказ↔тред» видна в треде (ref) и в Offer.order.

## 6. Инкременты (батч-конвенция) и замки

1. **Модель+сервис:** Offer/OfferLine (⚠️ миграция), OfferSM, offers.py,
   `create_order(custom_lines=...)`. Тесты: create_order со свободными и
   product-строками (сток списан/не тронут, снимки цены), send/accept/decline
   (идемпотентность, истечение, конверсия customer), FSM-гейты.
2. **Кабинет:** кнопка+композер+карточки+system-message+письма. Тесты: композер
   рендерит пикер, POST создаёт Offer с выбранными+свободными строками,
   письмо с прямой ссылкой, unread/thread-инварианты целы.
3. **Публичная страница:** роут `/o/<token>/`, accept/decline/expired/404,
   маршрутизация оплаты. Тесты e2e: 2 позиции (1 товар со стоком + 1 свободная)
   → accept → Order создан, сток −qty, ref в треде, vorkasse-ветка и
   stripe-ветка (мок checkout-URL), двойной POST → один заказ.
4. **Финал:** i18n (новые msgid → en/tr/ru/uk .po), `npm ci`+`build:css` при
   новых утилитах, build-log+CLAUDE.md+ТЗ-статус, зелёный CI → FF-merge.

Приёмка ТЗ A1 закрывается: 2 позиции ✅, без логина ✅, оплата/Vorkasse ✅,
канбан+связь ✅, отклонение ✅, сток ✅, письмо ✅, паритет jobs ✅ (не тронут).
