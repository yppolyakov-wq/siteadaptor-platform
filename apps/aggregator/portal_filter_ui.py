"""FLT-1d: панель фильтров городского портала — строка пилюль, поповеры, шторка.

План — docs/flt-portal-filters-plan-2026-11-04.md §4–§6, §12.4, §13.3. Всё работает без JS:
поповеры — `<details>` со ссылками-переключателями, шторка — одна GET-форма. Состояние
страницы — ТОЛЬКО параметры: район пути становится отмеченной галочкой, а действие формы и
ссылок — корень (или `/<facet>/`), поэтому снять район пути можно, как любой другой.

Ссылки ведут на query-вариации (noindex) — у них `rel="nofollow"` в шаблоне (§12.4).
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from django.utils.translation import gettext as _

from apps.core import city_categories as cc
from apps.core import districts as district_registry

# Параметры, которыми управляет шторка: их нет среди скрытых полей формы (иначе значение
# ушло бы дважды), всё остальное состояние едет скрытыми полями (W0: «Anwenden» ничего не
# теряет — ни марку, ни компанию, ни карту, ни «roh=ort»).
DRAWER_KEYS = frozenset(
    {"kat", "stadtteil", "merkmal", "preis_von", "preis_bis", "datum", "verfuegbar", "offen"}
)
DRAWER_KEYS_WITH_POINT = DRAWER_KEYS | {"umkreis"}


def base_path(facet: str | None) -> str:
    return f"/{quote(facet, safe='')}/" if facet else "/"


def state_params(request, *, scope, q, filters, area, point) -> list[tuple[str, str]]:
    """Полное состояние выдачи параметрами (район пути — тоже параметром), без курсора."""
    from . import geo
    from . import search as search_engine

    out: list[tuple[str, str]] = []
    if scope.kind_key:
        out.append(("kind", scope.kind_key))
    if scope.new_only:
        out.append(("neu", "1"))
    # Сорт — только явно заданный: «naehe» по умолчанию при точке в ссылки не пишем.
    explicit_sort = (request.GET.get("sort") or "").strip()
    out += [
        (k, v)
        for k, v in search_engine.carry(q, filters)
        if k != "stadtteil" and (k != "sort" or v == explicit_sort)
    ]
    out += [("stadtteil", d) for d in area]
    if point is not None:
        out += geo.carry(*point)
    out += [("roh", v) for v in request.GET.getlist("roh") if v == "ort"]
    if geo.view_mode(request):  # PH-14: вид (Liste/Karte) переживает фильтры
        out.append(("ansicht", geo.view_mode(request)))
    out += hotel_params(request)
    return out


HOTEL_KEYS = ("von", "bis", "gaeste")


def hotel_params(request) -> list[tuple[str, str]]:
    """H8b: поиск отеля по датам переживает любой фильтр (ревью FLT-1d, F2)."""
    from . import hotel_search

    von = hotel_search.parse_date(request.GET.get("von"))
    bis = hotel_search.parse_date(request.GET.get("bis"))
    if not (von and bis and bis > von):
        return []
    try:
        guests = max(1, min(int(request.GET.get("gaeste", "2")), 50))
    except (TypeError, ValueError):
        guests = 2
    return [("von", von.isoformat()), ("bis", bis.isoformat()), ("gaeste", str(guests))]


def _url(path: str, params) -> str:
    return f"{path}?{urlencode(list(params))}" if params else path


def build(
    request,
    portal,
    *,
    facet,
    facets,
    axis,
    district,
    scope,
    q,
    filters,
    area,
    point,
    counts,
    hits,
    hits_capped,
) -> dict:
    """Контекст панели фильтров (см. модуль)."""
    from . import geo
    from . import search as search_engine

    path = base_path(facet)
    params = state_params(request, scope=scope, q=q, filters=filters, area=area, point=point)

    def toggle(key: str, value: str) -> str:
        if (key, value) in params:
            return _url(path, [p for p in params if p != (key, value)])
        return _url(path, [*params, (key, value)])

    def without(*keys: str) -> str:
        return _url(path, [p for p in params if p[0] not in keys])

    kats = set(filters.kats)
    tags = set(filters.tags)
    open_sections = {
        (cc.section(k) or cc.section(getattr(cc.category(k), "section", ""))).key
        for k in kats
        if cc.section(k) or cc.category(k)
    }
    sections = []
    for sec in cc.SECTIONS:
        n = counts.sections.get(sec.key, 0)
        checked = sec.key in kats
        if not n and not checked and sec.key not in open_sections:
            continue
        cats = []
        if sec.key in open_sections:
            for cat in cc.CATEGORIES:
                if cat.section != sec.key:
                    continue
                cn = counts.categories.get(cat.key, 0)
                if cn or cat.key in kats:
                    cats.append(
                        {
                            "key": cat.key,
                            "label": str(cat.label),
                            "count": cn,
                            "checked": cat.key in kats,
                            "url": toggle("kat", cat.key),
                        }
                    )
        sections.append(
            {
                "key": sec.key,
                "label": f"{sec.icon} {sec.label}",
                "count": n,
                "checked": checked,
                "url": toggle("kat", sec.key),
                "categories": cats,
            }
        )
    districts = []
    for slug, name in district_registry.choices_for(portal.city or ""):
        n = counts.districts.get(slug, 0)
        if len(area) == 1 and slug == area[0] and hits is not None:
            n = hits  # единственный выбранный район = «N Treffer» (инвариант §3)
        checked = slug in area
        if n or checked:
            districts.append(
                {
                    "slug": slug,
                    "name": name,
                    "count": n,
                    "checked": checked,
                    "url": toggle("stadtteil", slug),
                }
            )
    tag_rows = []
    for key, label in cc.TAGS:
        n = counts.tags.get(key, 0)
        if n or key in tags:
            tag_rows.append(
                {
                    "key": key,
                    "label": str(label),
                    "count": n,
                    "checked": key in tags,
                    "url": toggle("merkmal", key),
                }
            )

    pills = []
    for kat in filters.kats:
        pills.append({"label": cc.label(kat), "url": toggle("kat", kat)})
    for slug in area:
        pills.append(
            {
                "label": district_registry.label(portal.city or "", slug) or slug,
                "url": toggle("stadtteil", slug),
            }
        )
    for tag in filters.tags:
        pills.append({"label": cc.tag_label(tag), "url": toggle("merkmal", tag)})
    from django.utils.formats import number_format

    if filters.price_from is not None:
        price = number_format(filters.price_from, 2)
        pills.append({"label": _("ab %(p)s €") % {"p": price}, "url": without("preis_von")})
    if filters.price_to is not None:
        price = number_format(filters.price_to, 2)
        pills.append({"label": _("bis %(p)s €") % {"p": price}, "url": without("preis_bis")})
    date_labels = {"heute": _("Heute"), "wochenende": _("Am Wochenende")}
    if filters.date:
        pills.append(
            {"label": date_labels.get(filters.date, filters.date), "url": without("datum")}
        )
    if filters.available:
        pills.append({"label": _("Nur verfügbar"), "url": without("verfuegbar")})
    if filters.size:
        pills.append({"label": _("Größe %(s)s") % {"s": filters.size}, "url": without("groesse")})
    if filters.brand:  # F1: марку/компанию (ссылки «Alle von …») тоже можно снять
        pills.append({"label": f"{_('Marke')}: {filters.brand}", "url": without("marke")})
    if filters.business:
        pills.append(
            {"label": f"{_('Unternehmen')}: {filters.business}", "url": without("unternehmen")}
        )
    if filters.radius_km:
        pills.append(
            {"label": _("≤ %(km)s km") % {"km": filters.radius_km}, "url": without("umkreis")}
        )
    open_pill = {"active": filters.open_now, "url": toggle("offen", "1")}

    drawer_keys = DRAWER_KEYS_WITH_POINT if point is not None else DRAWER_KEYS
    hidden = [(k, v) for k, v in params if k not in drawer_keys]
    sort_hidden = [(k, v) for k, v in params if k != "sort"]
    price_hidden = [(k, v) for k, v in params if k not in ("preis_von", "preis_bis")]
    # PH-14: «In der Nähe» — всегда пункт сортировки (вместо отдельной кнопки «In meiner Nähe»):
    # без точки скрипт берёт геолокацию и дописывает lat/lng; без JS/разрешения сервер
    # «naehe» без точки игнорирует (search.parse) — выдача просто прежняя.
    sorts = [("", _("Relevanz") if q else _("Standard"))] + list(search_engine.SORT_LABELS.items())
    # «Branche» — ссылками: отрасль задаётся путём, GET-форма её не выразит (§13.9).
    branches = []
    if axis == "business_type" and facets:
        # Один район — путевые страницы района (`/stadtteil/<d>/<facet>/`, индексируемые);
        # несколько — путь отрасли + районы параметрами.
        if len(area) == 1:
            prefix = f"/stadtteil/{quote(area[0], safe='')}"
            state = [p for p in params if p != ("stadtteil", area[0])]
        else:
            prefix, state = "", list(params)
        branches.append({"label": _("All"), "url": _url(f"{prefix}/", state), "active": not facet})
        for value, label in facets:
            branches.append(
                {
                    "label": label,
                    "url": _url(prefix + base_path(value), state),
                    "active": facet == value,
                }
            )
    active_count = len(pills) + (1 if filters.open_now else 0)
    return {
        "action": path,
        "hidden": hidden,
        "sort_hidden": sort_hidden,
        "price_hidden": price_hidden,
        "sections": sections,
        "districts": districts,
        "tags": tag_rows,
        "pills": pills,
        "open_pill": open_pill,
        "filters": filters,
        "sorts": sorts,
        "has_point": point is not None,
        "radius_choices": geo.RADIUS_CHOICES,
        "branches": branches,
        "active_count": active_count,
        # Сброс — все фильтры (вкл. марку, компанию, размер, сорт, даты отеля); остаются
        # запрос, вид, точка и вид-карта.
        "reset_url": _url(
            path,
            [
                p
                for p in params
                if p[0] not in drawer_keys
                and p[0] not in search_engine.FILTER_PARAMS
                and p[0] not in HOTEL_KEYS
            ],
        ),
        "hotel_hidden": [p for p in params if p[0] not in HOTEL_KEYS],
        "hits": hits,
        "hits_capped": hits_capped,
        "area_label": ", ".join(p["label"] for p in pills[len(filters.kats) :][: len(area)]),
    }
