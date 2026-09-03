"""DL-19.1 — реестр форм карточки + приоритет «своя у объекта > дефолт сайта».

Замки написаны ДО веток разметки: сначала фиксируем правило выбора формы и
паритет («" " = прежняя карточка»), потом добавляем сами формы.
"""

from __future__ import annotations

import pytest
from django.template import Context, Template

from apps.catalog.tests.factories import ProductFactory
from apps.core import card_forms
from apps.promotions.models import Promotion
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def _resolved(entity, kind, site_default):
    ctx_key = "storefront_promo_card" if kind == "promo" else "storefront_card_style"
    tpl = Template("{% load siteui %}{% card_form p kind as cs %}{{ cs }}")
    return tpl.render(Context({"p": entity, "kind": kind, ctx_key: site_default}))


# --- реестр --------------------------------------------------------------------
def test_registry_kinds_are_disjointly_gated():
    prod, promo = card_forms.keys_for("product"), card_forms.keys_for("promo")
    # общие формы канваса доступны обоим видам
    assert {"regal", "lookbook", "deal"} <= prod & promo
    # «купон» и «кольцо» держатся на данных акции (номинал, срок) — товару их нет
    assert {"coupon", "ring"} <= promo and not {"coupon", "ring"} & prod
    # прежние формы товара не переезжают в акцию (у неё своя ветка «preis»)
    assert {"overlay", "compact", "etikett"} <= prod and "preis" in promo
    assert "" not in prod and "" not in promo  # пустой ключ = «форма не задана»
    assert [k for k, *_ in card_forms.forms_for("promo")][0] == ""  # Standard первым


# --- приоритет -----------------------------------------------------------------
def test_own_form_beats_site_default():
    p = ProductFactory(card_style="regal")
    assert card_forms.card_form(p, "overlay", "product") == "regal"
    assert _resolved(p, "product", "overlay") == "regal"


def test_empty_own_falls_back_to_site_default():
    p = ProductFactory()
    assert card_forms.card_form(p, "compact", "product") == "compact"
    assert _resolved(p, "product", "compact") == "compact"
    assert card_forms.card_form(p, "", "product") == ""


def test_unknown_values_degrade_to_the_previous_form():
    """Мусор в любом слое → прежняя карточка, а не 500 (правило option_styles)."""
    p = ProductFactory(card_style="haha")
    assert card_forms.card_form(p, "regal", "product") == "regal"  # своё невалидно → сайт
    assert card_forms.card_form(p, "quatsch", "product") == ""
    # форма акции товару не подходит и наоборот — вид сущности гейтит
    assert card_forms.card_form(ProductFactory(card_style="coupon"), "", "product") == ""
    promo = Promotion.objects.create(
        title={"de": "X"}, status="active", promo_type="discount", card_style="overlay"
    )
    assert card_forms.card_form(promo, "", "promo") == ""
    assert _resolved(promo, "promo", "") == ""


def test_promo_own_form_beats_site_default():
    promo = Promotion.objects.create(
        title={"de": "X"}, status="active", promo_type="discount", card_style="coupon"
    )
    assert _resolved(promo, "promo", "preis") == "coupon"


def test_stub_entities_without_the_field_still_render():
    """Секции главной рендерят карточки стабами-SimpleNamespace — getattr с фолбэком."""
    from types import SimpleNamespace

    assert card_forms.card_form(SimpleNamespace(), "regal", "product") == "regal"


# --- конфиг сайта ---------------------------------------------------------------
def test_normalize_accepts_new_forms_and_stays_presence_minimal():
    sd = siteconfig.normalize({"site_defaults": {"card_style": "regal", "promo_card": "coupon"}})[
        "site_defaults"
    ]
    assert sd["card_style"] == "regal" and sd["promo_card"] == "coupon"
    # форма акции не принимается как форма товара (и наоборот) + мусор дропается
    sd = siteconfig.normalize({"site_defaults": {"card_style": "coupon", "promo_card": "overlay"}})[
        "site_defaults"
    ]
    assert "card_style" not in sd and "promo_card" not in sd
    assert "card_style" not in siteconfig.normalize({})["site_defaults"]


# --- DL-19.2: формы карточки товара --------------------------------------------
def _card(product, site_default=""):
    return Template('{% include "storefront/_product_card.html" %}').render(
        Context({"p": product, "storefront_card_style": site_default})
    )


def test_product_forms_render_their_own_markup():
    p = ProductFactory(name={"de": "Äpfel 1 kg"}, base_price="1.99")
    for key in ("regal", "lookbook", "deal"):
        html = _card(p, key)
        assert f'data-card-form="{key}"' in html, key
        assert "Äpfel 1 kg" in html and "1,99" in html.replace(".", ",")
    # прежняя форма своих маркеров не получает
    assert "data-card-form=" not in _card(p, "")


def test_regal_leads_with_the_price_and_deal_is_a_row():
    p = ProductFactory(name={"de": "Butter"}, base_price="1.39")
    regal = _card(p, "regal")
    # ценник: цена ВЫШЕ названия (в стандартной форме — наоборот)
    assert regal.index("data-price-plate") < regal.index("<h3")
    assert "text-2xl leading-none font-extrabold" in regal
    deal = _card(p, "deal")
    assert deal.index("<h3") < deal.index("font-extrabold")  # название первым, цена рядом
    assert "items-center gap-3" in deal  # горизонтальная строка


def test_lookbook_is_a_tall_quiet_frame():
    p = ProductFactory(name={"de": "Leinenhemd"}, base_price="89.00")
    html = _card(p, "lookbook")
    assert "aspect-[3/4]" in html
    assert "sf-card" not in html  # без рамки и тени — кадр решает
    assert "text-red-600" not in html  # спокойная цена, пока нет акции


def test_new_forms_keep_canvas_and_wishlist_hooks():
    """Форма не должна отбирать у владельца правку на канве, а у гостя — «отложить»."""
    p = ProductFactory(name={"de": "Kaffee"}, base_price="5.90")
    for key in ("regal", "lookbook", "deal"):
        html = _card(p, key)
        assert 'data-edit-field="name"' in html and "data-photo-edit" in html, key
        assert "sf-edit-link" in html, key


def test_new_forms_use_the_look_hooks_for_price_and_badge():
    """«Применяем с учётом стиля сайта»: слой [data-sf-look] цепляется за
    `text-red-600` / `bg-red-600 … rounded-full` — новые формы берут их."""
    p = ProductFactory(name={"de": "Tomaten"}, base_price="2.99")
    p.promo_price, p.promo_badge, p.promo_savings = "2.24", "−25 %", "0.75"
    for key in ("regal", "deal"):
        html = _card(p, key)
        assert "font-extrabold text-red-600" in html, key
        assert "bg-red-600 text-white text-xs font-bold" in html, key
        assert "rounded-full" in html and "−25 %" in html, key
        assert "data-savings" in html, key


# --- DL-19.3: формы карточки акции ---------------------------------------------
def _promo(**kw):
    kw.setdefault("title", {"de": "Kaffee-Woche"})
    kw.setdefault("status", "active")
    kw.setdefault("promo_type", "discount")
    return Promotion.objects.create(**kw)


def _promo_card(promo, site_default="", **extra):
    ctx = {"p": promo, "storefront_promo_card": site_default}
    ctx.update(extra)
    return Template('{% include "storefront/_promo_card.html" %}').render(Context(ctx))


def test_promo_forms_render_their_own_markup():
    promo = _promo(discount_percent=25, compare_at_price="6.90")
    for key in ("regal", "lookbook", "deal", "coupon", "ring"):
        html = _promo_card(promo, key)
        assert f'data-card-form="{key}"' in html, key
        assert "Kaffee-Woche" in html, key
    assert "data-card-form=" not in _promo_card(promo, "")


def test_promo_forms_reuse_the_single_source_of_discount_parts():
    """Условия и цена приходят из `_discount_display` — иначе mystery потекла бы."""
    promo = _promo(discount_percent=30, compare_at_price="10.00", discount_style="mystery")
    for key in ("regal", "deal", "coupon", "ring"):
        html = _promo_card(promo, key)
        assert f'data-mystery-root="{promo.pk}"' in html, key
        # цена — за reveal-кнопкой (та же механика UE2-3, что у прежних форм)
        assert "data-mystery-reveal" in html and "data-mystery-price hidden" in html, key
        assert "data-savings" not in html, key  # выгода не должна выдавать скидку
        assert "data-grundpreis" not in html, key  # из Grundpreis цена восстановима


def test_wide_strip_keeps_a_wide_form_only():
    """Полоса «Endet bald» рисует широкие карточки: узкие формы там не применяются,
    а «Deal-Kachel» — сама широкая строка, её пускаем."""
    promo = _promo(discount_percent=20, compare_at_price="5.00")
    for key in ("regal", "lookbook", "coupon", "ring"):
        html = _promo_card(promo, key, wide=True)
        assert "data-card-form=" not in html, key
        assert "sf-wide" in html, key
    deal = _promo_card(promo, "deal", wide=True)
    assert 'data-card-form="deal"' in deal and "sf-wide" in deal


def test_ring_shows_the_remaining_share_of_the_window():
    from datetime import timedelta

    from django.utils import timezone

    now = timezone.now()
    promo = _promo(
        discount_percent=10, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=3)
    )
    assert 70 <= promo.time_left_pct <= 80  # 3 из 4 дней впереди
    assert 'data-time-ring="' in _promo_card(promo, "ring")
    # без срока кольца нет (рисовать нечем), карточка живая
    open_ended = _promo(discount_percent=10)
    assert open_ended.time_left_pct is None
    html = _promo_card(open_ended, "ring")
    assert "data-time-ring" not in html and 'data-card-form="ring"' in html
    # окно позади — кольцо пустое, а не отрицательное
    past = _promo(
        discount_percent=10, starts_at=now - timedelta(days=5), ends_at=now - timedelta(days=1)
    )
    assert past.time_left_pct == 0


def test_coupon_shows_the_value_and_the_action():
    promo = _promo(promo_type="reservation", discount_percent=40, compare_at_price="20.00")
    html = _promo_card(promo, "coupon")
    assert "−40 %" in html and "border-dashed" in html
    assert "data-deal-cta" in html
