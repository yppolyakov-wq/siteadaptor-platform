"""M21.2: перенос магазина с CS-Cart (каталог + фото + старые адреса).

Первый клиент — haanerteeladen.de (план ``docs/m21-cscart-migration-plan-2026-10-31.md``).
Разбор — чистые функции над HTML (тестируются на фикстурах), сеть — только
``safe_fetch`` (SSRF-политика проекта), запись — ``apply_site`` в текущей схеме.

Источник правды о товаре — JSON-LD ``Product`` страницы: название, артикул, фото,
``AggregateOffer.offers[]`` (артикул/цена/наличие/адрес ``?variation_id=N`` каждой
фасовки). Подпись фасовки («100g») CS-Cart рисует радио-кнопкой с тем же адресом
в ``data-ca-product-url`` — так фасовки и сопоставляются; фото фасовки лежит в
блоке ``det_img_…<variation_id>``.

Повторный прогон идемпотентен: товар узнаётся по ``metadata.cscart.url``,
фасовка — по артикулу, категория — по уже созданной переадресации её старого
адреса. Существующие фото и тексты владельца не перезаписываются.
"""

from __future__ import annotations

import html as html_lib
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urljoin, urlsplit

from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)

IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
PAGE_PAUSE_S = 0.4
MAX_LISTING_PAGES = 30
MAX_PRODUCTS = 2000

# Стандартные адреса CS-Cart → страницы витрины (url-name; None = 410 «удалено»).
STATIC_ROUTES = {
    "/allgemeine-geschaftsbedienungen": "storefront-agb",
    "/agb": "storefront-agb",
    "/privacy-policy": "storefront-privacy",
    "/cart": "storefront-cart",
    "/checkout": "storefront-cart",
    "/our-team": "storefront-about",
    "/about-us": "storefront-about",
    "/contact-us": "storefront-message",
    "/gift-certificates": "storefront-gutschein",
    "/wishlist": "storefront-wishlist",
    "/sitemap": "storefront-products",
    "/login": "account-login",
    "/profiles-add": "account-login",
    "/profiles-update": "account-home",
    "/orders": "account-home",
    "/versand": "storefront-about",
    "/versand-de": "storefront-about",
    "/blog": None,
    "/contacts": None,
    "/compare": None,
}
# Списки CS-Cart (`index.php?dispatch=…`) → каталог.
DISPATCH_TO_CATALOG = (
    "products.search",
    "products.newest",
    "products.bestsellers",
    "products.on_sale",
    "product_features.view_all",
)


# --- Разбор ------------------------------------------------------------------


@dataclass
class CsCategory:
    path: str  # «schwarzertee/klassisch-schwarzertee/assam» — без слэшей по краям
    name: str

    @property
    def parent_path(self) -> str:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""

    @property
    def segment(self) -> str:
        return self.path.rsplit("/", 1)[-1]


@dataclass
class CsVariant:
    sku: str
    price: Decimal
    url: str
    label: str = ""
    grams: Decimal | None = None
    in_stock: bool = True
    image_url: str = ""


@dataclass
class CsProduct:
    url: str
    path: str
    name: str
    sku: str
    description_html: str = ""
    image_urls: list = field(default_factory=list)
    variants: list = field(default_factory=list)
    product_id: str = ""
    variation_ids: list = field(default_factory=list)

    @property
    def category_path(self) -> str:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""

    @property
    def segment(self) -> str:
        return self.path.rsplit("/", 1)[-1]


def path_of(url: str) -> str:
    return urlsplit(url).path.strip("/")


def nice_name(raw: str) -> str:
    """«KLASSISCH SCHWARZERTEE» → «Klassisch Schwarzertee»; смешанный регистр не трогаем."""
    text = html_lib.unescape(raw or "").strip()
    letters = [c for c in text if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return text.title()
    return text


_GRAMS_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(kg|g)\s*$", re.I)


def grams_of(label: str) -> Decimal | None:
    m = _GRAMS_RE.match(label or "")
    if not m:
        return None
    value = Decimal(m.group(1).replace(",", "."))
    return value * 1000 if m.group(2).lower() == "kg" else value


_NAME_GRAMS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g)\b", re.I)


def name_grams(name: str) -> Decimal | None:
    """Вес из названия фасованного товара: «Kamillenblüten ganz, 100g» → 100."""
    m = _NAME_GRAMS_RE.search(name or "")
    return grams_of(f"{m.group(1)}{m.group(2)}") if m else None


def nice_label(label: str) -> str:
    m = _GRAMS_RE.match(label or "")
    if not m:
        return (label or "").strip()
    return f"{m.group(1)} {m.group(2).lower()}"


def parse_sitemap(html: str, base: str) -> list[CsCategory]:
    """Дерево категорий со страницы ``/sitemap/`` (блок ``ty-sitemap__tree``)."""
    out, seen = [], set()
    host = urlsplit(base).netloc
    for href, text in re.findall(
        r'ty-sitemap__tree-list-item[^>]*>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', html, re.S
    ):
        url = urljoin(base, html_lib.unescape(href))
        if urlsplit(url).netloc != host:
            continue
        path = path_of(url)
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(CsCategory(path=path, name=nice_name(re.sub(r"<[^>]+>", "", text))))
    return out


def parse_listing(html: str, base: str, known_categories: set) -> tuple[set, bool]:
    """Адреса товаров на странице категории + есть ли следующая страница.

    Товар — ссылка вида ``/<известная категория>/<слаг>/``, сама не категория."""
    host = urlsplit(base).netloc
    found = set()
    for href in re.findall(r'href="([^"]+)"', html):
        url = urljoin(base, html_lib.unescape(href))
        parts = urlsplit(url)
        if parts.netloc != host or parts.query or not parts.path.endswith("/"):
            continue
        path = path_of(url)
        if "/" not in path or path in known_categories:
            continue
        if path.rsplit("/", 1)[0] in known_categories:
            found.add(f"{parts.scheme}://{host}/{path}/")
    return found, "ty-pagination__next" in html


def _json_ld_product(html: str) -> dict | None:
    for raw in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", html, re.S):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and str(node.get("@type", "")).endswith("Product"):
                return node
    return None


def _price(value) -> Decimal | None:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return price if Decimal("0") <= price < Decimal("100000") else None


def _variation_id(url: str) -> str:
    return (parse_qs(urlsplit(url).query).get("variation_id") or [""])[0]


def _inner_html(html: str, marker: str) -> str:
    """Внутренний HTML первого ``<div>``, в открывающем теге которого есть marker."""
    start = html.find(marker)
    if start < 0:
        return ""
    open_end = html.find(">", start)
    if open_end < 0:
        return ""
    depth, pos = 1, open_end + 1
    for m in re.finditer(r"<(/?)div\b[^>]*>", html[pos:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[pos : pos + m.start()].strip()
    return ""


def _detailed_url(base: str, fragment: str) -> str:
    """Любая миниатюра CS-Cart → оригинал ``/images/detailed/<n>/<файл>``."""
    m = re.search(r"detailed/(\d+)/([^\"'\s)?]+)", fragment)
    return urljoin(base, f"/images/detailed/{m.group(1)}/{m.group(2)}") if m else ""


def parse_product(html: str, url: str) -> CsProduct | None:
    node = _json_ld_product(html)
    if not node or not node.get("name"):
        return None
    name = nice_name(str(node["name"]))
    product = CsProduct(
        url=url, path=path_of(url), name=name[:200], sku=str(node.get("sku") or "")[:100]
    )
    product.description_html = _inner_html(html, "content-description")
    images = node.get("image") or []
    for img in images if isinstance(images, list) else [images]:
        if isinstance(img, str) and img.startswith(("http://", "https://")):
            full = _detailed_url(url, img) or img
            if full not in product.image_urls:
                product.image_urls.append(full)
    m = re.search(r"product_id=(\d+)", html)
    product.product_id = m.group(1) if m else ""

    # Подписи фасовок: радио с адресом варианта.
    labels = {}
    for inp, label in re.findall(
        r"(<input[^>]+data-ca-product-url=\"[^\"]+\"[^>]*>)\s*<label[^>]*>(.*?)</label>",
        html,
        re.S,
    ):
        href = html_lib.unescape(re.search(r'data-ca-product-url="([^"]+)"', inp).group(1))
        labels[_variation_id(href)] = nice_label(re.sub(r"<[^>]+>", "", label))
    # Фото фасовок: блок det_img_…<variation_id>.
    variant_images = {}
    for m in re.finditer(r'id="det_img_(\d+)"', html):
        variant_images[m.group(1)] = _detailed_url(url, html[m.end() : m.end() + 800])

    offers = node.get("offers") or []
    offers = offers if isinstance(offers, list) else [offers]
    flat = []
    for offer in offers:
        if isinstance(offer, dict) and isinstance(offer.get("offers"), list):
            flat.extend(o for o in offer["offers"] if isinstance(o, dict))
        elif isinstance(offer, dict):
            flat.append(offer)
    vids_all = {_variation_id(html_lib.unescape(str(o.get("url") or ""))) for o in flat} - {""}
    for offer in flat:
        price = _price(offer.get("price", offer.get("lowPrice")))
        if price is None:
            continue
        o_url = html_lib.unescape(str(offer.get("url") or url))
        vid = _variation_id(o_url)
        label = labels.get(vid, "")
        if not label and vid and vid == product.product_id:
            # Базовый оффер CS-Cart несёт ?variation_id=<id товара>, а его радио — адрес
            # без параметра: подпись базовой фасовки лежит под ключом «».
            label = labels.get("", "")
        image = ""
        if vid:
            product.variation_ids.append(vid)
            image = _variant_image(variant_images, vid, vids_all)
        product.variants.append(
            CsVariant(
                sku=str(offer.get("sku") or "")[:100],
                price=price,
                url=o_url,
                label=label,
                grams=grams_of(label),
                in_stock="OutOfStock" not in str(offer.get("availability") or ""),
                image_url=image,
            )
        )
    if not product.variants:
        return None
    product.variants.sort(key=lambda v: (v.grams is None, v.grams or 0, v.price))
    return product


def _variant_image(images: dict, vid: str, vids: set) -> str:
    """Фото блока ``det_img_<префикс><variation_id>``: ключ относим к САМОМУ ДЛИННОМУ id,
    которым он кончается — иначе id 6 «забирал» бы фото варианта 806."""
    for key, url in images.items():
        owners = [v for v in vids if key.endswith(v)]
        if url and owners and max(owners, key=len) == vid:
            return url
    return ""


def html_to_text(html: str) -> str:
    """HTML правовой/текстовой страницы → плоский текст с абзацами."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def page_body(html: str) -> str:
    return _inner_html(html, "ty-mainbox-body")


# --- Обход сайта ---------------------------------------------------------------


@dataclass
class ScrapedSite:
    base: str
    categories: list = field(default_factory=list)
    products: list = field(default_factory=list)
    pages: dict = field(default_factory=dict)  # «agb»/«about» → HTML тела
    errors: list = field(default_factory=list)


def _default_fetch(url: str, *, accept=("text/html",), max_bytes=4 * 1024 * 1024):
    from apps.core.ssrf import safe_fetch

    return safe_fetch(url, accept=accept, max_bytes=max_bytes)


def scrape(base: str, *, fetch=None, pause: float = PAGE_PAUSE_S, log=None) -> ScrapedSite:
    """Обойти магазин: /sitemap/ → категории → товары → тексты страниц."""
    fetch = fetch or _default_fetch
    log = log or (lambda msg: None)
    base = base.rstrip("/") + "/"
    site = ScrapedSite(base=base)

    def get(url):
        try:
            got = fetch(url)
        except Exception as exc:  # noqa: BLE001 — сеть/SSRF: адрес пропускаем, обход идёт
            site.errors.append(f"{url}: {type(exc).__name__}")
            return None
        finally:
            if pause:
                time.sleep(pause)
        if not got.ok:
            site.errors.append(f"{url}: HTTP {got.status}")
            return None
        return got.text()

    sitemap = get(urljoin(base, "sitemap/"))
    if sitemap is None:
        return site
    site.categories = parse_sitemap(sitemap, base)
    known = {c.path for c in site.categories}
    log(f"categories: {len(site.categories)}")

    product_urls: set = set()
    for cat in site.categories:
        for page in range(1, MAX_LISTING_PAGES + 1):
            html = get(urljoin(base, f"{cat.path}/?items_per_page=96&page={page}"))
            if html is None:
                break
            found, has_next = parse_listing(html, base, known)
            new = found - product_urls
            product_urls |= found
            if not has_next or not new:
                break
    log(f"product pages: {len(product_urls)}")

    if len(product_urls) > MAX_PRODUCTS:
        site.errors.append(f"more than {MAX_PRODUCTS} products — only the first were read")
    for url in sorted(product_urls)[:MAX_PRODUCTS]:
        html = get(url)
        if html is None:
            continue
        product = parse_product(html, url)
        if product is None:
            site.errors.append(f"{url}: no product data")
            continue
        site.products.append(product)

    for key, slug in (("agb", "allgemeine-geschaftsbedienungen/"), ("about", "our-team/")):
        html = get(urljoin(base, slug))
        if html:
            site.pages[key] = page_body(html)
    return site


# --- Запись в схему бизнеса -------------------------------------------------------


@dataclass
class ApplyStats:
    categories_created: int = 0
    products_created: int = 0
    products_updated: int = 0
    variants: int = 0
    images: int = 0
    redirects: int = 0
    notes: list = field(default_factory=list)


def _url_name(name: str) -> str | None:
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def _redirect(source: str, target: str | None, stats: ApplyStats) -> None:
    from apps.core import legacy_redirects
    from apps.core.models import LegacyRedirect

    status = LegacyRedirect.STATUS_GONE if target is None else LegacyRedirect.STATUS_MOVED
    try:
        path, query = legacy_redirects.parse_source(source)
    except legacy_redirects.RedirectError as exc:
        stats.notes.append(f"redirect {source}: {exc}")
        return
    if LegacyRedirect.objects.filter(
        source_path=path, source_query=query, origin="manual"
    ).exists():
        return  # правило, заданное владельцем вручную, важнее импорта
    try:
        legacy_redirects.upsert(source, target or "", status=status, origin="import")
    except legacy_redirects.RedirectError as exc:
        stats.notes.append(f"redirect {source}: {exc}")
        return
    stats.redirects += 1


def _category_for(cat: CsCategory, by_path: dict, stats: ApplyStats):
    """Категория по старому адресу: уже перенесённая (по переадресации) или новая."""
    from apps.catalog.models import Category
    from apps.catalog.slugs import unique_slug
    from apps.core.legacy_redirects import normalize_path
    from apps.core.models import LegacyRedirect

    rule = LegacyRedirect.objects.filter(
        source_path=normalize_path(cat.path), source_query="", origin="import"
    ).first()
    if rule and rule.target.startswith("/sortiment/"):
        slug = rule.target.strip("/").split("/")[-1]
        found = Category.objects.filter(slug=slug).first()
        if found is not None:
            return found
    parent = by_path.get(cat.parent_path)
    base = cat.segment
    if Category.objects.filter(slug=base).exists() and parent is not None:
        base = f"{parent.slug}-{cat.segment}"
    category = Category.objects.create(
        name={"de": cat.name},
        slug=unique_slug(Category, base),
        parent=parent,
        sort_order=len(by_path),
    )
    stats.categories_created += 1
    return category


def _save_image(url: str, fetch_image) -> dict | None:
    from PIL import Image

    from apps.catalog.images import save_product_image

    try:
        got = fetch_image(url)
        if not got.ok:
            return None
        with Image.open(io.BytesIO(got.body)) as img:
            if img.width * img.height > 25_000_000:
                return None
            img.verify()
        with Image.open(io.BytesIO(got.body)) as img:
            img = img.convert("RGB")
            img.thumbnail((2000, 2000))
            buf = io.BytesIO()
            img.save(buf, "WEBP", quality=85)
        return save_product_image(ContentFile(buf.getvalue(), name="import.webp"), is_primary=True)
    except Exception as exc:  # noqa: BLE001 — сеть/битое фото: позиция без фото
        logger.info("cscart image skipped: %s", type(exc).__name__)
        return None


def _default_fetch_image(url):
    return _default_fetch(url, accept=IMAGE_TYPES, max_bytes=8 * 1024 * 1024)


def _product_slug_base(p: CsProduct) -> str:
    """Слаг из старого адреса; при коллизии (один слаг в двух категориях CS-Cart) —
    с сегментом категории («chai-rooibos»), а не безликое «chai-2»."""
    from apps.catalog.models import Product

    if Product.objects.filter(slug=p.segment).exists() and p.category_path:
        return f"{p.segment}-{p.category_path.rsplit('/', 1)[-1]}"
    return p.segment


def _save_product(p: CsProduct, category, vat: Decimal, stats: ApplyStats):
    from apps.catalog.models import Product
    from apps.catalog.slugs import unique_slug
    from apps.core.richtext import sanitize

    base_variant = p.variants[0]
    grams = base_variant.grams or name_grams(p.name)
    product = Product.objects.filter(metadata__cscart__url=p.url).first()
    # Повторный прогон синхронизирует только цену и вес (план §7 п.8 — «перед
    # переключением DNS»); категория, НДС, склад и видимость — уже владельца.
    fields = {"unit": "g" if grams else "", "content_amount": grams}
    no_price = base_variant.price <= 0
    if not no_price:
        fields["base_price"] = base_variant.price
    if product is None:
        product = Product(
            name={"de": p.name},
            description={"de": sanitize(p.description_html)},
            slug=unique_slug(Product, _product_slug_base(p)),
            metadata={"cscart": {"url": p.url, "product_id": p.product_id, "path": p.path}},
            sku=p.sku or base_variant.sku,
            category=category,
            vat_rate=vat,
            **{"base_price": base_variant.price, **fields},
        )
        if len(p.variants) == 1 and not base_variant.in_stock:
            product.stock_quantity = 0
        if no_price:
            # CS-Cart: «Kontaktieren Sie uns für den Preis». «0,00 €» на витрине — это
            # неверная цена (PAngV) → товар скрыт до цены от владельца.
            product.primary_action = "request"
            product.is_active = False
        product.save()
        stats.products_created += 1
    else:
        for key, value in fields.items():
            setattr(product, key, value)
        product.save()
        stats.products_updated += 1
    if no_price:
        stats.notes.append(f"no price on old site, hidden until priced: {p.sku} {p.name}")
    return product


def _save_variants(product, p: CsProduct, fetch_image, stats: ApplyStats) -> None:
    from apps.catalog.models import ProductVariant

    priced = [v for v in p.variants if v.price > 0]
    if len(priced) < len(p.variants):
        stats.notes.append(f"variants without price skipped: {p.sku} {p.name}")
    if len(priced) < 2:
        return
    for i, v in enumerate(priced):
        # Без артикула ключ — артикул товара + номер фасовки, иначе фасовки слились бы в одну.
        sku = v.sku or f"{p.sku or product.pk}.v{i}"
        variant = ProductVariant.objects.filter(product=product, sku=sku).first()
        if variant is None:
            # Новая фасовка: всё из старого магазина. Повторный прогон обновляет только
            # цену и вес — склад, видимость и подпись остаются за владельцем.
            variant = ProductVariant(
                product=product,
                sku=sku,
                label=v.label or sku,
                stock_quantity=None if v.in_stock else 0,
                sort_order=i,
                is_active=True,
            )
        variant.price = v.price
        variant.content_amount = v.grams
        if fetch_image and v.image_url and not variant.images:
            ref = _save_image(v.image_url, fetch_image)
            if ref:
                variant.images = [ref]
                stats.images += 1
        variant.save()
        stats.variants += 1


def apply_site(
    site: ScrapedSite,
    *,
    vat: Decimal = Decimal("7.00"),
    with_images: bool = True,
    fetch_image=None,
    log=None,
) -> ApplyStats:
    """Записать обход в текущую схему (вызывать внутри ``schema_context``)."""
    from apps.core.models import LegalDoc

    log = log or (lambda msg: None)
    fetch_image = (fetch_image or _default_fetch_image) if with_images else None
    stats = ApplyStats()

    by_path: dict = {}
    with transaction.atomic():
        for cat in sorted(site.categories, key=lambda c: c.path.count("/")):
            category = _category_for(cat, by_path, stats)
            by_path[cat.path] = category
            _redirect("/" + cat.path + "/", f"/sortiment/{category.slug}/", stats)

    for p in site.products:
        with transaction.atomic():
            product = _save_product(p, by_path.get(p.category_path), vat, stats)
            _save_variants(product, p, fetch_image, stats)
            target = product.get_absolute_url()
            _redirect("/" + p.path + "/", target, stats)
            if p.product_id:
                _redirect(
                    f"/index.php?dispatch=products.view&product_id={p.product_id}", target, stats
                )
                for vid in p.variation_ids:
                    _redirect(f"/index.php?dispatch=products.view&product_id={vid}", target, stats)
        if fetch_image and not product.images and p.image_urls:
            ref = _save_image(p.image_urls[0], fetch_image)
            if ref:
                product.images = [ref]
                product.save(update_fields=["images", "updated_at"])
                stats.images += 1
    log(f"products: {stats.products_created} new, {stats.products_updated} updated")

    with transaction.atomic():
        for source, name in STATIC_ROUTES.items():
            _redirect(source + "/", None if name is None else _url_name(name) or "/", stats)
        catalog = _url_name("storefront-products") or "/"
        for dispatch in DISPATCH_TO_CATALOG:
            _redirect(f"/index.php?dispatch={dispatch}", catalog, stats)
        _redirect("/index.php", "/", stats)

    agb = html_to_text(site.pages.get("agb", ""))
    if agb and not LegalDoc.objects.filter(kind="agb", locale="de").exclude(text="").exists():
        LegalDoc.objects.update_or_create(kind="agb", locale="de", defaults={"text": agb})
        stats.notes.append(
            "AGB imported into LegalDoc — owner must review (payment, shipping, address)."
        )
    about = html_to_text(site.pages.get("about", ""))
    if about:
        stats.notes.append("About text found — copied to the profile if it was empty.")
    return stats


def apply_about(tenant, site: ScrapedSite) -> bool:
    """«Über uns» в ``site_config.about_text``, только если у бизнеса пусто."""
    about = html_to_text(site.pages.get("about", ""))
    config = dict(tenant.site_config or {})
    if not about or (config.get("about_text") or "").strip():
        return False
    config["about_text"] = about[:5000]
    tenant.site_config = config
    tenant.save(update_fields=["site_config"])
    return True
