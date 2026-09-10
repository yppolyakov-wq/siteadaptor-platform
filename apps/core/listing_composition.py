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
    rows = list(_call(entries) or [])
    raw = selected_code(config, surface)
    # обложку считаем ДО резолва: без фото «С обложкой» проваливается в сетку
    hero_data = _call(hero) if raw == "kopfbild" else None
    code = compositions.resolve(
        surface,
        raw,
        has_children=bool(rows),
        has_photo=bool((hero_data or {}).get("photo")),
    )
    ctx: dict = {"page_composition": code}
    if code in _ENTRY_CODES:
        ctx["comp_entries"] = rows
        ctx["comp_carry"] = carry
    elif code == "regale":
        ctx["comp_shelves"] = list(_call(shelves) or [])
        ctx["comp_item_template"] = item_template
        ctx["comp_kind"] = kind
    elif code == "kopfbild":
        ctx["comp_hero"] = hero_data
    return ctx


def hero_from_tenant(tenant, config: dict | None) -> dict:
    """Обложка листинга: надзаголовок «вид бизнеса · город» + фото сайта.

    У категории для «С обложкой» есть СВОЁ фото и описание; у списка услуг или
    отзывов их нет, поэтому берём то, что у витрины есть всегда, — hero сайта.
    Нет фото — композиция не применяется вовсе (гейт `NEEDS_PHOTO`).
    """
    cfg = config or {}
    heroes = cfg.get("heroes") or []
    photo = cfg.get("hero_image") or (
        (heroes[0] or {}).get("image", "") if heroes and isinstance(heroes[0], dict) else ""
    )
    eyebrow = ""
    if tenant is not None:
        try:
            eyebrow = tenant.get_business_type_display()
            if getattr(tenant, "city", ""):
                eyebrow = f"{eyebrow} · {tenant.city}"
        except Exception:  # noqa: BLE001 — витрина не падает из-за подписи
            eyebrow = ""
    return {"eyebrow": eyebrow, "text": "", "photo": photo}
