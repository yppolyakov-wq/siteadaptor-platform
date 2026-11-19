"""FB-33 M2d-0: заголовок и вступление страниц-списков и форм ДО «Заголовка страницы».

Характеризация (план M2d): у каждой страницы снимок шапки — от <main> до конца первого
абзаца после H1 — и ровно один <h1>. Пока своих текстов нет, страница обязана остаться
байт-в-байт прежней (сверка с этими снимками в M2d-1/M2d-2).

Свои блоки «сверху» стоят ВЫШЕ H1 только у форм (`FORMS_BLOCKS_ABOVE_H1`); у страниц-списков
H1 — самое верхнее. Строка «Seitentitel» в схеме обязана стоять там же (M2d-1).

Обновить (только осознанно): FB33M2D_GOLDEN=update uv run pytest <этот файл>
"""

import os
import re
from pathlib import Path

import pytest
from django.http import Http404

from apps.core.tests.test_fb31p5_detail_golden import _req

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m2d"
UPDATE = os.environ.get("FB33M2D_GOLDEN") == "update"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _view(dotted):
    mod, name = dotted.rsplit(".", 1)
    import importlib

    return getattr(importlib.import_module(mod), name)


#: хост → (адрес, вьюха). Список хостов — `HEAD_HOSTS` плана M2d (+ `/aktionen/`, M2d-3).
PAGES = {
    "services": ("/termin/", "apps.booking.public_views.termin_index"),
    "stay_rooms": ("/unterkunft/", "apps.stays.public_views.unterkunft_index"),
    "events": ("/veranstaltung/", "apps.events.public_views.veranstaltung_index"),
    "tours": ("/touren/", "apps.events.public_views.touren_index"),
    "blog": ("/blog/", "apps.events.public_views.blog_index"),
    "reviews": ("/bewertungen/", "apps.promotions.public_views.reviews_page"),
    "wishlist": ("/merkliste/", "apps.orders.public_views.wishlist_view"),
    "combos": ("/kombi/", "apps.orders.public_views.combo_list_public"),
    "team": ("/team/", "apps.promotions.public_views.team_page"),
    "gallery": ("/galerie/", "apps.promotions.public_views.gallery_page"),
    "message": ("/nachricht/", "apps.inbox.public_views.contact"),
    "anfrage": ("/anfrage/", "apps.jobs.public_views.anfrage"),
    "gift": ("/gutschein/", "apps.loyalty.public_views.gutschein_index"),
    "loyalty": ("/treue/", "apps.promotions.public_views.loyalty_page"),
    "passes": ("/karten/", "apps.booking.public_views.karten"),
    "teachers": ("/lehrer/", "apps.events.public_views.lehrer_index"),
    "event_calendar": (
        "/veranstaltung/kalender/",
        "apps.events.public_views.veranstaltung_calendar",
    ),
    "promos": ("/aktionen/", "apps.promotions.public_views.promotion_list"),
}


#: минимум данных, без которого страница отдаёт 404 (пустых страниц витрина не плодит)
NEEDS = {
    "gallery": {"gallery": [{"url": "/media/g/1.jpg", "alt": "Laden"}]},
    "team": {"team": [{"name": "Anna", "role": "Inhaberin"}]},
    "reviews": {"testimonials": [{"name": "Max", "text": "Super!"}]},
    "wishlist": {"wishlist": True},
}


def _render(host, cfg=None, monkeypatch=None):
    path, view = PAGES[host]
    req = _req(path, {**NEEDS.get(host, {}), **(cfg or {})})
    if host == "gift" and monkeypatch is not None:
        # продажа гутшайнов — при настроенной онлайн-оплате (Stripe Connect)
        from apps.loyalty import public_views as loyalty_views

        monkeypatch.setattr(loyalty_views, "gift_purchase_active", lambda tenant: True)
    try:
        resp = _view(view)(req)
    except Http404:
        return None
    if resp.status_code != 200:
        return None
    return resp.content.decode()


def _head(html):
    """Шапка страницы: от <main> до конца первого абзаца после H1 (или до конца H1)."""
    start = html.find("<main")
    h1 = html.find("<h1", start)
    if h1 == -1:
        return ""
    end = html.find("</h1>", h1) + len("</h1>")
    nxt = html.find("</p>", end)
    if nxt != -1 and nxt - end < 600:
        end = nxt + len("</p>")
    body = html[start:end]
    body = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", body)
    body = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "UUID", body)
    return re.sub(r"\n\s*\n+", "\n", body)


def _anchor(host):
    """Строка, НАД которой стоит свой блок: раздел формы или маркер основного списка."""
    from apps.core import detail_sections
    from apps.tenants import siteconfig

    keys = detail_sections.section_keys(host) if host in detail_sections.DETAIL_SECTIONS else ()
    return {"key": keys[0]} if keys else {"key": siteconfig.MAIN_LIST_KEY}


TEXT_ABOVE = {
    "key": "text",
    "id": "t-m2d",
    "enabled": True,
    "data": {"title": "Hinweis", "body": "x"},
}
#: вариант → (язык, свои блоки над формой/списком)
CASES = {"de": ("de", False), "ru": ("ru", False), "de-block": ("de", True)}


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("host", sorted(PAGES))
def test_page_head_is_as_before_and_has_one_h1(host, case, monkeypatch):
    from django.utils import translation

    lang, block = CASES[case]
    cfg = {"page_blocks": {host: [TEXT_ABOVE, _anchor(host)]}} if block else {}
    with translation.override(lang):
        html = _render(host, cfg, monkeypatch=monkeypatch)
    if html is None:
        pytest.skip(f"{host}: страница недоступна без данных/модуля")
    assert html.count("<h1") == 1, f"{host}: H1 не один"
    got = _head(html)
    path = GOLDEN / f"{host}-{case}.html"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB33M2D_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"шапка изменилась: {path.name}"


#: формы: свои блоки «сверху» рисуются над H1 (у списков H1 — самое верхнее)
FORMS_BLOCKS_ABOVE_H1 = frozenset(
    {"anfrage", "event_calendar", "gift", "loyalty", "message", "passes", "teachers"}
)


@pytest.mark.parametrize("host", sorted(PAGES))
def test_where_own_blocks_above_stand_relative_to_h1(host, monkeypatch):
    from django.utils import translation

    with translation.override("de"):
        html = _render(host, {"page_blocks": {host: [TEXT_ABOVE, _anchor(host)]}}, monkeypatch)
    block, h1 = html.find("Hinweis"), html.find("<h1")
    assert block != -1
    assert (block < h1) is (host in FORMS_BLOCKS_ABOVE_H1)
