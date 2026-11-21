"""FB-33 M3-5c: замки ДО кода — окно, которого переводы не касаются, байт-в-байт прежнее.

L1: у бизнеса с одним языком панели окна всех видов строк (CASES окна M3-0 и FAQ/плашки/
«Seitentitel») — как до среза. L2: у бизнеса с несколькими языками — строки без переводимых
текстов («Liste», плашки без своей подписи, «Von einer Seite», баннер, ★, раздел, итог корзины,
«Einstellungen der Seite»). Эталоны сняты на de ДО правок кода (`golden_fb33m35c/`);
пересъёмка — `FB33_M35C_REGEN=1`.
"""

import copy
import os
import re
from pathlib import Path

import pytest
from django.utils import translation

from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CASES, CFG, _panel

pytestmark = pytest.mark.django_db

GOLDEN = Path(__file__).parent / "golden_fb33m35c"

#: CASES окна M3-0 и окна, где срез добавляет поля перевода у бизнеса с языками
SINGLE = (
    *CASES,
    ("home", "t1", "&tab=texte"),
    ("home", "faq", "&tab=texte"),
    ("home", "quicklinks"),
    ("text", "f1", "&tab=texte"),
)
#: у бизнеса с языками — строки без переводимых текстов
FOREIGN = (
    ("home", "hero"),
    ("home", "usp_bar"),
    ("home", "l1"),
    ("home", "quicklinks"),
    ("home", "products"),
    ("catalog", "main"),
    ("catalog", "categories"),
    ("product", "related"),
    ("cart", "summary"),
    ("text", "tp1"),
    ("text", "bn1"),
    ("text", "__page"),
)

FAQ = [{"q": "A?", "a": "1"}, {"q": "B?", "a": "2"}]


def _cfg():
    cfg = copy.deepcopy(CFG)
    cfg["faq"] = copy.deepcopy(FAQ)
    return cfg


def _normalize(html: str) -> str:
    html = re.sub(
        r'name="csrfmiddlewaretoken" value="[^"]*"', 'name="csrfmiddlewaretoken" value="X"', html
    )
    html = re.sub(r'name="wopen" value="[^"]*"', 'name="wopen" value="W"', html)
    return re.sub(r"wopen=[A-Za-z0-9_-]+", "wopen=W", html) + "\n"


def _render(case, locales) -> str:
    tenant = _tenant()
    tenant.site_config = _cfg()
    tenant.enabled_locales = list(locales)
    tenant.save()
    code, ref, extra = (*case, "")[:3]
    with translation.override("de"):
        html = Browser(tenant).get(f"?seite={code}&block={ref}{extra}")
    return _normalize(_panel(html))


def _name(prefix, case) -> str:
    raw = "_".join(case).replace("&", "").replace("=", "-")
    return prefix + re.sub(r"[^A-Za-z0-9_-]", "", raw) + ".html"


def _check(got: str, path: Path):
    if os.environ.get("FB33_M35C_REGEN") == "1":
        GOLDEN.mkdir(parents=True, exist_ok=True)
        path.write_text(got)
        pytest.fail("регенерация эталонов — перезапусти без FB33_M35C_REGEN")
    assert got == path.read_text(), path.name


@pytest.mark.parametrize("case", SINGLE, ids=["|".join(c) for c in SINGLE])
def test_one_language_window_is_byte_for_byte_the_same(case):
    _check(_render(case, ("de",)), GOLDEN / _name("one_", case))


@pytest.mark.parametrize("case", FOREIGN, ids=["|".join(c) for c in FOREIGN])
def test_rows_without_texts_are_byte_for_byte_the_same(case):
    _check(_render(case, ("de", "ru")), GOLDEN / _name("multi_", case))
