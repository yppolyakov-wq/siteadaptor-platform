"""Тесты wizard-вьюх импорта через RequestFactory (вызов view напрямую).

Как и в каталоге: урлы живут в urls_tenant, но в тестах django-tenants
работает в public-схеме → реальный роутинг даёт 404. Тестируем view-функции
напрямую (паттерн _attach_session_user из catalog/tests/test_views.py).
"""

from pathlib import Path

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


def test_upload_is_stored_under_random_name_keeping_extension(user):
    """P0-2 (аудит 2026-09-03 §9.3): исходное имя файла не должно быть путём —
    `imports/<исходное имя>` угадывалось и отдавалось с любого хоста. Расширение
    сохраняем: по нему `tabular.is_excel` выбирает парсер."""
    req = RequestFactory().post(
        "/imports/start/",
        {"source_file": SimpleUploadedFile("Preisliste Sommer 2026.xlsx", b"PK\x03\x04")},
    )
    _attach_session_user(req, user)
    views.import_start(req)
    job = ImportJob.objects.latest("created_at")
    name = job.source_file.name
    assert name.startswith("imports/") and name.endswith(".xlsx")
    assert "Preisliste" not in name and "Sommer" not in name
    stem = name[len("imports/") : -len(".xlsx")]
    assert len(stem) == 32 and all(c in "0123456789abcdef" for c in stem)


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["get", "post"])
def test_map_without_source_file_redirects_to_status(user, method, monkeypatch):
    """P0-2: после completed файл удалён (или его добрал cleanup_import_files) —
    шаг маппинга без файла раньше падал бы на read_headers. Теперь честный
    редирект на статус с сообщением, задача в очередь не ставится."""
    calls = []
    monkeypatch.setattr(views.preview_import, "delay", lambda **kw: calls.append(kw))
    job = ImportJob.objects.create(resource_type="product", status="completed", source_file="")
    req = getattr(RequestFactory(), method)(f"/imports/{job.pk}/map/", {"delimiter": "auto"})
    _attach_session_user(req, user)
    resp = views.import_map(req, pk=job.pk)
    assert resp.status_code == 302
    assert resp["Location"].endswith(f"/{job.pk}/status/")
    assert calls == []
    assert [m.message for m in req._messages]  # владелец видит, почему не шаг маппинга


@pytest.mark.django_db
def test_uppercase_excel_extension_still_selects_excel_parser(user):
    """Расширение нормализуется в нижний регистр — `tabular.is_excel` сверяет
    суффикс по lower(), но замок держит саму связку «PREISE.XLSX → парсер Excel»."""
    from apps.imports.tabular import is_excel

    req = RequestFactory().post(
        "/imports/start/", {"source_file": SimpleUploadedFile("PREISE.XLSX", b"PK\x03\x04")}
    )
    _attach_session_user(req, user)
    views.import_start(req)
    job = ImportJob.objects.latest("created_at")
    assert job.source_file.name.endswith(".xlsx")
    assert is_excel(job.source_file)


def test_upload_rename_is_the_only_way_a_job_gets_a_file():
    """План P0-2 обещал callable `upload_to`; реализовано переименованием во
    вьюхе, потому что смена `upload_to` — миграция ради нулевого DDL. Гарантия
    держится, ПОКА место создания одно: второй колл-сайт (админка, API, сидер)
    молча вернул бы `imports/<исходное имя>`, а имя файла клиента снова стало бы
    угадываемым путём. Замок по исходнику — вместо миграции."""
    import re

    root = Path(__file__).resolve().parents[3]
    # Создание, а не объявление: `class ImportJob(...)` в models.py не в счёт.
    # `\w*create` покрывает create/get_or_create/bulk_create/update_or_create:
    # прежняя регулярка видела только прямой конструктор и .objects.create(.
    creation = re.compile(r"(?<!class )\bImportJob(?:\.objects\.\w*create)?\s*\(")
    sites = []
    for py in sorted((root / "apps").rglob("*.py")):
        parts = py.relative_to(root).parts
        if "tests" in parts or "migrations" in parts:
            continue
        for i, line in enumerate(py.read_text().splitlines(), 1):
            if creation.search(line):
                sites.append(f"{py.relative_to(root)}:{i}")
    # Сверяем ФАЙЛЫ, а не строки: номер строки поедет от любой правки выше и
    # покраснеет без причины; строки печатаем для диагностики.
    assert sorted({site.split(":")[0] for site in sites}) == ["apps/imports/views.py"], sites
    view_src = (root / "apps/imports/views.py").read_text()
    assert "uuid.uuid4().hex" in view_src
