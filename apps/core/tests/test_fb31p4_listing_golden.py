"""FB-31 P4 R0: характеризация оформления девяти листингов ДО разбивки шаблонов на блоки.

Все девять страниц-списков строят оформление (шапка, навигация, полки) одной функцией
`listing_composition.context()`, а каркас `listing.html` читает только её ответ. Поэтому
эталон — её ответ для каждой поверхности × каждого кода × данных (есть подразделы / фото).
Следующие срезы (`docs/fb31-p4-listings-plan-2026-11-16.md`) обязаны отвечать так же.

Обновить (только осознанно): FB31P4_GOLDEN=update uv run pytest <этот файл>
"""

import json
import os
from pathlib import Path

import pytest

from apps.core import compositions, listing_composition

# FB-31.7 B3b: модуль проверяет отрисовку по старым кодам шаблонов (до B4) — см. conftest
LEGACY_CODES = True

GOLDEN = Path(__file__).parent / "golden_fb31p4" / "contexts.json"
UPDATE = os.environ.get("FB31P4_GOLDEN") == "update"

ENTRIES = [{"label": "Damen", "url": "?k=damen", "active": False, "count": 3}]
SHELVES = [{"label": "Damen", "slug": "damen", "url": "?k=damen", "total": 3, "items": []}]
HERO = {"eyebrow": "Salon · Haan", "text": "", "photo": "/media/hero.jpg"}
NO_PHOTO = {"eyebrow": "Salon · Haan", "text": "", "photo": ""}
CODES = sorted({c for s in compositions.LISTING_SURFACES for c in compositions.valid_for(s)})


#: подразделы вьюхи передают только эти листинги (у прочих `entries` не бывает вовсе)
WITH_ENTRIES = {"services", "stays", "events", "combos"}


def _cases():
    for surface in sorted(compositions.LISTING_SURFACES):
        for code in [*CODES, "quatsch"]:
            for entries in (True, False) if surface in WITH_ENTRIES else (False,):
                for photo in (True, False):
                    yield surface, code, entries, photo


def _ctx(surface, code, entries, photo, cfg=None):
    config = cfg if cfg is not None else ({"page_styles": {surface: code}} if code else {})
    return listing_composition.context(
        config,
        surface,
        entries=(lambda: ENTRIES) if entries else (lambda: []),
        shelves=lambda: SHELVES,
        hero=lambda: HERO if photo else NO_PHOTO,
        carry="k",
        kind="service",
    )


def _key(surface, code, entries, photo):
    return f"{surface}|{code or 'standard'}|{'entries' if entries else 'flat'}|{'photo' if photo else 'nophoto'}"


def test_every_listing_composition_answers_as_before():
    got = {_key(*case): _ctx(*case) for case in _cases()}
    if UPDATE or not GOLDEN.exists():
        if not UPDATE:
            pytest.fail("нет эталона: FB31P4_GOLDEN=update")
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, sort_keys=True, ensure_ascii=False, indent=1) + "\n")
        return
    want = json.loads(GOLDEN.read_text())
    diff = [k for k in sorted(set(want) | set(got)) if want.get(k) != got.get(k)]
    assert not diff, f"оформление листингов изменилось: {diff[:10]}"
