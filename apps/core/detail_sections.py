"""UA4-1 (U-A): единый реестр секций детальной страницы — KEYS + подписи (LABELS)
в одном месте, для всех kind (товар/услуга/номер/событие).

Раньше KEYS жили в `apps/tenants/siteconfig.py`, а подписи для билдера — отдельно
в `apps/core/views.py` (`_EVENT_SECTION_LABELS`/`_PRODUCT_SECTION_LABELS`). Здесь они
сведены в ОДИН источник: инспектор билдера и (позже, UA4-2) data-driven рендер читают
его, а не два рассинхронных списка.

Границы (важно):
- Здесь ТОЛЬКО опциональные body/wide секции детали (описание/атрибуты/FAQ/инфо/
  отзывы/команда/amenities/похожие/тематические). Спец-секции (галерея/buy-box/buybar)
  НЕ здесь — они всегда присутствуют, живут в своих `{% block %}` и не управляются
  реестром (инвариант §6 плана).
- UA4-1 = только реестр/подписи (нулевое изменение вывода витрины). Data-driven цикл
  рендера — UA4-2. Обобщённый нормализатор `config['<module>_detail']` — Slice B (пока
  KEYS-нормализация остаётся в `siteconfig.py`, а реестр держит те же ключи + подписи).

`module` — ключ модуля витрины (`catalog`/`events`/`booking`/`stays`), совпадает с
источником в `apps.core.archetypes`. Порядок дескрипторов = дефолтный порядок рендера.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class ContentSource:
    """FB-33 M5d-2: откуда содержимое раздела и где оно правится — для части окна «Inhalt»
    (`apps/core/window_parts.py::content_part`). Только описание: ссылку, право и тексты
    видимости строит часть окна. Куда ведёт ссылка — по-прежнему `DetailSection.content_nav`
    (экран у `setting`, СПИСОК объектов у `field`, «Seiten» у `page`); второго списка экранов
    здесь нет. Все тексты — `gettext_lazy`."""

    #: "field" — поле объекта (у типа — ссылка на список, у объекта — на его форму);
    #: "setting" — экран настроек; "page" — редактор текстовой страницы; "auto" — править нечего
    kind: str
    #: после «Dieser Block zeigt:» (без точки; «%(page)s» — имя текстовой страницы);
    #: пусто — сводка или подпись строки, как у G2
    shows: object = ""
    #: после «Woher:» целой фразой с точкой; у "field" — собирается из подписи поля и
    #: `site_schema.OBJECT_WORDS`
    woher: object = ""
    #: имя поля формы объекта, если подпись есть в коде формы
    #: (`site_schema.object_field_label`); иначе — `field_label` и замок «подпись есть на форме»
    field: str = ""
    field_label: object = ""
    #: что считать «ausgefüllt» у объекта: атрибуты и ключи словаря ("description",
    #: "details.idea"); хватает одного заполненного
    fields: tuple = ()
    #: добавка к адресу экрана («?tab=lieferung») и её подпись («Lieferung» → «… › Lieferung»)
    query: str = ""
    sub: object = ""
    #: фраза после сводки («Hierhin führt „zzgl. Versandkosten“ bei jedem Preis.»)
    note: object = ""
    #: у типа после «Woher»: когда раздел вообще появляется (`ONLY_IF_FILLED` или свой текст);
    #: у раздела с presence-гейтом обязателен
    only_if: object = ""
    #: источник только у строки ОБЪЕКТА: у типа у этой строки своё окно («Ähnliche Produkte»)
    object_only: bool = False


#: FB-33 M5d-2: обычное «когда появляется» раздела-поля
ONLY_IF_FILLED = _("Erscheint nur, wenn das Feld ausgefüllt ist.")


@dataclass(frozen=True)
class DetailSection:
    """Дескриптор одной секции детальной страницы (мета, не данные).

    `label` — ленивая i18n-строка (подпись в инспекторе билдера). `hideable` — можно
    ли скрыть через билдер; `orderable` — можно ли переупорядочить (сейчас только
    event; product/service/stay — hide-only, порядок фиксирован шаблоном)."""

    key: str
    label: object
    hideable: bool = True
    orderable: bool = False
    #: FB-33 M2g: раздел «на месте» — только скрывается: не двигается, в поток/вкладки и якоря
    #: своих блоков не входит (страница рисует его там, где он был)
    in_place: bool = False
    #: FB-33 M2g: у общего хоста двух видов (события и туры) — чей это раздел ("event"/"tour")
    only: str = ""
    #: FB-33 M5d-1: имя URL экрана кабинета, где правится содержимое неподвижной строки
    #: (часть окна «Inhalt»); подпись ссылки и доступ — из записи `nav_registry` по этому имени
    content_nav: str = ""
    #: FB-33 M5d-2: откуда содержимое (поле объекта, настройка, текст страницы, авто); None и
    #: `content_nav` — прежняя строка G2 (экран настроек, сводка — из строки)
    source: ContentSource | None = None


#: FB-33 M5d-3: закреплённый текст текстовой страницы («Über uns», «Versand», своя «Seite») —
#: правится в её редакторе («Seiten › <имя страницы>»); один источник на три хоста
_PAGE_TEXT = ContentSource(kind="page", shows=_("den Text der Seite „%(page)s“"))

# UC5-1: граница канвы — buy-box (выбор дат/слотов/количества, POST-движки
# брони/покупки) конфигурируется ФОРМОЙ, не канвой: он сознательно НЕ входит в
# DETAIL_SECTIONS ни одного модуля (нельзя скрыть/перетащить/вставить on-canvas);
# канва правит презентацию ВОКРУГ (единый _buybox.html — диспатч по
# purchase_mode + двухшаговый гейт, UA3-1/3-2). Замок —
# test_buybox_boundary_not_canvas_configurable.
BUYBOX_CONFIGURABLE = "form"

# module → секции детальной в дефолтном порядке рендера. Ключи совпадают с
# `siteconfig.{EVENT,PRODUCT}_DETAIL_SECTION_KEYS` (Slice B сведёт и их к реестру).
DETAIL_SECTIONS: dict[str, tuple[DetailSection, ...]] = {
    # --- catalog ---
    "catalog": (
        DetailSection("description", _("Description")),
        DetailSection("info", _("Product info (origin/ingredients/allergens)")),
        # FB-33 M2f: разделы первого экрана, которые раньше были зашиты в страницу товара
        DetailSection("sizes", _("Größentabelle")),
        DetailSection("trust", _("Vertrauensleiste")),
        DetailSection("anprobe", _("In der Anprobe zurücklegen")),
        DetailSection("waitlist", _("Warteliste")),
        DetailSection("instore", _("Im Geschäft erhältlich")),
        DetailSection("question", _("Frage stellen")),
        DetailSection("reviews", _("Customer reviews")),
        DetailSection("related", _("Related products")),
        # FB-33 M2f: «Zuletzt angesehen» — только в браузере посетителя (localStorage)
        DetailSection("recent", _("Zuletzt angesehen")),
    ),
    # --- events ---
    "events": (
        DetailSection("for_whom", _("For whom"), orderable=True),
        DetailSection("idea", _("The idea"), orderable=True),
        DetailSection("includes", _("What's included"), orderable=True),
        DetailSection("program", _("Schedule"), orderable=True),
        DetailSection("venue", _("Venue"), orderable=True),
        DetailSection("accommodation", _("Accommodation"), orderable=True),
        DetailSection("food", _("Food"), orderable=True),
        DetailSection("hosts", _("Hosts"), orderable=True),
        DetailSection("price", _("Price"), orderable=True),
        DetailSection("bring", _("What to bring"), orderable=True),
        DetailSection("faq", _("FAQ"), orderable=True),
        DetailSection("testimonials", _("Testimonials"), orderable=True),
        DetailSection("before_after", _("Before & after"), orderable=True),
        DetailSection("certifications", _("Certifications"), orderable=True),
        # FB-33 M2g: после «Buchung», скрываются на месте (у тура — свой раздел приватного выезда)
        DetailSection("groups", _("Groups & companies"), in_place=True, only="event"),
        DetailSection("more_dates", _("Weitere Termine"), in_place=True, only="event"),
        DetailSection("private_tour", _("Request a private tour"), in_place=True, only="tour"),
    ),
    # --- booking ---
    # UA4-1 slice C: секции детальной УСЛУГИ (booking.Service) — ключи по факту
    # service_detail.html (описание/атрибуты/FAQ/команда/отзывы). Hide-only.
    "booking": (
        DetailSection("description", _("Description")),
        # LS-1: «📹 Per Video zeigen lassen» — wa.me-CTA; present-гейт: услуга
        # is_video И у бизнеса есть whatsapp_number. Скрываемо как любая секция.
        DetailSection("video", _("Video-Beratung")),
        DetailSection("attributes", _("Details")),
        DetailSection("faq", _("Frequently asked questions")),
        DetailSection("team", _("Our team")),
        DetailSection("reviews", _("Customer reviews")),
        # B3: кросс-селл товаров («к стрижке берут шампунь») — при активном
        # catalog и наличии товаров; скрываемо в билдере как любая секция.
        DetailSection("upsell", _("Goes well with this")),
    ),
    # --- confirmation ---
    # UA4-1 slice C: секции детальной НОМЕРА (stays.StayUnit) — по факту stay_detail.html
    # (описание/оснащение/отзывы/похожие). Hide-only.
    # FB-32 S4: страница корзины — «Passt gut dazu» строкой схемы (двигается, скрывается,
    # свои блоки выше/ниже). Видимость — прежний ключ `cart_show_upsell`.
    # FB-33 M2h: оформление — строки корзины: позиции, форма и итог с кнопкой неподвижны и не
    # скрываются (§ 312j BGB: кнопка сразу после итога); свои блоки — над корзиной, «Hinweise»
    # над формой (после позиций), под сеткой и в хвосте
    # FB-33 M2h: подтверждение (заказ, запись, номер, билет, стол) — карточка сделки неподвижна;
    # «Was passiert jetzt» — только при своём тексте; «Empfehlungen» включает владелец (K3)
    # FB-33 M5d-5: «Bestätigung» собирается из сделки (править нечего); «Empfehlungen» — товары
    # с галочкой «Empfohlen» (`catalog.upsell`, не больше `confirmation_page.RECOMMEND_MAX`),
    # ссылка — «Sortiment» (ответ владельца: записи «Produkte» в навигации нет)
    "confirmation": (
        DetailSection(
            "summary",
            _("Bestätigung"),
            hideable=False,
            source=ContentSource(
                kind="auto",
                shows=_("die Bestätigung nach dem Kauf — Nummer, Positionen, Summe, Zahlung"),
                note=_("Gilt für Bestellung, Termin, Zimmer, Ticket und Tisch."),
                woher=_("automatisch — aus der Bestellung oder Buchung."),
            ),
        ),
        DetailSection("next", _("Was passiert jetzt"), hideable=False),
        DetailSection(
            "recommend",
            _("Empfehlungen"),
            content_nav="sellable-manage",
            source=ContentSource(
                kind="setting",
                shows=_(
                    "bis zu 4 Produkte unter der Bestätigung — empfohlene zuerst, ohne die "
                    "gerade gekauften"
                ),
                woher=_("Produkte mit Häkchen „Empfohlen“."),
                only_if=_("Erscheint nur, wenn es Produkte gibt."),
            ),
        ),
    ),
    # --- cart ---
    # FB-33 M5d-5: «Positionen» — из корзины покупателя (править нечего); «Bestellformular»,
    # «Summe und Bestellbutton» и «Passt gut dazu» — со своими окнами, источника у них нет
    "cart": (
        DetailSection(
            "items",
            _("Positionen"),
            hideable=False,
            source=ContentSource(
                kind="auto",
                shows=_(
                    "die Artikel, die der Kunde in den Warenkorb gelegt hat — mit Menge und Preis"
                ),
                woher=_("automatisch — aus dem Warenkorb des Kunden. Nichts zu pflegen."),
            ),
        ),
        DetailSection("form", _("Bestellformular"), hideable=False),
        DetailSection("summary", _("Summe und Bestellbutton"), hideable=False),
        DetailSection("upsell", _("Goes well with this")),
    ),
    # --- info ---
    # FB-32 S6a: «Über uns» — текст (всегда на странице) и карточка контактов (видимость —
    # прежний ключ `about_contact`); своя страница «Seite» — только текст. Порядок постоянный.
    # FB-33 M5d-3: текст страницы правится в «Seiten» — у строки окно «Inhalt» (`_PAGE_TEXT`)
    "info": (
        DetailSection(
            "pagetext",
            _("Text"),
            hideable=False,
            content_nav="content-pages",
            source=_PAGE_TEXT,
        ),
        DetailSection("contact", _("Kontakt & Öffnungszeiten")),
    ),
    # --- page ---
    "page": (
        DetailSection(
            "pagetext",
            _("Text"),
            hideable=False,
            content_nav="content-pages",
            source=_PAGE_TEXT,
        ),
    ),
    # --- message ---
    # FB-32 S6b: «Versand» — свой текст и список Versandkosten (§ 6 PAngV: сюда ведёт
    # «zzgl. Versandkosten»). Список снимается только галочкой у страницы «Versand» (один
    # писатель; без своего текста список виден всегда) — в схеме строка не скрывается.
    # FB-32 S6c: «Kontakt» и «Anfrage» — форма (с визиткой и Rückruf в боковой колонке, раскладка
    # SP-9 не делится) одной строкой: свои блоки над ней или под ней. Не скрывается.
    "message": (
        DetailSection("form", _("Kontaktformular"), hideable=False, content_nav="settings"),
    ),
    # --- anfrage ---
    "anfrage": (DetailSection("form", _("Anfrage-Formular"), hideable=False),),
    # --- gift ---
    # FB-32 S6d: «Gutschein» — форма покупки (деньги, кнопка «Zahlungspflichtig bestellen»,
    # § 312j BGB) и «Treue» — программы; одной неподвижной строкой, свои блоки над ней и под ней
    "gift": (
        DetailSection(
            "form", _("Gift voucher"), hideable=False, content_nav="promotions:voucher-list"
        ),
    ),
    # --- loyalty ---
    "loyalty": (
        DetailSection(
            "programs",
            _("Loyalty programme"),
            hideable=False,
            content_nav="promotions:loyalty-list",
        ),
    ),
    # --- blog_post ---
    # FB-32 S6e: запись блога — статья (не скрывается) и «More posts» (скрывается, прежний
    # список из 4); Finder — опросник одной строкой
    "blog_post": (
        DetailSection("article", _("Text"), hideable=False),
        DetailSection("more", _("More posts")),
    ),
    # --- finder ---
    "finder": (
        DetailSection("wizard", _("Finder"), hideable=False, content_nav="finder-settings"),
    ),
    # --- promo ---
    # FB-32 S6f: деталь акции — «Angebot» (строка оси P3: цена, условия, купон, бронь —
    # деньги и PAngV, не скрывается и не делится) и «Weitere Aktionen» (скрывается,
    # `promo_show_related`). Порядок постоянный.
    "promo": (
        DetailSection("offer", _("Angebot"), hideable=False),
        # FB-33 M2g: внутри колонки «Angebot» — скрываются на месте (цены в них нет)
        DetailSection("share", _("Teilen und QR-Code"), in_place=True),
        DetailSection("card", _("So finden Sie uns"), in_place=True),
        DetailSection("related", _("Weitere Aktionen")),
    ),
    # --- teachers ---
    # FB-32 S6g-1: страницы, у которых блоков не было, — содержимое одной неподвижной строкой
    "teachers": (
        DetailSection(
            "teacherlist", _("Teachers"), hideable=False, content_nav="events:teacher-list"
        ),
    ),
    # --- event_calendar ---
    "event_calendar": (
        DetailSection("calendar", _("Retreat calendar"), hideable=False, content_nav="events:list"),
    ),
    # --- passes ---
    "passes": (
        DetailSection(
            "plans", _("Multi-visit cards"), hideable=False, content_nav="booking:passes"
        ),
    ),
    # --- booking_slots ---
    # FB-32 S6g-2: выбор времени (ресурс или «Tisch reservieren») — вся коробка календаря и
    # формы брони одной неподвижной строкой
    "booking_slots": (
        DetailSection("slots", _("Book a slot"), hideable=False, content_nav="booking:resources"),
    ),
    # --- combo ---
    # FB-32 S6g-3: Kombi-Detail — конфигуратор (форма и цена, PAngV: не скрывается) и блоки
    # под ним (MEN-21), каждый скрывается (`combo_show_*`, presence-minimal). Порядок постоянный.
    "combo": (
        DetailSection("config", _("Kombi"), hideable=False),
        DetailSection("reviews", _("Customer reviews")),
        DetailSection("examples", _("Beispiele unserer Arbeit")),
        DetailSection("cta", _("Sie planen eine Veranstaltung?")),
        DetailSection("related", _("Weitere Menüs aus dieser Kategorie")),
    ),
    # --- versand ---
    # FB-33 M5d-3: «Versandkosten» — способы доставки из «Zahlarten & Lieferung» (вкладка
    # «Lieferung & Abholung»); числа способов в окне нет (план стопки 12 §9 №2), галочка названа
    # как на форме страницы «Versand» (`content_page_form.html`)
    "versand": (
        DetailSection(
            "pagetext",
            _("Text"),
            hideable=False,
            content_nav="content-pages",
            source=_PAGE_TEXT,
        ),
        DetailSection(
            "costs",
            _("Versandkosten"),
            hideable=False,
            content_nav="payment-settings",
            source=ContentSource(
                kind="setting",
                shows=_("Ihre Versandarten mit Preisen"),
                note=_(
                    "Hierhin führt „zzgl. Versandkosten“ bei jedem Preis. Die Liste lässt sich "
                    "nur auf der Seite „Versand“ abschalten (Häkchen „Ihre Versandarten mit "
                    "Preisen unter dem Text anzeigen“) — und nur mit eigenem Text."
                ),
                query="?tab=lieferung",
                sub=_("Lieferung & Abholung"),
            ),
        ),
    ),
    # --- stays ---
    "stays": (
        DetailSection("description", _("Description")),
        DetailSection("amenities", _("Amenities")),
        DetailSection("reviews", _("Customer reviews")),
        DetailSection("similar", _("Similar rooms")),
    ),
}


def sections_for(module: str) -> tuple[DetailSection, ...]:
    """Дескрипторы секций модуля в дефолтном порядке (пустой кортеж — нет реестра)."""
    return DETAIL_SECTIONS.get(module, ())


def section_keys(module: str) -> tuple[str, ...]:
    """Ключи секций модуля в дефолтном порядке рендера."""
    return tuple(s.key for s in sections_for(module))


def flow_keys(module: str) -> tuple[str, ...]:
    """FB-33 M2g: разделы, которые двигаются и служат якорями (без разделов «на месте»)."""
    return tuple(s.key for s in sections_for(module) if not s.in_place)


def in_place_keys(module: str) -> frozenset:
    """FB-33 M2g: разделы «на месте» (только скрываются)."""
    return frozenset(s.key for s in sections_for(module) if s.in_place)


def only_of(module: str, key: str) -> str:
    """FB-33 M2g: чей раздел на общем хосте ("event"/"tour"; "" — общий)."""
    return next((s.only for s in sections_for(module) if s.key == key), "")


def section_labels(module: str) -> dict:
    """{key: lazy label} для инспектора билдера — единый источник подписей."""
    return {s.key: s.label for s in sections_for(module)}
