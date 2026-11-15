"""FB-29.8b: товары-примеры для предпросмотра дизайна на пустом магазине.

Владелец выбирает дизайн раньше, чем заводит товары — без карточек предпросмотр пуст
и дизайн не оценить. В предпросмотре дизайна (`?preview=1` вместе с `look` или
`bundle`) пустой список товаров показывает примеры: объекты `Product` в памяти, в базу
ничего не пишется, на живом сайте их нет.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

#: (название, цена, ключ демо-фото)
_SAMPLES = (
    ("Beispielprodukt 1", "9.90", "tea"),
    ("Beispielprodukt 2", "14.50", "coffee"),
    ("Beispielprodukt 3", "24.00", "chocolate"),
    ("Beispielprodukt 4", "6.80", "bakery"),
)


def wanted(request) -> bool:
    """Идёт ли предпросмотр ДИЗАЙНА (а не обычное превью страницы)."""
    get = getattr(request, "GET", None) or {}
    return get.get("preview") == "1" and bool(get.get("look") or get.get("bundle"))


def products() -> list:
    """Четыре товара-примера: несохранённые `Product`, ссылки никуда не ведут."""
    from apps.catalog.models import Product
    from apps.tenants.demo_images import demo_image_url

    out = []
    for i, (name, price, keyword) in enumerate(_SAMPLES):
        item = Product(
            pk=uuid.UUID(int=i + 1),
            name={"de": name, "en": name},
            base_price=Decimal(price),
            images=[
                {
                    "id": f"sample-{i}",
                    "url": demo_image_url(keyword, w=800, h=800, lock=700 + i),
                    "alt": name,
                    "is_primary": True,
                }
            ],
        )
        item.is_sample = True
        item.get_absolute_url = lambda: "#"
        out.append(item)
    return out


def for_empty_shop(request) -> list:
    """Примеры — только в предпросмотре дизайна и только пока своих товаров нет."""
    if not wanted(request):
        return []
    from apps.catalog.models import Product

    if Product.objects.filter(is_active=True).exists():
        return []
    return products()


# ───────── примеры услуг, номеров и событий (тот же принцип: в памяти, без записи) ─────────


def _photo(keyword: str, lock: int, alt: str) -> list:
    from apps.tenants.demo_images import demo_image_url

    return [
        {
            "id": f"sample-{lock}",
            "url": demo_image_url(keyword, w=800, h=600, lock=lock),
            "alt": alt,
            "is_primary": True,
        }
    ]


def services() -> list:
    from apps.booking.models import Service

    out = []
    for i, (name, minutes, cents) in enumerate(
        (
            ("Beispielleistung 1", 30, 2500),
            ("Beispielleistung 2", 60, 4900),
            ("Beispielleistung 3", 90, 7900),
        )
    ):
        item = Service(
            pk=uuid.UUID(int=101 + i), name=name, duration_minutes=minutes, price_cents=cents
        )
        item.is_sample = True
        out.append(item)
    return out


def stays() -> list:
    from apps.stays.models import StayUnit

    out = []
    for i, (name, cents, keyword) in enumerate(
        (
            ("Beispielzimmer 1", 8900, "bedroom"),
            ("Beispielzimmer 2", 11900, "hotel"),
            ("Beispielzimmer 3", 14900, "bedroom"),
        )
    ):
        item = StayUnit(pk=uuid.UUID(int=201 + i), name=name, price_cents=cents)
        item.images = _photo(keyword, 720 + i, name)
        item.is_sample = True
        out.append(item)
    return out


def events() -> list:
    import datetime

    from django.utils import timezone

    from apps.events.models import Event

    out = []
    for i, (title, days, cents) in enumerate(
        (
            ("Beispielveranstaltung 1", 14, 2900),
            ("Beispielveranstaltung 2", 28, 4500),
            ("Beispielveranstaltung 3", 42, 0),
        )
    ):
        item = Event(
            pk=uuid.UUID(int=301 + i),
            title=title,
            starts_at=timezone.now() + datetime.timedelta(days=days),
            status=Event.STATUS_PUBLISHED,
            price_cents=cents,
        )
        item.is_sample = True
        out.append(item)
    return out


_MAKERS = {
    "services": ("apps.booking.models.Service", services),
    "stay_rooms": ("apps.stays.models.StayUnit", stays),
    "events": ("apps.events.models.Event", events),
}


def for_empty_section(request, key: str) -> list:
    """Примеры для пустой секции главной `key` — только в предпросмотре дизайна и только
    пока своих записей этого вида нет. Сбой при сборке примера — без примеров."""
    import importlib
    import logging

    if key not in _MAKERS or not wanted(request):
        return []
    path, make = _MAKERS[key]
    module, _dot, name = path.rpartition(".")
    try:
        model = getattr(importlib.import_module(module), name)
        if model.objects.exists():
            return []
        return make()
    except Exception:  # noqa: BLE001 — предпросмотр важнее примеров
        logging.getLogger(__name__).exception("design samples: %s failed", key)
        return []


#: T4: страница-список → (ключ примеров, имя переменной, которую ждёт частичный секции).
_LISTINGS = {
    "services": "services_preview",
    "stay_rooms": "stay_rooms",
    "events": "events_preview",
}


def listing_context(request, key: str) -> dict:
    """Контекст примеров для пустой страницы-списка (`{}` — примеров нет): тот же
    частичный секции главной рисует их с пометкой и без ссылок."""
    items = for_empty_section(request, key)
    if not items:
        return {}
    return {_LISTINGS[key]: items, "sample_sections": {key}}


# ───────── FB-30.10: полный набор примеров для главной ─────────


def wanted_owner(request) -> bool:
    """Предпросмотр дизайна И вход в кабинет этого бизнеса. `?preview=1&look=` открыт
    любому посетителю опубликованного сайта — отзывы-примеры (выдуманные оценки) показываем
    только владельцу, иначе на витрине стояли бы ненастоящие отзывы (UWG)."""
    if not wanted(request):
        return False
    from apps.core import roles

    try:
        return bool(roles.has_cabinet_access(getattr(request, "user", None)))
    except Exception:  # noqa: BLE001 — сомнение = не владелец
        import logging

        logging.getLogger(__name__).warning("design samples: owner check failed", exc_info=True)
        return False


def _wide_photo(keyword: str, lock: int) -> str:
    from apps.tenants.demo_images import demo_image_url

    return demo_image_url(keyword, w=1200, h=800, lock=lock)


def _faq() -> list[dict]:
    from django.utils.translation import gettext as _

    return [
        {"q": _("Beispielfrage: Wie lange dauert die Lieferung?"), "a": _("Beispielantwort.")},
        {"q": _("Beispielfrage: Kann ich vor Ort abholen?"), "a": _("Beispielantwort.")},
        {"q": _("Beispielfrage: Welche Zahlungsarten gibt es?"), "a": _("Beispielantwort.")},
    ]


def _team() -> list[dict]:
    from django.utils.translation import gettext as _

    return [
        {
            "name": _("Beispielname %(n)s") % {"n": i + 1},
            "role": _("Beispielrolle"),
            "photo": _wide_photo(key, 720 + i),
        }  # fmt: skip
        for i, key in enumerate(("barista-woman", "baker-man", "shop-assistant"))
    ]


def _gallery() -> list[dict]:
    keys = ("cafe-interior", "tea", "coffee", "market-stall", "bakery", "chocolate")
    return [{"url": _wide_photo(key, 740 + i), "alt": {}} for i, key in enumerate(keys)]


def _testimonials() -> list[dict]:
    from django.utils.translation import gettext as _

    return [
        {"name": _("Beispielkundin"), "text": _("Beispiel für eine Kundenstimme."), "stars": 5},
        {"name": _("Beispielkunde"), "text": _("Beispiel für eine Kundenstimme."), "stars": 5},
    ]


def promotions() -> list[dict]:
    """Акции-примеры — простые словари для своего партиала (карточка настоящей акции
    тянет ценовой слой и связи; пример — только вид)."""
    from django.utils.translation import gettext as _

    return [
        {
            "title": _("Beispielaktion %(n)s") % {"n": i + 1},
            "old": old,
            "new": new,
            "image": _wide_photo(key, 760 + i),
        }  # fmt: skip
        for i, (key, old, new) in enumerate(
            (("tea", "12,90", "9,90"), ("coffee", "8,50", "6,50"), ("chocolate", "4,20", "2,90"))
        )
    ]


def site_with_samples(site: dict, request) -> tuple[dict, set]:
    """Копия `site`, где ПУСТЫЕ содержательные секции главной заполнены примерами, и
    ключи заполненных. Только в предпросмотре дизайна; своё содержимое не заменяется;
    исходный словарь не меняется. Баннер: фото и текст-пример, если у главной нет ни фото,
    ни выбранных баннеров (иначе «Vollbild» и фото-виды падали в «Akzent»)."""
    # Ревью FB-30.10: `?preview=1&look=` открыт любому посетителю — содержимое-примеры
    # (вопросы, команда, текст баннера, отзывы, акции с ценой «statt») показываем только
    # владельцу, иначе посторонний видел бы на витрине выдуманные сведения о бизнесе.
    if not wanted_owner(request) or not isinstance(site, dict):
        return site, set()
    from django.utils.translation import gettext as _

    out, keys = dict(site), set()
    fillers = {"faq": _faq, "gallery": _gallery, "team": _team, "testimonials": _testimonials}
    for key, make in fillers.items():
        if key == "gallery" and out.get("gallery_video"):
            continue
        if not out.get(key):
            out[key] = make()
            keys.add(key)
    hero = out.get("hero_banners") if isinstance(out.get("hero_banners"), dict) else {}
    if not hero.get("pick") and not out.get("hero_image") and not out.get("heroes"):
        out["hero_image"] = _wide_photo("cafe-interior", 790)
        if not out.get("hero_text"):
            out["hero_text"] = _("Beispieltext: ein Satz über Ihr Geschäft.")
        keys.add("hero")
    return out, keys


# ───────── FB-30.10, часть 2: страница товара-примера и страницы предпросмотра ─────────


def sample_product(request, pk):
    """Товар-пример с этим pk — только в предпросмотре дизайна и пока своих товаров нет
    (иначе None: адрес примера на живом сайте — 404)."""
    if not wanted(request):
        return None
    found = next((p for p in products() if p.pk == pk), None)
    if found is None:
        return None
    from apps.catalog.models import Product

    try:
        if Product.objects.filter(is_active=True).exists():
            return None
    except Exception:  # noqa: BLE001 — сомнение = без примера
        import logging

        logging.getLogger(__name__).warning("design samples: catalog check failed", exc_info=True)
        return None
    return found


def preview_pages(request, query: str) -> list[dict]:
    """Страницы, которые показывает предпросмотр дизайна: главная, основной список бизнеса
    (у магазина — каталог, у салона — запись, у отеля — номера) и страница товара, если
    бизнес продаёт товары (настоящего, если он есть, иначе примера). `query` —
    `?preview=1&look=…`."""
    from django.urls import NoReverseMatch, reverse
    from django.utils.translation import gettext as _

    from apps.core import archetypes

    tenant = getattr(request, "tenant", None)
    pages = [{"key": "home", "label": _("Startseite"), "url": "/" + query}]
    primary = (archetypes.primary_item(tenant) or {}) if tenant is not None else {}
    try:
        catalog = bool(tenant is None or tenant.is_module_active("catalog"))
    except Exception:  # noqa: BLE001
        catalog = True
    real = None
    if catalog:
        from apps.catalog.models import Product

        real = (
            Product.objects.filter(is_active=True).order_by("-is_featured", "-created_at").first()
        )
    # магазин: главный раздел — каталог, либо товары уже есть, либо главный раздел не задан
    shop = catalog and (
        primary.get("module") == "catalog" or real is not None or not primary.get("landing")
    )
    landing = "storefront-products" if shop else primary.get("landing") or ""
    try:
        pages.append({"key": "liste", "label": _("Liste"), "url": reverse(landing) + query})
    except NoReverseMatch:
        pass
    if not shop:
        return pages  # бизнес без товаров и не магазин — страницы товара не показываем
    pk = real.pk if real is not None else products()[0].pk
    try:
        pages.append(
            {
                "key": "produkt",
                "label": _("Produkt"),
                "url": reverse("storefront-product", args=[pk]) + query,
            }
        )
    except NoReverseMatch:
        pass
    return pages
