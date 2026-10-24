"""KA-12 E4.2a: навыки мастера — какие ресурсы оказывают услугу.

Пусто — любой активный ресурс (как раньше, паритет). Иначе слоты, назначение
ресурса, «ближайший свободный» и выбор мастера на витрине — только из навыков;
подмена формы чужим мастером не проходит; компактный Save без чекбоксов связи
не стирает."""

import pytest

from apps.booking import availability
from apps.booking.models import Resource
from apps.booking.tests.test_services import _aware, _future_day, _resource, _rule, _service

pytestmark = pytest.mark.django_db


def _two_masters(day):
    anna, ben = _resource(type="staff"), _resource(type="staff")
    _rule(anna, day, "09:00", "10:00")
    _rule(ben, day, "11:00", "12:00")
    return anna, ben


def test_empty_skills_any_resource():
    day = _future_day()
    anna, ben = _two_masters(day)
    svc = _service(duration_minutes=60)
    starts = availability.service_slots(svc, day)
    assert _aware(day, 9) in starts and _aware(day, 11) in starts


def test_skilled_service_only_on_its_masters():
    day = _future_day()
    anna, ben = _two_masters(day)
    svc = _service(duration_minutes=60)
    svc.resources.set([ben])
    starts = availability.service_slots(svc, day)
    assert starts == [_aware(day, 11)]
    assert availability.assign_resource(svc, _aware(day, 9)) is None
    assert availability.assign_resource(svc, _aware(day, 11)) == ben
    assert availability.next_free_slot(svc, from_day=day) == _aware(day, 11)


def test_explicit_foreign_master_gets_no_slots():
    day = _future_day()
    anna, ben = _two_masters(day)
    svc = _service(duration_minutes=60)
    svc.resources.set([ben])
    assert availability.service_slots(svc, day, resource=anna) == []
    assert availability.assign_resource(svc, _aware(day, 9), resource=anna) is None


def test_inactive_skilled_masters_close_the_service():
    """Ревью: все мастера навыка выключены → пул пуст (fail-closed). Владелец явно
    ограничил услугу — отпуск мастера не открывает её мастерам без квалификации,
    и витрина не предлагает мастера, которого бронь потом отвергнет."""
    day = _future_day()
    anna, ben = _two_masters(day)
    svc = _service(duration_minutes=60)
    svc.resources.set([ben])
    Resource.objects.filter(pk=ben.pk).update(is_active=False)
    assert availability.service_pool(svc) == []
    assert availability.service_slots(svc, day) == []
    assert not availability.has_skill(svc, anna)


def test_has_skill_matches_pool_for_inactive_skill():
    day = _future_day()
    anna, ben = _two_masters(day)
    svc = _service(duration_minutes=60)
    svc.resources.set([anna, ben])
    Resource.objects.filter(pk=ben.pk).update(is_active=False)
    assert availability.has_skill(svc, anna)
    assert not availability.has_skill(svc, ben)


def test_slot_page_queries_do_not_grow_per_day(settings):
    """Ревью: пул считается один раз на запрос, а не по дню месяца (N+1)."""
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.booking import public_views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two_masters(day)
    svc = _service(duration_minutes=60)
    svc.resources.set([ben])
    req = RequestFactory().get(f"/termin/leistung/{svc.pk}/", {"tag": day.isoformat()})
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(schema_name="public")
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        public_views.service_slots(req, pk=svc.pk)
    pool_queries = [q for q in ctx.captured_queries if "booking_service_resources" in q["sql"]]
    assert len(pool_queries) <= 3, len(pool_queries)


def test_has_skill():
    day = _future_day()
    anna, ben = _two_masters(day)
    svc = _service()
    assert availability.has_skill(svc, anna)
    svc.resources.set([ben])
    assert not availability.has_skill(svc, anna) and availability.has_skill(svc, ben)


def test_public_book_with_foreign_master_is_404(settings):
    from django.http import Http404
    from django.test import RequestFactory

    from apps.booking import public_views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two_masters(day)
    svc = _service(duration_minutes=60)
    svc.resources.set([ben])
    req = RequestFactory().post(
        f"/termin/leistung/{svc.pk}/buchen/",
        {
            "start": _aware(day, 9).isoformat(),
            "resource": str(anna.pk),
            "name": "X",
            "email": "x@t.de",
        },
    )
    req.tenant = TenantFactory.build(schema_name="public")
    with pytest.raises(Http404):
        public_views.service_book(req, pk=svc.pk)


def test_save_without_sentinel_keeps_skills(settings):
    from apps.booking import views
    from apps.booking.tests.test_cabinet import _req

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two_masters(day)
    svc = _service()
    svc.resources.set([ben])
    base = {"action": "update", "service": str(svc.pk), "duration": "30", "price_eur": "10"}
    views.services_view(_req("post", data=base))
    assert list(svc.resources.all()) == [ben]
    views.services_view(
        _req("post", data={**base, "resources_present": "1", "resources": [str(anna.pk)]})
    )
    assert list(svc.resources.all()) == [anna]
    views.services_view(_req("post", data={**base, "resources_present": "1", "resources": ["abc"]}))
    assert not svc.resources.exists()


def test_slot_page_offers_only_skilled_masters(settings):
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.booking import public_views
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    anna, ben = _two_masters(day)
    third = _resource(type="staff", title="Coloristin")
    for r in (anna, ben):
        r.title = "Friseur"
        r.save(update_fields=["title"])
    svc = _service(duration_minutes=60)
    svc.resources.set([anna, third])
    req = RequestFactory().get(f"/termin/leistung/{svc.pk}/", {"tag": day.isoformat()})
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(schema_name="public")
    body = public_views.service_slots(req, pk=svc.pk).content.decode()
    assert anna.name in body and third.name in body
    assert ben.name not in body
