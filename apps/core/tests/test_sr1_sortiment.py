"""SR-1 (утверждённый канвас 2026-08-24): Sortiment — единственная страница
ассортимента. Замки: вид Kacheln↔Liste (персист presence-minimal), карточка без
текстового «Bearbeiten» (кликабельны фото и имя), Liste несёт инструменты
умершей /catalog/products/ (Art.-Nr./Bestand/merge), товарные фильтры."""

import pytest
from django.test import RequestFactory

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    return TenantFactory(slug=kw.pop("slug", "sr1"), name="SR", business_type="bakery", **kw)


def _get(tenant, params=None):
    req = RequestFactory().get("/dashboard/angebote/", params or {})
    req.tenant = tenant
    req.user = type("U", (), {"is_authenticated": True, "username": "o"})()
    return views.sellable_manage(req)


def _post_view(tenant, view, next_path="/dashboard/angebote/"):
    req = RequestFactory().post("/dashboard/angebote/ansicht/", {"view": view, "next": next_path})
    req.tenant = tenant
    req.user = type("U", (), {"is_authenticated": True, "username": "o"})()
    return views.sortiment_view_set(req)


# --- normalize: presence-minimal ---------------------------------------------


def test_normalize_sortiment_view_is_presence_minimal():
    # дефолт (kacheln) и мусор ключа не материализуют
    assert "sortiment_view" not in siteconfig.normalize({})
    assert "sortiment_view" not in siteconfig.normalize({"sortiment_view": "kacheln"})
    assert "sortiment_view" not in siteconfig.normalize({"sortiment_view": "quatsch"})
    assert siteconfig.normalize({"sortiment_view": "liste"})["sortiment_view"] == "liste"


# --- сеттер: персист + возврат к дефолту чистит ключ --------------------------


def test_view_setter_persists_and_default_pops_key():
    t = _tenant()
    resp = _post_view(t, "liste")
    assert resp.status_code == 302
    t.refresh_from_db()
    assert t.site_config.get("sortiment_view") == "liste"
    _post_view(t, "kacheln")
    t.refresh_from_db()
    assert "sortiment_view" not in t.site_config


def test_view_setter_rejects_garbage_and_external_next():
    t = _tenant()
    _post_view(t, "quatsch")
    t.refresh_from_db()
    assert "sortiment_view" not in t.site_config
    resp = _post_view(t, "liste", next_path="//evil.example")
    assert resp["Location"] == "/dashboard/angebote/"


# --- рендер: карточка и Liste -------------------------------------------------


def test_card_links_and_no_bearbeiten_text():
    t = _tenant()
    p = ProductFactory(name={"de": "Brot"}, stock_quantity=7)
    body = _get(t).content.decode()
    # фото и имя — ссылки на родную форму; текстовой «Bearbeiten» нет
    assert f"/catalog/products/{p.pk}/edit/" in body
    assert ">Bearbeiten<" not in body
    assert "Bestand" in body  # наличие — главная информация карточки


def test_liste_view_carries_product_tools():
    t = _tenant()
    cat = CategoryFactory(name={"de": "Backwaren"})
    ProductFactory(name={"de": "Brot"}, sku="BR-001", category=cat, stock_quantity=0)
    body = _get(t, {"ansicht": "liste"}).content.decode()
    assert "BR-001" in body  # Art.-Nr.
    assert "Backwaren" in body  # категория
    assert 'form="merge-form"' in body  # чекбоксы объединения
    assert "products/merge/" in body or "zusammenf" in body.lower()
    # явный GET сильнее сохранённого — и наоборот, персист работает без GET
    t.site_config = {"sortiment_view": "liste"}
    t.save(update_fields=["site_config"])
    body2 = _get(t).content.decode()
    assert 'form="merge-form"' in body2


def test_product_filters_scope_sections():
    t = _tenant()
    cat = CategoryFactory(name={"de": "Backwaren"})
    ProductFactory(name={"de": "Brot"}, category=cat)
    ProductFactory(name={"de": "Saft"})
    body = _get(t, {"kategorie": str(cat.pk)}).content.decode()
    assert "Brot" in body and "Saft" not in body
    hidden = ProductFactory(name={"de": "Torte"}, is_active=False)
    body = _get(t, {"status": "0"}).content.decode()
    assert "Torte" in body and "Brot" not in body
    assert hidden.pk  # noqa: B018 — использование фикстуры
