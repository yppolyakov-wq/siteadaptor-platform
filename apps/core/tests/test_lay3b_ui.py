"""LAY-3b (UI) — контролы «типа вывода» в Студии и их сохранение.

Движок (ключи `rows`/`page_size`/`speed`, `output_mode`, `effective_limit`) закрыт
замками `test_lay3_output_axis.py`. Здесь — вторая половина: владелец обязан иметь
чем эти ключи задать, а Save и живой черновик обязаны их доносить. Настройка без
контрола — такая же ложь интерфейса, как контрол без настройки (правило STU-9,
только с другой стороны).

Замки написаны ДО правок и краснеют на текущем коде.
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# Поверхность → префикс полей формы (тот же, что у селекта пресета).
SURFACES = ["catalog_preset", "events_preset", "stay_preset", "service_preset"]


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _request(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _tenant(slug):
    return TenantFactory(
        schema_name="public",
        slug=slug,
        name=slug.upper(),
        enabled_modules=["catalog", "events", "stays", "booking"],
    )


def _body(tenant):
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    assert resp.status_code == 200
    return resp.content.decode()


def _save(tenant, data):
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


@pytest.mark.parametrize("field", SURFACES)
@pytest.mark.parametrize("suffix", ["mode", "rows", "page_size", "speed", "tail"])
def test_every_surface_offers_the_output_controls(field, suffix):
    """Каждая поверхность листинга даёт все контролы типа вывода."""
    body = _body(_tenant(f"lay3b{SURFACES.index(field)}"))
    assert f'name="{field}_{suffix}"' in body, f"нет контрола {field}_{suffix}"


def test_save_writes_the_output_parameters():
    tenant = _tenant("lay3bs")
    cfg = _save(
        tenant,
        {
            "catalog_preset": "cols5",
            "catalog_preset_mode": "slider",
            "catalog_preset_rows": "2",
            "catalog_preset_page_size": "24",
            "catalog_preset_speed": "6",
            "catalog_preset_tail": "fill",
        },
    )
    lay = cfg["catalog_layout"]
    assert lay["preset"] == "cols5"
    assert lay["scroll"] is True
    assert lay["rows"] == 2 and lay["page_size"] == 24 and lay["speed"] == 6
    assert lay["tail"] == "fill"
    assert siteconfig.effective_limit(lay) == 10, "«10 = 2 ряда по 5» считается само"


def test_empty_fields_mean_as_before():
    """Пустые поля не создают ключей: «как раньше» — это ОТСУТСТВИЕ ключа."""
    tenant = _tenant("lay3be")
    cfg = _save(
        tenant,
        {
            "catalog_preset": "cols3",
            "catalog_preset_mode": "grid",
            "catalog_preset_rows": "",
            "catalog_preset_page_size": "",
            "catalog_preset_speed": "",
            "catalog_preset_tail": "",
        },
    )
    lay = cfg["catalog_layout"]
    for key in ("rows", "page_size", "speed", "tail", "scroll"):
        assert key not in lay, key
    assert siteconfig.effective_limit(lay) is None


def test_draft_carries_the_output_parameters():
    """Живой черновик показывает выбор ДО Save (иначе контрол «не работает»)."""
    tenant = _tenant("lay3bd")
    req = _request("post", "/dashboard/site/preview-draft/", tenant=tenant)
    req._body = (
        b'{"catalog_layout": {"preset": "cols4", "scroll": true, "rows": 2,'
        b' "page_size": 12, "speed": 5, "tail": "fill"}}'
    )
    req.META["CONTENT_TYPE"] = "application/json"
    resp = views.site_preview_draft(req)
    assert resp.status_code in (200, 204)
    lay = (req.session.get("site_preview_draft") or {}).get("catalog_layout") or {}
    assert lay.get("rows") == 2 and lay.get("page_size") == 12 and lay.get("speed") == 5
    assert lay.get("scroll") is True and lay.get("tail") == "fill"
