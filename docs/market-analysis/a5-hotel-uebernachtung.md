# Архетип A5 «Übernachtung / Hotel» — анализ рынка и гэпы

> Статус: **АНАЛИЗ для согласования** (2026-06-25). Конвенция: docs до кода.
> Source of truth по сделанному — `build-log.md`, планы — `hotel-archetype-plan.md` /
> `hotel-growth-plan.md` / `hotel-channel-manager-plan.md`. Этот документ — срез рынка
> прямого бронирования малого отеля DACH + честная оценка визуальных/технических гэпов
> и рекомендации по блочному редактору (M20). Сегмент: Pension, kleines Hotel,
> Ferienwohnung/-haus, B&B, Gästezimmer, Hostel, Camping/Stellplatz (1–20 юнитов).

## Контекст и позиционирование

Платформа — мультитенантный SaaS для микробизнеса DACH: один тенант = один сайт на
субдомене, ~39 €/мес, **прямое бронирование без комиссии и без аккаунта гостя, без
трекинг-куки, DSGVO-first, Double-Opt-In по UWG §7**. Это рамка, в которой мы НЕ
строим маркетплейс уровня Booking/Airbnb, а даём отелю собственный сайт-движок,
который конвертирует не хуже OTA, но оставляет деньги бизнесу. Северная звезда —
«анти-Битрикс»: настройка в ≤5–10 шагов, нативная лёгкая правка, «сайт соберёт
ребёнок», блочная архитектура.

Важная этическая/правовая граница: ряд конверсионных приёмов OTA (ложный дефицит
«nur noch 1 Zimmer», «X человек смотрят сейчас») сейчас квалифицируется как dark
pattern по EU-UCPD; Испания оштрафовала Booking.com на €413 млн в т. ч. за
манипулятивный дизайн ([behavioralinsight](https://behavioralinsight.substack.com/p/dark-patterns-on-bookingcom-manipulation)).
Для нас это совпадает с UX-принципом владельца: дефицит показываем только правдивый
(реальный «последний свободный номер»), либо не показываем вовсе.

## Current coverage

Движок `apps.stays` (Track E) + кит `hotel` («Pension Seeblick») закрывают H1–H9 и
бэклог роста G1–G11 (a/b). Кратко, что уже работает «из коробки»:

**Инвентарь и бронирование.** `StayUnit` (тип room/apartment/house/bed/pitch, quantity
идентичных юнитов, цена·ночь, выходная цена, `SeasonRate` сезонные окна, min_nights,
max_guests, deposit, require_manual_confirm, фото-галерея). Анти-овербукинг
пер-ночный под блокировкой строки (`services.book_stay`, `availability.range_available`),
`UnitBlock` (ремонт/iCal), мультикомнатная бронь (`rooms`, G5).

**Тарифы и цена (H1, G4, G7).** `RatePlan` (percent_adjust ±%, surcharge·ночь,
Verpflegung ohne/Frühstück/Halb-/Vollpension, cancellation flexible/non_refundable +
free_cancel_days, prepayment_percent 0/частично/100). Авто-скидки `StaySettings.
auto_discount_rules` многоступенчато (LOS / Frühbucher / Last-Minute, берётся
максимальный %). Промокод/ваучер (`loyalty.Voucher`, H4a), снимки цены/скидок в
`StayBooking`.

**Право и доверие.** Kurtaxe (H9, `StaySettings.kurtaxe_cents`, отдельная строка
в счёте, дети бесплатно опц.). Hausordnung (H6, страница). JSON-LD `LodgingBusiness`/
`Hotel` (H6). Цифровой Meldeschein + Online-Checkin (G6, `GuestRegistration`,
BMG §29–30, простая подпись Ф.И.О.+время+IP, retention 1 год, beat-очистка).
Самоотмена по подписанной ссылке с уважением условий тарифа (H4b).

**Деньги и удержание.** Депозит/предоплата через Stripe Connect (деньги бизнесу),
авто-Rechnung (7 % Beherbergung, DATEV/GoBD), Extras per-night (`core.Extra`:
Frühstück/Parkplatz/Spät-Checkout/Haustier). Geschenkgutscheine (G1). Pre-/post-stay
письма + запрос отзыва (G2). Newsletter-кампании гостям с DOI (G3). Отчёты
Belegung %/ADR/RevPAR (G9). Booking-виджет/iframe (`?embed=1`, G10).

**Дистрибуция.** iCal импорт занятости Booking/Airbnb/Google (`ICalSource`) + экспорт
нашего iCal-фида + фид цен/наличия `/stays/feed.json` для метапоиска (G8). Модель
`Channel` + идемпотентный `import_external_booking` (G11a/b). Собственный
вертикальный агрегатор `hotels.<base>` с поиском по датам (H8a/b).

**Витрина (storefront).** Единая `detail.html` (галерея слева, бронь-карточка справа,
sticky/мобильный buybar), страница номера `stay_detail.html` (выбор дат GET → котировка
→ выбор тарифа с условиями отмены/предоплатой ДО оплаты, Extras, промокод, Kurtaxe-
строка, «похожие номера», Ausstattung-иконки `amenities`). Поиск по датам с главной
(секция `stay_search`), карточки номеров на главной (`stay_rooms`), список
`/unterkunft/` с ценой «ab … € total» за диапазон. Меню отеля (HOTEL_MENUS, sticky +
мобильный таб-бар). Реестр секций M20 + layout-движок (пресеты list/cols2-4/gallery).

**Грубая оценка покрытия дневного цикла малого отеля: ~85 %.** Функциональное ядро
прямого бронирования и право DACH практически закрыты; основные пробелы — в
**визуальной/UX-полировке** (на уровне ожиданий «как у Booking/Airbnb») и в нескольких
конверсионных/дистрибуционных надстройках.

## Market benchmark

### Что гость теперь ожидает от ЛЮБОГО сайта размещения (визуал/UX)
- **Фото-герой-сетка + полноэкранный лайтбокс**: 1 большое + 2×2 плитки, кнопка
  «Alle Fotos anzeigen» → затемнённый свайп-лайтбокс. Фото — главный сигнал доверия;
  профессиональные фото дают Airbnb-хостам до +21 % дохода и +19 % броней
  ([clickz](https://www.clickz.com/10-great-ux-features-from-the-airbnb-website/),
  [airbnb photo tour](https://www.airbnb.com/resources/hosting-homes/a/how-to-organize-listing-photos-into-a-home-tour-456)).
- **Карточки номеров**: миниатюра + название + бейдж рейтинга + ряд иконок-удобств +
  «ab X€/Nacht» + чипы «Kostenlose Stornierung»/«keine Vorauszahlung» + CTA
  ([wix rooms templates](https://www.wix.com/website/templates/html/travel-tourism/apartments-and-hostels)).
- **Диапазонный date-picker** с подсветкой span, авто-переходом к выезду, серыми
  занятыми датами и видимым Mindestaufenthalt (Airbnb открыл [react-dates](https://airbnb.io/projects/react-dates/)).
- **Прозрачность итоговой цены**: «ab X€» → разбивка (ночи × тариф + налоги/сборы =
  заметный итог). В DACH это закон (PAngV), а не полировка
  ([booking EU consumer law](https://partner.booking.com/en-gb/help/legal-security/policies-local-laws/complying-european-union-consumer-law)).
- **Доверие**: числовой балл «8,5 / Sehr gut» + число отзывов у заголовка и на
  карточках; звёзды-классификация отдельно
  ([pricelabs direct-booking best practices](https://hello.pricelabs.co/blog/hotel-direct-booking-websites/)).
- **Карта + «in der Umgebung»**: встроенная карта с пином + расстояния до транспорта/
  достопримечательностей.
- **Чипы бесплатной отмены/без предоплаты** с явной датой дедлайна — высокий и
  юридически безопасный конверсионный рычаг
  ([little hotelier cancellation](https://www.littlehotelier.com/blog/running-your-property/booking-com-cancellation-policy/)).
- **Мобайл**: липкий нижний бар брони + bottom-sheet/полноэкранный date-picker.
- **Дефицит/срочность**: эффективны, но правдивые; ложные — штрафуются по EU-UCPD
  ([sciencedirect scarcity cues](https://www.sciencedirect.com/science/article/abs/pii/S1567422319300870),
  [pricelabs psychology](https://awning.com/post/understanding-guest-psychology-how-pricing-urgency-and-limited-availability-influence-bookings)).

### Что движки бронирования считают table-stakes vs premium
Table-stakes (Smoobu, Beds24, Lodgify, Sirvoy, eviivo, Little Hotelier/Cloudbeds,
SiteMinder, TravelLine, Hotel-Spider): **2-way real-time channel-sync** (Booking/Airbnb/
Vrbo/Expedia, rate-parity, центральный ARI/календарь); встраиваемый виджет/iframe;
оплата картой+PayPal (Klarna набирает) + депозит; мультикомнатная бронь;
online/contactless check-in + цифровая регистрация; единый guest-inbox; коннект к
Google Hotel Ads + Free Booking Links
([smoobu](https://www.smoobu.com/en/), [beds24 IBE](https://www.beds24.com/online-booking-system.html),
[lodgify small hotel](https://www.lodgify.com/hotel-booking-software/),
[cloudbeds engine](https://www.cloudbeds.com/booking-engine/)).
Premium: динамическое/сезонное ценообразование по спросу (глубоко у Beds24/SiteMinder/
Cloudbeds; на SMB-уровне — базовые LOS/Frühbucher/Last-Minute, как у нас); **upsells/
extras на чекауте** (Frühstück/Parkplatz/Transfer/Upgrade/Erlebnis); AI-чат, восстановление
брошенной брони через WhatsApp, ADR/RevPAR-отчёты, housekeeping, GDS.

### Онбординг билдеров (Jimdo/Wix/Smoobu/Lodgify)
Сошлись на **AI/wizard-first, template-second**: Jimdo-ассистент спрашивает отрасль/
цели → готовый сайт «за минуты»; Wix — AI-билдер или шаблон → ~6 тем
([wix AI](https://www.websitebuilderexpert.com/website-builders/wix-ai-features/),
[wix hotels](https://www.wix.com/hotels/website)). PMS-билдеры **data-driven**: заполнил
поля объекта один раз (номера/кровати/площадь/удобства/гео) → секции сами наполняются
(Smoobu [New Website Builder](https://support.smoobu.com/hc/en-us/articles/23888817835282--New-Website-Builder),
Lodgify — 5-шаговый визард: trial → импорт из Airbnb ~2 мин → шаблон+бренд → Stripe/PayPal →
каналы). Единая блок-структура шаблона отеля: Hero (фул-скрин слайдер + название +
«Book Now») → Welcome → **Rooms как CMS-записи** (название/тип/цена/кровати/гости/площадь/
удобства) → Amenities → Gallery → Reviews → встроенная карта + район → контакт/форма →
футер. DACH-дифференциатор: **Jimdo Legal-Text-Generator** авто-создаёт И
авто-поддерживает Impressum/Datenschutz (Trusted Shops) — конкуренты заставляют
вставлять тексты eRecht24 вручную ([jimdo legal](https://www.jimdo.com/addon/legal-text-generator/)).

### Право/дистрибуция DACH (сверка с нашим состоянием)
- **Kurtaxe/Gästebeitrag** — сбор с гостя за чел./ночь, ставка по Gemeinde
  (сезон/возраст/Business-льготы). Это сбор гостя → может показываться **отдельно**
  от цены номера («ab X€ zzgl. Kurtaxe Y€ p.P./Nacht, vor Ort») — в отличие от
  Bettensteuer оператора, который обязан быть внутри итога
  ([lodgify Kurtaxe DE](https://www.lodgify.com/blog/de/kurtaxe-in-deutschland/)). У нас ✅ H9.
- **Meldeschein (BMG §29–30)** — обязателен; цифровой/онлайн явно разрешён без
  мокрой подписи; retention 1 год ([§30 BMG](https://www.gesetze-im-internet.de/bmg/__30.html)).
  У нас ✅ G6.
- **Бесплатная отмена/предоплата** — топ-3 критерий брони (~80 % важно). Стандарт —
  две ставки: flexible (free cancel 24/48ч, без предоплаты) vs non-refundable
  (Anzahlung/Vorkasse, дешевле на ~10–20 %). Жильё с фикс-датой освобождено от
  14-дневного Widerruf. У нас ✅ H1/G7.
- **PAngV §3** — отображаемый Gesamtpreis включает НДС + все обязательные сборы;
  Kurtaxe — документированное исключение (отдельно)
  ([PAngV](https://www.gesetze-im-internet.de/pangv_2022/BJNR492110021.html)).
- **Google Free Booking Links / Hotel Ads** — бесплатная «Official site» ссылка под
  платными Hotel Ads; нужен живой ARI-фид через connectivity-партнёра; малые отели
  допущены; тот же фид кормит Trivago/Kayak/Tripadvisor
  ([google FBL](https://support.google.com/hotelprices/answer/10472393),
  [d-edge FBL](https://www.d-edge.com/googles-free-booking-links-the-secret-weapon-for-hotels-in-the-battle-for-direct-bookings/)).
  У нас ✅ фид G8 (формат под connectivity-партнёра — гэп).
- **Impressum/Datenschutz** — Impressum по **§5 DDG** (TMG → DDG c 14.05.2024;
  TTDSG → TDDDG), доступен в ≤2 клика с каждой страницы
  ([e-recht24](https://www.e-recht24.de/news/datenschutz/13296-webseitenbetreiber-aufgepasst-das-tmg-wird-zum-digitale-dienste-gesetz-aktualisieren-sie-jetzt-ihr-impressum.html)).
  **Действие:** проверить, что наши юр-страницы ссылаются на DDG/TDDDG, а не TMG.

## Visual gaps

(A) Визуальные/UX-пробелы относительно ожиданий гостя «как у Booking/Airbnb».

| Гэп | Почему (рынок) | Усилие | Уже частично? |
|---|---|---|---|
| **V1. Полноэкранный лайтбокс галереи** | Сейчас `_media_gallery.html` лишь меняет большое фото по клику миниатюры (vanilla swap), без затемнённого свайп-просмотра/зума/«Alle Fotos». Лайтбокс — базовая конвенция Airbnb/Booking, фото = главный сигнал доверия. | S | да — есть галерея+миниатюры, нет лайтбокса/свайпа |
| **V2. Визуальный календарь наличия** | Сейчас выбор дат — два нативных `<input type=date>`. Гость ждёт диапазонный календарь с подсветкой span, серыми занятыми ночами и видимым Mindestaufenthalt ([react-dates](https://airbnb.io/projects/react-dates/)); «calendar pickers convert better than static from-X€» ([pricelabs](https://hello.pricelabs.co/blog/hotel-direct-booking-websites/)). | M–L | нет (только date-input) |
| **V3. Прозрачная разбивка итоговой цены** | Сейчас показывается итог тарифа и строка Kurtaxe, но без явной разбивки «ночи × тариф + Extras + Kurtaxe = Gesamtpreis». PAngV §3 требует Gesamtpreis с НДС/сборами; Kurtaxe — отдельной строкой (исключение). | S | да — строки есть, нет единого breakdown-компонента |
| **V4. Отзывы/рейтинг на странице номера и карточках** | `BusinessReview`/рейтинг есть, но рендерятся секцией `reviews` только на главной; на `stay_detail`/карточках номеров балла «8,5 / X Bewertungen» нет. Балл у заголовка — базовый сигнал доверия. | S–M | да — модель и секция есть, нет на detail/cards |
| **V5. Карта локации + «in der Umgebung»** | Гео есть в агрегаторе, но на витрине отеля нет встроенной карты с пином/расстояниями. Карта — стандарт у всех OTA; «без трекинг-куки» → статичная карта/OSM-тайлы без внешнего JS-трекинга. | M | частично (гео в агрегаторе, не на витрине) |
| **V6. Чипы «Kostenlose Stornierung / keine Vorauszahlung» на карточках** | Условия отмены показываются внутри выбора тарифа, но не как зелёный чип на карточке номера/в списке — высокий и юр-безопасный конверсионный рычаг. | S | да — данные есть (RatePlan), нет чипа на карточке |
| **V7. Правдивый «последний номер» (без тёмных паттернов)** | `quantity` известен → можно честно показать «Nur noch 1 frei» когда реально 1. Ложный дефицит штрафуется (EU-UCPD), правдивый — допустим и конвертит. | S | нет |

## Technical gaps

(B) Технические/функциональные пробелы. Многие имеют готовый фундамент.

| Гэп | Почему (рынок) | Усилие | Уже частично? |
|---|---|---|---|
| **T1. Реальные 2-way OTA API (Booking/Expedia/Airbnb)** | Table-stakes у всех движков — двусторонний ARI-push + приём броней. У нас iCal (односторонне) + модель `Channel`/`import_external_booking` (швы). Полный 2-way требует партнёрских ключей/сертификации — **шаг владельца**, не код (G11c–e). | L | да — фундамент G11a/b + iCal; нет реального ARI-push/reservations-API |
| **T2. Upsells/Extras с фото и количеством на чекауте** | Premium-движки продают Frühstück/Parkplatz/Transfer/Upgrade с фото и qty. У нас Extras — чекбоксы без фото/количества/группировки. | S–M | да — `core.Extra` per-night, но плоский UI |
| **T3. Метапоиск-фид в формате connectivity-партнёра** | G8 даёт `/stays/feed.json`, но Google FBL/Hotel Ads требует ARI-фид через connectivity-партнёра (тот же кормит Trivago/Kayak). Гэп — формат/коннектор, не данные. | M–L | да — фид наличия/цен есть, формат под партнёра — нет |
| **T4. Гостевой inbox/мессенджинг по брони** | Единый guest-inbox — table-stakes; у нас есть storefront-message (вопрос по юниту), но не нить «по конкретной брони» с историей. | M | частично (storefront inbox по юниту) |
| **T5. Платёжные методы PayPal/Klarna** | Stripe Connect (карта/депозит/предоплата) есть; PayPal/Klarna набирают в DACH. Через Stripe Payment Methods — конфиг, не новая инфраструктура. | S–M | да — Stripe Connect готов, методы не расширены |
| **T6. Возрастные детские тарифы (по решению — узко)** | adults/children есть для вместимости и Kurtaxe; детских ценовых сеток нет (намеренно, Revenue-уровень). Для FeWo/семейных — изредка нужно; оставляем вне scope MVP. | M | да — adults/children поля; цен нет (by design) |
| **T7. Брошенная бронь / напоминание о незавершённой** | Premium-приём (recovery). У нас есть pre-stay/post-stay письма (G2), но не «вы начали бронь — завершите». | S–M | частично (beat-инфраструктура писем есть) |

## Anti-Bitrix block editor

(C) Рекомендации для блочного редактора M20 — переиспользуемые блоки, ≤10 шагов до
рабочего сайта брони, умные дефолты. Принцип M20: **без новых моделей, поверх JSON
`site_config` и реестра секций**; data-driven (как Smoobu/Lodgify — заполнил номера
один раз, секции наполнились). Сейчас в реестре есть `stay_search` и `stay_rooms`.

**Рекомендуемые блоки (секции реестра + панель свойств):**
- **B1. Room-cards блок** — есть (`stay_rooms`); добавить в панель свойств чипы
  отмены (V6), бейдж рейтинга (V4), правдивый «nur noch N frei» (V7). Layout-движок
  (cols2-4/gallery) уже применяется.
- **B2. Booking-widget блок** — выделить «Suchformular» (`stay_search`) в самостоятельный
  переиспользуемый блок с визуальным календарём (V2) вместо date-input; вставляется на
  главную, в hero и как iframe (G10 уже есть).
- **B3. Amenities блок** — оснащение объекта (а не номера) иконками из каталога
  `AMENITIES` — общий для отеля; data-driven из `StayUnit.amenities`-объединения или
  отдельного поля тенанта.
- **B4. Map блок** — встроенная карта (статичная/OSM без трекинга) с пином и
  расстояниями «in der Umgebung» (V5); адрес уже в Tenant.
- **B5. Reviews блок** — есть секция `reviews`; добавить вариант «компактный балл +
  число» для размещения у заголовка/в hero (V4).
- **B6. Price-breakdown** — не секция главной, а компонент карточки брони (V3);
  переиспользуется на `stay_detail` и в iframe.

**Онбординг ≤10 шагов до рабочего сайта брони (data-driven wizard):**
1. Тип бизнеса = «Übernachtung» → кит `hotel` как старт. 2. Название/адрес/гео.
3. Добавить номера (тип/цена/гости/площадь/кровати/удобства/фото) — это и есть
CMS-записи, кормящие B1/B2/B3. 4. Тариф(ы) по умолчанию (Basis + опц. Frühstück).
5. Условия отмены/предоплата (V6/G7). 6. Kurtaxe (вкл/сумма, H9). 7. Stripe Connect
(депозит/оплата). 8. Фото-герой + галерея. 9. Юр-страницы авто (Impressum/Datenschutz
по DDG/TDDDG — наш аналог Jimdo Legal-Generator, дифференциатор). 10. Publish →
работающий `/unterkunft/` + поиск с главной + iframe.

**Умные дефолты:** archetype-aware главная отеля уже включает `stay_search` + `stay_rooms`
+ `reviews` + `gallery` + `contact`; meal=Frühstück по умолчанию в первом тарифе;
flexible-тариф первым; мобильный buybar/таб-бар включены. Цель — после шага 3 (номера)
сайт уже бронируем; шаги 4–10 — улучшения, не блокеры.

## Prioritized backlog table

Ранжировано по (леверидж прямого бронирования малого отеля DACH) × (близость к
ожиданиям гостя / праву) ÷ усилие. Все — надстройки над `apps.stays`/M20, без дублей.

| # | Гэп | Тип | Усилие | Приоритет | Примечание |
|---|---|---|---|---|---|
| 1 | V1 Лайтбокс галереи | Визуал | S | 🥇 | базовая конвенция, дёшево; правит `_media_gallery.html` (общий для всех архетипов) |
| 2 | V3 Price-breakdown (B6) | Визуал/право | S | 🥇 | PAngV §3; Kurtaxe отдельной строкой; компонент карточки брони |
| 3 | V6 Чипы отмены/предоплаты на карточках | Визуал | S | 🥇 | данные в `RatePlan` уже есть |
| 4 | V4 Рейтинг/отзывы на detail+карточках (B5) | Визуал/доверие | S–M | 🥇 | `BusinessReview` уже есть, рендер на главной |
| 5 | V2 Визуальный календарь наличия (B2) | Визуал/UX | M–L | 🥈 | сильнейший конверсионный рычаг; vanilla/Alpine без CDN |
| 6 | V7 Правдивый «nur noch N frei» | Визуал | S | 🥈 | только при реально N≤порог; без тёмных паттернов |
| 7 | T2 Upsells/Extras с фото+qty | Технич. | S–M | 🥈 | надстройка над `core.Extra` |
| 8 | V5 Карта + «in der Umgebung» (B4) | Визуал | M | 🥈 | статичная карта/OSM без трекинга |
| 9 | T5 PayPal/Klarna через Stripe | Технич. | S–M | 🥉 | конфиг Payment Methods |
| 10 | T7 Recovery брошенной брони | Технич. | S–M | 🥉 | beat-инфраструктура писем готова (G2) |
| 11 | T4 Гостевой inbox по брони | Технич. | M | 🥉 | расширение storefront-message |
| 12 | T3 Метапоиск-фид формата партнёра | Технич./дистриб. | M–L | 🥉 | формат под connectivity-партнёра Google |
| 13 | T1 Реальный 2-way OTA API | Технич. | L | отложено | партнёрские ключи/сертификация = шаг владельца (G11c–e) |
| 14 | T6 Детские ценовые сетки | Технич. | M | вне scope | Revenue-уровень; намеренно не для MVP малого отеля |

**Сквозное действие (право):** проверить, что `/impressum` и `/datenschutz`
ссылаются на DDG/TDDDG (а не TMG/TTDSG — изменено 14.05.2024).
