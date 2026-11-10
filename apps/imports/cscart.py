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
from datetime import timedelta
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


def gone_paths(html: str, base: str) -> list:
    """Статьи блога CS-Cart (демо-контент «зомби/Nintendo») — переносить нечего, → 410."""
    host = urlsplit(base).netloc
    out = []
    for href in re.findall(r'href="([^"]+)"', html):
        url = urljoin(base, html_lib.unescape(href))
        path = path_of(url)
        if urlsplit(url).netloc == host and path.startswith("blog/") and path not in out:
            out.append(path)
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


def page_title(html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    return html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()[:120] if m else ""


# --- M21.3: главная (баннеры, плитки категорий, меню, логотип, подвал) -----------------


@dataclass
class CsHome:
    banners: list = field(default_factory=list)  # URL картинок слайдера по порядку
    tiles: list = field(default_factory=list)  # [(путь категории, URL картинки)]
    menu: list = field(default_factory=list)  # дерево [{label, url, children}]
    logo_url: str = ""
    footer_text: str = ""


def parse_home(html: str, base: str) -> CsHome:
    home = CsHome()
    for block in re.findall(r'class="ty-banner__image-item[^"]*"[^>]*>(.*?)</div>', html, re.S):
        m = re.search(r'(?:data-src|src)="([^"]+)"', block)
        if m:
            url = urljoin(base, html_lib.unescape(m.group(1)))
            if url not in home.banners:
                home.banners.append(url)
    for href, src in re.findall(
        r'<a\s+href="([^"]+)"[^>]*>\s*<img[^>]+src="([^"]+/images/promo/[^"]+)"', html
    ):
        path = path_of(urljoin(base, html_lib.unescape(href).strip()))
        if path:
            home.tiles.append((path, urljoin(base, html_lib.unescape(src))))
    home.menu = parse_menu(html, base)
    m = re.search(r'ty-logo-container__image[^>]+src="([^"]+)"', html) or re.search(
        r'<img[^>]+src="([^"]+/images/logos/[^"]+\.(?:png|jpe?g|webp|svg))"', html
    )
    home.logo_url = urljoin(base, html_lib.unescape(m.group(1))) if m else ""
    footer = html.find("ty-footer")
    home.footer_text = html_to_text(html[footer:]) if footer >= 0 else ""
    return home


# Подпись ссылки ≤1000 знаков и область ≤500 КБ — линейный разбор чужой страницы.
MENU_REGION_MAX = 500_000
_MENU_TOKEN_RE = re.compile(r"<li\b|</li>|<a\b([^>]*)>(.{0,1000}?)</a>", re.S | re.I)


def parse_menu(html: str, base: str) -> list:
    """Верхнее меню CS-Cart деревом по вложенности ``<li>`` (до 3 уровней).

    Пункт — ссылка с классом ``ty-menu__item-link``/``ty-menu__submenu-link``; подпись —
    дословно (как в оригинале). Без ``href`` (переключатель «Menü») и чужой хост — мимо."""
    host = urlsplit(base).netloc
    start = html.find("ty-menu__items")
    if start < 0:
        return []
    end = html.find("tygh-content", start)
    region = html[start : end if end > 0 else len(html)][:MENU_REGION_MAX]
    roots: list = []
    stack: list = []  # на каждый открытый <li>: узел меню или None
    for m in _MENU_TOKEN_RE.finditer(region):
        token = m.group(0)
        if token.lower().startswith("<li"):
            stack.append(None)
            continue
        if token.lower() == "</li>":
            if stack:
                stack.pop()
            continue
        attrs = m.group(1) or ""
        if not re.search(r'class="[^"]*ty-menu__(?:item|submenu)-link', attrs):
            continue
        href = re.search(r'href="([^"]*)"', attrs)
        label = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        if not href or not href.group(1).strip() or not label:
            continue
        url = urljoin(base, html_lib.unescape(href.group(1)).strip())
        if urlsplit(url).netloc != host:
            continue
        node = {"label": label[:80], "url": url, "children": []}
        parent = next((n for n in reversed(stack[:-1]) if n is not None), None)
        if parent is not None:
            parent["children"].append(node)
        else:
            roots.append(node)
        if stack and stack[-1] is None:
            stack[-1] = node
    return roots


_DAYS = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6}
_HOURS_RE = re.compile(
    r"\b(Mo|Di|Mi|Do|Fr|Sa|So)\b\.?\s*(?:[-–]\s*(Mo|Di|Mi|Do|Fr|Sa|So)\b\.?)?\s*[,:]?\s*"
    r"(\d{1,2})[:.](\d{2})\s*(?:Uhr)?\s*[-–]\s*(\d{1,2})[:.](\d{2})",
    re.I,
)


def parse_hours(text: str) -> dict:
    """«Mo-Fr, 10:00 - 18:00 Uhr Sa 10:00 -14:00 Uhr» → {"0": ["10:00","18:00"], …}."""
    out = {}
    for d1, d2, h1, m1, h2, m2 in _HOURS_RE.findall(text or ""):
        a, b = _DAYS[d1.lower()], _DAYS[(d2 or d1).lower()]
        if b < a:
            continue
        span = [f"{int(h1):02d}:{m1}", f"{int(h2):02d}:{m2}"]
        for day in range(a, b + 1):
            out.setdefault(str(day), span)
    return out


def parse_contacts(text: str) -> dict:
    """Адрес и телефон из подвала («Adresse: …», «Tel.: …»)."""
    out = {}
    flat = re.sub(r"\s+", " ", text or "")
    m = re.search(r"Adresse:\s*(.+?)\s*(?:Tel\b|Telefon\b|Mo\b|$)", flat)
    if m:
        out["address"] = m.group(1).strip(" ,")[:300]
        city = re.search(r"\b\d{5}\s+([A-ZÄÖÜ][\wäöüß .-]+)$", out["address"])
        if city:
            out["city"] = city.group(1).strip()[:100]
    m = re.search(r"Tel(?:efon)?\.?:\s*(\+?[\d][\d /()-]{4,})", flat)
    if m:
        out["phone"] = m.group(1).strip()[:30]
    return out


def dominant_color(image_bytes: bytes) -> str:
    """Фирменный цвет из логотипа: среднее «цветных» пикселей (без белого/серого фона)."""
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        img.thumbnail((200, 200))
        pixels = list(img.getdata())
    picked = [
        (r, g, b) for r, g, b in pixels if max(r, g, b) - min(r, g, b) > 40 and (r + g + b) < 600
    ]
    if len(picked) < 20:
        return ""
    n = len(picked)
    r, g, b = (sum(c[i] for c in picked) // n for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


def strip_dangling(text: str) -> str:
    """Убрать фразы, обрывающиеся двоеточием без продолжения («…wie folgt:»)."""
    paragraphs = []
    for para in (text or "").split("\n\n"):
        lines = [ln for ln in para.split("\n")]
        if lines and lines[-1].rstrip().endswith(":"):
            lines[-1] = re.sub(r"[^.!?\n]*:\s*$", "", lines[-1]).rstrip()
        para = "\n".join(ln for ln in lines if ln.strip())
        if para:
            paragraphs.append(para)
    return "\n\n".join(paragraphs)


# --- Обход сайта ---------------------------------------------------------------


@dataclass
class ScrapedSite:
    base: str
    categories: list = field(default_factory=list)
    products: list = field(default_factory=list)
    pages: dict = field(default_factory=dict)  # «agb»/«about»/«versand»… → HTML тела
    errors: list = field(default_factory=list)
    home: CsHome | None = None  # M21.3: витрина главной (баннеры, плитки, меню, подвал)
    gone_paths: list = field(default_factory=list)  # демо-мусор CS-Cart (статьи блога) → 410


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
    site.gone_paths = gone_paths(sitemap, base)
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

    for key, slug in (
        ("agb", "allgemeine-geschaftsbedienungen/"),
        ("about", "our-team/"),
        ("versand", "versand/"),
        ("impressum", "impressum/"),
        ("zahlung", "versand-de/"),
    ):
        html = get(urljoin(base, slug))
        if html:
            site.pages[key] = page_body(html)
            site.pages[key + "_title"] = page_title(html)
    home = get(base)
    if home is not None:
        site.home = parse_home(home, base)
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


def _save_image(url: str, fetch_image, crop: tuple | None = None) -> dict | None:
    """Скачать → проверить → webp. ``crop`` — (верх, низ) долями высоты: вырезать
    полосу без нарисованных надписей (баннеры CS-Cart несут текст в самой картинке)."""
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
            if crop:
                top, bottom = crop
                img = img.crop((0, int(img.height * top), img.width, int(img.height * bottom)))
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
    if 0 < len(priced) < len(p.variants):  # все без цены — уже отмечено у товара
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
        for path in site.gone_paths:
            _redirect("/" + path + "/", None, stats)
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


_VAT_RE = re.compile(r"\b(DE\s?\d{9})\b")
_MAIL_RE = re.compile(r"(?:E-?Mail|Mail)\s*:\s*([\w.+-]+@[\w-]+(?:\.[\w-]+)+)", re.I)
_RESPONSIBLE_RE = re.compile(r"Verantwortlich[^:\n]*:\s*([^\n]+)")


def parse_impressum(text: str) -> dict:
    """Структурные поля Impressum старого сайта (только то, что видно однозначно)."""
    out = {}
    if m := _VAT_RE.search(text or ""):
        out["vat_id"] = m.group(1).replace(" ", "")
    if m := _MAIL_RE.search(text or ""):
        out["contact_email"] = m.group(1)
    if m := _RESPONSIBLE_RE.search(text or ""):
        out["legal_responsible"] = m.group(1).strip()[:200]
    if re.search(r"\bEinzelunternehmen\b", text or ""):
        out["legal_form"] = "einzel"
    return out


# M21.6: Impressum старого сайта — привести к действующему праву.
# Ссылка на ODR-платформу ЕС: платформа закрыта 20.07.2025 (VO (EU) 2024/3228),
# ссылка на неё больше не обязательна и ведёт в никуда. Убираем целое предложение.
_ODR_SENTENCE_RE = re.compile(
    r"[^\n.]*(?:Online-Streitbeilegung|OS-Plattform)[^\n]*?ec\.europa\.eu/consumers/odr/?\S*?"
    r"\.?(?=\s|$)\s*",
    re.I,
)
_ODR_URL_RE = re.compile(r"\S*ec\.europa\.eu/consumers/odr\S*", re.I)
_OEKO_CODE_RE = re.compile(r"^DE-(?:ÖKO|OEKO)-\d{3}$", re.I)
_EMPTY_OEKO_RE = re.compile(r"^\s*Öko-Kontrollstelle\s*:?\s*$", re.I | re.M)
_MANAGER_RE = re.compile(r"^(\s*)Geschäftsführer(?:in)?\s*:", re.M)


def clean_impressum(
    text: str, *, oeko_code: str = "", renames: tuple[tuple[str, str], ...] = ()
) -> tuple[str, list[str]]:
    """Убрать устаревшее и неверное из Impressum; ничего не выдумывать.

    - ODR-предложение/ссылка — удалить;
    - «Geschäftsführer» у Einzelunternehmen (это обозначение GmbH) → «Inhaber»;
    - пустая строка «Öko-Kontrollstelle» → строка с кодом, если он дан, иначе удалить
      (пустая строка ничего не сообщает) и сказать, что код нужен;
    - ``renames`` — точные замены, напр. имя в порядке «Vorname Nachname».
    """
    notes = []
    out = text or ""
    if _ODR_URL_RE.search(out):
        out = _ODR_SENTENCE_RE.sub("", out)
        out = "\n".join(line for line in out.split("\n") if not _ODR_URL_RE.search(line))
        notes.append("ODR link removed (EU platform closed 20.07.2025)")
    if re.search(r"\bEinzelunternehm", out) and _MANAGER_RE.search(out):
        out = _MANAGER_RE.sub(r"\1Inhaber:", out)
        notes.append("«Geschäftsführer» → «Inhaber» (Einzelunternehmen hat keinen Geschäftsführer)")
    if _EMPTY_OEKO_RE.search(out):
        code = (oeko_code or "").strip().upper().replace("OEKO", "ÖKO")
        if code:
            out = _EMPTY_OEKO_RE.sub(f"Öko-Kontrollstelle: {code}", out)
            notes.append(f"Öko-Kontrollstelle: {code}")
        else:
            out = _EMPTY_OEKO_RE.sub("", out)
            notes.append(
                "empty «Öko-Kontrollstelle» line removed — Bio products need the code "
                "(DE-ÖKO-0xx, Art. 32 VO (EU) 2018/848): rerun with --oeko-code"
            )
    for old, new in renames:
        if old and old in out:
            out = out.replace(old, new)
            notes.append(f"«{old}» → «{new}»")
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out, notes


def impressum_gaps(text: str) -> list[str]:
    """Что § 5 DDG требует и чего не видно в тексте (проверка, не генерация)."""
    t = text or ""
    gaps = []
    if not re.search(r"\b\d{5}\s+\S", t):
        gaps.append("postal address (street, postcode, city)")
    if not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", t):
        gaps.append("e-mail address")
    if not re.search(r"(?:Telefon|Tel\.?|Fon)\s*:?\s*[+\d(]", t, re.I):
        gaps.append("phone (fast contact)")
    if not re.search(r"\bDE\s?\d{9}\b|Steuernummer|§\s*19\s*UStG", t):
        gaps.append("VAT ID (if the business has one)")
    if re.search(r"\b(?:GmbH|UG|AG|KG|OHG|e\.K\.)\b", t) and not re.search(
        r"Registergericht|Amtsgericht|HR[AB]\s*\d", t
    ):
        gaps.append("register court and number")
    return gaps


def apply_legal(tenant, site: ScrapedSite) -> list:
    """Impressum старого сайта → LegalDoc (если своего нет) + пустые поля бизнеса.

    Текст переносится как есть (с юридическим адресом), контакты магазина остаются
    отдельными полями — у бизнеса бывают разные адреса Impressum и лавки."""
    from apps.core.models import LegalDoc

    notes = []
    text = html_to_text(site.pages.get("impressum", ""))
    if not text:
        return notes
    if not LegalDoc.objects.filter(kind="impressum", locale="de").exclude(text="").exists():
        cleaned, fixes = clean_impressum(text)
        LegalDoc.objects.update_or_create(kind="impressum", locale="de", defaults={"text": cleaned})
        notes.append("Impressum imported into LegalDoc — owner must review")
        notes += [f"Impressum: {f}" for f in fixes]
    elif "ec.europa.eu/consumers/odr" in (
        LegalDoc.objects.filter(kind="impressum", locale="de")
        .values_list("text", flat=True)
        .first()
        or ""
    ):
        notes.append("Impressum links the EU ODR platform (closed 20.07.2025) — run fix_impressum")
    fields = []
    for name, value in parse_impressum(text).items():
        if value and not getattr(tenant, name):
            setattr(tenant, name, value)
            fields.append(name)
    if fields:
        tenant.save(update_fields=fields)
        notes.append(f"legal fields set: {', '.join(fields)}")
    return notes


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


# --- M21.3: перенос главной и визуала --------------------------------------------------


@dataclass
class DesignOptions:
    hero_title: str = ""
    hero_button_label: str = ""
    hero_button_url: str = "/sortiment/"
    skip_banners: tuple = ()  # 1-based номера баннеров, которые не переносим
    banner_crop: tuple | None = None  # (верх, низ) долями высоты — полоса без надписей
    replace_menu: bool = False  # перезаписать уже собранное меню (и порядок разделов)


def _category_by_old_path(path: str):
    """Категория, в которую уехал старый адрес (по переадресации импорта)."""
    from apps.catalog.models import Category
    from apps.core.legacy_redirects import match

    rule = match("/" + path.strip("/") + "/", "")
    if rule is None or not rule.target.startswith("/sortiment/"):
        return None
    return Category.objects.filter(slug=rule.target.strip("/").split("/")[-1]).first()


def _old_path_target(path: str):
    """Старый путь → (вид, новая цель): ("category", slug) | ("url", путь) | None.

    Сначала точная переадресация импорта; иначе — по ХВОСТУ пути: в меню CS-Cart
    встречаются битые ссылки (``/klassisch-schwarzertee/kenia-und-nepal/`` без раздела),
    сопоставляем их с единственной перенесённой страницей, путь которой так кончается."""
    from apps.catalog.models import Category
    from apps.core.legacy_redirects import match, normalize_path
    from apps.core.models import LegacyRedirect

    norm = normalize_path(path)
    rule = match(norm, "")
    if rule is None and norm != "/":
        tail = [
            r
            for r in LegacyRedirect.objects.filter(
                origin="import", source_query="", source_path__endswith=norm
            )
            if r.status == LegacyRedirect.STATUS_MOVED
        ]
        rule = tail[0] if len(tail) == 1 else None
    if rule is None or not rule.target:
        return None
    parts = rule.target.strip("/").split("/")
    if len(parts) == 2 and parts[0] == "sortiment":
        if Category.objects.filter(slug=parts[1]).exists():
            return ("category", parts[1])
    return ("url", rule.target)


# Списки CS-Cart в меню → цели витрины (подпись пункта остаётся оригинальной).
DISPATCH_MENU = {
    "products.newest": ("url", "/sortiment/?sort=newest"),
    "products.bestsellers": ("url", "/sortiment/"),
    # гаснет сам, если модуль акций выключен (узел меню без адреса не рисуется)
    "products.on_sale": ("archetype", "promotions"),
}
# Витрина только на немецком: английские подписи CS-Cart по умолчанию → немецкие.
DISPATCH_LABELS_DE = {
    "products.newest": "Neuheiten",
    "products.bestsellers": "Bestseller",
    "products.on_sale": "Angebote",
}
_CSCART_EN_LABELS = {"newest", "new", "new products", "bestsellers", "sales", "sale", "on sale"}


def _menu_nodes(menu: list) -> list:
    """Дерево меню старого сайта → узлы конструктора меню, как в оригинале."""
    out = []
    for item in menu:
        parts = urlsplit(item["url"])
        dispatch = (parse_qs(parts.query).get("dispatch") or [""])[0]
        if dispatch:
            target = DISPATCH_MENU.get(dispatch)
        else:
            target = _old_path_target(parts.path)
        children = _menu_nodes(item.get("children") or [])
        if target is None and not children:
            continue
        ntype, value = target or ("group", "")
        label = item["label"]
        if dispatch in DISPATCH_LABELS_DE and label.lower() in _CSCART_EN_LABELS:
            label = DISPATCH_LABELS_DE[dispatch]
        out.append({"label": label, "type": ntype, "target": value, "children": children})
    return out


def _count_nodes(nodes: list) -> int:
    return sum(1 + _count_nodes(n.get("children") or []) for n in nodes)


def _order_categories_by_menu(nodes: list) -> None:
    """Порядок разделов каталога = порядок меню оригинала (не карты сайта)."""
    from apps.catalog.models import Category

    seen: list = []

    def walk(items):
        for n in items:
            if n["type"] == "category" and n["target"] not in seen:
                seen.append(n["target"])
            walk(n["children"])

    walk(nodes)
    by_slug = {c.slug: c for c in Category.objects.filter(slug__in=seen)}
    # раздел, в который ведёт только его подкатегория (GRÜNER → …/aromatisch), тоже в строй
    for slug in list(seen):
        cat = by_slug.get(slug)
        while cat is not None and cat.parent_id:
            cat = cat.parent
            if cat.slug not in seen:
                seen.insert(seen.index(slug), cat.slug)
                by_slug[cat.slug] = cat
    for pos, slug in enumerate(seen):
        Category.objects.filter(slug=slug).update(sort_order=pos)


def _is_uuid(value) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _de(value) -> str:
    return value.get("de", "") if isinstance(value, dict) else str(value or "")


def cleanup_foreign(tenant, *, apply: bool = False) -> list:
    """M21.5: убрать из перенесённого магазина то, чего нет в оригинале.

    Два источника «чужого» после переезда: демо-контент платформы («Demo-Inhalte
    laden» — категория «Beliebt», образцы товаров, демо-акции) и товары второго
    импортёра («Website importieren», Г1), который берёт с того же сайта только
    JSON-LD — без фасовок, отдельной категорией, то есть дублями. Удаляем ровно их:
    демо — штатным `clear_demo` (по сохранённым id), Г1 — по целям его позиций;
    категория уходит, только если после этого в ней не осталось товаров и подкатегорий.
    По умолчанию — только список (dry-run)."""
    from apps.catalog.models import Category, Product
    from apps.imports.models import SiteImportItem
    from apps.tenants import demo

    notes: list = []
    if demo.has_demo(tenant):
        notes.append("demo content: remove")
        if apply:
            demo.clear_demo(tenant)
    # цель → когда импортёр её последний раз записал (правки владельца позже — не дубль)
    applied: dict = {}
    for target, at in (
        SiteImportItem.objects.filter(target_kind="product")
        .exclude(target_id="")
        .values_list("target_id", "applied_at")
    ):
        if at and (target not in applied or (applied[target] and at > applied[target])):
            applied[target] = at
        else:
            applied.setdefault(target, at)
    ids = [t for t in applied if _is_uuid(t)]  # чужая строка в target_id — не падать
    # товар, который ведёт сам перенос (метка cscart), не трогаем никогда — даже если
    # Г1 позже сопоставил с ним свою позицию
    products = list(
        Product.objects.filter(pk__in=ids)
        .exclude(metadata__has_key="cscart")
        .select_related("category")
    )
    # ревью безопасности: проданный или правленный после импорта товар — уже не «дубль»,
    # его не удаляем, а показываем отдельно (решает владелец)
    from apps.orders.models import OrderItem

    sold = set(OrderItem.objects.filter(product__in=products).values_list("product_id", flat=True))
    doomed = []
    for p in products:
        at = applied.get(str(p.pk))
        if p.pk in sold:
            notes.append(f"kept (has orders): {_de(p.name)}")
        elif at and p.updated_at and p.updated_at > at + timedelta(minutes=1):
            notes.append(f"kept (edited after import): {_de(p.name)}")
        else:
            doomed.append(p)
            notes.append(f"website-import duplicate: {_de(p.name)}")
    products = doomed
    category_ids = {p.category_id for p in products if p.category_id}
    if apply:
        for p in products:
            p.delete()  # soft-delete, как кнопка «Löschen» в кабинете
        for cat in Category.objects.filter(pk__in=category_ids):
            if not Product.objects.filter(category=cat).exists() and not cat.children.exists():
                notes.append(f"empty category removed: {_de(cat.name) or cat.slug}")
                cat.delete()
    return notes


def read_export_codes(text: str) -> set:
    """M21.5: артикулы из выгрузки CS-Cart («Product code» — первая колонка, `;`)."""
    import csv
    import io

    csv.field_size_limit(8 * 1024 * 1024)  # описания товаров в полной выгрузке длинные
    reader = csv.reader(io.StringIO(text.lstrip("\ufeff")), delimiter=";")
    header = [h.strip().lower() for h in next(reader, [])]
    col = header.index("product code") if "product code" in header else 0
    # полная выгрузка несёт «Status»: D (выключен в магазине) на сайте и не был —
    # такие коды «недостающими» не считаем
    status = header.index("status") if "status" in header else None
    out = set()
    for row in reader:
        if len(row) <= col or not row[col].strip():
            continue
        if status is not None and len(row) > status and row[status].strip().upper() == "D":
            continue
        out.add(row[col].strip())
    return out


def missing_codes(codes: set) -> list:
    """Артикулы выгрузки, которых нет ни у товара, ни у фасовки (после импорта)."""
    from apps.catalog.models import Product, ProductVariant

    ours = set(Product.objects.exclude(sku="").values_list("sku", flat=True))
    ours |= set(ProductVariant.objects.exclude(sku="").values_list("sku", flat=True))
    return sorted(codes - ours)


def apply_locales(tenant, locales: list) -> None:
    """Языки витрины бизнеса (первый — основной). Неизвестный код → ValueError."""
    from django.conf import settings

    known = {code for code, _name in settings.LANGUAGES}
    if not locales or any(code not in known for code in locales):
        raise ValueError(f"unknown locale in {locales!r}")
    tenant.enabled_locales = list(dict.fromkeys(locales))
    tenant.default_locale = tenant.enabled_locales[0]
    tenant.save(update_fields=["enabled_locales", "default_locale"])


#: M21.6: страницы старого магазина → свои страницы сайта (ключ ScrapedSite.pages,
#: slug страницы, заголовок по умолчанию). Тексты, которые M21.3 клал блоками на
#: «Über uns», снимаются, если владелец их не менял.
PAGE_IMPORTS = (
    ("versand", "versand", "Versand"),
    ("zahlung", "zahlung", "Zahlungsarten"),
    ("about", "ueber-uns", "Über uns"),
)
_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
_IMG_SRC_RE = re.compile(r"""\bsrc\s*=\s*["']([^"']+)["']""", re.I)
_EMPTY_P_RE = re.compile(r"<p>\s*(?:<br\s*/?>|&nbsp;|\s)*</p>", re.I)


def page_html(html: str, base: str, fetch_image=None) -> str:
    """HTML страницы старого магазина → тело своей страницы: картинки перезалиты к нам
    (чужие ссылки на картинки санитайзер всё равно режет), пустые абзацы убраны."""
    from apps.core.richtext import sanitize_page

    def _img(match):
        tag = match.group(0)
        src = _IMG_SRC_RE.search(tag)
        if not src or fetch_image is None:
            return ""
        ref = _save_image(urljoin(base, html_lib.unescape(src.group(1))), fetch_image)
        if not ref or not ref.get("url"):
            return ""
        return f'<img src="{html_lib.escape(ref["url"])}" alt="">'

    body = _IMG_RE.sub(_img, html or "")
    body = sanitize_page(body)
    body = _EMPTY_P_RE.sub("", body)
    return body.strip()


def apply_pages(site: ScrapedSite, config: dict, *, fetch_image=None) -> list:
    """Создать свои страницы из страниц старого магазина (только если их ещё нет) и
    снять прежние текстовые блоки этих страниц с «Über uns». ``config`` правится на
    месте — его сохраняет вызывающий (apply_design)."""
    from apps.core import content_pages
    from apps.core.models import ContentPage
    from apps.tenants import siteconfig

    notes = []
    blocks = dict(config.get("page_blocks") or {})
    info = list(blocks.get("info") or [])
    for key, slug, fallback in PAGE_IMPORTS:
        raw = site.pages.get(key, "")
        if not raw:
            continue
        title = site.pages.get(key + "_title") or fallback
        if key == "about":
            title = fallback
        legacy_text = strip_dangling(html_to_text(raw))
        before = len(info)
        info = [
            b
            for b in info
            if not (
                isinstance(b, dict)
                and b.get("key") == "text"
                and (b.get("data") or {}).get("body") == legacy_text
            )
        ]
        if len(info) < before:
            notes.append(f"about page: text block «{title}» moved to its own page")
        page = ContentPage.objects.filter(slug=slug).first()
        if page is None:
            body = page_html(raw, site.base, fetch_image)
            if not body:
                continue
            page = ContentPage.objects.create(slug=slug, title=title[:200], body=body)
            notes.append(f"page created: {content_pages.page_url(page)} ({title})")
        if key == "zahlung" and page.is_published:
            # STATIC_ROUTES вели старый адрес на «Über uns» — теперь на свою страницу.
            _redirect("/versand-de/", content_pages.page_url(page), ApplyStats())
    blocks["info"] = info
    config["page_blocks"] = siteconfig.normalize_page_blocks(blocks)
    return notes


def apply_design(
    tenant, site: ScrapedSite, *, options=None, with_images=True, fetch_image=None
) -> list:
    """Главная как на старом сайте: слайдер → плитки направлений → товары → «О нас»;
    меню, логотип, фирменный цвет, контакты/часы, тексты Versand/Zahlung на «О нас».

    Пишет только пустое/невыбранное: повторный прогон не трогает правки владельца
    (слайдер, секции и цвет — только пока слайдер пуст, т. е. до первой настройки)."""
    from apps.catalog.models import Category
    from apps.tenants import siteconfig

    options = options or DesignOptions()
    fetch_image = (fetch_image or _default_fetch_image) if with_images else None
    notes: list = []
    home = site.home or CsHome()
    config = dict(tenant.site_config or {})
    fresh = not siteconfig.normalize_heroes(config.get("heroes"))
    fields: set = set()

    # 1. Слайдер (только пока у бизнеса нет своих слайдов).
    if fresh and fetch_image:
        slides = []
        for i, url in enumerate(home.banners, start=1):
            if i in options.skip_banners:
                continue
            ref = _save_image(url, fetch_image, crop=options.banner_crop)
            if ref is None:
                continue
            slides.append(
                {
                    "image": ref["url"],
                    "title": options.hero_title,
                    "text": "",
                    "button_label": options.hero_button_label,
                    "button_url": options.hero_button_url if options.hero_button_label else "",
                }
            )
        if slides:
            config["heroes"] = siteconfig.normalize_heroes(slides)
            notes.append(f"hero slides: {len(slides)}")

    # 2. Плитки направлений → фото категорий (только у категорий без фото).
    if fetch_image:
        for path, url in home.tiles:
            category = _category_by_old_path(path)
            if category is None or category.images:
                continue
            ref = _save_image(url, fetch_image)
            if ref:
                Category.objects.filter(pk=category.pk).update(images=[ref])
                notes.append(f"category image: {category.slug}")

    # 3. Порядок главной как на старом сайте (только при первом переносе).
    if fresh and config.get("heroes"):
        config["sections"] = siteconfig.normalize_sections(
            [
                {"key": "hero", "enabled": True},
                {
                    # 6 плиток направлений старой главной — 2 полных ряда по 3
                    # (при 4 колонках неполный ряд прячется правилом «полных рядов»).
                    "key": "categories",
                    "enabled": True,
                    "style": "wide",
                    "layout": {"preset": "cols3"},
                },
                {"key": "products", "enabled": True, "source": "featured_first"},
                {"key": "about", "enabled": True},
                # Акций при переезде ещё нет — пустой блок «Keine Angebote» не показываем;
                # владелец включит его вместе с первой акцией.
                {"key": "promotions", "enabled": False},
            ]
        )

    # 4. Меню (только если владелец своё ещё не собирал).
    if options.replace_menu or "menus" not in (tenant.site_config or {}):
        nodes = _menu_nodes(home.menu)
        if nodes:
            nav = siteconfig.normalize(config)["nav"]
            # Повтор с replace_menu меняет только пункты верхнего меню: нижнее меню,
            # стиль и «липкость» шапки — настройки владельца, их не трогаем.
            old = config.get("menus") if isinstance(config.get("menus"), dict) else {}
            top = {**(old.get("top") or {}), "items": nodes}
            bottom = old.get("bottom") or {"enabled": False, "items": []}
            config["menus"] = siteconfig._normalize_menus({"top": top, "bottom": bottom}, nav)
            _order_categories_by_menu(nodes)
            notes.append(f"menu items: {len(nodes)}")
            kept = _count_nodes(config["menus"]["top"]["items"])
            if kept < _count_nodes(nodes):
                notes.append(
                    f"menu shortened: {kept} of {_count_nodes(nodes)} entries kept "
                    "(max 3 levels, 20 items per level)"
                )

    # 5. M21.6: Versand / Zahlungsarten / Über uns — своими страницами (с картинками).
    notes += apply_pages(site, config, fetch_image=fetch_image)

    # 6. Логотип и фирменный цвет (цвет — из логотипа, только при первом переносе).
    if fetch_image and home.logo_url and not tenant.logo_url:
        got = None
        try:
            got = fetch_image(home.logo_url)
        except Exception as exc:  # noqa: BLE001 — сеть: без логотипа
            logger.info("cscart logo skipped: %s", type(exc).__name__)
        ref = _save_image(home.logo_url, lambda _u: got) if got is not None and got.ok else None
        if ref:
            tenant.logo_url = ref["url"]
            fields.add("logo_url")
            color = dominant_color(got.body) if fresh else ""
            if color:
                tenant.primary_color = color
                fields.add("primary_color")
                notes.append(f"brand color from logo: {color}")

    # 7. Контакты и часы работы из подвала (только пустые поля).
    contacts = parse_contacts(home.footer_text)
    for field_name, key in (("address", "address"), ("contact_phone", "phone"), ("city", "city")):
        if contacts.get(key) and not getattr(tenant, field_name):
            setattr(tenant, field_name, contacts[key])
            fields.add(field_name)
    hours = parse_hours(home.footer_text)
    if hours and not tenant.opening_hours_structured:
        tenant.opening_hours_structured = hours
        fields.add("opening_hours_structured")

    # 8. M21.5: вид как у старого магазина — фото целиком (круглые тарелки чая не
    #    срезаются), логотип крупнее, подвал колонками. Только незаданное владельцем.
    sd = dict(config.get("site_defaults") or {})
    if not sd.get("media_places"):
        whole = {"ratio": "1-1", "fit": "contain"}
        sd["media_places"] = {"product": whole, "detail": whole}
        notes.append("photos: square, whole image (cards and product page)")
    if not sd.get("logo_size"):
        sd["logo_size"] = "l"
    # M21.6: текстовые страницы (Über uns, Versand, право) — во всю ширину.
    if not sd.get("text_width"):
        sd["text_width"] = "full"
        notes.append("text pages: full width")
    config["site_defaults"] = sd
    menus = dict(config.get("menus") or {})
    nav = siteconfig.normalize(config)["nav"]
    if not (menus.get("footer") or {}).get("columns"):
        menus["footer"] = {"columns": FOOTER_COLUMNS}
        config["menus"] = siteconfig._normalize_menus(menus, nav)
        notes.append("footer columns like the old shop")
    elif _split_versand_link(menus):
        config["menus"] = siteconfig._normalize_menus(menus, nav)
        notes.append("footer: «Versand & Zahlung» → own pages Versand, Zahlungsarten")

    tenant.site_config = config
    fields.add("site_config")
    tenant.save(update_fields=sorted(fields))
    return notes


#: M21.6: Versand и Zahlungsarten — свои страницы (были одной ссылкой на «Über uns»).
_VERSAND_LINKS = (
    {"label": "Versand", "type": "cpage", "target": "versand"},
    {"label": "Zahlungsarten", "type": "cpage", "target": "zahlung"},
)


def _split_versand_link(menus: dict) -> bool:
    """Ссылку M21.5 «Versand & Zahlung → Über uns» в подвале заменить двумя ссылками
    на свои страницы. Только эту, нетронутую владельцем; правит ``menus`` на месте."""
    footer = dict(menus.get("footer") or {})
    changed = False
    columns = []
    for col in footer.get("columns") or []:
        if not isinstance(col, dict):
            columns.append(col)
            continue
        items = []
        for item in col.get("items") or []:
            if (
                isinstance(item, dict)
                and item.get("label") == "Versand & Zahlung"
                and item.get("type") == "page"
                and item.get("target") == "about"
            ):
                items.extend(dict(link) for link in _VERSAND_LINKS)
                changed = True
            else:
                items.append(item)
        columns.append({**col, "items": items})
    if changed:
        menus["footer"] = {**footer, "columns": columns}
    return changed


#: Подвал старого магазина (Mein Konto · Kundendienst · Über uns; контакты платформа
#: рисует сама колонкой «Kontakt» из данных бизнеса). «Vergleichsliste» у нас нет.
FOOTER_COLUMNS = [
    {"label": "Mein Konto", "items": [{"label": "Anmelden", "type": "page", "target": "account"}]},
    {
        "label": "Kundendienst",
        "items": [
            *_VERSAND_LINKS,
            {"label": "Wunschzettel", "type": "page", "target": "wishlist"},
            {"label": "Kontakt", "type": "page", "target": "contact"},
        ],
    },
    {
        "label": "Über uns",
        "items": [
            {"label": "Über uns", "type": "page", "target": "about"},
            {"label": "Datenschutz", "type": "url", "target": "/datenschutz/"},
            {"label": "AGB", "type": "url", "target": "/agb/"},
            {"label": "Impressum", "type": "url", "target": "/impressum/"},
        ],
    },
]
