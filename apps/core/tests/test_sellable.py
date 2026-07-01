"""U-A / UA1-3 — контракт SellableEntity + 5 адаптеров.

Адаптеры делегируют i18n/цену/фото существующим методам объекта; kind→mode/label —
из archetypes (без дублей). `jobs` НЕ sellable (U-D). Тесты — на несохранённых
инстансах, где свойства чистые (UUID-pk присваивается на __init__ → reverse работает);
product — под django_db (свойство has_variants ходит в БД).
"""

from decimal import Decimal

import pytest

from apps.core import sellable
from apps.core.sellable import sellable_for


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_registry_is_five_kinds_and_excludes_jobs():
    assert set(sellable.SELLABLE_KINDS) == {"product", "service", "stay", "event", "combo"}
    assert "job" not in sellable.SELLABLE_KINDS and "jobs" not in sellable.SELLABLE_KINDS


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        sellable_for("job", object())


def test_service_adapter_i18n_price_mode_and_detail_url():
    from apps.booking.models import Service

    s = Service(name="Ölwechsel", description="Öl + Filter", price_cents=4900,
                name_i18n={"en": "Oil change"})  # fmt: skip
    e = sellable_for("service", s, locale="en")
    assert e.kind == "service"
    assert e.name == "Oil change"  # i18n-оверлей
    assert e.description == "Öl + Filter"  # нет en → база (фолбэк)
    assert e.price_display == "49,00 €"
    assert e.purchase_mode == "booking"
    assert e.purchase_label == "Jetzt buchen"
    assert str(s.pk) in e.detail_url and e.detail_url.startswith("/")


def test_service_free_has_empty_price():
    from apps.booking.models import Service

    assert sellable_for("service", Service(name="Beratung", price_cents=0)).price_display == ""


def test_stay_adapter_ab_price_and_gallery():
    from apps.stays.models import StayUnit

    u = StayUnit(name="Doppelzimmer", price_cents=8900,
                 images=[{"url": "/1.jpg", "is_primary": True}, {"url": "/2.jpg"}])  # fmt: skip
    e = sellable_for("stay", u)
    assert e.price_display == "ab 89,00 €"
    assert e.gallery == ["/1.jpg", "/2.jpg"]
    assert e.image_url == "/1.jpg"  # image_url отдаёт primary
    assert e.purchase_mode == "booking"


def test_event_tiers_from_price_and_i18n():
    from apps.events.models import Event

    ev = Event(
        title="Konzert",
        tiers=[{"label": "A", "price_cents": 2000}, {"label": "B", "price_cents": 3500}],
        title_i18n={"en": "Concert"},
    )
    e = sellable_for("event", ev, locale="en")
    assert e.name == "Concert"
    assert e.price_display.startswith("ab ")  # has_tiers → «ab from_price»
    assert "20,00" in e.price_display  # минимальный тариф
    assert e.purchase_mode == "booking"


def test_combo_cart_mode_no_image():
    from apps.catalog.models import Combo

    c = Combo(name="Menü 1", description="Burger + Cola", price=Decimal("9.90"))
    e = sellable_for("combo", c)
    assert e.kind == "combo"
    assert e.name == "Menü 1"
    assert e.price_display == "9,90 €"
    assert e.image_url == "" and e.gallery == []
    assert e.purchase_mode == "cart"
    assert e.purchase_label == "In den Warenkorb"


@pytest.mark.django_db
def test_product_adapter_cart_mode_price_and_gallery():
    from apps.catalog.models import Product

    p = Product.objects.create(
        name={"de": "Brot", "en": "Bread"},
        description={"de": "Frisch"},
        base_price=Decimal("2.50"),
        currency="EUR",
        images=[{"url": "/b.jpg", "is_primary": True}],
    )
    e = sellable_for("product", p, locale="en")
    assert e.name == "Bread"  # i18n
    assert e.description == "Frisch"  # нет en → база
    assert e.price_display == "2,50 €"  # без вариантов
    assert e.image_url == "/b.jpg"
    assert e.gallery == ["/b.jpg"]
    assert e.purchase_mode == "cart"
    assert e.purchase_label == "In den Warenkorb"
    assert str(p.pk) in e.detail_url


def test_non_eur_currency_uses_code():
    from apps.catalog.models import Combo

    c = Combo(name="X", price=Decimal("5.00"), currency="CHF")
    assert sellable_for("combo", c).price_display == "5,00 CHF"
