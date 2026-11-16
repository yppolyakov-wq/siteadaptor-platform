"""STU-18d: композиция ЛИСТИНГА — одна точка сборки контекста для девяти страниц.

Решение владельца Р-2 («композиция на всех девяти листингах сразу»). Каркас
`templates/storefront/listing.html` рисует хром композиции сам, но данные для него
— под-сущности, полки, обложка — знает только вьюха поверхности: у услуг и номеров
это подборки, у события тема, у поездки страна, у набора категория. Здесь собран
общий узел, чтобы девять вьюх не расписывали одно и то же (и не разъехались).

Контракт наружу — ровно те ключи, что читает каркас:

* `page_composition`  — резолвнутый код («» = обычная сетка);
* `comp_entries`      — под-сущности `{label, url, active, count}`;
* `comp_shelves`      — полки `{label, slug, url, total, more, items}`;
* `comp_hero`         — обложка `{eyebrow, text, photo}`;
* `comp_item_template`/`comp_kind` — чем рисовать элемент полки.

Fail-safe: код проверяется и по поверхности, и по ДАННЫМ (`compositions.resolve`).
Владелец мог выбрать «Полки», а потом удалить последнюю подборку — страница обязана
вернуться к обычной сетке, а не показать пустоту.

Тяжёлые данные приходят callable'ами: полки — это запрос на каждую под-сущность,
и считать их ради композиции, которая сейчас не выбрана, незачем.
"""

from __future__ import annotations

from collections.abc import Callable

from apps.core import compositions

#: элемент полки на листингах, которые рисуют карточку тегом `sellable_card`
SELLABLE_ITEM = "storefront/composition/_item_sellable.html"

#: композиции, которым нужен список под-сущностей
_ENTRY_CODES = ("tabs", "kompakt", "navigator")


def _call(value):
    return value() if callable(value) else value


def selected_code(config: dict | None, surface: str) -> str:
    """Сырой выбор владельца для поверхности («» — не задан)."""
    return ((config or {}).get("page_styles") or {}).get(surface, "")


def context(
    config: dict | None,
    surface: str,
    *,
    entries: Callable | list | tuple | None = None,
    shelves: Callable | list | tuple | None = None,
    hero: Callable | dict | None = None,
    carry: str = "",
    kind: str = "",
    item_template: str = SELLABLE_ITEM,
) -> dict:
    """Контекст композиции для вьюхи листинга.

    `entries` считаются всегда (по ним же гейтится доступность кода), `shelves` и
    `hero` — только когда выбрана их композиция.
    """
    from apps.core import listing_parts
    from apps.core import page_parts as pp

    rows = list(_call(entries) or [])
    # FB-31 P4: шаблон — набор осей (шапка, навигация); строки схемы страницы сильнее кода.
    # Гейты данных (`compositions.resolve`: нет подразделов / нет фото) — как раньше, по оси.
    s = listing_parts.LISTINGS.get(surface)
    if s is not None:
        parts = listing_parts.effective(config, surface)
        nav_raw = pp.legacy_code(s, s.parts(groups=parts.groups)) if parts.groups else ""
        head_raw = "kopfbild" if parts.head == "titelbild" else ""
    else:
        raw = selected_code(config, surface)
        nav_raw = "" if raw == "kopfbild" else raw
        head_raw = "kopfbild" if raw == "kopfbild" else ""
    # обложку считаем ДО резолва: без фото «С обложкой» проваливается в сетку
    hero_data = _call(hero) if head_raw else None
    nav = compositions.resolve(surface, nav_raw, has_children=bool(rows)) if nav_raw else ""
    head = (
        compositions.resolve(surface, head_raw, has_photo=bool((hero_data or {}).get("photo")))
        if head_raw
        else ""
    )
    code = nav or head
    ctx: dict = {"page_composition": code}
    # Композиция, которая САМА выводит под-сущности, забирает их себе: чипы того
    # же фасета на странице стали бы вторым списком тех же подборок. Стенд поймал
    # это сразу — над вкладками «Damen · Herren» висел точно такой же ряд чипов.
    ctx["comp_owns_entries"] = nav in _ENTRY_CODES
    if nav in _ENTRY_CODES:
        ctx["comp_entries"] = rows
        ctx["comp_carry"] = carry
    elif nav == "regale":
        ctx["comp_shelves"] = list(_call(shelves) or [])
        ctx["comp_item_template"] = item_template
        ctx["comp_kind"] = kind
    if head:  # обложка — своя ось: рисуется и вместе с навигацией (новое сочетание)
        ctx["comp_hero"] = hero_data
    return ctx


def hero_from_tenant(tenant, config: dict | None) -> dict:
    """Обложка листинга: надзаголовок «вид бизнеса · город» + фото сайта.

    У категории для «С обложкой» есть СВОЁ фото и описание; у списка услуг или
    отзывов их нет, поэтому берём то, что у витрины есть всегда, — hero сайта.
    Нет фото — композиция не применяется вовсе (гейт `NEEDS_PHOTO`).
    """
    cfg = config or {}
    from apps.core import banners

    photo = cfg.get("hero_image") or banners.first_image(cfg)
    eyebrow = ""
    if tenant is not None:
        try:
            eyebrow = tenant.get_business_type_display()
            if getattr(tenant, "city", ""):
                eyebrow = f"{eyebrow} · {tenant.city}"
        except Exception:  # noqa: BLE001 — витрина не падает из-за подписи
            eyebrow = ""
    return {"eyebrow": eyebrow, "text": "", "photo": photo}
