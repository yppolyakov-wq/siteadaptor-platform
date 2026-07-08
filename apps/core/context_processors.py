"""SEO-1: context processor витрины — резолвит title/description из движка
мета-заготовок (`seo_meta`) для главной и листингов.

Кладёт в контекст `seo_meta` = {title, description}; `_base.html` использует их как
ДЕФОЛТ блоков title/meta_description (страницы с явным override блока — не трогаются;
их миграция на движок — SEO-1b с кабинетом SEO-2). Per-сущность деталь — позже.
"""

from django.utils.translation import gettext_lazy as _

from apps.core import seo_meta

# url_name → (page_type, heading). Только витринные страницы (storefront-*).
_PAGE_MAP = {
    "storefront-home": ("home", ""),
    "storefront-products": ("listing", _("Sortiment")),
    "storefront-aktionen": ("listing", _("Aktionen")),
    "storefront-termin": ("listing", _("Termine")),
    "storefront-unterkunft": ("listing", _("Zimmer")),
    "storefront-events": ("listing", _("Veranstaltungen")),
    "storefront-combos": ("listing", _("Angebote")),
    "storefront-gutschein": ("listing", _("Gutscheine")),
}


def seo(request):
    """Отдаёт `seo_meta` для витринных главной/листингов. Не витрина / нет tenant /
    url_name не в карте → {} (шаблон падает на дефолт tenant.name)."""
    tenant = getattr(request, "tenant", None)
    match = getattr(request, "resolver_match", None)
    if tenant is None or match is None:
        return {}
    entry = _PAGE_MAP.get(getattr(match, "url_name", None))
    if not entry:
        return {}
    page_type, heading = entry
    ctx = {"heading": str(heading)} if heading else None
    return {"seo_meta": seo_meta.resolve(tenant, page_type, ctx)}
