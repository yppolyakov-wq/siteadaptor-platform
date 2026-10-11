"""Шаблонные теги SEO: LocalBusiness JSON-LD в <head> витрины (Track B5)."""

from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

from apps.core.seo import blogposting_ld, breadcrumb_ld, entity_ld, faqpage_ld, localbusiness_ld

register = template.Library()


def _tenant_rating():
    """(avg, count) рейтинга текущего тенанта из SHARED BusinessRating, или None.

    Ленивая зависимость на aggregator (импорт в теле функции) — core не тянет его
    на уровне модуля (иначе цикл: aggregator → core.seo). SEO не должен ронять
    <head>, поэтому ошибки гасим."""
    try:
        from django.db import connection

        from apps.aggregator.models import BusinessRating

        r = BusinessRating.objects.filter(
            tenant_schema=connection.schema_name, review_count__gt=0
        ).first()
        return (r.avg_rating, r.review_count) if r else None
    except Exception:  # noqa: BLE001 — SEO-обвязка не должна ломать страницу
        return None


def _stays_seo(tenant):
    """(price_range, image) для отеля/пансиона (H6): диапазон цен «ab …€» и фото
    из активных номеров. Только при активном модуле stays; ошибки гасим (SEO не
    должен ронять <head>)."""
    try:
        from apps.core import modules

        if not modules.is_module_active(tenant, "stays"):
            return "", ""
        from apps.stays.models import StayUnit

        units = list(StayUnit.objects.filter(is_active=True, price_cents__gt=0))
        if not units:
            return "", ""
        prices = sorted(u.price_cents for u in units)
        lo, hi = prices[0] // 100, prices[-1] // 100
        price_range = f"ab {lo} €" if lo == hi else f"{lo}–{hi} €"
        image = next((u.image_url for u in units if u.image_url), "")
        return price_range, image
    except Exception:  # noqa: BLE001 — SEO-обвязка не должна ломать страницу
        return "", ""


@register.simple_tag(takes_context=True)
def house_rules_present(context):
    """True, если у активного модуля stays задана Hausordnung (H6) — для ссылки в
    футере. Ошибки гасим (футер не должен ломаться)."""
    try:
        from django.db import connection

        from apps.core import modules
        from apps.stays.models import StaySettings

        request = context.get("request")
        tenant = getattr(request, "tenant", None) if request is not None else None
        if tenant is None or connection.schema_name == "public":
            return False
        if not modules.is_module_active(tenant, "stays"):
            return False
        return bool((StaySettings.load().house_rules or "").strip())
    except Exception:  # noqa: BLE001
        return False


@register.simple_tag(takes_context=True)
def gift_link_active(context):
    """B1.1: показывать ли ссылку «Gutschein» в футере — модуль gift активен
    И онлайн-оплата настроена. Ошибки гасим (футер не должен ломаться)."""
    try:
        from apps.loyalty.public_views import gift_purchase_active

        request = context.get("request")
        return gift_purchase_active(getattr(request, "tenant", None))
    except Exception:  # noqa: BLE001
        return False


@register.simple_tag
def agb_present():
    """E-2/L5: True, если задан непустой AGB-текст (LegalDoc, любая локаль) —
    ссылка в футере. Ошибки гасим (футер не должен ломаться; на public-схеме
    tenant-таблицы нет)."""
    try:
        from apps.core.models import LegalDoc

        texts = LegalDoc.objects.filter(kind="agb").values_list("text", flat=True)
        return any(t.strip() for t in texts)
    except Exception:  # noqa: BLE001
        return False


@register.simple_tag
def business_rating():
    """(avg, count) рейтинга текущего тенанта или None — для звёзд на витрине (P3)."""
    return _tenant_rating()


@register.simple_tag
def storefront_reviews(limit=6):
    """Опубликованные отзывы текущего тенанта (G8/#6) для блока на витрине.

    Читаем SHARED BusinessReview напрямую по connection.schema_name (public в
    search_path, как business_rating). Имя автора — дружелюбная производная от
    email (приватность; имени у PortalUser нет). Ошибки гасим — секция витрины
    не должна ронять страницу."""
    try:
        from django.db import connection

        from apps.aggregator.models import BusinessReview

        rows = list(
            BusinessReview.objects.filter(
                tenant_schema=connection.schema_name, status=BusinessReview.STATUS_PUBLISHED
            ).select_related("author")[: max(1, min(int(limit), 24))]
        )
    except Exception:  # noqa: BLE001 — блок отзывов не должен ломать витрину
        return []
    out = []
    for r in rows:
        email = getattr(r.author, "email", "") or ""
        local = email.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
        name = local.split(" ")[0].capitalize() if local else "Gast"
        out.append(
            {
                "name": name,
                "rating": r.rating,
                "stars": "★" * r.rating + "☆" * (5 - r.rating),
                # I18N-12: секция отдаёт ПЛОСКИЕ dict'ы, поэтому локализуем здесь —
                # в шаблоне аксессора модели уже нет (демо-перевод, у живых отзывов
                # оверлей пуст → возвращается подлинный текст гостя).
                "comment": r.comment_localized(),
                "created_at": r.created_at,
            }
        )
    return out


def _entity_schema_type(sellable, request) -> str:
    """A9: услуга Kfz-Werkstatt (`site_config.jobs_vehicle`) → schema.org AutoRepair
    вместо дефолтного Service (плановый дефолт UA4-4b §5). Прочие услуги — ''."""
    if getattr(sellable, "kind", "") != "service":
        return ""
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return ""
    from apps.tenants import siteconfig

    if siteconfig.normalize(getattr(tenant, "site_config", {}) or {}).get("jobs_vehicle"):
        return "AutoRepair"
    return ""


# UC4-2: крошки детальной — kind → (метка листинга, url-name). combo без листинга.
_BREADCRUMB_LISTINGS = {
    "product": ("Sortiment", "storefront-products"),
    "service": ("Termine", "storefront-termin"),
    "stay": ("Unterkunft", "storefront-unterkunft"),
    "event": ("Veranstaltungen", "storefront-events"),
}


@register.simple_tag(takes_context=True)
def entity_jsonld(context, sellable, review_summary=None):
    """<script ld+json> продаваемой сущности (протокол `SellableEntity`) с
    AggregateRating из отзывов (UA4-4b) + BreadcrumbList (UC4-2).

    URL — абсолютный из `sellable.detail_url`. Ошибки гасим (SEO не должен ронять
    страницу)."""
    request = context.get("request")
    if sellable is None or request is None:
        return ""
    try:
        detail_url = getattr(sellable, "detail_url", "") or "/"
        payload = entity_ld(
            sellable,
            url=request.build_absolute_uri(detail_url),
            review_summary=review_summary,
            schema_type=_entity_schema_type(sellable, request),
        )
    except Exception:  # noqa: BLE001 — JSON-LD не должен ломать деталь
        return ""
    if not payload:
        return ""
    scripts = [f'<script type="application/ld+json">{payload}</script>']
    try:
        crumbs = [("Start", request.build_absolute_uri("/"))]
        listing = _BREADCRUMB_LISTINGS.get(getattr(sellable, "kind", ""))
        if listing:
            label, urlname = listing
            crumbs.append((label, request.build_absolute_uri(reverse(urlname))))
        crumbs.append((getattr(sellable, "name", "") or "", ""))  # текущая — без item
        bc = breadcrumb_ld(crumbs)
        if bc:
            scripts.append(f'<script type="application/ld+json">{bc}</script>')
    except Exception:  # noqa: BLE001 — крошки не должны ломать деталь
        pass
    return mark_safe("".join(scripts))


@register.simple_tag(takes_context=True)
def blogposting_jsonld(context, post):
    """<script ld+json> BlogPosting записи блога (CM-1). Ошибки гасим."""
    request = context.get("request")
    if post is None or request is None:
        return ""
    try:
        payload = blogposting_ld(
            headline=post.title,
            url=request.build_absolute_uri(),
            date_published=post.published_at,
            image=post.cover_url or "",
            description=post.excerpt or "",
        )
    except Exception:  # noqa: BLE001 — SEO не должен ронять страницу
        return ""
    if not payload:
        return ""
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


@register.simple_tag
def faqpage_jsonld(items):
    """SEO-3: <script> FAQPage JSON-LD из списка [{q,a}] (site_config.faq). Пусто/
    ошибка → '' (SEO-обвязка не должна ронять страницу)."""
    try:
        payload = faqpage_ld(items)
        return (
            mark_safe(f'<script type="application/ld+json">{payload}</script>') if payload else ""
        )
    except Exception:  # noqa: BLE001
        return ""


@register.simple_tag(takes_context=True)
def localbusiness_jsonld(context):
    """Готовый <script type=application/ld+json> с LocalBusiness текущего тенанта.

    Тенант берём из request; вне витрины (нет request/tenant) — пусто. Если у
    бизнеса есть отзывы (G8) — добавляем AggregateRating (звёзды в сниппете).
    """
    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    if tenant is None:
        return ""
    # H6: для отелей/пансионов добавляем priceRange («ab …€») и фото из номеров.
    price_range, image = _stays_seo(tenant)
    payload = localbusiness_ld(
        tenant,
        url=request.build_absolute_uri("/"),
        aggregate_rating=_tenant_rating(),
        price_range=price_range,
        image=image,
    )
    if not payload:
        return ""
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


@register.simple_tag(takes_context=True)
def canonical_link(context):
    """T-8.25: canonical витрины — ОСНОВНОЙ адрес (свой домен, иначе поддомен) + путь.

    Без query: фильтры/сорт/язык не плодят «разные» страницы для поисковика.
    """
    from django.utils.html import escape

    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        return ""
    from apps.tenants.hosts import public_base_url

    href = public_base_url(tenant) + request.path
    return mark_safe(f'<link rel="canonical" href="{escape(href)}">')


@register.simple_tag(takes_context=True)
def city_portal_link(context):
    """T-8.25: взаимная ссылка «Auch im Stadtportal <Stadt>» в подвале витрины.

    Только у бизнеса, который сейчас в каталоге города, и только если портал его города
    есть (демо-бизнес — только на портале с показом демо). Кэш на тенанта — подвал
    рисуется на каждой странице. {"url", "city"} или None.
    """
    from django.core.cache import cache

    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        return None
    from apps.aggregator.visibility import listable

    if not listable(tenant) or not (getattr(tenant, "city", "") or "").strip():
        return None
    key = f"t825:city_portal:{tenant.pk}"
    try:
        cached = cache.get(key)
    except Exception:  # noqa: BLE001
        cached = None
    if cached is None:
        cached = ""
        try:
            from apps.aggregator.models import AggregatorPortal

            portal = AggregatorPortal.objects.filter(
                kind=AggregatorPortal.KIND_CITY, city__iexact=tenant.city.strip(), is_active=True
            ).first()
            if portal is not None and (portal.show_demo or not getattr(tenant, "is_demo", False)):
                cached = portal.host
        except Exception:  # noqa: BLE001 — подвал не падает из-за портала
            cached = ""
        try:
            cache.set(key, cached, 300)
        except Exception:  # noqa: BLE001
            pass
    if not cached:
        return None
    from django.conf import settings

    scheme = "http" if getattr(settings, "DEBUG", False) else "https"
    return {"url": f"{scheme}://{cached}/", "city": tenant.city.strip()}
