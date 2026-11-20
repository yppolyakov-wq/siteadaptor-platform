"""FB-33 M2b-2b C2: свои вопросы FAQ объекта — один писатель `object_faq.put`.

Замки: L4 перестановка/удаление/вставка не сдвигают переводы (у всех пяти видов), правка
немецкого снимает перевод своего поля, у события и тура прочие ключи `details` и
`details_i18n` нетронуты; лимиты по виду; «|» в ответе события — по первому; формы услуги и
события пишут через `put`; L7 grep «один писатель».
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.core import faq_content, object_faq

pytestmark = pytest.mark.django_db

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


def make(kind, faq=BASE, ru=RU):
    if kind == "service":
        from apps.booking.models import Service

        return Service.objects.create(
            name="Balayage", duration_minutes=30, faq=faq, faq_i18n={"ru": ru}
        )
    if kind == "product":
        from apps.catalog.tests.factories import ProductFactory

        return ProductFactory(faq=faq, faq_i18n={"ru": ru})
    if kind == "stay":
        from apps.stays.models import StayUnit

        return StayUnit.objects.create(name="FeWo", price_cents=9000, faq=faq, faq_i18n={"ru": ru})
    from apps.events.models import Event, Tour

    details = {"idea": "Musik.", "bring": ["Decke"], "faq": faq}
    i18n = {"ru": {"idea": "Музыка.", "faq": ru}, "en": {"idea": "Music."}}
    if kind == "event":
        return Event.objects.create(
            title="Konzert",
            starts_at=timezone.now() + timedelta(days=7),
            details=details,
            details_i18n=i18n,
        )
    return Tour.objects.create(title="Tour", slug="tour-x", details=details, details_i18n=i18n)


def ru_of(obj, kind):
    return object_faq.overlays(obj, kind).get("ru")


KINDS = list(object_faq.KINDS)


@pytest.mark.parametrize("kind", KINDS)
def test_reorder_delete_insert_keep_translations(kind):
    obj = make(kind)
    fp = object_faq.fingerprint(obj, kind)
    new = [BASE[2], {"q": "Neu?", "a": "x"}, BASE[0]]  # Lieferung удалён, вставка в середину
    fields = object_faq.put(obj, kind, new, [2, None, 0], fp)
    obj.save(update_fields=fields)
    obj.refresh_from_db()
    assert object_faq.items(obj, kind) == new
    assert ru_of(obj, kind) == [RU[2], {}, RU[0]]


@pytest.mark.parametrize("kind", KINDS)
def test_german_edit_drops_only_that_field(kind):
    obj = make(kind)
    new = [{**BASE[0], "a": "Nein."}, *BASE[1:]]
    object_faq.put(obj, kind, new, [0, 1, 2], object_faq.fingerprint(obj, kind))
    assert ru_of(obj, kind)[0] == {"q": RU[0]["q"]}
    assert ru_of(obj, kind)[1:] == RU[1:]


@pytest.mark.parametrize("kind", KINDS)
def test_stale_base_matches_by_text(kind):
    obj = make(kind)
    object_faq.put(obj, kind, BASE[::-1], [0, 1, 2], "0" * 16)
    assert ru_of(obj, kind) == RU[::-1]


@pytest.mark.parametrize("kind", ["event", "tour"])
def test_event_put_touches_only_faq(kind):
    obj = make(kind)
    fields = object_faq.put(obj, kind, BASE[:1], [0], object_faq.fingerprint(obj, kind))
    assert sorted(fields) == ["details", "details_i18n"]
    assert obj.details == {"idea": "Musik.", "bring": ["Decke"], "faq": BASE[:1]}
    assert obj.details_i18n == {"ru": {"idea": "Музыка.", "faq": RU[:1]}, "en": {"idea": "Music."}}
    object_faq.put(obj, kind, [], [])
    assert obj.details_i18n == {"ru": {"idea": "Музыка."}, "en": {"idea": "Music."}}


@pytest.mark.parametrize("kind", KINDS)
def test_put_without_change_reports_no_fields(kind):
    obj = make(kind)
    assert object_faq.put(obj, kind, BASE, [0, 1, 2], object_faq.fingerprint(obj, kind)) == []


def test_object_remap_is_the_shared_remap():
    """Перевод своих вопросов — тот же разбор, что у общего FAQ (L2)."""
    cfg = {"faq": list(BASE), "i18n": {"ru": {"faq": list(RU)}}}
    new = [BASE[1], {"q": "Neu?", "a": ""}, {**BASE[0], "q": "Parken?"}]
    faq_content.put(cfg, new, [1, None, 0], faq_content.fingerprint(BASE))
    obj = make("product")
    object_faq.put(obj, "product", new, [1, None, 0], object_faq.fingerprint(obj, "product"))
    assert obj.faq_i18n == {"ru": cfg["i18n"]["ru"]["faq"]}


@pytest.mark.parametrize(
    ("kind", "limits"),
    [("service", (12, 200, 1000)), ("product", (12, 200, 1000)), ("stay", (12, 200, 1000)),
     ("event", (30, 200, 2000)), ("tour", (30, 200, 2000))],
)  # fmt: skip
def test_limits_by_kind(kind, limits):
    n, q, a = limits
    notes = []
    rows = [{"q": "Q" * (q + 5), "a": "A" * (a + 5)}] + [{"q": f"F{i}", "a": ""} for i in range(n)]
    items, src = object_faq.clean_input(rows, kind, notes)
    assert len(items) == n and len(items[0]["q"]) == q and len(items[0]["a"]) == a
    assert len(notes) == 2 and str(n) in notes[1]


def test_event_line_splits_at_the_first_bar():
    from apps.events import details

    got = details.normalize({"faq": ["Kosten? | 10 € | ermäßigt 5 €", "Nur Frage"]})["faq"]
    assert got == [{"q": "Kosten?", "a": "10 € | ermäßigt 5 €"}, {"q": "Nur Frage", "a": ""}]
    text = details.records_to_text(got, ("q", "a"))
    assert details.normalize({"faq": text.splitlines()})["faq"] == got
    other = details.normalize({"includes": ["Yoga | sanft | extra"]})["includes"]
    assert other == [{"title": "Yoga", "text": "sanft"}]  # прочие записи — как раньше


def test_event_form_writes_faq_through_put_and_keeps_translations():
    """Форма события: перестановка строк textarea — переводы за вопросом (по тексту)."""
    from apps.events import landing

    obj = make("event")
    landing.apply(obj, "event", {"faq_text": "Karte? | Online.\nParkplatz? | Ja.", "idea": "Neu"})
    assert object_faq.items(obj, "event") == [BASE[2], BASE[0]]
    assert obj.details["idea"] == "Neu"
    assert obj.details_i18n["ru"] == {"idea": "Музыка.", "faq": [RU[2], RU[0]]}


def test_service_form_explicit_translations():
    obj = make("service")
    fields = object_faq.put(
        obj, "service", BASE[:1], per_locale={"ru": [{"q": "Парк?"}]}, tenant=None
    )
    assert obj.faq == BASE[:1] and "faq" in fields


@pytest.mark.parametrize("kind", ["product", "stay"])
def test_accessors_of_product_and_stay(kind):
    from django.utils import translation

    obj = make(kind)
    assert obj.faq_list == BASE
    with translation.override("ru"):
        assert obj.faq_localized() == RU
    assert obj.faq_localized("de") == BASE


def test_form_rows_and_from_form_round_trip():
    obj = make("product")
    rows = object_faq.form_rows(obj, "product", ["ru"])
    assert len(rows) == 4 and rows[0]["i18n"][0]["q"] == RU[0]["q"] and rows[-1]["q"] == ""
    post = {"faq_present": "1"}
    for r in rows:
        post[r["q_name"]], post[r["a_name"]] = r["q"], r["a"]
        for t in r["i18n"]:
            post[t["q_name"]], post[t["a_name"]] = t["q"], t["a"]
    post["faq_q_0"] = ""  # первый вопрос удалён — вместе со своим переводом
    base, per_locale = object_faq.from_form(post, ["ru"], "product")
    assert base == BASE[1:] and per_locale == {"ru": RU[1:]}
    assert object_faq.from_form({}, ["ru"], "product") is None


# ───────────── L7: один писатель ─────────────
ROOT = Path(__file__).resolve().parents[3]
#: запись своих вопросов: поля `faq`/`faq_i18n` объекта, `details["faq"]`, `details_i18n`
WRITE = re.compile(
    r"\.faq\s*=[^=]|\.faq_i18n\s*=[^=]|\.details_i18n\s*=[^=]|"
    r"\"faq_i18n\"\s*,\s*per_locale|details\[\"faq\"\]\s*=[^=]"
)
ALLOWED = {
    "apps/core/object_faq.py",  # единственный писатель
    "apps/tenants/demo_kits.py",  # демо собирает объекты целиком (исключение, как у общего FAQ)
    "apps/tenants/demo_i18n.py",
}


def test_one_writer_of_object_faq():
    bad = []
    for path in (ROOT / "apps").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel or "/migrations/" in rel or rel in ALLOWED:
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if WRITE.search(line) and not line.lstrip().startswith("#"):
                bad.append(f"{rel}:{n}: {line.strip()}")
    assert not bad, "свои вопросы FAQ пишет только object_faq.put:\n" + "\n".join(bad)


def test_object_forms_call_the_writer():
    for rel in ("apps/booking/views.py", "apps/events/landing.py"):
        assert "object_faq.put(" in (ROOT / rel).read_text(), rel
    assert "def _rich_faq" not in (ROOT / "apps/booking/views.py").read_text()
