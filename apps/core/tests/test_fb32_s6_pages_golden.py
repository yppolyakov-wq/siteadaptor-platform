"""FB-32 S6a R0: характеризация «Über uns» и своей страницы ДО строк разделов. Без якорей
(строк разделов в `page_blocks`) страница обязана остаться байт-в-байт прежней — сверка с этими
снимками (`docs/fb32-unified-blocks-plan-2026-11-17.md`, S6).

Обновить (только осознанно): FB32S6_GOLDEN=update uv run pytest <этот файл>
"""

import os
import re
from pathlib import Path

import pytest

from apps.core.tests.test_fb31p5_detail_golden import _req

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb32s6"
UPDATE = os.environ.get("FB32S6_GOLDEN") == "update"

TEXT = {"key": "text", "id": "t-s6", "enabled": True, "data": {"title": "Anfahrt", "body": "Bus 5"}}
CASES = {
    "plain": {},
    "tail": {"page_blocks": {"info": [TEXT]}},
    "nocontact": {"about_contact": False, "page_blocks": {"info": [TEXT]}},
    "texts": {"about_title": "Wir", "about_text": "Seit 1990."},
}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _main(html: str) -> str:
    start = html.find("<main")
    end = html.find("</main>", start)
    body = html[start:end] if start != -1 else html
    body = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", body)
    return re.sub(r"\n\s*\n+", "\n", body)


def _about(cfg):
    from apps.promotions import public_views

    req = _req("/ueber-uns/", cfg)
    req.tenant.address = "Hauptstr. 1, 42651 Solingen"  # иначе карточки контактов нет
    req.tenant.contact_phone = "+49 212 1234"
    return _main(public_views.about_page(req).content.decode())


def _page(cfg):
    from apps.core import content_page_views
    from apps.core.models import ContentPage

    ContentPage.objects.get_or_create(
        slug="anfahrt", defaults={"title": "Anfahrt", "body": "<p>Hier</p>"}
    )
    cfg = {**cfg, "page_blocks": {"seite:anfahrt": (cfg.get("page_blocks") or {}).get("info", [])}}
    req = _req("/anfahrt/", cfg)
    return _main(content_page_views.storefront_page(req, "anfahrt").content.decode())


def _check(name, got):
    path = GOLDEN / f"{name}.html"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB32S6_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"страница изменилась: {path.name}"


@pytest.mark.parametrize("case", sorted(CASES))
def test_about_page_without_anchors_looks_as_before(case):
    _check(f"about-{case}", _about(CASES[case]))


@pytest.mark.parametrize("case", ("plain", "tail"))
def test_content_page_without_anchors_looks_as_before(case):
    _check(f"page-{case}", _page(CASES[case]))
