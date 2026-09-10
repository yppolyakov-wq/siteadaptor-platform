"""LAY-2: ЕДИНЫЙ реестр композиций страницы («шаблонов вывода структуры»).

Волна LAY (решение владельца 2026-09-09 «делаем полную унификацию»). До неё коды
шаблонов страницы жили в ЧЕТЫРЁХ списках — товарная категория и корень каталога
(`catalog/category_styles.py`), обзор акций, страница группы и деталь акции
(`promotions/group_styles.py`). Разведка нашла 13 пересечений: `schaufenster`
описан трижды, `magazin` четырежды, `kompakt` обзора акций рендерит тот же
include, что `prospekt` группы, а восемь кодов `preisliste*` продублированы
дословно. Владелец видел это как «кашу» — и был прав: это ошибка моделирования,
а не богатство вариантов.

**Что здесь.** Один словарь `COMPOSITIONS`: код → спека. Спека отвечает на три
вопроса, ради которых реестр и заводится:

* `applies_to` — НА КАКИХ поверхностях композиция имеет смысл. Это и есть гейт
  доступности, заменяющий четыре отдельных списка. Правило STU-9: не предлагать
  настройку там, где страница её не читает.
* `requires` — от чего композиция зависит по ДАННЫМ (`children` — подкатегории
  или группы; `combos` — наборы). «Полки» и «Вкладки» без под-сущностей
  показывать нечего, поэтому такие коды гейтятся по факту, а не по списку `if`
  в пяти шаблонах.
* `recommended_grid` — какая сетка идёт композиции. Сегодня шаблон МОЛЧА
  переписывает раскладку владельца (`magazin→cols2` и т.п.); в LAY-5 эта
  рекомендация станет применяться только там, где владелец сетку не трогал.

**Чего здесь НЕТ.** Рендера. Прежние реестры остаются как производные
представления (`styles_for`), их публичная форма — та же тройка
(код, метка, подсказка) в том же порядке, поэтому шаблоны плиток, формы и
валидаторы охвата не меняются ни строкой. Прецедент — `HUB_TABS`, производные
от `nav_registry` (волна W8).

Подсказки контекстные: «Preisliste» у товаров и у акций объясняется разными
словами, и обобщать их до одной фразы значило бы ухудшить текст ради красоты
структуры. Поэтому `hints` — словарь по поверхности с фолбэком на общий текст.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

# Поверхности вывода, которые уже умеют выбирать композицию. Список РАСТЁТ по
# мере волны (LAY-3/LAY-4 добавят листинги услуг, номеров, событий, наборов и
# туров) — но ровно тогда, когда рендер этих страниц действительно читает выбор.
SURFACES = frozenset(
    {
        "catalog",  # корень /sortiment/
        "category",  # страница товарной категории
        "promos",  # обзор /aktionen/
        "promo_group",  # страница группы акций (?gruppe=)
        "promo",  # деталь одной акции
    }
)

# Требования по данным. Композиция, чьё требование не выполнено на конкретной
# странице, не предлагается владельцу (и не ломает витрину, если досталась из
# старого конфига: резолверы по-прежнему проваливаются в Standard).
NEEDS_CHILDREN = "children"  # подкатегории (каталог) или группы (акции)
NEEDS_COMBOS = "combos"  # наборы/меню


@dataclass(frozen=True)
class Composition:
    """Одна композиция страницы.

    `label`/`hint` — общий текст; `labels`/`hints` — переопределения для
    конкретной поверхности (у акций своя лексика). `order` задаёт положение
    плитки, `orders` — его переопределение для поверхности: у страницы группы
    и у детали акции владелец видит СВОЙ порядок, и он сохранён 1:1.
    """

    code: str
    label: object
    hint: object
    applies_to: frozenset
    order: int
    orders: dict = field(default_factory=dict)
    requires: frozenset = frozenset()
    recommended_grid: str = ""
    labels: dict = field(default_factory=dict)
    hints: dict = field(default_factory=dict)

    @property
    def needs_children(self) -> bool:
        return NEEDS_CHILDREN in self.requires

    def label_for(self, surface: str):
        return self.labels.get(surface, self.label)

    def hint_for(self, surface: str):
        return self.hints.get(surface, self.hint)

    def order_for(self, surface: str) -> int:
        return self.orders.get(surface, self.order)


_LISTING = frozenset({"catalog", "category", "promos", "promo_group"})
_ALL = frozenset({"catalog", "category", "promos", "promo_group", "promo"})


def _c(code, label, hint, applies_to, order, **kw) -> Composition:
    return Composition(code=code, label=label, hint=hint, applies_to=applies_to, order=order, **kw)


COMPOSITIONS: dict[str, Composition] = {
    c.code: c
    for c in [
        _c(
            "",
            _("Standard (Raster)"),
            _("Wie bisher: Filter, Unterkategorien, Produktraster."),
            _ALL,
            0,
            hints={
                "promos": _("As before: groups as sections, offers as a grid."),
                "promo_group": _("As before: a plain grid of all offers in the group."),
                "promo": _("As before: photo on the left, price and CTA on the right."),
            },
            labels={
                # У акций своя лексика: «Standard (grid)» было и в обзоре, и в группе.
                "promos": _("Standard (grid)"),
                "promo_group": _("Standard (grid)"),
                "promo": _("Standard (2 Spalten)"),
            },
        ),
        _c(
            "kopfbild",
            _("Mit Kopfbild"),
            _("Hero mit Foto und Beschreibung, Unterkategorien als Foto-Kacheln."),
            frozenset({"catalog", "category", "promos"}),
            10,
            hints={"promos": _("Banner with photo and counts above the sections.")},
        ),
        _c(
            "sets",
            _("Sets & Menüs zuerst"),
            _("Menü-Sets dieser Kategorie als Karten über dem Raster."),
            frozenset({"catalog", "category"}),
            20,
            requires=frozenset({NEEDS_COMBOS}),
        ),
        _c(
            "preisliste",
            _("Preisliste"),
            _("Produkte dieser Kategorie als Preisliste statt Raster."),
            frozenset({"category", "promos"}),
            30,
            hints={"promos": _("Offers as a table by default — visitors can switch to cards.")},
        ),
        _c(
            "regale",
            _("Regale (Unterkategorien als Leisten)"),
            _("Jede Unterkategorie als horizontale Leiste mit Pfeilen — alles auf einen Blick."),
            frozenset({"catalog", "category", "promos"}),
            40,
            requires=frozenset({NEEDS_CHILDREN}),
            hints={"promos": _("Every group as a strip with arrows, no minimum size.")},
        ),
        _c(
            "tabs",
            _("Tabs (Unterkategorien als Reiter)"),
            _("Unterkategorien als Reiter über dem Raster — Wechsel ohne Neuladen."),
            frozenset({"catalog", "category", "promos"}),
            50,
            requires=frozenset({NEEDS_CHILDREN}),
            hints={"promos": _("«All» plus one tab per group above the offers.")},
        ),
        _c(
            "schaufenster",
            _("Showcase"),
            _("The first product as a wide card with text and button, the rest as a grid."),
            _LISTING,
            60,
            orders={"promo_group": 10},
            hints={
                "promos": _("The main deal as a wide card, then the sections."),
                "promo_group": _(
                    "Group header and the main deal as a wide card, the rest as a grid."
                ),
            },
        ),
        _c(
            "navigator",
            _("Navigator"),
            _("Subcategories and filters in a side column, products on the right."),
            frozenset({"catalog", "category", "promos"}),
            70,
            hints={
                "promos": _("Groups, filters and search in a side column, offers on the right.")
            },
        ),
        _c(
            "magazin",
            _("Magazine"),
            _("Cover image, then two large cards per row with a description."),
            _ALL,
            80,
            orders={"promo_group": 30, "promo": 40},
            recommended_grid="cols2",
            hints={
                "promos": _("Two offers per row with their conditions."),
                "promo_group": _("Cover, two offers per row, conditions right on the card."),
                "promo": _("Story first with a wide text column, photo alongside."),
            },
            labels={"promo": _("Magazin")},
        ),
        _c(
            "mosaik",
            _("Mosaic"),
            _("Tiles of different sizes — needs strong photos."),
            frozenset({"catalog", "category"}),
            90,
            recommended_grid="cols4",
        ),
        _c(
            "kompakt",
            _("Compact"),
            _("Subcategory index in columns and a dense grid — for large ranges."),
            frozenset({"catalog", "category", "promos", "promo"}),
            100,
            orders={"promo": 30},
            recommended_grid="cols6",
            hints={
                "promos": _("Group index in columns and a dense grid without sections."),
                "promo": _(
                    "Narrow column, small photo — for offers where the price is the message."
                ),
            },
            labels={"promo": _("Kompakt")},
        ),
        # Композиции, живущие только у акций.
        _c(
            "prospekt",
            _("Flyer"),
            _("Coloured header with the validity period and a dense grid — like a leaflet."),
            frozenset({"promo_group", "promo"}),
            110,
            orders={"promo_group": 20, "promo": 20},
            hints={
                "promo": _(
                    "Coloured price band first, photo and conditions below — like a leaflet."
                )
            },
            labels={"promo": _("Angebotszettel")},
        ),
        _c(
            "countdown",
            _("Countdown"),
            _("One timer for the whole campaign, offers sorted by time left."),
            frozenset({"promo_group"}),
            120,
            orders={"promo_group": 40},
        ),
        _c(
            "vergleich",
            _("Comparison"),
            _("Offers side by side as columns — for packages and tariffs."),
            frozenset({"promo_group"}),
            130,
            orders={"promo_group": 50},
        ),
        _c(
            "plakat",
            _("Plakat"),
            _("Wide photo across the top, price and button centred underneath."),
            frozenset({"promo"}),
            140,
            orders={"promo": 10},
        ),
    ]
}


# Поверхности, где отдельные коды НАМЕРЕННО не предлагаются, хотя формально
# подходят. Держим списком с причиной, а не молчаливым отсутствием в applies_to:
# иначе через полгода никто не вспомнит, почему «Preisliste» нет на корне.
EXCLUDED_REASONS = {
    ("catalog", "preisliste"): "прайс-вид корня уже даёт catalog_layout.preset (DL-21.1)",
    # LAY-5: тот же дубль был и на СТРАНИЦЕ КАТЕГОРИИ — два контрола писали одно и то
    # же, причём ось сетки предлагает восемь прайс-видов против одного «шаблона».
    # Именно это владелец называл «кашей». Код остаётся ЧИТАЕМЫМ (старые конфиги
    # рендерятся как раньше, Р-2), но больше не предлагается.
    ("category", "preisliste"): "прайс-вид задаётся осью сетки (там их восемь), LAY-5",
}


def styles_for(surface: str) -> list[tuple[str, object, object]]:
    """Производное представление реестра: тройки (код, метка, подсказка).

    Форма и порядок — те же, что у прежних четырёх списков, поэтому шаблоны
    плиток, формы кабинета и валидатор охвата Studio не меняются.
    """
    return [
        (spec.code, spec.label_for(surface), spec.hint_for(surface))
        for spec in sorted(COMPOSITIONS.values(), key=lambda s: s.order_for(surface))
        if surface in spec.applies_to and (surface, spec.code) not in EXCLUDED_REASONS
    ]


def valid_for(surface: str, *, offered_only: bool = False) -> frozenset:
    """Допустимые коды поверхности — единственный источник для резолверов.

    По умолчанию ЧТЕНИЕ шире ПРЕДЛОЖЕНИЯ: код, снятый из плиток (`EXCLUDED_REASONS`),
    всё ещё резолвится, иначе у тех, кто выбрал его раньше, витрина сменилась бы
    молча (инвариант волны LAY: живые сайты не меняются, Р-2).
    `offered_only=True` даёт ровно то, что видно владельцу в плитках.
    """
    if offered_only:
        return frozenset(code for code, _l, _h in styles_for(surface))
    return frozenset(spec.code for spec in COMPOSITIONS.values() if surface in spec.applies_to)


def available_for(surface: str, *, has_children: bool = True, has_combos: bool = True):
    """Композиции, которые на ЭТОЙ странице действительно имеют смысл.

    Гейт доступности из §4 плана: «полки» и «вкладки» без под-сущностей и
    «Sets» без наборов не предлагаются. Правило STU-9 в чистом виде — не
    обещать настройку, которая ничего не сделает.
    """
    out = []
    for code, label, hint in styles_for(surface):
        spec = COMPOSITIONS[code]
        if NEEDS_CHILDREN in spec.requires and not has_children:
            continue
        if NEEDS_COMBOS in spec.requires and not has_combos:
            continue
        out.append((code, label, hint))
    return out


def recommended_grid(code: str) -> str:
    """Сетка, которую подразумевает композиция ("" — никакой рекомендации)."""
    spec = COMPOSITIONS.get((code or "").strip())
    return spec.recommended_grid if spec else ""
