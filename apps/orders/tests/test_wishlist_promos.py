"""SF-4a: Merkzettel знает АКЦИИ — главный контент магазина акций.

До SF-4a список покрывал только catalog.Product, опция была недоступна
не-ритейл архетипам (ключ site_config["wishlist"] никто не писал), пункт меню
wishlist гейтился только модулем orders (при выключенной опции вёл в 404),
а закончившиеся позиции выпадали молча.
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.orders import public_views, wishlist
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/merkzettel/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build(
        business_type="grocery", site_config={"wishlist": True}, disabled_modules=[]
    )
    return request


def _promo(title, status="active", **kw):
    return Promotion.objects.create(title={"de": title}, status=status, **kw)


def test_promo_toggle_separate_key_and_total_count():
    request = _req()
    promo = _promo("KaffeeDeal")
    assert wishlist.toggle(request, promo.pk, "promotion") is True
    assert wishlist.has(request, promo.pk, "promotion")
    # товарный список не тронут, счётчик бейджа — общий
    assert wishlist.ids(request) == []
    assert wishlist.count(request) == 1
    wishlist.toggle(request, "11111111-1111-1111-1111-111111111111")  # товарный pk
    assert wishlist.count(request) == 2


def test_promotions_marks_ended_and_drops_draft():
    request = _req()
    active = _promo("LiveDeal")
    ended = _promo("VorbeiDeal", status="ended")
    draft = _promo("GeheimDraft", status="draft")
    for p in (active, ended, draft):
        wishlist.toggle(request, p.pk, "promotion")
    out = wishlist.promotions(request)
    # draft наружу не светился → выпадает как мёртвый pk; ended — с пометкой
    assert [p.pk for p in out] == [ended.pk, active.pk]
    assert [p.wish_ended for p in out] == [True, False]


def test_page_renders_promos_and_ended_tile():
    tenant = TenantFactory(
        schema_name="public",
        slug="wlp1",
        name="WL",
        site_config={"wishlist": True},
    )
    request = _req(tenant=tenant)
    live = _promo("FrischDeal")
    gone = _promo("WegDeal", status="ended")
    wishlist.toggle(request, live.pk, "promotion")
    wishlist.toggle(request, gone.pk, "promotion")
    body = public_views.wishlist_view(request).content.decode()
    assert "FrischDeal" in body  # обычная промо-карточка
    assert "data-wish-ended" in body and "WegDeal" in body
    assert "Beendet" in body
    # у закончившейся — путь к актуальным акциям (модуль promotions активен)
    assert "/aktionen/" in body


def test_promo_card_and_detail_carry_heart():
    # урок ST-3: modules_nav → {} на public-схеме; хром витрины (сердечко из
    # контекст-процессора) тестируем на обычной схеме
    tenant = TenantFactory(
        schema_name="wlp2", slug="wlp2", name="WL", site_config={"wishlist": True}
    )
    from apps.promotions import public_views as promo_views

    promo = _promo("HerzDeal")
    request = _req(path=f"/p/{promo.pk}/", tenant=tenant)
    body = promo_views.promotion_detail(request, pk=promo.pk).content.decode()
    assert f"/merkzettel/aktion/{promo.pk}/" in body

    listing = promo_views.promotion_list(_req(path="/aktionen/", tenant=tenant)).content.decode()
    assert f"/merkzettel/aktion/{promo.pk}/" in listing


def test_heart_absent_when_option_disabled():
    tenant = TenantFactory(
        schema_name="wlp3", slug="wlp3", name="WL", site_config={"wishlist": False}
    )
    from apps.promotions import public_views as promo_views

    _promo("OhneHerz")
    body = promo_views.promotion_list(_req(path="/aktionen/", tenant=tenant)).content.decode()
    assert "merkzettel" not in body


def test_menu_wishlist_target_gated_by_option():
    from apps.tenants import menu

    cfg = {
        "menus": {"top": {"items": [{"label": "Merkliste", "type": "page", "target": "wishlist"}]}}
    }
    on = TenantFactory.build(
        business_type="grocery", site_config={**cfg, "wishlist": True}, disabled_modules=[]
    )
    off = TenantFactory.build(
        business_type="grocery", site_config={**cfg, "wishlist": False}, disabled_modules=[]
    )
    labels_on = [n["label"] for n in menu.resolve_menu(on, "top")]
    labels_off = [n["label"] for n in menu.resolve_menu(off, "top")]
    assert "Merkliste" in labels_on
    assert "Merkliste" not in labels_off  # раньше пункт вёл бы в 404


def test_kit_aktionsmarkt_enables_wishlist_with_menu_entry():
    from apps.tenants import demo_kits

    kit = demo_kits.KITS["aktionsmarkt"]
    assert kit.config_patch.get("wishlist") is True
    bottom = kit.menus["bottom"]["items"]
    assert any(i.get("target") == "wishlist" for i in bottom)
