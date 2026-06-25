# Архетип A9 «Kfz-Werkstatt / Reparatur» — анализ рынка и пробелы

> Статус: **АНАЛИЗ для согласования** (2026-06-25). Конвенция: docs до кода.
> Source of truth по вертикалям — `micro-business-verticals.md` (A9, ~95 %), по
> сделанному — `build-log.md`, по китам — `kit-archetype-coverage.md`. Этот документ —
> рыночный бенчмарк DACH + приоритизированный бэклог пробелов. Кодим только после
> подтверждения порядка.

## 0. Контекст и позиционирование

A9 (Kfz-Werkstatt, Reifenservice, Autoglas, мото/вело-сервис, Handy/PC-Reparatur)
у нас — **не новый движок, а симбиоз**: `booking` (Termin на пост) + `jobs`
(Kostenvoranschlag → Auftrag → Rechnung) + `catalog`/`orders` (продажа Teile +
остаток) + `finance` (счёт, НДС 19 %). Рамка платформы: один тенант = один сайт на
субдомене, ~39 €/мес, витрина без аккаунта и без трекинг-куки, Double-Opt-In по
UWG §7, anti-marketplace. Это важно: рыночные ориентиры ниже (FairGarage,
werkstars, clickrepair) — **порталы-агрегаторы** с lead-gen и комиссией; мы берём
из них не бизнес-модель, а **ожидания конечного клиента** (что он привык видеть на
странице автосервиса) и переносим их на сайт одного бизнеса.

## Current coverage

Движок A9 по docs закрыт на ~95–100 % (`micro-business-verticals.md` §A9,
`kit-archetype-coverage.md` §A7/A9 — «покрытие ~100 %»). Фактически в коде есть:

- **Termin онлайн** — `apps.booking`: `Service` (название + `duration_minutes` +
  `price_cents` + `deposit_cents`, снимок цены в выручку при выполнении), ресурсы
  (Hebebühne как `Resource`), слот-доступность, депозит/предоплата (Stripe Connect,
  P2.5b), напоминание клиенту за N часов (`booking/tasks.py send_due_reminders`,
  one-shot + дедуп `Notification`).
- **Kostenvoranschlag → Rechnung** — `apps.jobs`: форма заявки `/anfrage/`,
  конструктор сметы, Angebot-PDF, публичное принятие сметы `/angebot/<token>/`,
  статусы (JobSM), «Rechnung erstellen» из позиций (`finance.Invoice`). Поле
  **`Job.vehicle`** (CharField 120, свободный текст «VW Golf · M-AB 12»,
  миграция `jobs/0007_job_vehicle`).
- **Расходники из каталога → склад** — `JobLine.product`/`variant`: деталь (Teile)
  в смете берётся из каталога; при `erledigt` остаток списывается атомарно
  (R3-паттерн, клампим в 0, идемпотентно), позиции попадают в Rechnung снимком.
- **Продажа/доставка запчастей** — `catalog` + `orders` (Click&Collect + Versand
  G4) + реальный остаток (R3).
- **Демо-кит `werkstatt`** (`demo_kits.py`, key="werkstatt", business_type="other"):
  5 услуг (Ölwechsel 30 мин/49 €, Inspektion 120/149, Reifenwechsel 45/39, HU/AU
  60/89, Bremsen-Check 30/0 €), 2 Hebebühnen-ресурса, 2 Fahrzeug-Angebote
  (`job_samples` с `vehicle`+позициями+VAT 19 %), каталог 5 Teile, Trust
  (`{"since":"1995","marks":["Meisterbetrieb","Markenoffen","HU/AU vor Ort"]}`),
  FAQ, Prozess (3 шага), Team (Meister), меню (Termin/Kostenvoranschlag/Teile),
  мобильный bottom-bar. Модули: `booking`, `jobs`, `orders`, `customer_account`.
- **Site Builder (M20/M20U)**: единая главная (hero-CTA, секции, archetype-aware
  дефолт), per-page раскладки, live-preview, мобильный таб-бар.

**Вывод:** дневной цикл бизнеса (Termin → услуга/смета → Teile → Rechnung) собран.
Пробелы — не в «движке записи/сметы», а в **авто-специфике** (данные авто, TÜV,
Reifeneinlagerung, статус ремонта) и в **витрине/доверии/прайс-прозрачности**, к
которым приучили клиента порталы.

## Market benchmark

Что показывают немецкие сайты/порталы автосервиса и ремонта (ожидания клиента):

- **FairGarage** ([fairgarage.com](https://www.fairgarage.com/de-de/index.html)) —
  ведущий портал прозрачности/честности с 2014; **онлайн-бронь желаемого слота**,
  отмена в любой момент; работа только с **Meisterbetriebe / члены Kfz-Innung**;
  единственный портал, **официально рекомендованный ZDK**
  ([Reifenservice](https://www.fairgarage.com/de-de/reifenservice)). Ключевое —
  **прайс-прозрачность и сравнение цен** до записи.
- **repareo** ([autoservicepraxis](https://www.autoservicepraxis.de/nachrichten/kfz-werkstatt/werkstattportal-repareo-erweitert-serviceangebot-2622121)) —
  после ввода базовых данных клиент получает **Preisvorschlag** на запрошенную
  услугу; у мастерской **собственный профиль** с услугами/ценами и приёмом
  заявок на Termin.
- **caroobi** ([caroobi.com](http://caroobi.com/)) — портал онлайн-посредничества
  закрылся (урок: чистый lead-gen-агрегатор не взлетел — подтверждает наш курс на
  «сайт бизнеса», а не комиссионный маркетплейс).
- **werkstars / pitstop / Vergölst / ATU** (Reifenservice,
  [pitstop Radwechsel](https://www.pitstop.de/Services/Radwechsel),
  [Vergölst](https://vergoelst.de/services/radwechsel-reifenmontage.html),
  [ATU](https://www.atu.de/pages/meisterwerkstatt/wartung-service/reifenwechsel.html)) —
  **онлайн-бронь Radwechsel/Reifenmontage по Festpreis**, **Reifeneinlagerung как
  Zusatzleistung к саезонному Räderwechsel** (доплата фикс-ценой, хранение до 8
  мес.), бронируется онлайн вместе с термином, выбор авто/слота, **Bewertungen** на
  карточке мастерской ([FairGarage Reifenservice](https://www.fairgarage.com/de-de/reifenservice)).
- **Werkstattsoftware** (easyWerkstatt, ru-software, smartwerkstatt) — стандарт
  отрасли:
  - **HSN/TSN → автозаполнение данных авто** из публикаций Kraftfahrt-Bundesamt;
    HSN/TSN-распознавание в карточке клиента
    ([easyWerkstatt HSN/TSN](https://easywerkstatt.com/download-links/hsn-tsn-abfrage/),
    [smartwerkstatt](https://www.smartwerkstatt.cloud/blog/hsn-tsn-ersatzteile-guide),
    [ADAC HSN/TSN](https://www.adac.de/rund-ums-fahrzeug/auto-kaufen-verkaufen/kfz-zulassung/hsn-tsn-faq/)).
  - **TÜV/HU-AU-напоминание** (по §57a/HU/MFK) — SMS/Mail перед следующей
    проверкой; «авто готово к выдаче» — SMS
    ([TÜV SÜD HU-Erinnerung](https://www.tuvsud.com/de-de/branchen/mobilitaet-und-automotive/hauptuntersuchung/hu-erinnerung),
    [easyWerkstatt Kundenverwaltung](https://easywerkstatt.com/funktionen/kundenverwaltungsprogramm/)).
  - **Reifeneinlagerung-учёт**: этикетка (DYMO) с именем/Kennzeichen/размером,
    привязка к клиенту ([easyWerkstatt updates](https://easywerkstatt.com/updates/)).
- **Handy/PC-Reparatur** (clickrepair) ([clickrepair.de](https://www.clickrepair.de/)) —
  клиент за секунды выбирает **Hersteller → Modell → дефект** и сразу видит
  **Sofort-Festpreis**; **прозрачные цены без скрытых сборов** (диагностика и
  пересылка бесплатны); **трекинг статуса ремонта** (Mail-апдейты + Kundenbereich),
  вариант **Versand-Reparatur** или локальная мастерская.

**Общий знаменатель ожиданий клиента:** (1) онлайн-Termin по конкретной услуге с
**видимой фикс-ценой**; (2) ввод **данных авто/устройства** (Kennzeichen/HSN-TSN
или модель); (3) **Reifeneinlagerung** как доп-услуга; (4) **Bewertungen +
Meisterbetrieb** как доверие; (5) **прайс-прозрачность** (от/Festpreis); (6) для
ремонта — **статус заказа** и опц. Versand.

## Visual gaps (витрина / UX)

| Пробел | Почему (рынок) | Усилие | Частично есть? |
|---|---|---|---|
| **V1. Прайс-лист услуг с фикс-ценой блоком** — «Leistungen ab/Festpreis» (Ölwechsel 49 €, HU 89 €, Reifenwechsel 39 €) карточками на главной | Festpreis/прайс-прозрачность — ядро FairGarage/pitstop/ATU; клиент выбирает по цене до записи | S | Частично: `Service` хранит цену; на витрине отдельного прайс-блока услуг нет (цена видна только в шаге брони) |
| **V2. Online-Termin flow «услуга → авто → слот»** в 2-3 шага с видимой ценой/длительностью и опц. доплатами | werkstars/pitstop/Vergölst: выбор услуги+Festpreis+слот в один поток; depository booking | M | Частично: `/termin/` выбирает услугу+слот; нет шага «данные авто» и видимых Zusatz/Festpreis-итога |
| **V3. Trust-блок «Meisterbetrieb + Bewertungen» на витрине** — печати Innung/Meister + отзывы клиентов прямо на странице | FairGarage берёт только Meisterbetriebe (член Kfz-Innung); отзывы — стандарт карточки мастерской | S–M | Частично: Trust-marks есть (`trust.marks`), отзывы (`testimonials`) есть в ките, но блок отзывов на витрине — сквозной пробел (`kit-archetype-coverage` §3.4) |
| **V4. Богатая карточка услуги** (что входит, длительность, «für alle Marken», фото) | repareo: профиль с описанием услуг; клиент хочет понять объём до брони | S | Нет: `Service` — только название/время/цена, без описания/изображения |
| **V5. Витрина Handy/PC: выбор «Modell → дефект → Sofort-Preis»** | clickrepair: 80 % UX ремонта телефонов — это селектор модели и мгновенная цена | M | Нет: сейчас только generic Termin/Anfrage; нет prijs-матрицы модель×дефект |
| **V6. Мобильность/CTA «Termin / Angebot anfordern»** — крупные липкие действия | весь сегмент мобилен (клиент с телефона у дороги) | S | Есть: мобильный buybar/таб-бар (M20U), hero-CTA — переиспользуется |

## Technical gaps (функциональные)

| Пробел | Почему (рынок) | Усилие | Частично есть? |
|---|---|---|---|
| **T1. Структурированные данные авто** (Kennzeichen + HSN/TSN + марка/модель/Erstzulassung) вместо одного `Job.vehicle` свободным текстом | Werkstattsoftware-стандарт: HSN/TSN → автозаполнение + поиск Teile; идентификация авто | M | Частично: `Job.vehicle` (свободный текст). Нет полей HSN/TSN/Kennzeichen, нет KBA-lookup |
| **T2. TÜV/HU-AU- и Service-напоминание** — дата следующей HU/инспекции на авто клиента → авто-Mail/SMS «HU fällig» (опц. с предложением Termin) | TÜV SÜD/easyWerkstatt: HU-Reminder — главный канал возврата клиента; ретеншн | M | Частично: движок напоминаний есть для брони (`reminder_sent_at` + дедуп), но не «по дате на авто» (нет сущности «обслуживаемое авто» с next-HU). UWG §7: сервисное письмо ≠ маркетинг, но нужен opt-in/основание |
| **T3. Reifeneinlagerung (хранение шин)** — учёт комплекта (клиент/Kennzeichen/размер/место), сезонная доплата онлайн как Zusatzleistung к Reifenwechsel, напоминание о смене сезона | pitstop/Vergölst/easyWerkstatt: ключевая повторяющаяся услуга и доп-доход; этикетка с Kennzeichen | M–L | Нет. Можно частично собрать на `Service`+`Extra`, но нет учёта комплекта/места/сезонного цикла |
| **T4. Repair-Status трекинг** — публичная страница `/r/<code>/` со статусом ремонта (angenommen → in Arbeit → fertig → abgeholt) + Mail-апдейт | clickrepair: трекинг статуса — must-have ремонта; снижает звонки | S–M | Частично: `JobSM` уже имеет статусы и публичный токен-доступ `/angebot/<token>/`; нет «клиентского» статус-view с понятными этапами + авто-письмо «fertig zur Abholung» |
| **T5. Видимость Teile в смете/прайсе для клиента** (Arbeit + Teile раздельно, прозрачно) | прайс-прозрачность; клиент хочет видеть, за что платит | S | Есть: `JobLine` (text/qty/unit_price + product), Angebot-PDF разбивает позиции. Усилить вывод «Arbeit/Teile» группами |
| **T6. Zusatzleistungen/Extras к Termin** (Achsvermessung, Klima-Service, Leihwagen, Hol-Bring) с доплатой при онлайн-брони | werkstars/pitstop: доп-услуги к основному термину | S | Частично: универсальные `core.Extra` есть (scope booking) — нужно завести/показать для werkstatt |
| **T7. Versand-Reparatur (Handy/PC)** — отправка устройства почтой + статус | clickrepair: Versand с бесплатной пересылкой — половина рынка ремонта телефонов | M | Частично: `orders` G4 (Versand/трек) есть, но не привязан к ремонтному заказу `jobs` |

## Anti-Bitrix block editor

Принцип: «ребёнок соберёт сайт автосервиса за ≤10 шагов», блоки переиспользуемы,
умные дефолты по архетипу. Рекомендации (поверх M20/M20U, без новых моделей где
возможно):

**Переиспользуемые блоки (палитра секций для A9):**
1. **Leistungen-/Preis-Block** (новый или вариант существующего list-блока) —
   карточки услуг из `Service` с фикс-ценой/длительностью, «ab»-цена, кнопка
   «Termin» на каждой. Закрывает V1/V4.
2. **Termin-CTA-Block** — крупная кнопка «Termin online buchen» + «Kostenvoranschlag
   anfordern» (две основные точки входа архетипа). Переиспользует hero-CTA M20U.
3. **Kostenvoranschlag-/Anfrage-Block** — встроенная форма заявки с полем авто
   (после T1 — структурированным: Kennzeichen/HSN-TSN). Закрывает вход в `jobs`.
4. **Bewertungen-Block** — отзывы на самой витрине (сквозной пробел V3/`kit-coverage`
   §3.4); переиспользуется всеми архетипами доверия (отель/салон/ретрит/Werkstatt).
5. **Trust-/Meisterbetrieb-Block** — печати (Meisterbetrieb, Kfz-Innung,
   markenoffen, HU/AU vor Ort), «seit 1995», логотипы. Из `trust.marks` (уже есть).
6. **Teile-Shop-Block** — превью каталога запчастей (вход в `catalog`/`orders`).
7. (Handy/PC) **Modell→Preis-Block** — селектор модель/дефект → Sofort-Preis
   (V5/T5); более крупная фича.

**≤10-step онбординг к рабочему сайту Werkstatt (умные дефолты из кита):**
1. Выбрать архетип «Werkstatt» → подтягивается layout (hero «Termin/Angebot», блоки
   Leistungen+Trust+Bewertungen+Teile), accent Werkstatt-Blau.
2. Название + адрес + часы (Mo–Fr 8–17 как дефолт).
3. Лого/hero-фото (или дефолт `car,workshop`).
4. Услуги: предзаполнены 5 типовых (Ölwechsel/Inspektion/Reifenwechsel/HU-AU/
   Bremsen) с дефолт-ценами — правит цены/удаляет лишнее.
5. Ресурсы: 1–2 Hebebühne (дефолт), часы записи.
6. Trust-marks: галочки (Meisterbetrieb / markenoffen / HU-AU vor Ort) + «seit».
7. Teile (опц.): импорт/несколько позиций или выключить shop.
8. Kostenvoranschlag вкл/выкл + поле авто.
9. Право: Impressum/Datenschutz (автогенерация платформы).
10. Publish.

**Умные дефолты:** archetype-aware главная (Termin-CTA в hero, прайс-блок услуг
сразу под hero, Trust+Bewertungen ниже), часы Mo–Fr 8–17, НДС 19 %, депозит 0 €
(включается одним тумблером), напоминание брони вкл. по умолчанию.

## Prioritized backlog table

| # | Код | Что | Тип | Усилие | Закрывает |
|---|---|---|---|---|---|
| 1 | V1+V4 | **Leistungen-/Preis-блок** на витрине (карточки `Service` с Festpreis/длительностью + описание/фото) | Visual | S–M | прайс-прозрачность, главная боль |
| 2 | V3 | **Bewertungen-блок на витрине** (не только агрегатор) | Visual | S–M | доверие (сквозное, не только A9) |
| 3 | T1 | **Структурированные данные авто** (Kennzeichen/HSN-TSN/марка/модель) на `Job` (+опц. KBA-lookup) | Tech | M | идентификация авто, поиск Teile |
| 4 | T4 | **Repair-Status-view** клиенту + письмо «fertig zur Abholung» (поверх `JobSM`) | Tech | S–M | ремонт (KFZ + Handy/PC), меньше звонков |
| 5 | T2 | **TÜV/HU + Service-Reminder** (сущность обслуживаемого авто + next-HU + авто-письмо, opt-in UWG §7) | Tech | M | ретеншн (главный канал возврата) |
| 6 | T3 | **Reifeneinlagerung** (учёт комплекта + сезонная доплата онлайн + смена-сезона-reminder) | Tech | M–L | повторяющийся доп-доход |
| 7 | V2+T6 | **Termin-flow «услуга→авто→слот» + Zusatzleistungen** (Extras с доплатой) | Visual/Tech | M | конверсия записи |
| 8 | V5+T7 | **Handy/PC: Modell→дефект→Sofort-Preis + Versand-Reparatur** | Visual/Tech | M–L | подвертикаль ремонта устройств |
| 9 | — | **Демо-обогащение**: смета с расходником из каталога (G11 не виден), вкл. `customer_account`-showcase, пример Reifeneinlagerung | Demo | S | видимость готового движка |

**Рекомендация порядка:** дешёвые витринные победы #1–#2 (прайс-блок + отзывы,
сквозные и для других архетипов) → #3 структурированное авто (фундамент под #5/#6)
→ #4 статус ремонта (общий для KFZ и Handy/PC) → #5 TÜV-Reminder (ретеншн) → #6
Reifeneinlagerung. #8 (Handy/PC) — отдельный трек, если владелец захочет покрыть
эту подвертикаль явно.

---

### Sources
- [FairGarage — Werkstattportal](https://www.fairgarage.com/de-de/index.html), [Reifenservice](https://www.fairgarage.com/de-de/reifenservice)
- [autoservicepraxis — repareo](https://www.autoservicepraxis.de/nachrichten/kfz-werkstatt/werkstattportal-repareo-erweitert-serviceangebot-2622121), [Vermittlungsportale](https://www.autoservicepraxis.de/nachrichten/kfz-werkstatt/vermittlungsportale-suche-nach-der-zauberformel-2659185)
- [caroobi](http://caroobi.com/)
- [pitstop Radwechsel](https://www.pitstop.de/Services/Radwechsel), [Vergölst Radwechsel/Reifenmontage](https://vergoelst.de/services/radwechsel-reifenmontage.html), [ATU Reifenwechsel](https://www.atu.de/pages/meisterwerkstatt/wartung-service/reifenwechsel.html)
- [easyWerkstatt — HSN/TSN](https://easywerkstatt.com/download-links/hsn-tsn-abfrage/), [Kundenverwaltung](https://easywerkstatt.com/funktionen/kundenverwaltungsprogramm/), [Updates](https://easywerkstatt.com/updates/)
- [smartwerkstatt — HSN/TSN Teile](https://www.smartwerkstatt.cloud/blog/hsn-tsn-ersatzteile-guide), [ADAC HSN/TSN](https://www.adac.de/rund-ums-fahrzeug/auto-kaufen-verkaufen/kfz-zulassung/hsn-tsn-faq/)
- [TÜV SÜD — HU-Erinnerung](https://www.tuvsud.com/de-de/branchen/mobilitaet-und-automotive/hauptuntersuchung/hu-erinnerung)
- [clickrepair — Handy-Reparatur](https://www.clickrepair.de/), [Handywerkstatt](https://www.clickrepair.de/handywerkstatt)
