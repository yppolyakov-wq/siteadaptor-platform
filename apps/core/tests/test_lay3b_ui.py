"""LAY-3b (UI) — контролы «типа вывода» и их сохранение.

STU-19f-2 (осознанно переписано): сетки страниц задаются в КАБИНЕТЕ («Seitenvorlage»,
блок «Ausgabe»); Студия показывает сводку и не пишет их ни Save'ом, ни черновиком.

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

from apps.core import page_settings, page_templates, views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# Тип страницы → настройка сетки (кабинет, экран Sortiment).
SURFACES = [
    ("catalog", "catalog_layout"),
    ("events", "events_layout"),
    ("stays", "stay_layout"),
    ("services", "service_layout"),
]


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


def _cabinet(tenant, typ):
    path = "/dashboard/seitenvorlagen/"
    resp = page_templates.page_templates_website(_request("get", path, {"typ": typ}, tenant))
    assert resp.status_code == 200
    return resp.content.decode()


def _cabinet_save(tenant, data):
    path = "/dashboard/seitenvorlagen/"
    resp = page_templates.page_templates_website(_request("post", path, data, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


@pytest.mark.parametrize("typ,code", SURFACES)
@pytest.mark.parametrize("suffix", ["mode", "rows", "tail", "speed"])
def test_every_surface_offers_the_output_controls(typ, code, suffix):
    """Каждая поверхность листинга даёт контролы типа вывода — в кабинете."""
    body = _cabinet(_tenant(f"lay3b{typ}"), typ)
    form = body.split(f'data-pt-setting="{code}"', 1)[1].split("</form>", 1)[0]
    assert f'name="out_{suffix}"' in form, f"нет контрола out_{suffix} у {code}"


def test_page_size_only_where_the_page_paginates():
    tenant = _tenant("lay3bps")
    body = _cabinet(tenant, "catalog")
    form = body.split('data-pt-setting="catalog_layout"', 1)[1].split("</form>", 1)[0]
    assert 'name="out_page_size"' in form
    events = _cabinet(tenant, "events")
    form = events.split('data-pt-setting="events_layout"', 1)[1].split("</form>", 1)[0]
    assert 'name="out_page_size"' not in form


def test_save_writes_the_output_parameters():
    tenant = _tenant("lay3bs")
    cfg = _cabinet_save(
        tenant,
        {
            "setting": "catalog_layout",
            "typ": "catalog",
            "value": "cols5",
            "out_mode": "slider",
            "out_rows": "2",
            "out_page_size": "24",
            "out_speed": "6",
            "out_tail": "fill",
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
    cfg = _cabinet_save(
        tenant,
        {
            "setting": "catalog_layout",
            "typ": "catalog",
            "value": "cols3",
            "out_mode": "grid",
            "out_rows": "",
            "out_page_size": "",
            "out_speed": "",
            "out_tail": "",
        },
    )
    lay = cfg["catalog_layout"]
    for key in ("rows", "page_size", "speed", "tail", "scroll"):
        assert key not in lay, key
    assert siteconfig.effective_limit(lay) is None


def test_studio_draft_cannot_change_a_grid():
    """STU-19f-2: черновик Студии берёт сетку из сохранённого конфига (кабинет — единственный
    писатель), прочитанная в превью раскладка = сохранённая."""
    tenant = _tenant("lay3bd")
    page_settings.write(tenant, "catalog_layout", "cols3", output={"rows": "1"})
    req = _request("post", "/dashboard/site/preview-draft/", tenant=tenant)
    req._body = b'{"catalog_layout": {"preset": "cols4", "scroll": true, "rows": 2}}'
    req.META["CONTENT_TYPE"] = "application/json"
    resp = views.site_preview_draft(req)
    assert resp.status_code in (200, 204)
    lay = (req.session.get("site_preview_draft") or {}).get("catalog_layout") or {}
    assert lay.get("preset") == "cols3" and lay.get("rows") == 1 and not lay.get("scroll")
