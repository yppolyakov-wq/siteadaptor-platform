"""FB-31 P3 R0: характеризация трёх страниц акций ДО разбивки шаблонов на блоки.

Снимок HTML (нормализованный: токены, UUID, даты и время — акции заданы от «сейчас») для
каждого шаблона обзора `/aktionen/` (`promo_page_style`), страницы группы
(`site_defaults.promo_group_style` / `promo_groups[key].style`) и детали акции
(`site_defaults.promo_detail_style` / `Promotion.page_style`). Следующие срезы
(`docs/fb31-p3-promotions-plan-2026-11-16.md`) обязаны оставить сайт байт-в-байт таким же.

Обновить снимки (только осознанно, с объяснением в коммите):
    FB31P3_GOLDEN=update uv run pytest apps/promotions/tests/test_fb31p3_promo_golden.py
"""

import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import compositions
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb31p3"
UPDATE = os.environ.get("FB31P3_GOLDEN") == "update"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
_CSRF = re.compile(r'(name="csrfmiddlewaretoken" value=")[^"]+')
_NONCE = re.compile(r'(nonce=")[^"]+')
# акции заданы от «сейчас»: даты, время и метки времени меняются от прогона к прогону
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:?\d{2}|Z)?")
_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.(\d{2,4})?")
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
_EPOCH = re.compile(r"\b\d{10,13}\b")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_PK = re.compile(r"(/aktionen/|/p/|pk=|data-promo-id=\")\d+")


@pytest.fixture(autouse=True)
def _urlconf(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    # «сегодня» эталонов: сводка «по времени» зависит от даты (урок CI 2026-11-17); часы
    # идут (порядок по времени создания сохраняется), старт — момент съёмки снимков
    from apps.core.tests.test_fb31p5_detail_golden import ticking_clock

    monkeypatch.setattr(timezone, "now", ticking_clock(datetime(2026, 11, 16, 5, 50, tzinfo=UTC)))


def _normalize(html: str) -> str:
    start, end = html.find("<main"), html.rfind("</main>")
    if start != -1 and end != -1:
        html = html[start : end + len("</main>")]
    html = _CSRF.sub(r"\1X", html)
    html = _NONCE.sub(r"\1X", html)
    html = _UUID.sub("UUID", html)
    html = _HEX32.sub("HEX", html)
    html = _ISO.sub("ISO", html)
    html = _DAY.sub("DAY", html)
    html = _DATE.sub("DATE", html)
    html = _TIME.sub("TIME", html)
    html = _EPOCH.sub("EPOCH", html)
    html = _PK.sub(r"\1N", html)
    return "\n".join(line.rstrip() for line in html.splitlines() if line.strip()) + "\n"


def _check(name: str, html: str):
    path = GOLDEN / f"{name}.html"
    got = _normalize(html)
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB31P3_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"вид страницы акций изменился: {path.name}"


def _promo(title, group="Wochenangebote", days=3, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("promo_type", "discount")
    kw.setdefault("price_override", Decimal("2.49"))
    kw.setdefault("compare_at_price", Decimal("3.49"))
    kw.setdefault("ends_at", timezone.now() + timedelta(days=days, hours=1))
    return Promotion.objects.create(title={"de": title}, group=group, **kw)


def _seed(groups=True):
    """Акции с разным сроком (порядок по окончанию однозначен); с группами — две группы
    по три акции (выше порога `MIN_GROUP_SECTION`), без групп — пять без группы."""
    if groups:
        n = 0
        for g in ("Wochenangebote", "Räumung"):
            for i in range(3):
                n += 1
                _promo(f"{g} {i}", group=g, days=n)
    else:
        for i in range(5):
            _promo(f"Angebot {i}", group="", days=i + 1)


def _request(path, tenant, **params):
    request = RequestFactory().get(path, params)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


def _overview(cfg, **params):
    tenant = TenantFactory.build(name="Laden X", site_config=cfg)
    return public_views.promotion_list(_request("/aktionen/", tenant, **params)).content.decode()


PROMOS = sorted(code for code, _l, _h in compositions.styles_for("promos"))
GROUP = sorted(code for code, _l, _h in compositions.styles_for("promo_group"))
DETAIL = sorted(code for code, _l, _h in compositions.styles_for("promo"))
_LIST = {"key": "text", "id": "t-promo", "data": {"title": "Hinweis", "body": "Gilt solange"}}


# ── обзор /aktionen/ ──


@pytest.mark.parametrize("groups", [True, False], ids=["groups", "nogroups"])
@pytest.mark.parametrize("code", PROMOS)
def test_overview_looks_as_before(code, groups):
    _seed(groups)
    html = _overview({"promo_page_style": code} if code else {})
    _check(f"promos-{code or 'standard'}-{'groups' if groups else 'nogroups'}", html)


@pytest.mark.parametrize("code", ["", "kompakt", "navigator", "regale", "magazin"])
def test_overview_grouped_by_time_looks_as_before(code):
    _seed(True)
    cfg = {"promo_grouping": "time"}
    if code:
        cfg["promo_page_style"] = code
    _check(f"promos-{code or 'standard'}-time", _overview(cfg))


@pytest.mark.parametrize("code", ["", "kopfbild", "tabs", "schaufenster"])
def test_overview_with_own_blocks_looks_as_before(code):
    _seed(True)
    cfg = {"page_blocks": {"promos": [_LIST, {"key": "main"}]}}
    if code:
        cfg["promo_page_style"] = code
    _check(f"promos-{code or 'standard'}-blocks", _overview(cfg))


def test_price_list_as_cards_looks_as_before():
    _seed(True)
    html = _overview({"promo_page_style": "preisliste"}, ansicht="karten")
    _check("promos-preisliste-karten", html)


@pytest.mark.parametrize("code", ["", "kompakt"])
def test_overview_paged_looks_as_before(code):
    _seed(True)
    cfg = {"promo_index_layout": {"page_size": 2}}
    if code:
        cfg["promo_page_style"] = code
    _check(f"promos-{code or 'standard'}-paged", _overview(cfg))


# ── страница группы ?gruppe= ──


@pytest.mark.parametrize("code", GROUP)
def test_group_page_looks_as_before(code):
    _seed(True)
    cfg = {"site_defaults": {"promo_group_style": code}} if code else {}
    _check(f"group-{code or 'standard'}", _overview(cfg, gruppe="Wochenangebote"))


@pytest.mark.parametrize("code", ["prospekt", "countdown"])
def test_group_own_style_beats_the_site_default_as_before(code):
    _seed(True)
    cfg = {
        "site_defaults": {"promo_group_style": "magazin"},
        "promo_groups": {"Wochenangebote": {"style": code}},
    }
    _check(f"group-own-{code}", _overview(cfg, gruppe="Wochenangebote"))
    _check(f"group-site-for-other-{code}", _overview(cfg, gruppe="Räumung"))


def test_countdown_group_with_explicit_sort_looks_as_before():
    _seed(True)
    cfg = {"site_defaults": {"promo_group_style": "countdown"}}
    _check("group-countdown-sorted", _overview(cfg, gruppe="Wochenangebote", sort="price_asc"))


def test_group_page_shows_the_overview_blocks_as_before():
    """Сегодня страница группы рисует блоки обзора — новый хост группы обязан откатываться."""
    _seed(True)
    cfg = {"page_blocks": {"promos": [_LIST, {"key": "main"}]}}
    _check("group-standard-overview-blocks", _overview(cfg, gruppe="Wochenangebote"))


# ── деталь акции ──


def _detail(promo, cfg):
    tenant = TenantFactory.build(name="Laden X", site_config=cfg)
    req = _request(f"/aktionen/{promo.pk}/", tenant)
    return public_views.promotion_detail(req, pk=promo.pk).content.decode()


@pytest.mark.parametrize("code", DETAIL)
def test_detail_looks_as_before(code):
    promo = _promo("Brot der Woche")
    cfg = {"site_defaults": {"promo_detail_style": code}} if code else {}
    _check(f"detail-{code or 'standard'}", _detail(promo, cfg))


@pytest.mark.parametrize("code", ["plakat", "kompakt"])
def test_detail_own_style_beats_the_site_default_as_before(code):
    promo = _promo("Brot der Woche", page_style=code)
    cfg = {"site_defaults": {"promo_detail_style": "magazin"}}
    _check(f"detail-own-{code}", _detail(promo, cfg))


# ── R3: витрина читает оси блоков ──


@pytest.mark.parametrize(
    "rows,golden",
    [
        ([{"key": "groups", "style": "tabs"}, {"key": "main"}], "promos-tabs-groups"),
        ([{"key": "main", "style": "magazin", "grouping": "ohne"}], "promos-magazin-groups"),
        (
            [
                {"key": "groups", "style": "index"},
                {"key": "main", "style": "prospekt", "grouping": "ohne"},
            ],
            "promos-kompakt-groups",
        ),
    ],
)
def test_stored_rows_draw_the_same_page_as_the_template(rows, golden):
    _seed(True)
    _check(golden, _overview({"page_blocks": {"promos": rows}}))


def test_new_combination_draws_both_parts():
    """Kopfbild + Reiter — сочетания, которого у шаблонов не было."""
    _seed(True)
    rows = [{"key": "page_head", "style": "titelbild"}, {"key": "groups", "style": "tabs"}]
    html = _overview({"page_blocks": {"promos": [*rows, {"key": "main"}]}})
    assert "data-promo-head" in html and "data-promo-tabs" in html
    assert 'data-promo-page="tabs"' in html


def test_explicit_standard_rows_beat_the_template():
    _seed(True)
    rows = [{"key": "groups", "style": "auto"}, {"key": "main"}]
    cfg = {"promo_page_style": "regale", "page_blocks": {"promos": rows}}
    _check("promos-standard-groups", _overview(cfg))


def test_detail_precedence_object_rows_then_own_then_shared_rows():
    promo = _promo("Brot der Woche", page_style="kompakt")
    shared = {"page_blocks": {"promo_detail": [{"key": "offer", "style": "plakat"}]}}
    assert 'data-promo-detail="kompakt"' in _detail(promo, shared), "своя акция сильнее общей"
    plain = _promo("Kuchen")
    assert 'data-promo-detail="plakat"' in _detail(plain, shared), "общая строка сильнее дефолта"
    own_host = {"page_blocks": {f"promo:{promo.pk.hex}": [{"key": "offer", "style": "magazin"}]}}
    assert 'data-promo-detail="magazin"' in _detail(promo, own_host), "«nur diese» сильнее всего"
