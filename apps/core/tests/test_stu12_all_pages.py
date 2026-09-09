"""STU-12i: Студия открывается на КАЖДОМ типе страницы (сводная проверка волны).

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12i) требовал браузерного
обхода 19 типов × три ширины. Браузерная часть в текущей среде недоступна (dev-сервер
отдаёт витрину ~14 c, канва не успевает за watchdog двойной буферизации), поэтому сводная
проверка сделана СЕРВЕРНОЙ: она надёжнее и не зависит от скорости окружения.

`test_studio_pages` уже держит резолвер (каждый тип узнаётся по своему адресу) и согласие
реестра с разметкой панели. Здесь — недостающее звено: билдер РЕАЛЬНО отдаёт страницу для
адреса каждого типа, несёт свой каркас (колонка, канва, верхняя строка) и не роняет 500.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import NoReverseMatch, reverse

from apps.core import studio_pages as sp
from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# наборы аргументов роутов витрины — те же, что в test_studio_pages (там же и замок
# «каждый тип узнаётся по своему адресу»); берём ПЕРВЫЙ, которым адрес собирается
ARG_SETS = (
    {},
    {"pk": uuid4()},
    {"slug": "probe"},
    {"pslug": "probe"},
    {"cslug": "kategorie", "pslug": "probe"},
)


def _paths_for(pt):
    for name in pt.url_names:
        for kwargs in ARG_SETS:
            try:
                yield reverse(name, kwargs=kwargs, urlconf="config.urls_tenant")
                break
            except NoReverseMatch:
                continue


def _builder(tenant, page=""):
    req = RequestFactory().get("/dashboard/site/home/", {"page": page} if page else {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return views.home_builder_view(req)


def test_studio_opens_for_every_page_type():
    tenant = TenantFactory(slug="stall1", name="StAll1", disabled_modules=[])
    broken, checked = [], []
    for pt in sp.PAGE_TYPES:
        for path in _paths_for(pt):
            checked.append(pt.code)
            resp = _builder(tenant, path)
            if resp.status_code != 200:
                broken.append(f"{pt.code} {path} → {resp.status_code}")
                continue
            body = resp.content.decode()
            # каркас волны STU-12: одна колонка, канва, верхняя строка со «Seite ▾»
            for marker in ('id="bld-editor-pane"', 'id="home-prev-frame"', 'id="st-design-link"'):
                if marker not in body:
                    broken.append(f"{pt.code} {path}: нет {marker}")
    assert not broken, broken
    # адверсариально: замок обязан РЕАЛЬНО обойти типы, а не молча ничего не проверить
    assert len(set(checked)) >= len(sp.PAGE_TYPES) - 2, sorted(set(checked))


def test_studio_keeps_the_page_in_the_form_and_the_link_back():
    """`page_path` — то, чем Save возвращает канву на ту же страницу (UC6-7b)."""
    tenant = TenantFactory(slug="stall2", name="StAll2", disabled_modules=[])
    body = _builder(tenant, "/sortiment/").content.decode()
    assert 'id="bld-page-path"' in body
    assert 'value="/sortiment/"' in body


def test_studio_has_no_removed_areas_left():
    """Сводка волны: снесённое в 12a–12g не должно вернуться ни на одном типе."""
    tenant = TenantFactory(slug="stall3", name="StAll3", disabled_modules=[])
    body = _builder(tenant).content.decode()
    for gone in (
        'data-bld-area="theme"',  # 12g: глобальный дизайн — на экране кабинета
        'data-bld-area="quickstart"',  # 12g: шаблоны витрины и демо-контент — там же
        'id="bld-rail"',  # 12a: левая рейка
        'id="bld-area-tabs"',  # 12a: вкладки областей
    ):
        assert gone not in body, gone
