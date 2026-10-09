"""T-8.1c: лёгкие демо «Nur Aktionen» пилота Solingen (ступень 0).

План — docs/t8-1-aktion-demos-plan-2026-10-09.md §4. Замок держит обещание демо:
визитка + акции, без каталога; один город; адрес, телефон и координаты для
«So finden Sie uns» и «рядом со мной» портала; рубрики «Neu bei uns» и т. п.
"""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.core import business_card, storefront_profile
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import demo_kits, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

LITE = [
    "klingenbrot",
    "ohligser_eck",
    "walder_faden",
    "wupperhof",
    "brueckenblick",
    "graefrather_markt",  # T-8.16: Stadtbezirk Gräfrath
]


def _request(path, tenant):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return request


def test_lite_kits_are_registered_with_own_subdomains():
    subdomains = {demo_kits.KITS[k].subdomain for k in LITE}
    assert len(subdomains) == len(LITE)
    full = {
        kit.subdomain or f"{key}-demo" for key, kit in demo_kits.KITS.items() if key not in LITE
    }
    assert not subdomains & full


@pytest.mark.parametrize("key", LITE)
def test_lite_kit_is_a_business_card_with_offers(key):
    kit = demo_kits.KITS[key]
    assert kit.profile == "aktionen" and not kit.categories
    tenant = TenantFactory(schema_name="public", slug=f"lite-{key}", name=kit.label)
    assert demo_kits.apply_kit(tenant, key) is True
    tenant.refresh_from_db()

    assert storefront_profile.is_aktionen(tenant)
    assert siteconfig.normalize(tenant.site_config)["profile"] == "aktionen"
    assert tenant.city == "Solingen"
    assert tenant.is_demo is True  # T-8.15: демо не попадают в настоящие порталы
    assert tenant.district  # T-8.17: у каждого демо свой район
    assert tenant.latitude is not None and tenant.longitude is not None
    assert business_card.card_context(tenant)["route_url"].startswith("https://www.google.com/maps")
    assert tenant.is_module_active("promotions")
    # до T-8.2 кнопка акции создаёт заказ — подтверждение заказа обязано открываться
    assert tenant.is_module_active("orders")

    promos = Promotion.objects.filter(status="active")
    assert promos.count() >= 6
    assert promos.filter(group="Neu bei uns").exists()

    html = public_views.storefront_home(_request("/", tenant)).content.decode()
    assert 'id="aktionen"' in html
    assert 'href="/sortiment/' not in html and 'href="/warenkorb/' not in html

    promo = promos.first()
    detail = public_views.promotion_detail(_request(f"/p/{promo.pk}/", tenant), promo.pk)
    assert "data-business-card" in detail.content.decode()


@pytest.mark.parametrize("key", LITE)
def test_lite_offers_are_sorted_urgent_first(key):
    """О-4: срочное первым, бессрочные «Neu»/«Auf Bestellung» — в конце.

    На главной — сортировка «endet» (без даты конца — последними), на /aktionen/ —
    секции по сроку. Раньше главная шла «новые сначала», и торт под заказ стоял
    перед «Feierabendtüte до закрытия».
    """
    kit = demo_kits.KITS[key]
    tenant = TenantFactory(schema_name="public", slug=f"lite-sort-{key}", name=kit.label)
    demo_kits.apply_kit(tenant, key)
    tenant.refresh_from_db()
    html = public_views.storefront_home(_request("/", tenant)).content.decode()
    section = html[html.index('id="aktionen"') :]
    endless = [s["title"] for s in kit.promotions_spec if s.get("no_end")]
    dated = [s["title"] for s in kit.promotions_spec if not s.get("no_end")]
    assert endless and dated
    shown = [t for t in dated + endless if f">{t}<" in section]
    first_endless = min(section.index(f">{t}<") for t in endless if t in shown)
    last_dated = max(section.index(f">{t}<") for t in dated if t in shown)
    assert last_dated < first_endless

    aktionen = public_views.promotion_list(_request("/aktionen/", tenant)).content.decode()
    order = [aktionen.find(label) for label in ("Endet heute", "Dauerhaft")]
    if all(i >= 0 for i in order):
        assert order[0] < order[1]
    assert "Dauerhaft" in aktionen
