"""UB1-2: единая карточка sellable-сущности — тег `sellable_card` + партиал
`storefront/_sellable_card.html` (услуга/номер; листинг + home-варианты)."""

import pytest
from django.template import Context, Template

from apps.booking.models import Service
from apps.stays.models import StayUnit

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"  # reverse detail_url в контракте


def _render(tpl, **ctx):
    return Template("{% load sellable_ui %}" + tpl).render(Context(ctx))


def _service(**kw):
    defaults = dict(
        name="Ölwechsel",
        description="Inkl. Öl und Filter.",
        duration_minutes=30,
        price_cents=4900,
        is_active=True,
    )
    defaults.update(kw)
    return Service.objects.create(**defaults)


def test_service_card_vertical_listing():
    s = _service()
    html = _render("{% sellable_card 'service' s h2=True %}", s=s)
    assert "sf-card" in html
    assert f"/termin/leistung/{s.pk}/" in html or f"/leistung/{s.pk}/" in html  # detail_url
    assert "Ölwechsel" in html and "Inkl. Öl und Filter." in html
    assert "30" in html and "min" in html  # мета-строка длительности
    assert 'data-edit-model="service"' in html and 'data-edit-field="name"' in html
    assert 'data-edit-field="description"' in html
    assert "data-price-edit" in html and 'data-price-field="price_eur"' in html
    assert "data-photo-edit" in html
    assert "<h2" in html and "<h3" not in html  # листинг — h2


def test_service_card_horizontal_home():
    s = _service(name="Haarschnitt")
    html = _render(
        "{% sellable_card 'service' s variant='horizontal' href='/x/' cta='purchase' badge='Festpreis' %}",
        s=s,
    )
    assert 'href="/x/"' in html  # override ссылки (home ведёт на слот-пикер)
    assert "flex items-center justify-between" in html  # горизонтальная раскладка
    assert "Festpreis" in html
    assert "data-purchase-action" in html  # CTA-пилюля purchase_label
    assert "<h3" in html  # home-секция — h3


def test_service_card_free_price():
    s = _service(price_cents=0)
    html = _render("{% sellable_card 'service' s variant='horizontal' %}", s=s)
    assert 'data-price="0"' in html  # «free» тоже правится прайс-эдитом


def test_stay_card_vertical_browse():
    u = StayUnit.objects.create(
        name="Zimmer Alpenblick", price_cents=8900, max_guests=3, min_nights=2, is_active=True
    )
    html = _render("{% sellable_card 'stay' u h2=True show_min_nights=True %}", u=u)
    assert "sf-card" in html and "Zimmer Alpenblick" in html
    assert "up to" in html  # мета: тип · гости
    assert "/ night" in html and "data-price-edit" in html
    assert "min." in html  # заметка min_nights (min_nights=2 > 1)
    assert 'data-edit-model="stay"' in html


def test_stay_card_home_with_area_and_cta():
    u = StayUnit.objects.create(
        name="Suite", price_cents=12900, max_guests=2, area_sqm=42, is_active=True
    )
    html = _render("{% sellable_card 'stay' u cta='purchase' show_area=True %}", u=u)
    assert "42 m²" in html  # м² — только на home-карточке
    assert "data-purchase-action" in html and "items-baseline justify-between" in html


def test_stay_card_search_result_total_no_edit():
    u = StayUnit.objects.create(name="Fewo", price_cents=8000, is_active=True)
    html = _render(
        "{% sellable_card 'stay' u href='/s/1/?von=x' edit=False cta='select' price_total=240 %}",
        u=u,
    )
    assert "total" in html and "/ night" not in html  # цена за диапазон, не за ночь
    assert "data-edit-model" not in html and "data-photo-edit" not in html  # без едит-хуков
    assert "bg-indigo-600" in html  # пилюля «Select» (как была у поиска)
    assert 'href="/s/1/?von=x"' in html
