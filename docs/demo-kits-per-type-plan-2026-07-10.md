# Демо-сайт под каждый тип бизнеса — анализ + план (2026-07-10)

Запрос владельца: «Демоверсии нужны для всех видов. Butcher/Metzgerei — это разные
демки, чтоб лучше продать. Не нашёл просто онлайн-магазин. Проведи анализ рынка и для
каждого типа сделай отдельный полноценный сайт. Если не хватает элементов — напиши,
обсудим». Разведка: 2 агента (карта demo_kits.py + свод рыночных доков A1–A9).

## 1. Текущее покрытие (13 типов ↔ 9 китов)

| Тип | Кит сейчас | Соответствие |
|---|---|---|
| bakery | aktionsmarkt (супермаркет скидок) | ⚠️ слабое: 3 хлебных позиции в «Backwaren», не пекарня |
| butcher | aktionsmarkt | ❌ худшее: ноль мяса/Wurst — видит «Sparfuchs» с яблоками и бытхимией |
| grocery | aktionsmarkt | ✅ родной (business_type=grocery, showcase акций) |
| clothing | shop (Hofladen — фермерская лавка) | ❌ худшее: мёд/сыр/яйца вместо моды; варианты = вес, не размеры |
| restaurant | restaurant-demo (Bella Vista) | ✅ родной |
| cafe | restaurant-demo | ⚠️ среднее: ужин-ресторан на 33 блюда, не кофейня |
| retail | shop | ✅ родной |
| tour_operator | retreat (йога-ретрит) | ⚠️ среднее: велнес вместо туров/экскурсий |
| hotel | hotel (Pension Seeblick) | ✅ родной |
| friseur | friseur (Salon Schöngut) | ✅ родной |
| handwerker | handwerker (Maler) | ✅ родной (❗на сервере не досеян — кнопки нет) |
| werkstatt | werkstatt | ✅ родной |
| events | retreat | ✅ родной |
| other | — | без демо (намеренно) |

**Вывод:** нужно 5 новых китов: bakery, butcher, clothing, cafe, tour_operator.

## 2. Стоимость (по факту кода)

Кит = чисто декларативная запись `DemoKit(...)` в `demo_kits.py` (~200–260 строк
немецкого контента: категории/товары `_p(...)`/услуги/акции/FAQ/отзывы/меню) +
`<KIT>_MENUS` (~20–30 строк) + 1 строка в реестре `KITS` + 1 строка маппинга
`DEMO_KIT_HOST` (onboarding.py). Движок (`apply_kit`) менять НЕ надо — всё, что нужно
новым китам, уже поддержано (варианты, модификаторы, аллергены, Grundpreis, брони,
jobs, events, отзывы, лояльность, доставка). 5 китов ≈ ~1 300 строк контента.

## 3. Спецификация новых китов (из рыночных доков)

### Волна 1 — bakery + butcher (владелец назвал явно)
- **BAKERY «Backhaus Krumme»** (`bakery.<base>`; orders+loyalty): категории
  Brot / Brötchen & Kleingebäck / Feingebäck & Kuchen / Torten (предзаказ);
  ~14 товаров (Roggenbrot 3,20, Bauernbrot 3,80, Croissant 1,80, Bienenstich 2,80,
  Torte 24,90 mit Vorlauf…), LMIV-аллергены везде, диеты (vegan/glutenfrei);
  **killer-акции:** Feierabend-Überraschungstüte 🌱 (surprise −50 %, TTL 3 ч),
  Angebot der Woche (weekly recurrence); C&C-предзаказ к времени; Stempelkarte;
  FAQ («Wann ist frisches Brot da?»), команда, отзывы.
- **BUTCHER «Metzgerei Bergmann»** (`butcher.<base>`; orders+jobs+loyalty):
  категории Frischfleisch / Wurst & Aufschnitt / Grill & Party / Feinkost;
  ~14 товаров с **весовым Grundpreis €/kg** (Rinderhack 9,90/kg, Rinderfilet
  29,90/kg, Bratwurst 5,50/4 St…); **killer:** Grillpaket-Vorbestellung
  (reservation, TTL 48 ч, к праздникам) + Wochenangebot; **Partyservice через
  jobs** (Anfrage → Angebot: кейтеринг-платте, канапе — рынок это ждёт);
  Herkunft на витрине; отзывы.

### Волна 2 — cafe + clothing
- **CAFE «Café Morgenrot»** (`cafe.<base>`; orders+booking+loyalty): Kaffee &
  Getränke (Cappuccino 3,20…) / Frühstück & Brunch (Frühstücksteller 8,50) /
  Kuchen & Süßes (Käsekuchen 3,80); Mittagstisch-акция (daily recurrence);
  бронь столика (booking-ресурс); Stempelkarte (7-й кофе бесплатно);
  инста-галерея, отзывы. Компактная карта (не 33 позиции).
- **CLOTHING «Studio Nordwind»** (`mode.<base>`; orders+loyalty): Damen / Herren /
  Accessoires; ~12 товаров с **размерными вариантами S/M/L/XL** (T-Shirt 19,90,
  Leinenhemd 39,90, Sommerkleid 45, Sneaker 69,90…), остатки per-вариант
  (waitlist по размеру), **Versand-фокус** (PLZ-доставка/DHL-зоны), Schlussverkauf
  −30 %; отзывы, lookbook-галерея.
  ⚠️ Гэп движка (не блокер демо): варианты одноосевые — «цвет×размер + фото
  на вариант» = отдельный трек (D3 из market-gap-a1a2), в демо размеры.

### Волна 3 — tour_operator
- **TOURS «Stadtgold Touren»** (`touren.<base>`; booking+events+orders):
  booking-услуги = регулярные туры по времени (Stadtführung 90 мин/25 €,
  Fahrradtour 35 €), events = датированные (Weinprobe 39 €, Tagesausflug 89 €
  с тирами/QR-билетами/waitlist); гиды как ресурсы с фото/био; FAQ
  (Treffpunkt, Wetter), карта, отзывы.
  ⚠️ Гэп движка (не блокер): «слоты одного дня у тура» (T6) — сейчас
  слот=услуга booking (работает), полноценная timeslot-модель — отдельный трек.

## 4. Недостающие элементы — НА ОБСУЖДЕНИЕ с владельцем

1. **Фото.** Все демо используют локальный SVG-генератор (градиент+эмодзи,
   GDPR-чисто, без внешних хостов). Для «продающих» демо реальные фото сильнее.
   Варианты: (a) оставить SVG — бесплатно/чисто; (b) набор CC0-фото в репо
   (Pexels/Unsplash — проверить лицензии); (c) AI-генерация набора фото 1 раз в
   репо. Решение владельца.
2. **«Просто онлайн-магазин»** — типа нет в реестре. Рекомендация: добавить
   `online_shop` («Online-Shop») в BUSINESS_TYPES (аддитивная миграция choices,
   как S6a) + карточка + пресет модулей (orders+Versand, без Abholung-акцента)
   + демо = кит clothing или дженерик-шоп. Альтернатива: не плодить тип, Retail
   уже «Online-Shop, Versand & Abholung». Решение владельца.
3. **Metzgerei Partyservice** — делаем через jobs (Anfrage→Angebot) — работает.
4. **Boutique цвет×размер** и **Tour-таймслоты** — гэпы движка, демо не блокируют
   (см. волны 2–3), кандидаты в roadmap после демо.
5. **Handwerker-демо на сервере не досеяно** (кнопка гейтится по Domain):
   `docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm web \
    python manage.py seed_demo_tenants --kit handwerker --recreate`
6. Дозасев существующих китов (по рыночному аудиту, мелочь): pranasy без
   diet-тегов (диет-фильтр пуст), у restaurant не засеяны комбо/QR-столы/брони.

## 5. Порядок работ

Волна 1 (bakery+butcher) → CI/чекпоинт → Волна 2 (cafe+clothing) → Волна 3
(tours) → (по решениям §4) online_shop-тип + фото-трек. Каждая волна: контент-кит
+ реестр KITS + DEMO_KIT_HOST + тест на маппинг/сид + локальный гейт. После
мержа каждой волны — на сервере `seed_demo_tenants` (новые киты) — кнопки
появятся сами. Миграций в волнах 1–3 НЕТ (только §4.2 online_shop = миграция).
