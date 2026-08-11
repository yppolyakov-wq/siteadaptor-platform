# Gap-анализ: goodkarma-catering.de ↔ siteadaptor-platform (2026-08-11)

Запрос владельца: «проанализируй https://www.goodkarma-catering.de/ — чего не хватает
на платформе, чтобы создать такой же сайт».

Метод: воркфлоу 14 агентов — 4 обошли сайт постранично (13 страниц), 6 сверили кодовую
базу по измерениям (билдер-секции, флоу заявки, контент-страницы, отзывы/social proof,
маркетинг/newsletter, архетип-соответствие), затем адверсариальная верификация всех
24 заявленных пробелов вторым проходом (каждый вердикт — с file-path-доказательствами).

## 1. Что за сайт

Лид-ген сайт вегетарианского/веганского кейтеринга (Münster, «deutschlandweit»).
**Никакой онлайн-продажи нет** — вся конверсия = форма заявки на событие.

Структура: главная (hero → рейтинг-плашка 4.9★/40+ клиентов с рядом аватарок → сетка
6 категорий услуг → 3 столпа философии → карусель отзывов → цифры «200+ Events /
50.000+ Gerichte / 10.830+ Gäste» → цитата основателя → форма заявки → footer с
newsletter) · `/services` + 6 лендингов категорий (Fingerfood/Hochzeiten/Seminar/
Business/Private/Messe — каждый: hero, вместимость «20–1000 Gäste», цена «ab 25 €
p.P.», список включённого, related-карточки, **форма заявки внизу**; у Fingerfood —
3 пакета Klassik/Plus/Premium) · `/menu` (табы категорий блюд; фактически пустая) ·
`/gallery` (плоская) · `/about` · `/faq` · `/blog` (1 пост) · право · newsletter.

Форма заявки на service-лендингах: Name, E-Mail, Telefon, **Art der Veranstaltung
(дропдаун), Wunschdatum, Anzahl Personen**, Nachricht. На главной — урезанная
(Name/E-Mail/Nachricht).

Примечательно: JSON-LD у них нет вовсе, FAQ без разметки, cookie-баннера нет,
меню пустое. Технически сайт слабый — конкурируем не с технологией, а с версткой.

## 2. Что у нас УЖЕ ЕСТЬ (подтверждено кодом)

| Возможность сайта-референса | Наш статус |
|---|---|
| Hero с CTA, слайдер | ✅ `_hero.html` + hero_widget/hero_tiles |
| Сетка категорий с фото | ✅ секция `categories` + `_category_tile.html` |
| Отзывы: страница `/bewertungen/`, секция, агрегат «4.9 (11)» | ✅ reviews.Review + BusinessReview + `_trust.html` |
| Кураторские testimonials (5 стилей) | ✅ site.testimonials + `testimonials_ref` |
| FAQ секция + **FAQPage JSON-LD** (у них нет!) | ✅ site.faq + `faq_ref` на 11 страницах |
| Галерея `/galerie/` (5 стилей, лайтбокс) | ✅ ST-8 |
| Team `/team/` | ✅ ST-8 |
| Блог: список/деталь/SEO/отложенная публикация/авто-шаринг | ✅ events.BlogPost (у них — 1 пост без разметки) |
| «Über uns» с C-блоками | ✅ `/ueber-uns/` + page_blocks["info"] |
| Право (Impressum/Datenschutz/AGB per-locale) | ✅ LegalDoc |
| Newsletter c **Double-Opt-In UWG §7** + RFC 8058 отписка | ✅ `/newsletter/` (у них DOI не виден) |
| Контакт-форма → inbox-тред с поллингом/typing | ✅ `/nachricht/` |
| Заявка → Angebot онлайн-принятие (+Anzahlung Stripe) | ✅ jobs `/anfrage/`→`/angebot/<token>/` + orders.Offer |
| WhatsApp/«Jetzt erreichbar» | ✅ (у них нет) |
| Диет-метки vegan/vegetarisch + аллергены + фильтр | ✅ food.py (их /menu вообще пуст) |
| Browse-only меню без корзины | ✅ выключить модуль orders — buybox/quick-add гаснут |
| «ab X €» цены | ✅ через варианты |
| Service-area «deutschlandweit» | ✅ Tenant.service_area_note |
| Часы работы в футере | ✅ |
| Кастом-домен | ✅ domains.py + Caddy on-demand TLS |
| Мультиязычность | ✅ (у них DE-only) |

**Вывод: сайт такого класса на платформе собирается уже сегодня** (business_type
restaurant/other + jobs primary + orders off), и по SEO/право/consent он будет
*сильнее* референса. Пробелы — ниже, по убыванию боли.

## 3. Пробелы (все верифицированы вторым проходом)

**Уточнение (владелец, 2026-08-11: «у нас же есть вроде catering»).** Верно:
кейтеринг как ПУТЬ на платформе есть — «Catering»/«Partyservice» в китах
restaurant, bakery, butcher и pranasy (пункт меню `_("Catering")` в
tenants/menu.py:269, hero-плитка «Partyservice anfragen» в `_hero_widget.html:97`,
job_samples «Catering Firmenfeier (25 Personen)», карточка «Events &
Catering-Anfragen» на /branchen/restaurant). Но ВСЕ эти входы — `type=archetype,
target=jobs`, т.е. ссылки на одну и ту же универсальную `/anfrage/` без
событийных полей («там только форма заявки у pranasy» — именно так). Спека
**MB-3** (`archetype-behavior-specs-2026-07-23.md`) уже требовала мини-форму
«дата события · гостей · пожелания» на главной как дефолт — реализован был
фолбэк-вариант (карточка-переход на /anfrage/), мини-форма не построена.
Пробелы C-1/C-2 — это «кейтеринг как ОСНОВНОЙ бизнес» + закрытие MB-3, а не
«кейтеринга нет вовсе».

### Tier 1 — ядро конверсии кейтеринга (блокируют «такой же сайт»)

- **C-1. Нет архетипа «Catering» как основного бизнеса** [подтверждено].
  Кейтеринг существует только как побочное предложение гастро-архетипов (см.
  уточнение выше); для ЧИСТОГО кейтеринг-бизнеса типа Good Karma нет:
  business_type в BUSINESS_TYPES (15 шт.), карточки мастера, `/branchen/`-страницы,
  демо-кита (14 шт.), JSON-LD `FoodEstablishment`/`CateringService` (grep = 0;
  добавить в `_SCHEMA_TYPES` — 2 строки по прецеденту AutoRepair, но только после
  появления типа). S6a показал, как добавлять типы (⚠️ миграция choices).
- **C-2. В `/anfrage/` нет событийных полей** [partial; = закрытие MB-3].
  Форма jobs: title/описание/имя/контакты/адрес/фото — **нет Wunschdatum, нет
  Anzahl Personen, нет дропдауна «Art der Veranstaltung», нет бюджета**
  (проверено чтением anfrage.html построчно). Для кейтеринга это главный
  инструмент продажи. Плюс: CTA «Angebot anfordern» из детали услуги идёт на
  /anfrage/ БЕЗ `?betreff=` — префилл-механика есть, но не подключена
  (apps/jobs/public_views.py:95).
- **C-3. Форму заявки нельзя встроить блоком на страницы** [partial]. У референса
  форма — внизу КАЖДОГО лендинга. У нас REPEATABLE_BLOCKS = text/image/image_text/
  button/spacer/promo, PAGE_REF_BLOCKS = faq/team/gallery/testimonials — form-блока
  нет; секция `contact` (home-only) — контакты без формы. Сегодня максимум —
  button-блок «Anfragen» → /anfrage/. Кандидат: `inquiry_ref`/`contact_form_ref`
  в PAGE_REF_BLOCKS (рендер существующей формы, POST в существующий приёмник).
- **C-4. Нет блока «полоса цифр»** [confirmed_missing]. «200+ Events / 50.000+
  Gerichte / 10.830+ Gäste» — ни секции, ни C-блока stats/counters. Обходной путь
  (3 узких text-блока в ряд через group_block_rows) без единой стилистики крупных
  чисел. Дешёвый кандидат: C-блок `stats` (пары число+подпись) + 2-3 пресета.

### Tier 2 — визуальный паритет главной

- **C-5. usp_bar без описаний** [partial]: icon+label (макс 6, фикс-эмодзи) — их
  «3 столпа философии» требуют icon+заголовок+абзац. Вариант: стиль `pillars` у
  usp_bar с полем text, либо пресет из трёх image_text.
- **C-6. Testimonials без фото и рейтинга; нет карусели** [partial]: пары name|text;
  звёзды — только у реальных BusinessReview; слайдер есть лишь у hero. Аватар-ряд
  «40+ Kunden» не собрать (поля фото нет вообще).
- **C-7. Цитата основателя** [partial]: собирается из image_text/пресета quote, но
  без полей имя/роль — некритично, хватит пресета `founder_quote` (фото+цитата+имя).
- **C-8. Newsletter не встраивается инлайн** [partial]: DOI-флоу полный, но подписка —
  только отдельная страница `/newsletter/`; email-поля в футере/секции нет. Кандидат:
  `newsletter_ref`-блок / опция футера, POST в существующий endpoint.
- **C-9. Нет настройки соцссылок** [partial]: Instagram/LinkedIn в шапку можно
  только текстовым пунктом меню (url-node); иконок-ряда в футере и поля в настройках
  нет (publishing OAuth — про постинг, не про отображение).

### Tier 3 — за пределами паритета (референс этого тоже не имеет / external)

- **C-10. Цена «pro Person» не first-class** [partial]: нет юнита, гостевого
  калькулятора, tier-цен («от 50 гостей дешевле»); Combo — фикс-цена (обход:
  цена=p.P., qty=гости). Пакеты Klassik/Plus/Premium моделируются 3 услугами/Combo.
  Реальный кейтеринг-прайс живёт в jobs-Angebot (qty×цена) — это уже есть.
- **C-11. Google-рейтинг/отзывы не подтягиваются** [confirmed_missing]: GBP-интеграция
  только исходящая (localPosts); «11 Google-Bewertungen» показать нечем — свой
  BusinessRating есть, но у нового тенанта он пуст. Places API — external-gated
  (→ external-integrations-backlog). Внимание: комментарий в `_trust.html:1` врёт
  («рейтинг Google» — рендерится наш рейтинг).
- **C-12. Instagram-feed embed** [confirmed_missing] — референс тоже не встраивает
  (только ссылки); если делать — через consent-гейт (принцип no-tracking, паттерн
  2-Klick как у YouTube).
- **C-13. PDF-меню** [partial]: documents-слой зрелый (5 генераторов), но генератора
  Speisekarte нет, и **загрузить произвольный PDF нельзя вовсе** (все upload-пути
  image-only). Референсу не нужно — по спросу.
- **C-14. Newsletter-композер минимален** [partial]: plain-text, без сегментации
  контент-кампаний/расписания/аналитики. Для паритета не нужно.
- Мелочь: галерея — плоская, кап 24 фото, без подписей/альбомов (у референса тоже
  плоская); лендинги услуг — наша деталь `/leistung/<uuid>/` покрывает анатомию
  (hero/фото/атрибуты/FAQ/related/CTA), но кастомных slug'ов/произвольных страниц
  нет (PAGE_BLOCK_HOSTS — закрытый список 11; CustomPage-модели нет — известное
  ограничение, вариант B UC2-3 за решением владельца).
- Попутная находка [actually_exists]: соцпостинг GBP/FB/IG **код-комплитен**,
  блокер только операционный (ключи Meta/Google в прод + app review) — уже учтено
  в external-integrations-backlog.
- Попутная находка (пред-существующая): публичная контакт-форма принимает POST-параметр
  `phone`, но `message_contact.html` инпут телефона не рендерит — поле никогда не
  собирается. Дешёвый фикс при C-2/C-3.

## 4. Рекомендуемый порядок (если владелец говорит «делаем»)

1. **C-2 + C-3** — событийные поля заявки + form-блок на страницы (ядро конверсии;
   без миграции: поля Job-модели можно нести в description/структурировать позже,
   либо ⚠️ маленькая аддитивная миграция jobs — решить план-доком).
2. **C-1** — архетип Catering: business_type (⚠️ миграция choices) + пресеты модулей
   (jobs primary, orders off, catalog=Speisekarte) + JSON-LD + карточка мастера +
   `/branchen/catering` + демо-кит «по новой идеологии».
3. **C-4 + C-5 + C-8** — блок цифр, usp-pillars, инлайн-newsletter (билдер, без миграций).
4. **C-6 + C-7 + C-9** — фото/рейтинг у testimonials, founder-пресет, соцссылки.
5. Tier 3 — по спросу / external-gated.

Пункты 1–4 закрывают «такой же сайт» полностью и усиливают ВСЕ гастро-архетипы
(restaurant/cafe/bakery/butcher получают форму-блок, цифры, pillars бесплатно).

Задачам нужны ID из `docs/task-catalog.md` ДО план-дока (конвенция §6) — присвоить
при отмашке владельца.
