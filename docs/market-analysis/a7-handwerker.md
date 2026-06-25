# A7 — Handwerker / выездной сервис: рыночный анализ и gap-analysis

Архетип A7 — выездные ремесленники DACH: Maler, Elektriker, SHK/Klempner,
Fliesenleger, Schreiner, Garten-/Landschaftsbau, Gebäudereinigung,
Hausmeisterservice, Umzug, Schlüsseldienst, Catering, mobiler Friseur,
Schädlingsbekämpfung. Бизнес-цикл принципиально иной, чем розница/бронь:
**Anfrage → Angebot (Kostenvoranschlag) → Auftrag → Rechnung**, без онлайн-оплаты
по умолчанию (Handwerker платят по счёту). Движок — `apps.jobs` (G6); выделенного
демо-кита Handwerker нет (ближайший — `werkstatt` для Kfz, A9).

Дата: 2026-06-25. Без правок кода — только анализ.

## Current coverage

Движок `apps.jobs` закрывает весь жизненный цикл заявки одной моделью `Job`
(зеркало `Order`/`StayBooking`):

- **Витрина-заявка `/anfrage/`** (`public_views.anfrage`, `templates/storefront/anfrage.html`):
  honeypot + rate-limit (5/600 c), поля title (обяз.), name (обяз.), email, phone,
  description, site_address (адрес работ ≠ адрес клиента), vehicle (A9 Werkstatt),
  **фото к заявке** до 5 шт ≤8 МБ (A7b, `add_job_photos` + `JobPhoto`),
  префилл темы из `?betreff`, письмо владельцу о новом лиде.
- **FSM `JobSM`** (`state_machine.py`): `new → quoted → accepted → done → invoiced`
  + выходы `declined`/`cancelled`. Переход `quoted` шлёт клиенту ссылку на публичное
  Angebot; `accepted`/`declined` уведомляют владельца (dedupe).
- **Кабинет `/dashboard/auftraege/`** (`views.py`): список по статусу, ручная
  заявка, конструктор сметы до 12 строк без JS (`JobLine`: text, qty Decimal — дробные
  часы A7a, unit_price нетто), VAT-rate, §19 Kleinunternehmer → НДС 0,
  пикер расходников из каталога (G11, `JobLine.product/variant` + списание склада
  при `done`), `valid_until` (Angebot gültig bis), Angebot-PDF (`pdf.build_quote_pdf`).
- **Публичное принятие `/angebot/<token>/`** (`public_views.angebot`): клиент без
  аккаунта принимает/отклоняет смету → FSM. **Online-Anzahlung** (A7c): при
  `deposit_cents > 0` и включённых платежах — Stripe Checkout (оплата = принятие).
- **Rechnung** (`quote_to_invoice`): черновик `finance.Invoice` из снимка позиций,
  получатель = клиент + адрес работ, суммы пересчитаны тем же `compute_totals`
  (совпадает со сметой); затем `done → invoiced`. DATEV/GoBD — в `apps.finance`.
- **Termin под работу** (A7d): `Job.booking → booking.Booking` — выездная запись из
  сметы (если включён модуль booking).
- **CRM**: `Customer` переиспользуется по email; PROTECT (DSGVO-анонимизация).
- **Демо**: дефолтные Catering-Anfrage у restaurant/pranasy (A4); `werkstatt`
  (`job_samples` с Fahrzeug, услуги, Teile-каталог). **Generic-кита Handwerker нет.**

Витрина (Site Builder, `apps.tenants/siteconfig.py` `SECTIONS`) уже даёт блоки:
hero (+слайдер), about, **process** («как мы работаем»), **team**, cta,
**testimonials**, **trust** (рейтинг + знаки + «Seit …»), **reviews** (из SHARED
`BusinessReview`), faq, **gallery** (до 24 фото), categories/products/events,
archetypes-тизеры, contact (часы/адрес). M20U: реестры `primary_item`/`purchase_mode`
(`jobs → request`, label «Anfrage senden»), hero-CTA, мобильный buybar.

**Оценка покрытия A7: ~75 %** функционального ядра цикла Anfrage→Rechnung (док
`micro-business-verticals.md` подтверждает ~75 %; `kit-archetype-coverage.md`
оценивает A7/A9 в связке ~100 %, но это про движок+Werkstatt-демо, а не про
generic-Handwerker как самостоятельный продукт с витриной-под-доверие).

## Market benchmark

**Лид-порталы (то, ОТ чего уводим бизнес).** MyHammer — лидер рынка, >8 млн
визитов/мес, клиент публикует задачу бесплатно, сравнивает мастеров и их рейтинги;
Check24 Profis — «опиши работу → получи предложения → выбери»; Blauarbeit —
членские пакеты вместо платы за лид; Aroundhome — крупные модернизации, преселект
предложений ([meister-leads](https://meister-leads.de/ratgeber/myhammer-alternativen),
[doozer](https://www.doozer.de/ratgeber/handwerker-portale-im-vergleich/)). Ключевая
боль порталов: **Kontaktgebühr 50–120 € за лид** независимо от исхода, конкуренция
за один заказ, мастер **не владеет ни клиентом, ни отзывами** — ровно тот
anti-marketplace-нерв, на котором стоит siteadaptor
([meister-leads](https://meister-leads.de/ratgeber/myhammer-alternativen)). Альтернатива,
которую советуют сами порталам-критики, — **собственный сайт + Google Business
Profile + own reviews**.

**Handwerkersoftware (бэк-офис).** Plancraft (от 29,90 €/мес), ToolTime, HERO,
Meisterwerk (модульно от 49 €/мес), pds/Streit/Sander — цифровые Angebot/Rechnung,
**Aufmaß (digitale Maße)**, тайм-трекинг, планирование, проект-менеджмент
([work5](https://work5.de/ratgeber/ratgeber/handwerker-software-vergleich),
[plancraft](https://plancraft.com/de-de/blog/handwerker-projektmanagement-software-vergleich),
[meisterwerk](https://www.meisterwerk.app/)). Это смежный, более тяжёлый сегмент;
siteadaptor конкурирует не с ними, а закрывает «витрина + лид + смета + счёт» легко.
Сигнал: Angebot/Rechnung — гигиена, наш дифференциатор — лёгкость и сайт-под-доверие.

**Что строит доверие на сайте Handwerker** (консенсус источников):
Meisterbrief/Meisterbetrieb, **Innungsmitgliedschaft**, Zertifikate/Fachbetrieb,
verifizierte Bewertungen на независимых платформах, годы опыта; **Referenzen mit
Bildern und kurzer Erklärung, idealerweise vorher/nachher (before/after)**; чёткие
контакты; быстрая загрузка
([owlymedia](https://www.owlymedia.de/blog/webseite-handwerker-anfragen),
[handwerkprojekt](https://www.handwerkprojekt.de/seo_local_seo_ki_seo_checkliste_fuer_handwerkbetriebe/),
[innung.org](https://www.innung.org/verbrauchertipps/handwerker-beauftragen/notdienst-service-von-handwerkern)).

**Что конвертирует:** контактная форма + телефон + **Rückruf-Option, в идеале с
гарантированным окном ответа**; **>80 % смотрят сайт с мобильного** — без идеального
мобайла «звонок не случится»; стратегически размещённые CTA и «klick-zum-anrufen»
([dbw-media](https://dbw-media.de/branchen/website-fuer-handwerker/),
[mein-handwerker-app](https://mein-handwerker-app.de/rueckruf/)). **Notdienst:**
Innungen/Betriebe держат телефон для экстренных вызовов — для SHK/Elektrik/
Schlüsseldienst Notdienst-баннер с телефоном — топ-конверсионный элемент
([innung.org](https://www.innung.org/verbrauchertipps/handwerker-beauftragen/notdienst-service-von-handwerkern)).

## Visual gaps

(A) Визуал/UX. Каждый: заголовок — почему (рынок) — объём — есть ли частично.

1. **Referenzen / before-after галерея как контент-тип.** Источники единогласно:
   проекты с фото и «до/после» — главный визуальный триггер доверия Handwerker
   ([owlymedia](https://www.owlymedia.de/blog/webseite-handwerker-anfragen)). Сейчас
   есть только общая `gallery` (плоский список фото) — нет пар «до/после», подписи
   проекта, категории работ. **Частично** (gallery). **M**.
2. **Notdienst-CTA / 24h-баннер с телефоном.** Для SHK/Elektrik/Schlüsseldienst —
   ключевой конверсионный блок (срочность + клик-звонок)
   ([innung.org](https://www.innung.org/verbrauchertipps/handwerker-beauftragen/notdienst-service-von-handwerkern)).
   Нет выделенного Notdienst-блока/липкого телефона. **Нет**. **S**.
3. **Meister/Innung/Siegel-блок доверия.** Meisterbetrieb, Innung, Zertifikate —
   сигнал компетенции ([handwerkprojekt](https://www.handwerkprojekt.de/seo_local_seo_ki_seo_checkliste_fuer_handwerkbetriebe/)).
   Есть `trust` (знаки-текст + «Seit …» + рейтинг), но без типизированных бейджей/
   логотипов (Meister-Icon, Innung-логотип, годовой стаж как крупная цифра).
   **Частично** (trust marks как текст). **S**.
4. **Презентация Einzugsgebiet (зона обслуживания).** Локальный сигнал: адрес,
   карта, «где мы работаем» ([dbw-media](https://dbw-media.de/branchen/website-fuer-handwerker/)).
   Нет блока «Wir arbeiten in …» / списка PLZ/городов / карты-радиуса. **Нет**. **M**.
5. **Мобильный «klick-zum-anrufen» / sticky-телефон.** >80 % трафика — мобайл;
   видимый телефон-кнопка решает ([dbw-media](https://dbw-media.de/branchen/website-fuer-handwerker/)).
   Есть мобильный buybar (M20U) под «Anfrage senden», но без явной tel:-кнопки
   рядом. **Частично**. **S**.
6. **Обещание времени ответа (Reaktionszeit).** «Antwort innerhalb 24 h /
   Rückruf am selben Tag» снижает трение лида ([dbw-media](https://dbw-media.de/branchen/website-fuer-handwerker/)).
   Нет места для промиса на форме/hero. **Нет**. **S**.
7. **Leistungen как структурированный список с иконками.** Сайты Handwerker
   ведут «что мы делаем, где, почему доверять» ([handwerkprojekt](https://www.handwerkprojekt.de/seo_local_seo_ki_seo_checkliste_fuer_handwerkbetriebe/)).
   Сейчас услуги выражаются через каталог/archetypes-тизеры — нет лёгкого
   «service-list» (иконка + название + 1 строка) без заведения товаров. **Частично**.
   **S**.

## Technical gaps

(B) Технические/функциональные.

1. **Поле PLZ/зоны обслуживания в модели + фильтр на форме.** Нужно для
   «обслуживаем ли мы ваш адрес» и для лид-квалификации
   ([dbw-media](https://dbw-media.de/branchen/website-fuer-handwerker/)). У `Job`
   нет PLZ-поля; `site_address` — свободный текст. Для зон уже есть прецедент
   (`delivery_zones` с PLZ в demo_kits). **Нет** (для jobs). **M**.
2. **Rückruf-Anfrage (запрос обратного звонка) как лёгкий лид.** Многие хотят не
   полную смету, а «перезвоните» ([mein-handwerker-app](https://mein-handwerker-app.de/rueckruf/),
   [winworker](https://www.winworker.de/rueckruf/)). Сейчас минимум — name+title;
   нет отдельного «только телефон + удобное время» (mode заявки). **Частично**
   (форма есть, но title обязателен). **S**.
3. **Структура заявки по типу работ (Leistung-выбор).** Check24/MyHammer ведут
   клиента «выбери услугу → опиши». На форме нет выпадающего «Was brauchen Sie?»
   (Malern/Elektrik/…), мастер потом сам типизирует. **Нет**. **S/M**.
4. **ReReferenz/Projekt как контент-сущность** (а не плоское фото): заголовок,
   до/после, категория, текст, привязка к Leistung. **Нет** (есть gallery JSON).
   **M**.
5. **Online-Anzahlung уже есть** (A7c, Stripe Checkout из Angebot) — рынок это
   ценит для дорогих заказов, но Handwerker по умолчанию платят по счёту → держим
   опциональным. **Есть**. —
6. **Termin/Scheduling под выезд уже есть** (A7d `Job.booking`) — для записи на
   замер/выезд. **Есть**. —
7. **Дробные часы/единицы в смете уже есть** (A7a, qty Decimal). **Есть**. —
8. **Bewertungen на витрине бизнеса.** `reviews`-блок читает SHARED
   `BusinessReview` (агрегатор) — но сбор отзывов после `invoiced` (письмо-просьба
   оставить отзыв) не автоматизирован под jobs. Verifizierte Bewertungen —
   топ-доверие ([owlymedia](https://www.owlymedia.de/blog/webseite-handwerker-anfragen)).
   **Частично**. **M**.
9. **Гарантия времени ответа как поле настройки** (для промиса на форме). **Нет**.
   **S**.

## Anti-Bitrix block editor

Принцип северной звезды: setup ≤5–10 шагов, нативное лёгкое редактирование,
«ребёнок соберёт сайт». Блочно. Все рекомендации — поверх существующего
JSON-Site-Builder (`siteconfig.SECTIONS`), **без новых тяжёлых моделей**, в духе
M20U («архетип = главный товар + способ покупки»).

**Переиспользуемые блоки (новые секции в `SECTIONS`, по образцу `trust`/`process`):**

1. **`service_list` — блок услуг** (иконка + название + 1 строка). Smart-default:
   засеян из набора Leistungen архетипа (Maler/Elektriker/…). Решает Visual-7,
   Tech-3 (источник для дропдауна на форме).
2. **`request_form` — встроенная форма заявки на главной** (а не только `/anfrage/`).
   Поля конфигурируются галочками: фото (уже есть), PLZ (Tech-1), «удобное время
   звонка» (Rückruf-mode, Tech-2), Leistung-дропдаун (Tech-3). Промис времени
   ответа над кнопкой (Visual-6/Tech-9).
3. **`references` / `portfolio` — галерея проектов с до/после** (пары фото +
   подпись + категория). Расширение текущей `gallery` до типизированной (Visual-1,
   Tech-4). Это самый важный новый блок — рынок ставит Referenzen во главу доверия.
4. **`service_area` — блок зоны обслуживания** (список PLZ/городов + опц. карта-
   радиус). Smart-default из адреса бизнеса + ввод PLZ. Решает Visual-4, Tech-1.
5. **`trust_badges` — типизированные бейджи** (Meister, Innung, Jahre, Siegel) —
   апгрейд `trust` от текста к иконкам/логотипам (Visual-3).
6. **`notdienst` — Notdienst-баннер** (телефон + «24h / sofort», sticky на мобайле).
   Включается галочкой (для SHK/Elektrik/Schlüssel). Visual-2/5.
7. **`reviews`** — уже есть; подключить авто-запрос отзыва после `invoiced`
   (Tech-8).

**≤10-шаговый онбординг к работающему лид-сайту Handwerker:**
1. Выбрать вид ремесла (Gewerk) → дефолтные Leistungen/тексты/цвета.
2. Название + логотип. 3. Телефон + email + адрес. 4. Зона обслуживания (PLZ/города).
5. 3–5 услуг (предзаполнены, правятся). 6. 2–4 фото-референса (опц. до/после).
7. Знаки доверия (Meister/Innung — галочки + «Seit …»). 8. Notdienst вкл/выкл +
телефон. 9. Промис времени ответа. 10. Опубликовать. Smart-defaults закрывают
1/5/6/7 «из коробки» → реально 4–5 обязательных вводов.

**Smart-defaults:** archetype-aware главная для `jobs` = hero (CTA «Anfrage
senden» + tel:) → service_list → references → trust_badges → service_area →
reviews → request_form → contact. Notdienst — вкл по дефолту для срочных Gewerke.

**Нужен ли выделенный демо-кит «Handwerker»? — ДА (приоритет средний).**
Сейчас движок jobs виден только через `werkstatt` (Kfz-специфика: Fahrzeug,
Hebebühne) и Catering-заглушки (A4). Для маляра/электрика/SHK нет ни одного
showcase, демонстрирующего цикл Anfrage→Angebot→Rechnung **без авто-контекста** —
а это самый широкий сегмент A7. Рекомендация: кит `maler` (или `handwerker`),
business_type `other`, модули `jobs` (+booking для замера, +customer_account),
с job_samples (смета «2 Zimmer streichen»: Arbeit-часы + Material), service_list,
references (до/после), trust (Meister/Innung), service_area (PLZ). Док-план перед
кодом (конвенция). Это и закроет замечание `kit-archetype-coverage.md` §2.107
(«опц. кит Handwerker (Maler), generic, без авто-специфики»).

## Prioritized backlog table

| # | Что | Тип | Почему (рынок) | Объём | Частично? |
|---|---|---|---|---|---|
| 1 | Кит-демо `handwerker`/`maler` (generic, jobs) | Demo | A7 не виден без Kfz-специфики; широчайший сегмент | M | нет (есть werkstatt) |
| 2 | `references` блок (галерея проектов + до/после) | Visual+Tech | Referenzen — главный триггер доверия Handwerker | M | gallery |
| 3 | `service_area` блок + PLZ на `Job` | Visual+Tech | Einzugsgebiet — локальный сигнал и квалификация лида | M | delivery_zones-прецедент |
| 4 | `notdienst`-баннер + sticky tel: на мобайле | Visual | Notdienst-телефон — топ-конверсия для SHK/Elektrik/Schlüssel | S | нет |
| 5 | `request_form` на главной + Rückruf-mode + промис времени | Visual+Tech | >80 % мобайл; Rückruf и быстрый ответ конвертируют | M | /anfrage/ есть |
| 6 | `service_list` блок (Leistungen, иконки) + источник дропдауна формы | Visual+Tech | «что мы делаем» структурно; гайд клиента по услуге | S | archetypes/каталог |
| 7 | `trust_badges` типизированные (Meister/Innung/Jahre/Siegel) | Visual | Meisterbetrieb/Innung — сигнал компетенции | S | trust (текст) |
| 8 | Авто-запрос отзыва после `invoiced` → `reviews` на витрине | Tech | Verifizierte Bewertungen — доверие, own reviews vs порталы | M | reviews-блок |
| 9 | Поле «Reaktionszeit» в настройках для промиса на форме | Tech | Гарантированное окно ответа снижает трение | S | нет |

Источники: см. инлайн-ссылки выше (meister-leads, doozer, owlymedia, handwerkprojekt,
innung.org, dbw-media, mein-handwerker-app, winworker, work5, plancraft, meisterwerk).
