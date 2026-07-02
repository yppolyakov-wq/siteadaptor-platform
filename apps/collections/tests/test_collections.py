"""UB3-2: модель `Collection` (M2M-подборки услуг/номеров) + фасет ?kollektion=
на листингах витрины. Проверяем: i18n-оверлей имени, чипы только «живых»
коллекций своего kind, фильтрацию с distinct и невозможность утечь на
booking_index/редирект юнита при пустой выдаче фасета."""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.booking.models import Service
from apps.collections.models import Collection
from apps.core import facets as core_facets
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/termin/", data=None):
    request = RequestFactory().get(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="cafe", disabled_modules=[])
    return request


def _collection(name, slug, **kw):
    return Collection.objects.create(name=name, slug=slug, **kw)


# --- модель --------------------------------------------------------------------


def test_collection_str_and_i18n_overlay():
    col = _collection("Damen", "damen", name_i18n={"en": "Women"})
    assert str(col) == "Damen"
    assert col.name_localized("en") == "Women"  # оверлей неосновной локали
    assert col.name_localized("de") == "Damen"  # база — в плоском поле
    assert col.name_localized("fr") == "Damen"  # фолбэк на базу


def test_collection_ordering_by_sort_order_then_name():
    _collection("Zuletzt", "zuletzt", sort_order=5)
    _collection("B-Erste", "b-erste", sort_order=1)
    _collection("A-Erste", "a-erste", sort_order=1)
    assert [c.slug for c in Collection.objects.all()] == ["a-erste", "b-erste", "zuletzt"]


# --- фасет: услуги ----------------------------------------------------------------


def test_service_collection_facet_apply_and_chips():
    damen = _collection("Damen", "damen")
    herren = _collection("Herren", "herren")
    empty = _collection("Leer", "leer")  # без услуг → чипа нет
    off = _collection("Aus", "aus", is_active=False)  # неактивная → нет и фильтра
    cut = Service.objects.create(name="Schnitt", price_cents=3000)
    cut.collections.add(damen, herren)  # услуга в ДВУХ подборках (distinct)
    color = Service.objects.create(name="Färben", price_cents=6000)
    color.collections.add(damen, off)
    qs = Service.objects.filter(is_active=True)
    provider = core_facets.provider_for("service")

    chips = provider.present(qs, {})["collection_chips"]
    assert [c["slug"] for c in chips] == ["damen", "herren"]  # без «Leer»/«Aus»
    assert empty.pk  # (создана выше, чипа нет)

    assert set(provider.apply(qs, {"kollektion": "damen"})) == {cut, color}
    assert list(provider.apply(qs, {"kollektion": "herren"})) == [cut]
    assert provider.apply(qs, {"kollektion": "aus"}).count() == 0  # неактивная коллекция
    assert provider.apply(qs, {"kollektion": ""}).count() == 2  # пусто → no-op
    # distinct: услуга в двух подборках не дублируется в выдаче без фильтра по одной
    assert provider.apply(qs, {"kollektion": "damen"}).count() == 2


def test_stay_collection_facet_apply_and_chips():
    see = _collection("Mit Seeblick", "mit-seeblick")
    fam = _collection("Familienzimmer", "familienzimmer")
    suite = StayUnit.objects.create(name="Suite", price_cents=15000)
    suite.collections.add(see)
    zimmer = StayUnit.objects.create(name="Zimmer", price_cents=8000)
    zimmer.collections.add(fam)
    qs = StayUnit.objects.filter(is_active=True)
    provider = core_facets.provider_for("stay")
    chips = provider.present(qs, {})["collection_chips"]
    assert {c["slug"] for c in chips} == {"mit-seeblick", "familienzimmer"}
    assert list(provider.apply(qs, {"kollektion": "mit-seeblick"})) == [suite]
    sel = provider.selected({"kollektion": " fam "})
    assert sel["kollektion"] == "fam"  # strip; даты/гости в selected сохранены
    assert "von" in sel and "adults" in sel


# --- витрина ----------------------------------------------------------------------


def test_termin_index_renders_chips_and_filters():
    from apps.booking import public_views

    damen = _collection("Damen", "damen", name_i18n={"en": "Women"})
    cut = Service.objects.create(name="Schnitt", price_cents=3000)
    cut.collections.add(damen)
    Service.objects.create(name="Bart", price_cents=1500)
    body = public_views.termin_index(_req()).content.decode()
    assert 'href="?kollektion=damen"' in body and "Damen" in body  # чип отрендерен
    body_f = public_views.termin_index(_req(data={"kollektion": "damen"})).content.decode()
    assert "Schnitt" in body_f and "Bart" not in body_f  # фасет фильтрует
    # фасет+поиск, опустошившие выдачу, НЕ уводят на листинг ресурсов
    body_none = public_views.termin_index(
        _req(data={"kollektion": "damen", "q": "zzz"})
    ).content.decode()
    assert "Nothing found" in body_none


def test_unterkunft_index_chips_filter_and_no_redirect():
    from apps.stays import public_views

    see = _collection("Mit Seeblick", "mit-seeblick")
    suite = StayUnit.objects.create(name="Alpensuite", price_cents=15000)
    suite.collections.add(see)
    StayUnit.objects.create(name="Standardzimmer", price_cents=8000)
    body = public_views.unterkunft_index(_req(path="/unterkunft/")).content.decode()
    assert 'href="?kollektion=mit-seeblick"' in body
    resp = public_views.unterkunft_index(
        _req(path="/unterkunft/", data={"kollektion": "mit-seeblick"})
    )
    assert resp.status_code == 200  # сузили до одного юнита — НЕ редирект на него
    body_f = resp.content.decode()
    assert "Alpensuite" in body_f and "Standardzimmer" not in body_f


# --- кабинет (CRUD) ---------------------------------------------------------------


def _dash_req(method="get", data=None, disabled=None):
    """Запрос в кабинет /dashboard/collections/ от «вошедшего» владельца
    (SimpleNamespace вместо реального юзера — обход login_required, как в
    test_home_builder)."""
    from types import SimpleNamespace

    request = getattr(RequestFactory(), method)("/dashboard/collections/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = SimpleNamespace(is_authenticated=True)
    request.tenant = TenantFactory.build(business_type="cafe", disabled_modules=disabled or [])
    return request


def test_cabinet_create_assign_toggle_delete():
    """Полный цикл кабинета: создать (slug авто) → состав услуг чекбоксами
    (presence-guard) → выключить → удалить."""
    from apps.collections import views

    svc = Service.objects.create(name="Schnitt", price_cents=3000)
    resp = views.collections_view(_dash_req("post", {"action": "create", "name": "Damen Cut"}))
    assert resp.status_code == 302
    col = Collection.objects.get()
    assert col.slug == "damen-cut"  # slug из имени

    views.collections_view(
        _dash_req(
            "post",
            {
                "action": "update",
                "collection": str(col.pk),
                "name": "Damen",
                "sort_order": "3",
                "services_present": "1",
                "services": [str(svc.pk)],
            },
        )
    )
    col.refresh_from_db()
    assert col.name == "Damen" and col.sort_order == 3
    assert list(col.services.all()) == [svc]
    assert col.slug == "damen-cut"  # slug стабилен при переименовании

    # POST без units_present/services_present не должен трогать состав
    views.collections_view(
        _dash_req("post", {"action": "update", "collection": str(col.pk), "name": "Damen"})
    )
    assert list(col.services.all()) == [svc]

    views.collections_view(_dash_req("post", {"action": "toggle", "collection": str(col.pk)}))
    col.refresh_from_db()
    assert col.is_active is False

    views.collections_view(_dash_req("post", {"action": "delete", "collection": str(col.pk)}))
    assert Collection.objects.count() == 0
    assert Service.objects.filter(pk=svc.pk).exists()  # услуга не удаляется с подборкой


def test_cabinet_slug_uniqueness_suffix():
    from apps.collections import views

    views.collections_view(_dash_req("post", {"action": "create", "name": "Damen"}))
    views.collections_view(_dash_req("post", {"action": "create", "name": "Damen"}))
    assert set(Collection.objects.values_list("slug", flat=True)) == {"damen", "damen-2"}


def test_cabinet_renders_checkbox_rows_and_gates_modules():
    from django.http import Http404

    from apps.collections import views

    col = _collection("Damen", "damen")
    Service.objects.create(name="Schnitt", price_cents=3000)
    body = views.collections_view(_dash_req()).content.decode()
    assert "?kollektion=damen" in body  # подсказка параметра фасета
    assert 'name="services"' in body and "Schnitt" in body  # чекбоксы состава
    assert col.name in body
    # ни booking, ни stays → страница недоступна
    with pytest.raises(Http404):
        views.collections_view(_dash_req(disabled=["booking", "stays"]))
