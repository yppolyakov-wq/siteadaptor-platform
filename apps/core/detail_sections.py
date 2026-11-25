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
class SourceField:
    """FB-33 M5d-8 (E7): одно поле раздела «Woher» из нескольких полей — путь «ausgefüllt»
    и подпись пункта списка окна «Inhalt» (`window_parts._content_woher`). Строка в
    `ContentSource.fields` — прежнее поведение (одна подпись раздела, «хватает одного»).
    Подписи — те же msgid, что на форме кабинета (замок `test_labels_on_cabinet_form`)."""

    #: поле МОДЕЛИ и ключи его словаря через точку ("brand", "details.venue", "images")
    path: str
    #: имя поля формы объекта — подпись из кода формы (`site_schema.object_field_label`)
    field: str = ""
    #: подпись, если её нет в коде формы; словарь «вид объекта → подпись», где "" — у общего
    #: типа двух видов (описание, а не подпись поля — без кавычек)
    label: object = ""
    #: вкладка формы («Grundlagen», «Kennzeichnung») и её подраздел («Marke & Zustand»)
    tab: object = ""
    section: object = ""
    #: сколько элементов списка нужно для «ausgefüllt» (фото — со второго: 2)
    min_items: int = 1
    #: только у этих видов объекта (у общего типа — с пометкой вида, `KIND_ONLY`)
    kinds: tuple[str, ...] = ()
    #: ключ закрытого реестра проб `window_parts._PROBES`: «ausgefüllt» по тому же производному
    #: значению, что гейт витрины (подписи аллергенов и удобств, `landing`, точка карты)
    probe: str = ""
    #: подстановки в подпись («%(lat)s» → подпись поля формы); подпись — целой фразой
    args: tuple = ()
    #: подпись — в кавычках «„…“» (как имя поля формы); False — целая фраза
    quote: bool = True

    def __str__(self) -> str:
        return self.path


#: FB-33 M5d-8: «Woher» из нескольких полей — у типа после списка
ONLY_IF_ANY = _("Erscheint nur, wenn mindestens eines davon ausgefüllt ist.")
#: FB-33 M5d-8: пункт со `min_items` 2 (фото со второго; первое — в шапке страницы)
FROM_SECOND_PHOTO = _("%(label)s — ab dem zweiten Foto")
#: FB-33 M5d-8: пункт «Ort» — точка на карте (`apps/events/services.py::map_point`)
MAP_POINT = _(
    "Punkt auf der Karte — „%(lat)s“ und „%(lng)s“ (sonst Ihre Adresse; nicht bei Online)"
)
#: FB-33 M5d-8: пометка пункта одного вида у общего типа (`SourceField.kinds`)
KIND_ONLY = {"event": _("(nur bei Veranstaltungen)")}


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
    #: "details.idea"); хватает одного заполненного. M5d-8: `SourceField` вместо строк —
    #: «Woher» списком полей (у объекта — каждое со своим «ausgefüllt»); это же описание —
    #: гейт показа витрины (замок `test_filled_matches_storefront_gate`)
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
    #: FB-33 M5d-2b: ещё экраны-списки для строки ТИПА общего хоста двух видов (события и
    #: туры: «Inhalt bearbeiten: Reisen») — имена URL записей `nav_registry`; только у раздела
    #: обоих видов (`DetailSection.only == ""`, без `kinds`), у строки одного объекта не действует
    more_nav: tuple[str, ...] = ()
    #: FB-33 M5d-2b: виды объекта, у которых раздел вообще рисуется (пусто — у всех видов хоста);
    #: у строки объекта другого вида окно говорит, что блока там нет
    kinds: tuple[str, ...] = ()
    #: FB-33 M5e-2a (§0.3 №2): своё имя ссылки («Geschäftsdaten bearbeiten») — имя экрана;
    #: пусто — прежнее «Inhalt bearbeiten: <экран>»
    link_text: object = ""
    #: FB-33 M5e-2a: чьи поля `fields` — "" объекта строки, "tenant" — бизнеса (`request.tenant`):
    #: «Woher» списком полей со словом «ausgefüllt»/«leer» и итогом «N von M ausgefüllt»;
    #: «ausgefüllt» — только пробами `window_parts._PROBES` (тот же гейт, что у витрины)
    subject: str = ""


#: FB-33 M5d-2: обычное «когда появляется» раздела-поля
ONLY_IF_FILLED = _("Erscheint nur, wenn das Feld ausgefüllt ist.")
#: FB-33 M5d-2b: второй список общего типа «Veranstaltungen» (`ContentSource.more_nav`)
_TOURS = ("events:tour-list",)


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
        # FB-33 M5d-4a: источники окна «Inhalt» (тексты — артборд M5dG1; список товаров —
        # запись «Sortiment», ответ владельца). `trust` и `reviews` — со своим окном, без источника.
        DetailSection(
            "description",
            _("Description"),
            content_nav="sellable-manage",
            source=ContentSource(
                "field",
                shows=_("die Beschreibung des Produkts"),
                field_label=_("Beschreibung"),
                fields=("description",),
                only_if=ONLY_IF_FILLED,
            ),
        ),
        DetailSection(
            "info",
            _("Product info (origin/ingredients/allergens)"),
            content_nav="sellable-manage",
            source=ContentSource(
                "field",
                shows=_(
                    "die Kennzeichnung des Produkts: Marke, Zustand, Material, Pflege, "
                    "Herkunft, Zutaten, Allergene und Zusatzstoffe"
                ),
                # подпись вкладки формы товара (тот же msgid, что в `product_form.html`)
                field_label=_("Labeling"),
                # M5d-8: поля по вкладкам формы (`product_form.html`); подписи — как на форме
                fields=(
                    SourceField(
                        "brand", label=_("Marke"), tab=_("Basics"), section=_("Marke & Zustand")
                    ),
                    SourceField(
                        "condition",
                        label=_("Zustand"),
                        tab=_("Basics"),
                        section=_("Marke & Zustand"),
                    ),
                    SourceField(
                        "material", label=_("Material / Zusammensetzung"), tab=_("Labeling")
                    ),
                    SourceField("care", label=_("Pflegehinweise"), tab=_("Labeling")),
                    SourceField("origin", label=_("Origin"), tab=_("Labeling")),
                    SourceField("ingredients", label=_("Ingredients"), tab=_("Labeling")),
                    SourceField(
                        "allergens",
                        label=_("Allergens"),
                        tab=_("Labeling"),
                        probe="allergen_labels",
                    ),
                    SourceField(
                        "additives",
                        label=_("Additives"),
                        tab=_("Labeling"),
                        probe="additive_labels",
                    ),
                ),
                only_if=ONLY_IF_ANY,
            ),
        ),
        # FB-33 M2f: разделы первого экрана, которые раньше были зашиты в страницу товара
        DetailSection(
            "sizes",
            _("Größentabelle"),
            content_nav="catalog:category-list",
            source=ContentSource(
                "setting",
                shows=_("die Größentabelle der Kategorie, zu der das Produkt gehört"),
                woher=_("Feld „Größentabelle“ bei der Kategorie."),
                only_if=_("Erscheint nur, wenn die Kategorie eine Größentabelle hat."),
            ),
        ),
        DetailSection("trust", _("Vertrauensleiste")),
        DetailSection(
            "anprobe",
            _("In der Anprobe zurücklegen"),
            source=ContentSource(
                "auto",
                shows=_(
                    "das Formular „In der Anprobe zurücklegen“ — unverbindlich reservieren, "
                    "48 Stunden"
                ),
                woher=_("automatisch — aus Bestand und Größen des Produkts. Nichts zu pflegen."),
                only_if=_(
                    "Erscheint nur, wenn die Anprobe-Reservierung eingeschaltet, die "
                    "Online-Bestellung aktiv und das Produkt vorrätig ist."
                ),
            ),
        ),
        DetailSection(
            "waitlist",
            _("Warteliste"),
            source=ContentSource(
                "auto",
                shows=_(
                    "das Formular „Ausverkauft? Benachrichtigen lassen“ — eine E-Mail, sobald "
                    "das Produkt wieder da ist"
                ),
                woher=_("automatisch — aus dem Bestand des Produkts. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn das Produkt oder eine Größe ausverkauft ist."),
            ),
        ),
        DetailSection(
            "instore",
            _("Im Geschäft erhältlich"),
            content_nav="settings",
            source=ContentSource(
                "setting",
                shows=_("den Hinweis „Im Laden erhältlich“ mit Öffnungszeiten und Adresse"),
                woher=_("Ihre Geschäftsdaten (Adresse, Öffnungszeiten)."),
            ),
        ),
        DetailSection(
            "question",
            _("Frage stellen"),
            source=ContentSource(
                "auto",
                shows=_("den Link zum Nachrichtenformular — mit dem Namen des Produkts"),
                woher=_("automatisch — die Frage kommt in „Nachrichten“ an. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn das Modul „Nachrichten“ aktiv ist."),
            ),
        ),
        DetailSection("reviews", _("Customer reviews")),
        # у типа у «Ähnliche Produkte» своё окно («Seite») — источник только строке объекта
        DetailSection(
            "related",
            _("Related products"),
            source=ContentSource(
                "auto",
                shows=_("weitere Produkte derselben Kategorie — empfohlene zuerst"),
                woher=_("automatisch — aus der Kategorie des Produkts. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn die Kategorie weitere aktive Produkte hat."),
                object_only=True,
            ),
        ),
        # FB-33 M2f: «Zuletzt angesehen» — только в браузере посетителя (localStorage)
        DetailSection(
            "recent",
            _("Zuletzt angesehen"),
            source=ContentSource(
                "auto",
                shows=_("die Produkte, die sich der Besucher zuletzt angesehen hat"),
                woher=_("automatisch — im Browser des Besuchers. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn der Besucher schon andere Produkte angesehen hat."),
            ),
        ),
    ),
    # --- events ---
    # FB-33 M5d-4d: откуда содержимое разделов (окно «Inhalt»). Хост события и тура общий —
    # у типа ссылка на список событий и (M5d-2b, `more_nav`) вторая — на список туров; у строки
    # объекта — на его форму. Поля — блоки `details` общего редактора
    # (`apps/events/landing.py`, подпись — по имени поля формы).
    "events": (
        DetailSection(
            "for_whom",
            _("For whom"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("für wen das Angebot gedacht ist — Punkt für Punkt"),
                field="for_whom_text",
                fields=("details.for_whom",),
                only_if=ONLY_IF_FILLED,
                more_nav=_TOURS,
            ),
        ),
        DetailSection(
            "idea",
            _("The idea"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("die Idee und die Atmosphäre"),
                field="idea",
                fields=("details.idea",),
                only_if=ONLY_IF_FILLED,
                more_nav=_TOURS,
            ),
        ),
        DetailSection(
            "includes",
            _("What's included"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("was dabei ist — Kacheln mit Titel und Text"),
                field="includes_text",
                fields=("details.includes",),
                only_if=ONLY_IF_FILLED,
                more_nav=_TOURS,
            ),
        ),
        # «Ablauf» — поле формы СОБЫТИЯ (`EventForm.program_text` → `Event.program`), в общем
        # редакторе его нет. M5d-2b: у тура программы нет вовсе (ни поля, ни вывода — `agenda`
        # собирает только страница события) — `kinds`: строка одного тура говорит, что блока нет
        DetailSection(
            "program",
            _("Schedule"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("den Ablauf als Zeitleiste"),
                field_label=_("Ablauf / Programm (ein Punkt pro Zeile)"),
                fields=("program",),
                only_if=ONLY_IF_FILLED,
                kinds=("event",),
            ),
        ),
        DetailSection(
            "venue",
            _("Venue"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("den Ort — Text, Karte und weitere Fotos"),
                field="venue",
                # M5d-8: гейт `_event_thematic.html` — поле, фото со второго, точка карты
                # (у тура её нет: `tour_detail` не кладёт `map_point`)
                fields=(
                    SourceField("details.venue", field="venue", probe="landing"),
                    SourceField(
                        "images",
                        label={
                            "event": _("Photos (venue, past events)"),
                            "tour": _("Photos"),
                            "": _("Photos"),
                        },
                        min_items=2,
                    ),
                    SourceField(
                        "latitude",
                        label=MAP_POINT,
                        args=(("lat", _("Latitude")), ("lng", _("Longitude"))),
                        quote=False,
                        kinds=("event",),
                        probe="map_point",
                    ),
                ),
                only_if=ONLY_IF_ANY,
                more_nav=_TOURS,
            ),
        ),
        DetailSection(
            "accommodation",
            _("Accommodation"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("die Unterkunft — Punkt für Punkt"),
                field="accommodation_text",
                fields=("details.accommodation",),
                only_if=ONLY_IF_FILLED,
                more_nav=_TOURS,
            ),
        ),
        DetailSection(
            "food",
            _("Food"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("die Verpflegung"),
                field="food",
                fields=("details.food",),
                only_if=ONLY_IF_FILLED,
                more_nav=_TOURS,
            ),
        ),
        # сначала — назначенные в форме ведущие (экран «Gastgeber»), иначе блок «Leitung»
        DetailSection(
            "hosts",
            _("Hosts"),
            orderable=True,
            content_nav="events:teacher-list",
            source=ContentSource(
                "setting",
                shows=_("die Gastgeber mit Foto und Titel"),
                woher=_("Gastgeber, die Sie im Formular zuordnen — sonst das Feld „Leitung“."),
                only_if=_("Erscheint nur, wenn es eines von beiden gibt."),
            ),
        ),
        DetailSection(
            "price",
            _("Price"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("den Preis und was enthalten ist"),
                field="price_includes_text",
                fields=(
                    SourceField(
                        "details.price_includes", field="price_includes_text", probe="landing"
                    ),
                    SourceField(
                        "details.price_excludes", field="price_excludes_text", probe="landing"
                    ),
                    SourceField("details.price_note", field="price_note", probe="landing"),
                ),
                only_if=ONLY_IF_ANY,
                more_nav=_TOURS,
            ),
        ),
        DetailSection(
            "bring",
            _("What to bring"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("was mitzubringen ist — Punkt für Punkt"),
                field="bring_text",
                fields=("details.bring",),
                only_if=ONLY_IF_FILLED,
                more_nav=_TOURS,
            ),
        ),
        DetailSection("faq", _("FAQ"), orderable=True),
        DetailSection("testimonials", _("Testimonials"), orderable=True),
        DetailSection(
            "before_after",
            _("Before & after"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("Vorher-Nachher-Bilder mit Text"),
                field="before_after_text",
                fields=("details.before_after",),
                only_if=ONLY_IF_FILLED,
                more_nav=_TOURS,
            ),
        ),
        DetailSection(
            "certifications",
            _("Certifications"),
            orderable=True,
            content_nav="events:list",
            source=ContentSource(
                "field",
                shows=_("Zertifikate und Auszeichnungen"),
                field="certifications_text",
                fields=("details.certifications",),
                only_if=ONLY_IF_FILLED,
                more_nav=_TOURS,
            ),
        ),
        # FB-33 M2g: после «Buchung», скрываются на месте (у тура — свой раздел приватного выезда)
        DetailSection(
            "groups",
            _("Groups & companies"),
            in_place=True,
            only="event",
            source=ContentSource(
                "auto",
                shows=_("einen Hinweis für Gruppen und Firmen — mit Knopf zur Angebotsanfrage"),
                woher=_("automatisch — fester Text. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn „Aufträge & Angebote“ aktiv ist."),
            ),
        ),
        DetailSection(
            "more_dates",
            _("Weitere Termine"),
            in_place=True,
            only="event",
            source=ContentSource(
                "auto",
                shows=_("die anderen Termine derselben Serie"),
                woher=_("automatisch — aus den Terminen der Serie. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn die Veranstaltung zu einer Serie gehört."),
            ),
        ),
        DetailSection(
            "private_tour",
            _("Request a private tour"),
            in_place=True,
            only="tour",
            source=ContentSource(
                "auto",
                shows=_("das Angebot, die Reise für die eigene Gruppe anzufragen"),
                woher=_("automatisch — fester Text. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn „Aufträge & Angebote“ aktiv ist."),
            ),
        ),
    ),
    # --- booking ---
    # UA4-1 slice C: секции детальной УСЛУГИ (booking.Service) — ключи по факту
    # service_detail.html (описание/атрибуты/FAQ/команда/отзывы). Hide-only.
    "booking": (
        # FB-33 M5d-4b: источники окна «Inhalt»; подписи полей — те же msgid, что на форме
        # услуги (`booking/service_page.html`). `faq`, `team`, `reviews` — со своим окном.
        DetailSection(
            "description",
            _("Description"),
            content_nav="booking:services",
            source=ContentSource(
                "field",
                shows=_("die Beschreibung der Leistung"),
                field_label=_("Description (what's included)"),
                fields=("description",),
                only_if=ONLY_IF_FILLED,
            ),
        ),
        # LS-1: «📹 Per Video zeigen lassen» — wa.me-CTA; present-гейт: услуга
        # is_video И у бизнеса есть whatsapp_number. Скрываемо как любая секция.
        DetailSection(
            "video",
            _("Video-Beratung"),
            content_nav="booking:services",
            source=ContentSource(
                "field",
                shows=_("den Knopf „Per Video zeigen lassen“ — er öffnet einen WhatsApp-Chat"),
                field_label=_("Video-Beratung möglich"),
                fields=("is_video",),
                note=_("Der Chat geht an Ihre WhatsApp-Nummer aus „Mein Geschäft“."),
                only_if=_(
                    "Erscheint nur, wenn das Häkchen gesetzt und eine WhatsApp-Nummer "
                    "eingetragen ist."
                ),
            ),
        ),
        DetailSection(
            "attributes",
            _("Details"),
            content_nav="booking:services",
            source=ContentSource(
                "field",
                shows=_("die Details der Leistung als Liste — bis zu 12 Punkte"),
                field_label=_("Details — one bullet per line"),
                fields=("attributes",),
                only_if=ONLY_IF_FILLED,
            ),
        ),
        DetailSection("faq", _("Frequently asked questions")),
        DetailSection("team", _("Our team")),
        DetailSection("reviews", _("Customer reviews")),
        # B3: кросс-селл товаров («к стрижке берут шампунь») — при активном
        # catalog и наличии товаров; скрываемо в билдере как любая секция.
        DetailSection(
            "upsell",
            _("Goes well with this"),
            content_nav="sellable-manage",
            source=ContentSource(
                "setting",
                shows=_("bis zu 4 Produkte unter der Leistung — empfohlene zuerst"),
                woher=_("Ihre Produkte — die mit Häkchen „Empfohlen“ stehen vorn."),
                only_if=_("Erscheint nur, wenn es aktive Produkte gibt."),
            ),
        ),
    ),
    # --- confirmation ---
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
                shows=_("die Bestätigung des Kunden — Nummer, Positionen, Summe, Zahlung"),
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
                woher=_("Ihre Produkte — die mit Häkchen „Empfohlen“ stehen vorn."),
                only_if=_("Erscheint nur, wenn es aktive Produkte gibt."),
            ),
        ),
    ),
    # --- cart ---
    # FB-32 S4: страница корзины — «Passt gut dazu» строкой схемы (двигается, скрывается,
    # свои блоки выше/ниже). Видимость — прежний ключ `cart_show_upsell`.
    # FB-33 M2h: оформление — строки корзины: позиции, форма и итог с кнопкой неподвижны и не
    # скрываются (§ 312j BGB: кнопка сразу после итога); свои блоки — над корзиной, «Hinweise»
    # над формой (после позиций), под сеткой и в хвосте
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
    # FB-33 M5d-4e: своей схемы у одной записи нет — источник только у типа страницы
    "blog_post": (
        DetailSection(
            "article",
            _("Text"),
            hideable=False,
            content_nav="blog-list",
            source=ContentSource(
                "setting",
                shows=_("den Beitrag — Titelbild, Datum, Titel, Kurztext und Text"),
                woher=_("Der jeweilige Beitrag aus Ihrem Blog."),
            ),
        ),
        DetailSection(
            "more",
            _("More posts"),
            source=ContentSource(
                "auto",
                shows=_("bis zu 4 weitere veröffentlichte Beiträge"),
                woher=_("automatisch — die neuesten anderen Beiträge. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn es weitere veröffentlichte Beiträge gibt."),
            ),
        ),
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
        # FB-33 стопка 15 M5e-2a (ревью 1): «Inhalt» строки типа — экран акций; у строки одной
        # акции части нет (её хост — не общий хост детали)
        DetailSection(
            "offer",
            _("Angebot"),
            hideable=False,
            content_nav="promotions:promotion-list",
            source=ContentSource(
                "setting",
                shows=_("Preis, Bedingungen und Gutscheincode der Aktion"),
                link_text=_("Aktion bearbeiten"),
            ),
        ),
        # FB-33 M2g: внутри колонки «Angebot» — скрываются на месте (цены в них нет)
        # FB-33 M5d-4e: откуда содержимое (окно «Inhalt»); строка одной акции части не получает
        DetailSection(
            "share",
            _("Teilen und QR-Code"),
            in_place=True,
            source=ContentSource(
                "auto",
                shows=_("Knöpfe zum Teilen und den QR-Code der Aktion"),
                woher=_("automatisch — aus der Adresse der Aktion. Nichts zu pflegen."),
            ),
        ),
        # визитка: при отклике «только показать» остаётся и скрытой (единственный путь к бизнесу)
        DetailSection(
            "card",
            _("So finden Sie uns"),
            in_place=True,
            content_nav="settings",
            source=ContentSource(
                "setting",
                shows=_("Adresse, Öffnungszeiten, Route und Telefon Ihres Geschäfts"),
                woher=_("Ihre Geschäftsdaten — Adresse, Öffnungszeiten, Telefon und WhatsApp."),
                note=_(
                    "Bei einer Aktion, die nur gezeigt wird (ohne Bestellung oder Anfrage), "
                    "bleibt er immer sichtbar."
                ),
                only_if=_("Erscheint nur, wenn Adresse oder Telefon eingetragen ist."),
            ),
        ),
        DetailSection(
            "related",
            _("Weitere Aktionen"),
            source=ContentSource(
                "auto",
                shows=_("bis zu 8 weitere Aktionen — zuerst aus derselben Gruppe"),
                woher=_("automatisch — Ihre anderen laufenden Aktionen. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn es weitere laufende Aktionen gibt."),
            ),
        ),
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
    # FB-33 M5d-4e: своей схемы у одного Kombi нет — источник только у типа страницы
    "combo": (
        DetailSection(
            "config",
            _("Kombi"),
            hideable=False,
            content_nav="catalog:combo-list",
            source=ContentSource(
                "setting",
                shows=_("das Kombi-Angebot zum Zusammenstellen — Auswahl, Preis und Bestellknopf"),
                woher=_("Das jeweilige Kombi-Angebot mit seinen Gruppen und Preisen."),
            ),
        ),
        DetailSection("reviews", _("Customer reviews")),
        # фото — галерея сайта (`site_config["gallery"]`, пополняется в Студии). FB-33 E6:
        # ссылка — запись «Galerie» (`site-home?page=%2F&block=gallery`, главная Студии)
        DetailSection(
            "examples",
            _("Beispiele unserer Arbeit"),
            content_nav="site-home",
            source=ContentSource(
                "setting",
                shows=_("bis zu 6 Fotos aus der Galerie Ihrer Website"),
                woher=_("Die ersten Fotos der Galerie Ihrer Website."),
                only_if=_("Erscheint nur, wenn die Galerie Fotos hat."),
            ),
        ),
        DetailSection("cta", _("Sie planen eine Veranstaltung?")),
        DetailSection(
            "related",
            _("Weitere Menüs aus dieser Kategorie"),
            source=ContentSource(
                "auto",
                shows=_("bis zu 8 weitere Kombi-Angebote derselben Kategorie"),
                woher=_("automatisch — aus derselben Kategorie. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn es in der Kategorie weitere Kombi-Angebote gibt."),
            ),
        ),
    ),
    # --- versand ---
    # FB-32 S6b: «Versand» — свой текст и список Versandkosten (§ 6 PAngV: сюда ведёт
    # «zzgl. Versandkosten»). Список снимается только галочкой у страницы «Versand» (один
    # писатель; без своего текста список виден всегда) — в схеме строка не скрывается.
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
    # UA4-1 slice C: секции детальной НОМЕРА (stays.StayUnit) — по факту stay_detail.html
    # (описание/оснащение/отзывы/похожие). Hide-only.
    "stays": (
        # FB-33 M5d-4c: источники окна «Inhalt»; подписи полей — те же msgid, что на форме
        # номера (`stays/unit_page.html`). `reviews` — со своим окном.
        DetailSection(
            "description",
            _("Description"),
            content_nav="stays:units",
            source=ContentSource(
                "field",
                shows=_("die Beschreibung der Unterkunft"),
                field_label=_("Description"),
                fields=("description",),
                only_if=ONLY_IF_FILLED,
            ),
        ),
        DetailSection(
            "amenities",
            _("Amenities"),
            content_nav="stays:units",
            source=ContentSource(
                "field",
                shows=_("Ausstattung, Bettart und Fläche der Unterkunft"),
                field_label=_("Amenities"),
                # M5d-8: подписи — как на странице номера (`stays/unit_page.html`)
                fields=(
                    SourceField("amenities", label=_("Amenities"), probe="amenity_badges"),
                    SourceField("bed_type", label=_("Bed type")),
                    SourceField("area_sqm", label=_("Area (m², 0 = hide)")),
                ),
                only_if=ONLY_IF_ANY,
            ),
        ),
        DetailSection("reviews", _("Customer reviews")),
        DetailSection(
            "similar",
            _("Similar rooms"),
            source=ContentSource(
                "auto",
                shows=_("bis zu 3 andere Unterkünfte — gleiche Art zuerst, dann nach Preis"),
                woher=_("automatisch — aus Ihren aktiven Unterkünften. Nichts zu pflegen."),
                only_if=_("Erscheint nur, wenn es weitere aktive Unterkünfte gibt."),
            ),
        ),
    ),
}


# --- FB-33 M5e-2a: источники «Inhalt» у строк главной и листингов --------------------------------

#: ключ семьи страницы → строки с источником содержимого (тот же `DetailSection`/`ContentSource`,
#: что у деталей; разделов-порядка здесь нет — только часть окна «Inhalt»). Семья — по хосту
#: (`window_parts.page_family`): у страницы с модулем деталей (`detail_parts.module_of`) действует он.
#: Экран ★ основного списка (`main`) — из записи источника списка
#: (`window_parts.main_list_screen`), своего `content_nav` у строки нет.
#: ★ основного списка: экран и имя — из записи источника (`window_parts.list_source_screen`)
_MAIN_LIST = DetailSection("main", _("Hauptliste"), source=ContentSource("setting"))
PAGE_SOURCES: dict[str, tuple[DetailSection, ...]] = {
    "home": (
        # артборд M5eInhalt: пункты — подписи формы «Mein Geschäft» (`tenants/forms.py`);
        # «ausgefüllt» — гейт `storefront/sections/_contact.html` (пробы `contact_*`)
        DetailSection(
            "contact",
            _("Contact & opening hours"),
            content_nav="settings",
            source=ContentSource(
                "setting",
                woher=_("Die Angaben kommen aus Ihren Geschäftsdaten."),
                # `field` — поле формы «Mein Geschäft» (подпись — та же строка, замок
                # `test_labels_on_cabinet_form`); ревью 1 №4: e-mail и карта тоже открывают блок
                fields=(
                    SourceField(
                        "address", field="address", label=_("Address"), probe="contact_address"
                    ),
                    SourceField(
                        "public_phone",
                        field="contact_phone",
                        label=_("Phone"),
                        probe="contact_phone",
                    ),
                    SourceField(
                        "opening_hours",
                        field="opening_hours",
                        label=_("Opening hours"),
                        probe="contact_hours",
                    ),
                    SourceField(
                        "public_email",
                        field="contact_email",
                        label=_("Email"),
                        probe="contact_email",
                    ),
                    SourceField(
                        "map_url", field="map_url", label=_("Karten-Link"), probe="contact_map"
                    ),
                ),
                link_text=_("Geschäftsdaten bearbeiten"),
                subject="tenant",
            ),
        ),
        DetailSection(
            "reviews",
            _("Customer reviews"),
            content_nav="reviews:list",
            source=ContentSource("setting"),
        ),
        DetailSection(
            "finder", _("Finder"), content_nav="finder-settings", source=ContentSource("setting")
        ),
        # запись «Galerie» — вход в Студию на главной у блока галереи (стопка 14 E6)
        DetailSection(
            "gallery",
            _("Photo gallery"),
            content_nav="site-home",
            source=ContentSource(
                "setting", only_if=_("Erscheint nur, wenn die Galerie Fotos hat.")
            ),
        ),
    ),
    "list": (_MAIN_LIST,),
    # ревью 1 №7: «Kategorien» и «Sets & Menüs» — только у страниц каталога и категорий
    "catalog_list": (
        _MAIN_LIST,
        DetailSection(
            "categories",
            _("Kategorien"),
            content_nav="catalog:category-list",
            source=ContentSource("setting"),
        ),
        DetailSection(
            "combos",
            _("Sets & Menüs"),
            content_nav="catalog:combo-list",
            source=ContentSource("setting"),
        ),
    ),
}


def page_sources(family: str) -> tuple[DetailSection, ...]:
    """FB-33 M5e-2a: строки с источником «Inhalt» семьи страницы (`window_parts.page_family`)."""
    return PAGE_SOURCES.get(family, ())


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
