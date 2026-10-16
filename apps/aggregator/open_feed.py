"""T-8.8: открытый машинный фид каталога города — JSON Feed 1.1 + Atom.

План — docs/t8-8-machine-readable-plan-2026-10-15.md §2 (Р-4/Р-5). Один набор
элементов, два формата. Источник — `listings_for(...)` → `objects.public()`, то есть
ровно то, что видит человек на портале; порядок по новизне, featured НЕ поднимается
(UWG §5a), но помечен `sponsored`. Цена/скидка только при `new_price` (mystery → нет).
Демо: настоящий портал и основной домен их не отдают никогда; превью-портал
(`show_demo`) помечает `demo: true` и `_siteadaptor.preview: true` в шапке.

HTTP: без query — `cache_public_page`; с query — лимит частоты в СВОЁМ scope
`open-feed` (scope `portal-feed` занят главной портала); условный GET (ETag/304) —
`ConditionalGetMiddleware` СНАРУЖИ кэша (кэш хранит только тело, Content-Type и Vary).
Last-Modified не ставим: max(updated_at) не меняется при скрытии/истечении → ложный 304.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import feedgenerator
from django.utils.translation import gettext as _

from apps.core import city_categories as cc
from apps.core import districts
from apps.core.pagination import paginate

from .models import AggregatorListing
from .platform_links import legal_links, platform_url

OPEN_FEED_RATE_LIMIT = 60
MAX_ITEMS = 100
JSON_FEED_VERSION = "https://jsonfeed.org/version/1.1"
JSON_CT = "application/feed+json; charset=utf-8"
ATOM_CT = "application/atom+xml; charset=utf-8"
#: Условия использования (решение владельца 2026-10-15, план §8; показать юристу).
LICENSE = (
    "Daten der jeweiligen Anbieter. Nutzung in Verzeichnissen, Suchdiensten und "
    "Assistenten mit Quellenangabe und Link erlaubt. Keine Vervielfältigung des "
    "gesamten Datenbestands. Preise und Verfügbarkeit ohne Gewähr."
)

_KINDS = {k for k, _l in AggregatorListing.KINDS}


@dataclass(frozen=True)
class FeedParams:
    kinds: tuple[str, ...]
    kat: str
    tag: str
    district: str
    limit: int
    cursor: str | None


def parse_params(request, *, city: str) -> FeedParams:
    """Мусор → дефолты, никогда не 500: неизвестный `?kind` — предложения по умолчанию,
    `?limit=abc`/`10000` — кламп, `?kat`/`?merkmal` — только значения справочника."""
    g = request.GET
    kinds = tuple(k for k in g.getlist("kind") if k in _KINDS)
    kat = (g.get("kat") or "").strip()
    if not cc.keys_for_filter(kat):
        kat = ""
    tag = (g.get("merkmal") or "").strip()
    if not cc.normalize_tags([tag]):
        tag = ""
    district = districts.normalize(city, g.get("stadtteil") or "") if city else ""
    try:
        limit = int(g.get("limit") or MAX_ITEMS)
    except (TypeError, ValueError):
        limit = MAX_ITEMS
    limit = max(1, min(limit, MAX_ITEMS))
    cursor = (g.get("cursor") or "").strip() or None
    return FeedParams(
        kinds=kinds or AggregatorListing.OFFER_KINDS,
        kat=kat,
        tag=tag,
        district=district,
        limit=limit,
        cursor=cursor,
    )


def feed_pool(*, city, business_type, include_demo: bool, params: FeedParams):
    from .views import listings_for

    qs = listings_for(
        city=city or None,
        business_type=business_type or None,
        kinds=params.kinds,
        district=params.district or None,
        city_category=params.kat or None,
        city_tag=params.tag or None,
        include_demo=include_demo,
    )
    # Индекс поиска в фиде не нужен — не тащим вектор и свёрнутый текст.
    return qs.defer("search_vector", "search_text")


_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xml_safe(text: str) -> str:
    """Управляющие символы недопустимы в XML 1.0 — один кривой заголовок ломал бы
    разбор ВСЕГО фида у потребителя."""
    return _XML_ILLEGAL.sub("", text or "")


def tag_uri(listing) -> str:
    """Стабильный id элемента: один и тот же листинг на портале и на основном домене —
    один id; authority — базовый домен платформы (хост с портом невалиден для tag-URI)."""
    return f"tag:{settings.TENANT_DOMAIN_BASE},2026:listing:{listing.pk}"


def _price_unit(listing) -> str | None:
    if listing.listing_kind == "stay":
        return "night"
    if listing.listing_kind == "menu" and listing.price_per_person:
        return "person"
    return None


def _business_page(request, listing) -> str:
    """Страница бизнеса на ТЕКУЩЕМ хосте (портал или основной домен)."""
    try:
        return request.build_absolute_uri(reverse("portal-business", args=[listing.tenant_slug]))
    except Exception:  # noqa: BLE001 — на хосте без такого роута страницы нет
        return ""


def _origin(url: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(url or "")
    return f"{parts.scheme}://{parts.netloc}/" if parts.scheme and parts.netloc else ""


def feed_item(listing, *, request, preview: bool) -> dict:
    """Элемент JSON Feed 1.1 + расширение `_siteadaptor` (цена/срок/категория/бизнес)."""
    from .structured import availability_iri, price_visible

    visible = price_visible(listing)
    ext: dict = {
        "kind": listing.listing_kind,
        "price": f"{listing.new_price:.2f}" if visible else None,
        "old_price": f"{listing.old_price:.2f}" if visible and listing.old_price else None,
        "discount_percent": listing.discount_percent if visible else None,
        # SF-8a: референс old_price — "uvp" | "lowest30" | null (как на витрине).
        "price_reference": (
            listing.price_reference
            if visible and listing.price_reference in ("uvp", "lowest30")
            else None
        ),
        "currency": listing.currency or "EUR",
        "price_unit": _price_unit(listing) if visible else None,
        "valid_from": listing.starts_at.isoformat() if listing.starts_at else None,
        "valid_until": listing.ends_at.isoformat() if listing.ends_at else None,
        "availability": availability_iri(listing),
        "is_new": bool(listing.is_new),
        "category": listing.city_category or None,
        "category_label": cc.label(listing.city_category) if listing.city_category else None,
        "tags": list(listing.city_tags or []),
        "district": listing.district or None,
        "district_name": listing.district_name or None,
        "city": listing.city or None,
        "lat": str(listing.latitude) if listing.latitude is not None else None,
        "lng": str(listing.longitude) if listing.longitude is not None else None,
        "business": {
            "name": listing.business_name,
            "page": _business_page(request, listing),
            "website": _origin(listing.detail_url),
        },
        "sponsored": bool(listing.is_featured_now),
    }
    item = {
        "id": tag_uri(listing),
        "url": request.build_absolute_uri(reverse("aggregator-offer", args=[listing.pk])),
        "external_url": listing.with_channel("feed"),
        "title": listing.title_text,
        # По спецификации обязателен content_text ИЛИ content_html.
        "content_text": listing.teaser_text or listing.title_text,
        "date_published": listing.created_at.isoformat(),
        "date_modified": listing.updated_at.isoformat(),
        "_siteadaptor": ext,
    }
    if listing.teaser_text:
        item["summary"] = listing.teaser_text
    if (listing.image or {}).get("url"):
        item["image"] = request.build_absolute_uri(listing.image["url"])
    return item


def _feed_meta(*, city: str, preview: bool) -> dict:
    legal = legal_links()
    meta = {
        "city": city or None,
        "license": LICENSE,
        "terms_url": legal["datenschutz"],
        "impressum": legal["impressum"],
        "datenschutz": legal["datenschutz"],
        "discover": platform_url("aggregator-index"),
    }
    if preview:
        meta["preview"] = True
    return meta


def json_feed(request, *, title: str, home_url: str, city: str, page, preview: bool) -> dict:
    items = [feed_item(it, request=request, preview=preview) for it in page.items]
    feed = {
        "version": JSON_FEED_VERSION,
        "title": title,
        "home_page_url": home_url,
        "feed_url": request.build_absolute_uri(request.path),
        "language": getattr(request, "LANGUAGE_CODE", "de") or "de",
        "description": _(
            "Aktuelle Angebote lokaler Anbieter — offener Feed für Verzeichnisse und Assistenten."
        ),
        "items": items,
        "_siteadaptor": _feed_meta(city=city, preview=preview),
    }
    if page.next_cursor:
        params = {k: v for k, v in request.GET.lists()}
        params["cursor"] = [page.next_cursor]
        feed["next_url"] = request.build_absolute_uri(
            f"{request.path}?{urlencode(params, doseq=True)}"
        )
    return feed


class _AtomWithRelated(feedgenerator.Atom1Feed):
    def add_item_elements(self, handler, item):
        super().add_item_elements(handler, item)
        if item.get("related"):
            handler.addQuickElement("link", "", {"rel": "related", "href": item["related"]})
        if item.get("demo"):
            handler.addQuickElement("category", "", {"term": "demo", "label": "Demo"})


def atom_feed(request, *, title: str, home_url: str, page, preview: bool) -> str:
    """Atom 1.0 штатным `feedgenerator` (экранирование и даты — его забота).
    Цен в Atom нет — цена строкой в summary, если видима."""
    from .structured import price_visible

    items = list(page.items)
    feed = _AtomWithRelated(
        title=title,
        link=home_url,
        description=_("Aktuelle Angebote lokaler Anbieter"),
        language=getattr(request, "LANGUAGE_CODE", "de") or "de",
        feed_url=request.build_absolute_uri(request.path),
        feed_copyright=LICENSE,
    )
    for it in items:
        summary = _xml_safe(it.teaser_text or it.title_text)
        if price_visible(it):
            summary = f"{it.new_price:.2f} {it.currency or 'EUR'} · {summary}"
        categories = [it.city_category] if it.city_category else []
        if it.is_featured_now:
            categories.append("sponsored")
        feed.add_item(
            title=_xml_safe(it.title_text),
            link=request.build_absolute_uri(reverse("aggregator-offer", args=[it.pk])),
            description=summary,
            unique_id=tag_uri(it),
            pubdate=it.created_at,
            updateddate=it.updated_at,
            categories=categories,
            author_name=_xml_safe(it.business_name) or None,
            # related = сайт бизнеса с атрибуцией канала.
            related=it.with_channel("feed"),
            demo=bool(it.is_demo) if preview else None,
        )
    return feed.writeString("utf-8")


def rate_limited(request) -> HttpResponse | None:
    """Запросы с параметрами идут мимо кэша → свой лимит частоты (scope `open-feed`)."""
    if not request.GET:
        return None
    from apps.core import ratelimit

    if ratelimit.hit(
        "open-feed", ratelimit.client_ip(request), limit=OPEN_FEED_RATE_LIMIT, window=60
    ):
        return HttpResponse(_("Zu viele Anfragen — bitte kurz warten."), status=429)
    return None


def render_feed(
    request,
    *,
    fmt: str,
    title: str,
    home_url: str,
    city: str,
    business_type: str,
    include_demo: bool,
    preview: bool = False,
):
    """Общее тело обеих вьюх (портал/основной домен) и обоих форматов.

    `preview` — портал ещё в режиме превью (T-8.26 Р-3: демо в фид не попадает, но
    мета `preview: true` честно говорит, что настоящей ленты пока нет)."""
    limited = rate_limited(request)
    if limited is not None:
        return limited
    params = parse_params(request, city=city)
    pool = feed_pool(
        city=city, business_type=business_type, include_demo=include_demo, params=params
    )
    page = paginate(pool, order_field="created_at", limit=params.limit, cursor=params.cursor)
    preview = bool(preview or include_demo)
    if fmt == "atom":
        body = atom_feed(request, title=title, home_url=home_url, page=page, preview=preview)
        return HttpResponse(body, content_type=ATOM_CT)
    data = json_feed(request, title=title, home_url=home_url, city=city, page=page, preview=preview)
    return JsonResponse(data, content_type=JSON_CT, json_dumps_params={"ensure_ascii": False})
