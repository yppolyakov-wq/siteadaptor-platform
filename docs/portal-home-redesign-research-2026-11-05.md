# Главная портала города — исследование рынка и «чего не хватает» (2026-11-05)

Запрос владельца (2026-11-05): «фильтр на главной портала скучный — разнообразить; посмотреть,
как сделаны порталы в этом направлении, чего не хватает; категории — в меню и крупнее; товар —
интереснее и выделеннее; сейчас это простой сельский сайт, нужен другой уровень»; референс —
https://unitheme.net/ (тема CS-Cart: выезжающее мега-меню категорий, чипы фильтров, богатые
карточки). Дизайн — через утверждение владельцем (правило 2026-08-24). Кода нет.

## Отчёт: главная «Entdecke Solingen» — рынок и чего не хватает

**Ограничение по источникам.** unitheme.net отдал 403, поэтому их паттерны восстановлены по документации и аналогичным темам CS-Cart. Платные статьи Baymard доступны только отрывками. Паттерны Booking, Zalando, Otto, Kleinanzeigen и Groupon ниже описаны по общеизвестной практике: ссылок на них нет, и перед мокапом их стоит проверить вживую.

### 1. Паттерны по областям

**Мега-меню категорий (референс владельца)**
- UniTheme — дочерняя тема Responsive от CS-Cart ([docs](https://docs.cs-cart.abt.team/en/abt__unitheme2.doc)).
- В родственных темах мега-меню устроено так: иконка или картинка категории, мини-описание, метки, миниатюры подкатегорий, баннер внутри меню ([VIVAshop](https://store.cart-power.com/vivashop-ultimate.html), [Smart Mega Menu](https://docs.simtechdev.com/addons/smart_mega_menu/index.html)).
- Бейджи на карточках («Neu», «−20 %», свои метки) делаются отдельным модулем ([Webkul Badges](https://store.webkul.com/CS-Cart-Product-Badges.html)).
- То, что владелец видел (большие строки «иконка + заголовок + описание + WICHTIG/POPULÄR + ›»), — это ровно этот паттерн.

**Категорийная полоса в стиле Airbnb**
- Горизонтальная лента «иконка + подпись», выбранная категория подчёркнута и выделена жирным.
- Работает для людей с размытой целью («что тут есть?»), а не для тех, кто знает, что ищет.
- Иконки читаются на любом языке.
- Источники: [разбор Crosley](https://blakecrosley.com/guides/design/airbnb), [Pratt critique](https://ixd.prattsi.org/2023/09/design-critique-airbnb-ios-app-2/), [Baymard: Airbnb](https://baymard.com/ecommerce-design-examples/filtering-options/10346-airbnb).

**Главная как набор каруселей (Wolt, Too Good To Go)**
- Wolt: баннер сверху, ниже карусели «Beliebt» / «Neu» / «Preiswert», затем строка категорий ([Wolt blog](https://blog.wolt.com/swe/2017/06/15/wolt-discovery)).
- Порядок каруселей Wolt задаётся по вовлечённости пользователей в конкретном городе, часть позиций закреплена вручную ([how search works](https://explore.wolt.com/en/deu/how-search-works)).
- Редизайн 2026: плавающий поиск и «window-shopping» — товары показываются поверх магазинов, а не только названия заведений ([press](https://press.wolt.com/en-WW/259591-wolt-redesigns-app-to-power-local-commerce-growth/)).
- TGTG, секции: «Empfohlen», «Jetzt abholen», «Heute/Morgen», «Neu», «Favoriten» ([TGTG](https://toogoodtogo.com/how-does-the-app-work), [Fueled](https://fueled.com/blog/too-good-to-go/)).
- TGTG, карточка: расстояние, ★ рейтинг, окно выдачи, цена, «noch N übrig».
- TGTG, сортировки: расстояние, цена, рейтинг, релевантность.
- Из неофициального редизайна TGTG ([UX Planet](https://uxplanet.org/too-good-to-go-redesign-e528b40f181e)):
  - нужна явная подпись «sortiert nach Entfernung»;
  - нужна сортировка «bald abholbar»;
  - распроданное в выдаче лишнее.

**Фильтры**
- Горизонтальная панель фильтров хороша, когда фильтров немного. При большом их числе теряется обзор, поэтому остальное уводят в «Alle Filter» ([Baymard horizontal](https://baymard.com/blog/horizontal-filtering-sorting-design)).
- Без строки применённых фильтров пользователи путаются и медленнее сужают выдачу ([Baymard applied filters](https://marketing-site-f2tmuig6e-baymard.vercel.app/blog/how-to-design-applied-filters)).
- Чипы подходят только для простых опций ([SAP Fiori](https://experience.sap.com/fiori-design-android/v0-9/filter-feedback-bar/)).
- Отраслевая норма (Zalando/About You/Booking/Airbnb):
  - чипы с выпадашками;
  - быстрые тумблеры («Jetzt geöffnet», «Angebote», «Kostenlose Stornierung»);
  - ползунок цены с гистограммой;
  - счётчик «N Ergebnisse» на кнопке применения;
  - на телефоне — нижняя шторка (bottom-sheet).

**Право (UWG)**
- Платное размещение (бывший § 5a Abs. 6, с 2022 — § 5a Abs. 4 UWG) нужно помечать явно ([e-recht24](https://www.e-recht24.de/online-marketing/12827-schleichwerbung.html)).
- Мелкое «Anzeige» рядом с яркой кнопкой считается недостаточным; выделенная позиция сама по себе воспринимается как рекомендация портала ([Ferner Alsdorf, OLG Karlsruhe](https://www.ferner-alsdorf.de/kennzeichnungspflichten-fuer-bezahlte-werbung-auf-vergleichsportalen/), [VZ](https://www.verbraucherzentrale.de/urteile/werbeanzeige-auf-vergleichsplattform-muss-deutlich-gekennzeichnet-werden-75822)).
- Отсюда правила:
  - метка «Anzeige» на каждой платной карточке, по контрасту и размеру не слабее CTA;
  - отдельная подписанная полоса;
  - органический порядок не смешивать с платным (это уже наш инвариант UWG §5a).

**Урок рынка**
- Локальные маркетплейсы обычно держат 30–60 продавцов на город и «gut gemeint, meist schlecht gemacht» ([Horizont](https://www.horizont.net/marketing/nachrichten/online-handel-lokale-marktplaetze-im-internet--immer-gut-gemeint-und-meist-schlecht-gemacht-178763)).
- Ценность — в «живости» и визитах, а не в онлайн-корзине. Главная должна выглядеть наполненной и сегодняшней.

### 2. Чего не хватает нашей главной (приоритет)

1. **Мега-меню «Kategorien».**
   - Выезжает слева.
   - 15 разделов крупными строками: иконка или фото, название, описание в одну строку, счётчик «N Angebote», бейдж «Beliebt/Neu», шеврон.
   - Справа — подкатегории с миниатюрами.
2. **Иконочная полоса разделов** под поиском в стиле Airbnb: SVG-иконки, горизонтальная прокрутка, sticky при скролле.
3. **Hero с живым поиском.**
   - Подсказки «Pizza heute», «Friseur Ohligs».
   - Чипы-примеры.
   - Строка цифр «N Geschäfte · N Angebote heute · N neu diese Woche» (полоса цифр у нас уже есть, GK-4).
4. **Быстрые тумблеры в строке фильтров:** «Jetzt geöffnet», «Angebote», «Neu», «In der Nähe», «Abholung heute» — плюс счётчик, пилюли ✕ и «Alle Filter».
5. **Богатая карточка предложения.**
   - Фото 4:3 с бейджами −N % / Neu / «Endet heute».
   - Логотип и название бизнеса.
   - Расстояние или район.
   - «Geöffnet bis 18:00».
   - ★ рейтинг (N).
   - Цена с зачёркнутой UVP/30-Tage-Preis (PAngV).
   - Сердечко «Merken».
   - Круглая кнопка быстрого действия: Zurücklegen / Coupon / Termin.
6. **Countdown и остаток** на карточках срочных акций: «noch 3 übrig», «endet in 02:14».
7. **Тематические карусели:** «Top-Deals heute», «Neu in Solingen», «Beliebt diese Woche», «Jetzt geöffnet in Ihrer Nähe», «Bald verfügbar / Vorschau».
8. **Полоса брендов и бизнесов:** круглые логотипы с подписью «Folgen».
9. **Карта районов:** кликабельные Stadtbezirke со счётчиками предложений и вход на `/stadtteil/`.
10. **Редакционные подборки** («Wochenmarkt», «Regional & Bio», сезонные) — большие фото-плитки, которые собираются по признакам T-8.13.
11. **Блок доверия:** «Geprüfte Geschäfte», реальные отзывы с фото, Google-рейтинг, «lokal aus Solingen».
12. **Визуальный уровень.**
    - Плотнее сетка: 4–5 колонок на десктопе.
    - Контрастные акцентные бейджи.
    - Фон секций чередуется.
    - Крупная фотография.
    - Тени и скругления 16 px.
    - Мобильный bottom-sheet для фильтров.
    - Платная полоса подписана «Anzeige» заметно.

### 3. Три концепта для мокапа

**A. «Marktplatz» — ближе всего к референсу UniTheme.**
- Слева мега-меню разделов (крупные строки, бейджи); на десктопе открыто, на телефоне выезжает.
- Справа hero-слайдер с акциями дня.
- Ниже ряды плотных товарных карточек с бейджами и кнопкой действия.
- Плюс полоса «Anzeige» и полоса логотипов бизнесов.
- Ощущение — «большой магазин города».

**B. «Heute in Solingen» — ставка на живость и срочность (TGTG + Wolt).**
- Hero: поиск и счётчики «heute».
- Иконочная полоса разделов, sticky.
- Строка тумблеров «Jetzt geöffnet / Angebote / Neu».
- Затем карусели: «Endet heute» с countdown, «Jetzt geöffnet in der Nähe», «Neu in der Stadt», «Beliebt diese Woche».
- Карточка ведёт с расстояния, часов работы и остатка.
- Ощущение — «что происходит сейчас».

**C. «Entdecken» — магазинный, визуальный (Airbnb + редакция).**
- Полноэкранная фото-шапка города с поиском.
- Иконочная полоса категорий в стиле Airbnb.
- Редакционные подборки большими плитками («Wochenmarkt», «Regional & Bio», «Für Familien»).
- Карта районов со счётчиками.
- Bento-сетка «Top-Deals» и витрина бизнесов-историй (фото владельца, «Seit 1952»).
- Ощущение — «журнал о городе, где можно сразу купить».

Рекомендация к мокапу: B как основа (сильнее всего отвечает на «скучно» и на урок Horizont про живость) плюс мега-меню из A как навигация. C — альтернатива для показа владельцу.

---

## Карта текущего кода (Explore, 2026-11-05)

- Корень портала без параметров рендерит `templates/aggregator/portal_discover.html`
  (`portal_views._render_home`, 956–1007): H1 · поиск · вкладки · полоса «Anzeigen» ·
  `_section_tiles` (эмодзи + подпись + счётчик, сетка 2/3/5) · 6 блоков по 6 карточек
  (`portal_home_blocks.BLOCKS`) · чипы районов · «Branche». **Строки фильтров FLT-1 на
  главной нет** — она только на ленте (`portal_home.html`, `_portal_filter_bar.html`).
- Шапка `portal_base.html`: логотип + язык + «Für Unternehmen»/вход; **меню/бургера/категорий нет**.
- Карточка `_cards.html` — одна на всё; квадратное фото, бейдж скидки, бизнес·город·район,
  рейтинг, цена/UVP/30-Tage, сердечко. **Данные есть, но не показаны:** часы работы на портале
  (`_attach_open_status` зовётся только на `/entdecken/`), `ends_at` (нет отсчёта при блоке
  «urgent»), `teaser`, `brand`, `city_tags` (vegan/regional), логотипа бизнеса в листинге нет вовсе.
- Реестр разделов `core/city_categories.py`: 15 разделов, иконка — эмодзи, картинок нет.
- Токен портала один — `--portal-color`; остальное серое/indigo Tailwind; `--ui-*` кабинета
  портал не использует.
- Замки разметки: `test_portal_discover.py` (34: блок ⊆ ленты, «★ Anzeige» отдельно, кэш без
  csrf, число запросов не растёт), `test_flt_*`, `test_portal_block_a/b`, `test_portal_seo`,
  `test_demo_hygiene`, `test_districts_portal`, `test_theme_portal`.
- Ограничения: главная кэшируется анонимно (POST-форм с csrf нет), UWG §5a — платное отдельно.
