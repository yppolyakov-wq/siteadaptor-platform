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


def test_every_grid_class_the_layout_engine_emits_exists_in_the_built_css():
    """Стенд 2026-08-26: раскладка «6 столбцов» (DS-5) рисовала ТРИ. Классы
    сетки собирает Python (`grid_class_string`), в шаблонах их литералов нет —
    поэтому purge Tailwind вырезал `lg:grid-cols-6`, и выбор владельца молча
    подменялся на sm-класс. Замок проверяет ВСЕ комбинации таблиц движка: новый
    пресет без записи в safelist больше не пройдёт незамеченным.
    """
    from pathlib import Path

    from apps.tenants import siteconfig

    css = Path("static/css/app.css").read_text(encoding="utf-8")
    missing = set()
    for preset in siteconfig.LAYOUT_PRESET_KEYS:
        layout = siteconfig.normalize_layout({"preset": preset})
        for tablet in (0, 1, 2, 3, 4):  # SE-3c: явный пер-девайс планшет
            classes = siteconfig.grid_class_string({**layout, "tablet": tablet})
            for cls in classes.split():
                if cls.startswith(("sf-", "grid")) and ":" not in cls and "-" not in cls:
                    continue
                selector = "." + cls.replace(":", r"\:").replace("/", r"\/")
                if selector not in css:
                    missing.add(cls)
    assert not missing, f"классы движка сеток отсутствуют в собранном CSS: {sorted(missing)}"
