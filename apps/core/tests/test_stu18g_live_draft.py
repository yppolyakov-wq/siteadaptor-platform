"""STU-18g: шаблон страницы акций применяется НА КЛИК, как в каталоге.

Фидбэк владельца 2026-09-11: «Шаблон страницы у акции применяется только после
нажатия Сохранить и перезагрузки… В каталоге шаблон меняется сразу при клике.
Сделай так же у акций».

Измерено на стенде: POST черновика с `{"promo_page_style": "kompakt"}` возвращал
204, но `/aktionen/?preview=1` продолжал рисовать сохранённый шаблон. Причина —
реестр `_PAGE_STYLE_KEYS` состоял из ОДНОГО каталожного ключа, и генерик-наложение
черновика выбрасывало выбор молча. Тот же пробел был у девяти листингов STU-18d
(ключ `page_styles` в черновик вообще не отправлялся).

Замки написаны ДО правки и краснеют на прежнем коде.
"""

import json
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import studio_pages as sp
from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

BUILDER = "templates/tenant/site_home.html"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _draft(tenant, payload):
    """POST в приёмник черновика → нормализованный черновик из сессии."""
    req = RequestFactory().post(
        "/dashboard/site/preview/draft/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = views.site_preview_draft(req)
    assert resp.status_code == 204
    return req.session["site_preview_draft"]


def test_draft_keeps_the_cabinet_promotions_page_template():
    """STU-19e-2 (deliberate rewrite): the offers page template is cabinet-owned — a
    Studio draft cannot set or unset it; the stored value stays."""
    tenant = TenantFactory(
        schema_name="public", slug="stu18g1", site_config={"promo_page_style": "magazin"}
    )
    assert _draft(tenant, {"promo_page_style": "kompakt"}).get("promo_page_style") == "magazin"
    assert _draft(tenant, {"promo_page_style": ""}).get("promo_page_style") == "magazin"


def test_draft_keeps_the_cabinet_listing_compositions():
    """STU-19e-1 (deliberate rewrite of the STU-18g lock): listing templates are set
    in the cabinet only. A Studio draft that sends `page_styles` cannot change them —
    the draft keeps the STORED value (its preview lives on the cabinet screen)."""
    tenant = TenantFactory(
        schema_name="public", slug="stu18g2", site_config={"page_styles": {"stays": "kopfbild"}}
    )
    draft = _draft(tenant, {"page_styles": {"services": "tabs", "stays": "regale"}})
    assert draft.get("page_styles") == {"stays": "kopfbild"}


def test_registry_lists_both_page_style_keys():
    """Срез page_config («что относится к этой странице») обязан их знать —
    иначе черновик per-page терял бы выбор при переключении страниц."""
    listing = siteconfig.PAGE_CONFIG_KEYS["listing"]
    assert "promo_page_style" in listing and "page_styles" in listing
    assert set(siteconfig._PAGE_STYLE_KEYS) == {"catalog_page_style", "promo_page_style"}


def test_builder_no_longer_sends_listing_styles():
    """STU-19e-1: the Studio has no listing-template control any more — sending the
    key would only invite a second writer."""
    markup = open(BUILDER, encoding="utf-8").read()
    assert "payload.page_styles" not in markup


def test_every_template_picker_in_the_panel_reaches_the_draft():
    """Класс дефекта, ради которого писан файл: ключ ЗНАЮТ три места — панель,
    Save и черновик. Достаточно выпасть из третьего, и владелец видит «шаблон не
    применяется, пока не нажму Сохранить» (жалоба 2026-09-11).

    Замок сам собирает обещание из ПАНЕЛИ: берёт каждую плитку-выбор шаблона, её
    первое непустое значение — и требует, чтобы черновик это значение принял.
    Новая поверхность, забытая в приёмнике черновика, краснит его сразу.

    Граница: покрываем строки с плитками (`data-cf-key`) — это и есть шаблоны
    страниц. Настройки-селекты (баннер, раскладка детали) едут в черновик своими
    ветками и проверяются отдельно.
    """
    import re

    tenant = TenantFactory(schema_name="public", slug="stu18gp")
    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    html = views.home_builder_view(req).content.decode()

    # Границу строки задаёт НАЧАЛО следующей: вложенные </div> считать бесполезно,
    # а «до следующей строки» даёт ровно тот кусок разметки, что принадлежит этой.
    marks = [(m.group(1), m.end()) for m in re.finditer(r'data-stu-setting="([a-z_0-9]+)"', html)]
    checked = []
    for i, (code, pos) in enumerate(marks):
        body = html[pos : marks[i + 1][1] if i + 1 < len(marks) else len(html)]
        if "data-cf-key" not in body:
            continue
        setting = sp.SETTINGS.get(code)
        if setting is None:
            continue
        values = [v for v in re.findall(r'data-cf-key="([^"]*)"', body) if v]
        if not values:
            continue
        value, path = values[0], setting.site_key
        if len(path) == 1:
            payload = {path[0]: value}
        else:
            payload = {path[0]: {path[1]: value}}
        draft = _draft(tenant, payload)
        got = draft.get(path[0])
        got = got.get(path[1]) if len(path) > 1 and isinstance(got, dict) else got
        assert got == value, (
            f"{code}: панель предлагает «{value}», но черновик его не принял "
            f"(получилось {got!r}) — правка будет видна только после Save"
        )
        checked.append(code)

    # STU-19f-3 (осознанно): все плитки-выборы (шаблоны и формы карточки) ушли в
    # кабинет — в Студии их нет, и черновик их не обязан принимать. Если в панель
    # вернётся плитка, цикл выше снова её проверит; принадлежать кабинету она не может.
    from apps.core import page_settings

    assert set(checked).isdisjoint(page_settings.CABINET_OWNED), checked
