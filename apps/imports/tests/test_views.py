"""Тесты wizard-вьюх импорта через RequestFactory (вызов view напрямую).

Как и в каталоге: урлы живут в urls_tenant, но в тестах django-tenants
работает в public-схеме → реальный роутинг даёт 404. Тестируем view-функции
напрямую (паттерн _attach_session_user из catalog/tests/test_views.py).
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from apps.imports import views
from apps.imports.models import ImportJob

CSV = "Name,Preis,SKU\nBrot,2.50,BR-1\n"


def _attach_session_user(request, user):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    return request


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="owner", email="owner@test.de", password="pw12345678"
    )


@pytest.mark.django_db
def test_start_requires_login():
    req = RequestFactory().get("/imports/start/")
    _attach_session_user(req, AnonymousUser())
    resp = views.import_start(req)
    assert resp.status_code in (301, 302)


@pytest.mark.django_db
def test_start_get_ok(user):
    req = RequestFactory().get("/imports/start/")
    _attach_session_user(req, user)
    resp = views.import_start(req)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_upload_creates_job(user):
    req = RequestFactory().post(
        "/imports/start/",
        {"source_file": SimpleUploadedFile("p.csv", CSV.encode("utf-8"))},
    )
    _attach_session_user(req, user)
    resp = views.import_start(req)
    assert resp.status_code == 302
    job = ImportJob.objects.latest("created_at")
    assert job.status == "uploaded"


@pytest.mark.django_db
def test_map_post_sets_mapping_and_status(user, monkeypatch):
    # не дёргаем Celery в тесте
    monkeypatch.setattr(views.preview_import, "delay", lambda **kw: None)
    job = ImportJob.objects.create(
        resource_type="product",
        status="uploaded",
        source_file=SimpleUploadedFile("p.csv", CSV.encode("utf-8")),
    )
    req = RequestFactory().post(
        f"/imports/{job.pk}/map/",
        {
            "map__Name": "name_de",
            "map__Preis": "base_price",
            "map__SKU": "sku",
            "update_existing": "on",
        },
    )
    _attach_session_user(req, user)
    resp = views.import_map(req, pk=job.pk)
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.status == "mapped"
    assert job.column_mapping == {
        "Name": "name_de",
        "Preis": "base_price",
        "SKU": "sku",
    }
    assert job.options.get("update_existing") is True
