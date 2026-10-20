"""T-8.10d D-1c: подписка на НАБОР ФИЛЬТРОВ поиска («Benachrichtigen, wenn es so etwas gibt»).

План — docs/t8-10d-search-subscriptions-plan-2026-10-19.md §2. Обобщение «Folgen» (T-8.7):
та же модель, тот же DOI, та же сводка; новый вид цели `query`, ключ = sha256 канонического
набора. Правила:

* Набор — только белый список параметров поиска, нормализованный тем же `parse_filters` и
  разбором намерения, что и страница: письмо и ссылка «Alle anzeigen» дают одну выборку.
* Не храним то, что относительно дня разбора («heute», «geöffnet»), сортировку и точку
  посетителя (координаты, радиус — персональные данные).
* Набор ровно из одного «старого» условия — компания, раздел или район — сводится к
  прежней цели: двух подписок на одно и то же не бывает, старые строки не мигрируются.
"""

from __future__ import annotations

import hashlib
import re
from types import SimpleNamespace
from urllib.parse import urlencode

from django.http import QueryDict

from apps.core import city_categories as cc
from apps.core import districts

Q_MAX = 60
MAX_KATS = 3
MAX_TAGS = 3
# Каноничный порядок ключей набора (и подписи).
KEYS = (
    "q",
    "kind",
    "kat",
    "merkmal",
    "stadtteil",
    "unternehmen",
    "marke",
    "groesse",
    "preis_von",
    "preis_bis",
    "verfuegbar",
    "roh",
)
# Принимаются, но в набор не идут: честно говорим жителю, что они не действуют.
DROPPED = ("datum", "offen", "umkreis", "sort", "lat", "lng")


def _params(value) -> QueryDict:
    if isinstance(value, QueryDict):
        return value
    qd = QueryDict(mutable=True)
    for key, val in value or ():
        qd.appendlist(str(key), str(val))
    return qd


# Ссылка/домен в свободном тексте: подпись набора уходит в DOI-письмо на ЛЮБОЙ адрес —
# чужой рекламный текст со ссылкой платформа рассылать не должна.
_LINKISH = re.compile(
    r"https?:|www\.|[a-z0-9-]+\.(?:de|com|net|org|io|info|eu|at|ch|ru|xyz|app|shop|online|site|biz)\b",
    re.IGNORECASE,
)


def _free_text(value: str, scrub) -> str:
    """Свободный текст набора (q, марка): без контактов (scrub) и без ссылок — иначе пусто."""
    text = " ".join(scrub(value or "").split())[:Q_MAX].strip()
    if "‹" in text or _LINKISH.search(text):  # адрес/телефон/ссылка — такой текст не храним
        return ""
    return text


def known_city(city: str) -> bool:
    """Город из реестра или с живыми листингами каталога — выдуманный `?city=` с
    /entdecken/ подписку не создаёт (письмо по пустому городу и мусорная подпись)."""
    from .models import AggregatorListing

    if not city:
        return False
    if districts.city_key(city) in districts.CITIES:
        return True
    return AggregatorListing.objects.public().filter(city__iexact=city).exists()


def city_for(params, portal) -> str:
    """Город области подписки: портала или `?city=` на /entdecken/ (только известный)."""
    if portal is not None:
        return districts.city_label(str(getattr(portal, "city", "") or "")[:100])
    city = districts.city_label(str(params.get("city", "") or "")[:100])
    return city if known_city(city) else ""


def canonical(params, *, city: str, portal: bool = True) -> tuple[tuple[str, str], ...] | None:
    """Набор фильтров подписки (кортеж пар в каноничном порядке) или None — подписываться
    не на что (пустой набор или нет города). `portal=False` — область /entdecken/: там
    вид — только ОДИН вид листинга (группы портала страница /entdecken/ не знает)."""
    from apps.core.pii import scrub

    from . import portal_home_blocks as home
    from . import search

    if not city:
        return None
    qd = _params(params)
    explicit = search.parse_filters(SimpleNamespace(GET=qd), city=city)
    roh = tuple(v for v in qd.getlist("roh") if v)
    q = (qd.get("q") or "").strip()[: search.SEARCH_MAX]
    q_eff, eff, _chips, _hints = search.resolve_intent(q, explicit, city=city, roh=roh)
    q_eff = _free_text(q_eff, scrub)
    brand = _free_text(eff.brand, scrub)
    pairs: list[tuple[str, str]] = []
    if q_eff:
        pairs.append(("q", q_eff))
    kind = (qd.get("kind") or "").strip()
    if portal:
        if not home.kinds_for(kind):
            kind = ""
        # Вид выдачи страницы считается по СЫРОМУ запросу: «unter 5 Euro» ищет по всем
        # видам, а в набор уходит только цена — без явного вида письмо сузилось бы до ленты.
        page_kind = home.default_kind(kind, q, explicit)
        kept = SimpleNamespace(
            kats=eff.kats, tags=eff.tags, size=eff.size, brand=brand, business=eff.business
        )
        if page_kind and page_kind != home.default_kind("", q_eff, kept):
            kind = page_kind
    elif kind not in home.ALL_KINDS:
        kind = ""
    pairs += [("kat", k) for k in sorted(eff.kats)[:MAX_KATS]]
    pairs += [("merkmal", t) for t in sorted(eff.tags)[:MAX_TAGS]]
    for key, value in (
        ("stadtteil", eff.district),
        ("unternehmen", eff.business),
        ("marke", brand),
        ("groesse", eff.size),
        ("preis_von", "" if eff.price_from is None else str(eff.price_from)),
        ("preis_bis", "" if eff.price_to is None else str(eff.price_to)),
        ("verfuegbar", "1" if eff.available else ""),
    ):
        if value:
            pairs.append((key, value))
    if not pairs:  # один лишь вид — «всё подряд», а не выбор жителя: такой подписки нет
        return None
    if kind:
        pairs.append(("kind", kind))
    # Без «roh=ort» повторный разбор остатка превратил бы слово района в фильтр, и
    # письмо разошлось бы со ссылкой — флаг храним, но только при живом тексте.
    if q_eff and "ort" in roh:
        pairs.append(("roh", "ort"))
    order = {k: i for i, k in enumerate(KEYS)}
    return tuple(sorted(pairs, key=lambda p: (order.get(p[0], 99), p[1])))


# Параметры только /entdecken/ (тип бизнеса, событийные фильтры, наборы меню): выборка
# письма их не знает, поэтому при них кнопку подписки не показываем вовсе.
ENTDECKEN_ONLY = ("type", "cat", "month", "gaeste", "anlass", "diet")
DROPPED_MARK = "entfaellt"  # ссылка несёт ИМЕНА непереносимых фильтров, не значения


def dropped(params) -> list[str]:
    """Параметры, которые подписка не переносит (для честной подсказки на /folgen/).

    Ссылка с выдачи передаёт их имена в `?entfaellt=` — координаты и даты посетителя
    в адрес страницы подписки не попадают."""
    qd = _params(params)
    marked = {k for k in (qd.get(DROPPED_MARK) or "").split(",") if k in DROPPED}
    return [k for k in DROPPED if (qd.get(k) or "").strip() or k in marked]


def follow_link(params, *, portal, path_district: str = ""):
    """Кнопка «Benachrichtigen» под выдачей: (Target, query-строка ссылки) или None.

    Только для набора, который НЕ сводится к старой цели (та уже есть кнопкой «Folgen»),
    и только при городе (портал или `?city=` на /entdecken/)."""
    from .follow import parse_target
    from .models import FollowSubscription

    qd = _params(params).copy()
    if any((qd.get(k) or "").strip() for k in ENTDECKEN_ONLY):
        return None
    qd.setlist("art", ["suche"])
    if path_district:
        qd.setlist("stadtteil", [path_district])
    target = parse_target(qd, portal=portal)
    if target is None or target.kind != FollowSubscription.TARGET_QUERY:
        return None
    pairs = list(target.as_params())
    lost = dropped(qd)
    if lost:
        pairs.append((DROPPED_MARK, ",".join(lost)))
    return target, urlencode(pairs)


def key(pairs) -> str:
    return hashlib.sha256(urlencode(list(pairs)).encode()).hexdigest()


def from_stored(value) -> tuple[tuple[str, str], ...]:
    """Набор из JSON модели/токена → кортеж пар (мусор отбрасывается)."""
    items = value.get("p") if isinstance(value, dict) else value
    out = []
    for item in items or ():
        if isinstance(item, (list, tuple)) and len(item) == 2:
            out.append((str(item[0]), str(item[1])))
    return tuple(out)


def stored(pairs) -> dict:
    return {"v": 1, "p": [list(p) for p in pairs]}


def legacy(pairs, *, city: str):
    """Набор из ОДНОГО старого условия → (kind, key) прежней цели или None."""
    from .models import FollowSubscription

    if len(pairs) != 1:
        return None
    name, value = pairs[0]
    if name == "unternehmen":
        return FollowSubscription.TARGET_BUSINESS, value
    if name == "kat" and cc.section(value):
        return FollowSubscription.TARGET_SECTION, value
    if name == "stadtteil":
        return FollowSubscription.TARGET_DISTRICT, value
    return None


def business_schema(slug: str) -> str | None:
    """Схема живой, видимой в каталоге компании по слагу (иначе None)."""
    from apps.tenants.models import Tenant

    from .follow import business_target

    tenant = Tenant.objects.filter(slug=slug, is_active=True).first()
    target = business_target(tenant)
    return target.key if target is not None else None


def valid_business(pairs) -> bool:
    """Компания из набора жива и видна в каталоге (демо/скрытая — подписки нет)."""
    slug = dict(pairs).get("unternehmen")
    return not slug or business_schema(slug) is not None


# --- показ ------------------------------------------------------------------------------


def describe(pairs, *, city: str = "") -> str:
    """Человеческая подпись набора: «„Tomaten“ · Obst & Gemüse · Ohligs · Marke Bosch»."""
    from django.utils.translation import gettext as _

    from . import portal_home_blocks as home

    parts: list[str] = []
    for name, value in pairs:
        if name == "q":
            parts.append(f"„{value}“")
        elif name == "kind":
            from .models import AggregatorListing

            tabs = {t.key: t.label for t in home.TABS}
            label = tabs.get(value) or dict(AggregatorListing.KINDS).get(value, value)
            parts.append(str(label))
        elif name == "kat":
            node = cc.category(value) or cc.section(value)
            parts.append(str(node.label) if node else value)
        elif name == "merkmal":
            parts.append(str(cc.tag_label(value) or value))
        elif name == "stadtteil":
            parts.append(districts.label(city, value) or value)
        elif name == "unternehmen":
            from apps.tenants.models import Tenant

            name_ = Tenant.objects.filter(slug=value).values_list("name", flat=True).first()
            parts.append(_("bei %(name)s") % {"name": name_ or value})
        elif name == "marke":
            parts.append(_("Marke %(brand)s") % {"brand": value})
        elif name == "groesse":
            parts.append(_("Größe %(size)s") % {"size": value})
        elif name == "preis_von":
            parts.append(_("ab %(price)s €") % {"price": value})
        elif name == "preis_bis":
            parts.append(_("bis %(price)s €") % {"price": value})
        elif name == "verfuegbar":
            parts.append(_("nur verfügbare"))
    return " · ".join(p for p in parts if p)


def url_params(pairs) -> list[tuple[str, str]]:
    """Параметры страницы выдачи для набора (ссылка «Alle anzeigen» / «Ansehen»)."""
    return [(k, v) for k, v in pairs]


# --- выборка письма ---------------------------------------------------------------------


def queryset(sub):
    """Выдача подписки — ТЕМ ЖЕ путём, что страница по ссылке «Alle anzeigen» (⊇ письма).

    Демо и скрытое — никогда (даже на превью-портале), журнал поиска не пишется,
    фолбэк опечаток выключен: письмо не уходит по «похожему» слову."""
    from . import portal_home_blocks as home
    from . import search
    from .models import AggregatorListing
    from .portal_views import _district_pool
    from .views import listings_for

    pairs = from_stored(sub.query)
    if not pairs:
        return AggregatorListing.objects.none()
    qd = _params(pairs)
    city = sub.city
    explicit = search.parse_filters(SimpleNamespace(GET=qd), city=city)
    q = (qd.get("q") or "").strip()
    q_eff, eff, _chips, _hints = search.resolve_intent(
        q, explicit, city=city, roh=tuple(qd.getlist("roh"))
    )
    kind = home.default_kind((qd.get("kind") or "").strip(), q, explicit)
    portal = sub.portal
    if portal is not None:
        kinds = home.kinds_for(kind) or AggregatorListing.OFFER_KINDS
        # Портал без демо (письма не шлют выдуманное), но с его темой (T-8.14).
        scope_portal = SimpleNamespace(
            show_demo=False,
            theme_tags=getattr(portal, "theme_tags", None) or [],
            theme_categories=getattr(portal, "theme_categories", None) or [],
        )
        _broad, _whole, _base, pool = _district_pool(
            scope_portal,
            portal.city or city or None,
            portal.business_type or None,
            "",
            q_eff,
            eff,
            kinds,
            False,
            None,
            fuzzy=False,
        )
        return pool
    pool = listings_for(city=city or None, include_demo=False)
    kinds = home.kinds_for(kind)
    if kinds:
        pool = pool.filter(listing_kind__in=kinds)
    return search.execute(
        pool, q_eff, eff, surface="entdecken", track=False, city=city, fuzzy=False
    ).qs
