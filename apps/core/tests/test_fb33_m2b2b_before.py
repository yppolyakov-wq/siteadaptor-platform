"""FB-33 M2b-2b C0: замки ДО среза «свои вопросы FAQ у объекта».

Снимки сняты до кода M2b-2b — после среза байт-в-байт:
- L1 детальные со своими вопросами в старом разделе «faq» (услуга, событие, тур) и без
  блока FAQ — страница не меняется (у товара и номера вопросов не было — их держит
  `test_fb31p5_detail_golden`);
- L2 общий писатель `faq_content.put` (перестановка, удаление, вставка, правка немецкого,
  сверка по тексту, мусор оверлея) — тот же результат после выноса цикла переводов;
- детальные с блоком FAQ без `source` — `test_fb33_m2b2a_before` (байт-в-байт).

Обновить (осознанно): FB33M2B2B_GOLDEN=update uv run pytest <этот файл>
"""

import copy
import json
import os
from pathlib import Path

import pytest

from apps.core import faq_content
from apps.core.tests import test_fb31p5_detail_golden as _p5

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m2b2b"
UPDATE = os.environ.get("FB33M2B2B_GOLDEN") == "update"
frozen_now = _p5.frozen_now

OWN = [
    {"q": "Wie lange dauert es?", "a": "Etwa 2,5 Stunden."},
    {"q": "Muss ich etwas mitbringen?", "a": "Nein."},
]


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _check(name, got):
    path = GOLDEN / name
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB33M2B2B_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"изменилось: {path.name}"


def service_with_faq_html(cfg):
    from apps.booking import public_views
    from apps.booking.models import Service

    s = Service.objects.create(
        name="Balayage",
        description="Strähnen von Hand.",
        duration_minutes=150,
        price_cents=12900,
        is_active=True,
        faq=OWN,
    )
    return public_views.service_detail(_p5._req("/leistung/", cfg), pk=s.pk).content.decode()


@pytest.mark.parametrize("layout", ["", "tabs"])
def test_service_section_faq_looks_as_before(layout):
    cfg = {"service_detail": {"layout": layout}} if layout else {}
    _check(
        f"service-section-{layout or 'standard'}.html", _p5._normalize(service_with_faq_html(cfg))
    )


@pytest.mark.parametrize("kind", ["event", "tour"])
def test_event_section_faq_looks_as_before(kind):
    html = _p5._normalize(_p5.RENDER[kind][0]({}).content.decode())
    assert "Parkplatz?" in html
    _check(f"{kind}-section.html", html)


BASE = [
    {"q": "Parkplatz?", "a": "Ja."},
    {"q": "Lieferung?", "a": "Ab 30 €."},
    {"q": "Karte?", "a": "Online."},
]
RU = [
    {"q": "Парковка?", "a": "Да."},
    {"q": "Доставка?", "a": "От 30 €."},
    {"q": "Меню?", "a": "Онлайн."},
]
PUT_CASES = {
    "reorder": (BASE[::-1], [2, 1, 0], True),
    "delete-first": (BASE[1:], [1, 2], True),
    "insert-middle": ([BASE[0], {"q": "Neu?", "a": "x"}, *BASE[1:]], [0, None, 1, 2], True),
    "german-answer": ([{**BASE[0], "a": "Nein."}, *BASE[1:]], [0, 1, 2], True),
    "german-question": ([{**BASE[0], "q": "Parken?"}, *BASE[1:]], [0, 1, 2], True),
    "by-text": (BASE[::-1], None, True),
    "stale-base": (BASE[::-1], [0, 1, 2], "stale"),
    "drop-all": ([], [], True),
    "duplicates": ([BASE[0], BASE[0]], [0, None], True),
}


def _put_result(items, src, base):
    cfg = {
        "faq": copy.deepcopy(BASE),
        "i18n": {
            "ru": {"faq": copy.deepcopy(RU), "hero_title": "Привет"},
            "en": {"faq": [{}, {"q": "Delivery?"}, "garbage"]},
            "tr": "garbage",
            "uk": {"hero_title": "x"},
        },
    }
    fp = faq_content.fingerprint(BASE) if base is True else "0" * 16
    faq_content.put(cfg, copy.deepcopy(items), src, fp)
    return cfg


def test_shared_put_gives_the_same_result_as_before():
    got = {name: _put_result(*case) for name, case in PUT_CASES.items()}
    _check("shared-put.json", json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
