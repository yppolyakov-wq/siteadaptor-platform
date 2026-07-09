"""W5: настройки Kanban-доски — переименование/порядок/скрытие колонок.

Правила переходов карт (FSM/statuses) НЕ трогаем (V4). Хранение — site_config['board']
(переживает normalize; ключ только при непустом — golden-паритет).
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import pipeline
from apps.core import views as core_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory


# --- resolve_columns (чистая функция) ---------------------------------------
def test_resolve_columns_default_is_pipeline():
    cols = pipeline.resolve_columns("order")
    assert [c["stage"] for c in cols] == list(pipeline.STAGES)


def test_resolve_columns_rename_reorder_hide():
    board = {
        "labels": {"intake": "Neu rein"},
        "hidden": ["terminal"],
        "order": ["done", "in_progress", "intake"],
    }
    cols = pipeline.resolve_columns("order", board)
    stages = [c["stage"] for c in cols]
    assert "terminal" not in stages  # скрыто
    assert stages == ["done", "in_progress", "intake"]  # порядок соблюдён
    intake = next(c for c in cols if c["stage"] == "intake")
    assert intake["label"] == "Neu rein"  # переименовано
    # statuses (правила переходов) не тронуты
    assert intake["statuses"] == pipeline.pipeline_for("order")[0]["statuses"]


# --- normalize_board (валидация + golden-паритет) ---------------------------
def test_normalize_board_empty_no_key():
    assert siteconfig.normalize_board(None) == {}
    assert siteconfig.normalize_board({}) == {}
    assert "board" not in siteconfig.normalize({})  # ключ не появляется (golden)


def test_normalize_board_validates_and_dedups():
    b = siteconfig.normalize_board(
        {
            "labels": {"intake": "X", "bogus": "Y"},
            "hidden": ["terminal", "bogus"],
            "order": ["done", "done", "nope", "intake"],
        }
    )
    assert b["labels"] == {"intake": "X"}  # чужая стадия отброшена
    assert b["hidden"] == ["terminal"]
    assert b["order"] == ["done", "intake"]  # дедуп + чужое отброшено, порядок сохранён


def test_normalize_preserves_board_key():
    cfg = siteconfig.normalize({"board": {"labels": {"intake": "Neu"}}})
    assert cfg["board"]["labels"]["intake"] == "Neu"


# --- board_settings view -----------------------------------------------------
def _req(method, user, tenant, data=None):
    request = getattr(RequestFactory(), method)("/dashboard/board/settings/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def _user(n):
    return get_user_model().objects.create_user(n, f"{n}@test.de", "pw12345678")


@pytest.mark.django_db
def test_board_settings_saves_and_preserves_other_keys(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(disabled_modules=[], site_config={"ui_mode": "simple"})
    data = {
        "label_intake": "Posteingang",
        "hidden_terminal": "on",
        "order_intake": "1",
        "order_in_progress": "2",
        "order_done": "3",
        "order_terminal": "4",
    }
    resp = core_views.board_settings(_req("post", _user("b1"), tenant, data))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["board"]["labels"]["intake"] == "Posteingang"
    assert "terminal" in tenant.site_config["board"]["hidden"]
    assert "order" not in tenant.site_config["board"]  # дефолтный порядок не материализуем
    assert tenant.site_config["ui_mode"] == "simple"  # чужой ключ цел (targeted write)


@pytest.mark.django_db
def test_board_settings_reorder_materialized(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(disabled_modules=[], site_config={})
    data = {"order_intake": "4", "order_in_progress": "3", "order_done": "2", "order_terminal": "1"}
    core_views.board_settings(_req("post", _user("b2"), tenant, data))
    tenant.refresh_from_db()
    assert tenant.site_config["board"]["order"] == ["terminal", "done", "in_progress", "intake"]


@pytest.mark.django_db
def test_board_renders_panel_and_custom_label(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        disabled_modules=[], site_config={"board": {"labels": {"intake": "Posteingang"}}}
    )
    req = RequestFactory().get("/dashboard/board/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _user("b3")
    req.tenant = tenant
    html = core_views.board(req).content.decode()
    assert "/dashboard/board/settings/" in html  # панель настроек видна
    assert "Posteingang" in html  # кастомная метка колонки на доске
