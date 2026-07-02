"""UC1-1 (шаг 0): golden-замки `siteconfig.normalize` — БАЙТ-В-БАЙТ паритет.

Эталоны `golden/normalize_<name>.json` сняты на коде ДО `PAGE_SECTION_REGISTRY`
(2026-07-02). Инвариант U-C (риск №5 uc-плана): legacy-конфиги обязаны
нормализоваться идентично после любых рефакторов реестров. Красный тест здесь =
регрессия схемы; регенерация эталона — только ОСОЗНАННЫМ решением с записью в
build-log (команда в докстринге golden_configs.py).
"""

import json
from pathlib import Path

import pytest

from apps.tenants import siteconfig
from apps.tenants.tests.golden_configs import GOLDEN_INPUTS

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.mark.parametrize("name", sorted(GOLDEN_INPUTS))
def test_normalize_matches_golden(name):
    expected = json.loads((GOLDEN_DIR / f"normalize_{name}.json").read_text())
    got = siteconfig.normalize(GOLDEN_INPUTS[name])
    # Сравнение через canonical-JSON — байт-в-байт, с читаемым diff при падении.
    assert json.dumps(got, ensure_ascii=False, sort_keys=True) == json.dumps(
        expected, ensure_ascii=False, sort_keys=True
    )


@pytest.mark.parametrize("name", sorted(GOLDEN_INPUTS))
def test_normalize_idempotent(name):
    once = siteconfig.normalize(GOLDEN_INPUTS[name])
    assert siteconfig.normalize(once) == once
