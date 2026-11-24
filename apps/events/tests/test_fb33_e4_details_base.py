"""FB-33 стопка 14 E4: форма события и тура не перетирает чужую правку `details`.

Форма несёт отпечаток `details_base` (`details` без `faq`, `apps/events/landing.py::fingerprint`),
он рендерится рядом с `faq_base`. Запись формы (`apps/events/views.py::_save_form_fresh`) сверяет
его под ОДНОЙ блокировкой строки, и та же строка уходит в `object_faq._sync` (ревью M7).
Расхождение — отказ ДО записи: ответ 200 с набранным, свои вопросы из POST, свежий отпечаток,
сообщение перед `<form>` (a11y L5) с просьбой выбрать фото заново. Повторный POST перезаписывает
осознанно (решение владельца). Поля в POST нет (форма открыта до деплоя) — проверки нет.
"""

import html
import logging
import re
from pathlib import Path

import polib
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.http import Http404
from django.test.utils import CaptureQueriesContext

from apps.events import views
from apps.events.models import Event, Tour
from apps.events.tests.test_tours import _cab

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]

KINDS = ("event", "tour")
CONFLICT = (
    "Die Seite dieses Angebots wurde inzwischen an anderer Stelle geändert – nichts wurde "
    "gespeichert. Ihre Eingaben stehen unten, Fotos bitte erneut auswählen. Bitte prüfen und "
    "erneut speichern."
)
MSGIDS = (CONFLICT,)
# Строку во все пять `.po` пишет координатор на верхушке стопки — тогда снять отметку.
OWN = [{"q": "Parken?", "a": "Ja."}]
REVIEW = pytest.mark.xfail(strict=True, reason="FB-33 стопка 14 E4: правки ревью диффа")
IMG = {"id": "img1", "url": "/media/x.jpg", "is_primary": True}
GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00"
    b"\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _model(kind):
    return Event if kind == "event" else Tour


def _make(kind, details):
    if kind == "event":
        return Event.objects.create(
            title="Konzert", starts_at="2030-01-01T10:00:00Z", details=details
        )
    return Tour.objects.create(
        title="Manali – Leh", slug=f"manali-{Tour.objects.count()}", details=details
    )


def _view(kind):
    return views.event_edit if kind == "event" else views.tour_edit


def _data(kind, obj, **extra):
    if kind == "event":
        data = {
            "title": obj.title,
            "starts_at": "2030-01-01T10:00",
            "capacity": 0,
            "price_eur": "0",
        }
    else:
        data = {"title": obj.title, "sort_order": "0"}
    data.update(extra)
    return data


def _get(kind, obj) -> str:
    resp = _view(kind)(_cab(), pk=obj.pk)
    assert resp.status_code == 200
    return resp.content.decode()


def _post(kind, obj, data):
    return _view(kind)(_cab(method="post", data=data), pk=obj.pk)


def _base_in(page: str):
    m = re.search(r'name="details_base" value="([^"]*)"', page)
    return html.unescape(m.group(1)) if m else None


def _with_base(data: dict, page: str) -> dict:
    base = _base_in(page)
    if base is not None:
        data["details_base"] = base
    return data


def _foreign(obj, **changes):
    """Чужая правка `details` в другом месте (окно, второй сотрудник)."""
    fresh = type(obj).objects.get(pk=obj.pk)
    details = dict(fresh.details) if isinstance(fresh.details, dict) else {}
    details.update(changes)
    type(obj).objects.filter(pk=obj.pk).update(details=details)


def _conflict(kind):
    """Форма открыта → чужая правка `idea` → POST с набранным."""
    obj = _make(kind, {"idea": "Alt", "faq": OWN})
    page = _get(kind, obj)
    _foreign(obj, idea="Fremd")
    data = _with_base(
        _data(
            kind,
            obj,
            title="Neuer Titel",
            idea="Meins",
            faq_present="1",
            faq_q_0="Meine Frage?",
            faq_a_0="Meine Antwort.",
        ),
        page,
    )
    if kind == "tour":
        data.update(it_present="1", it_day_0="1", it_title_0="Meine Etappe")
    return obj, data


# ───────────── охранные (зелёные на базе) ─────────────


@pytest.mark.parametrize("kind", KINDS)
def test_base_excludes_faq(kind):
    """№1/№11: чужая правка ТОЛЬКО своих вопросов не делает отпечаток формы устаревшим."""
    obj = _make(kind, {"idea": "Alt", "faq": OWN})
    page = _get(kind, obj)
    _foreign(obj, faq=[{"q": "Fremd?", "a": ""}])
    resp = _post(kind, obj, _with_base(_data(kind, obj, idea="Meins"), page))
    assert resp.status_code == 302
    fresh = _model(kind).objects.get(pk=obj.pk)
    assert fresh.details["idea"] == "Meins"
    assert fresh.details["faq"] == [{"q": "Fremd?", "a": ""}]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("legacy", [[], "x"])
def test_legacy_details_not_dict(kind, legacy):
    """№6: старые `details` не-словарём — отпечаток как у `{}`, сохранение проходит."""
    obj = _make(kind, {})
    _model(kind).objects.filter(pk=obj.pk).update(details=legacy)
    page = _get(kind, obj)
    resp = _post(kind, obj, _with_base(_data(kind, obj, idea="Meins"), page))
    assert resp.status_code == 302
    assert _model(kind).objects.get(pk=obj.pk).details["idea"] == "Meins"


@pytest.mark.parametrize("kind", KINDS)
def test_missing_base_no_check(kind):
    """Форма открыта до деплоя (поля `details_base` в POST нет) — проверки нет."""
    obj = _make(kind, {"idea": "Alt"})
    _foreign(obj, idea="Fremd")
    resp = _post(kind, obj, _data(kind, obj, idea="Meins"))
    assert resp.status_code == 302
    assert _model(kind).objects.get(pk=obj.pk).details["idea"] == "Meins"


# ───────────── красные ─────────────


@pytest.mark.parametrize("kind", KINDS)
def test_base_checked_under_lock(kind, monkeypatch):
    """№9 (M7): форма несёт отпечаток; одна `FOR UPDATE` строки раньше её `UPDATE`, и та же
    свежая строка передаётся в `object_faq._sync`."""
    from apps.core import object_faq

    obj = _make(kind, {"idea": "Alt", "faq": OWN})
    page = _get(kind, obj)
    assert _base_in(page), "форма не несёт details_base"
    seen = []
    real_sync = object_faq._sync

    def spy(target, fresh, k):
        seen.append(fresh)
        return real_sync(target, fresh, k)

    monkeypatch.setattr(object_faq, "_sync", spy)
    table = _model(kind)._meta.db_table
    with CaptureQueriesContext(connection) as ctx:
        resp = _post(kind, obj, _with_base(_data(kind, obj, idea="Meins"), page))
    assert resp.status_code == 302
    sqls = [q["sql"] for q in ctx.captured_queries if f'"{table}"' in q["sql"]]
    first_update = next(i for i, s in enumerate(sqls) if s.startswith("UPDATE"))
    locks = [s for s in sqls[:first_update] if "FOR UPDATE" in s]
    assert len(locks) == 1, locks
    assert seen and seen[0].pk == obj.pk and seen[0] is not obj


@pytest.mark.parametrize("kind", KINDS)
def test_conflict_writes_nothing(kind):
    """№10: отказ до записи — ни поля формы, ни `details`, ни свои вопросы, ни маршрут."""
    obj, data = _conflict(kind)
    _model(kind).objects.filter(pk=obj.pk).update(images=[IMG])
    data.update(
        photos=SimpleUploadedFile("neu.gif", GIF, content_type="image/gif"),
        delete_image="img1",
        page_override_present="1",
        ps_layout="tabs",
    )
    before = _model(kind).objects.get(pk=obj.pk)
    resp = _post(kind, obj, data)
    assert resp.status_code == 200
    fresh = _model(kind).objects.get(pk=obj.pk)
    assert fresh.images == [IMG]  # ни загрузки, ни удаления
    assert fresh.page_override == before.page_override
    assert fresh.title == before.title
    assert fresh.details == before.details
    assert fresh.details["idea"] == "Fremd" and fresh.details["faq"] == OWN
    if kind == "tour":
        assert fresh.itinerary == before.itinerary


@pytest.mark.parametrize("kind", KINDS)
def test_conflict_returns_typed(kind):
    """№7: 200, набранное и свои вопросы из POST, свежий `details_base`."""
    from apps.events import landing

    obj, data = _conflict(kind)
    resp = _post(kind, obj, data)
    assert resp.status_code == 200
    page = resp.content.decode()
    assert "Meins" in page and "Neuer Titel" in page
    assert "Meine Frage?" in page and "Meine Antwort." in page
    fresh = _model(kind).objects.get(pk=obj.pk)
    assert _base_in(page) == landing.fingerprint(fresh)
    assert _base_in(page) != data["details_base"]


@pytest.mark.parametrize("kind", KINDS)
def test_retry_after_conflict_overwrites(kind):
    """Решение владельца: повторный POST после отказа (свежий отпечаток) пишет набранное."""
    obj, data = _conflict(kind)
    first = _post(kind, obj, data)
    assert first.status_code == 200  # сначала отказ
    resp = _post(kind, obj, _with_base(dict(data), first.content.decode()))
    assert resp.status_code == 302
    assert _model(kind).objects.get(pk=obj.pk).details["idea"] == "Meins"


@REVIEW
@pytest.mark.parametrize("kind", KINDS)
def test_conflict_logged(kind, caplog):
    """№8: отказ в журнале — схема, вид, pk; без значений полей."""
    obj, data = _conflict(kind)
    with caplog.at_level(logging.INFO, logger="apps.events.views"):
        _post(kind, obj, data)
    recs = [r for r in caplog.records if r.name == "apps.events.views"]
    assert all(r.levelno == logging.WARNING for r in recs), "отказ — warning (ревью LOW б)"
    assert recs, "отказ не записан в журнал"
    text = " ".join(r.getMessage() for r in recs)
    assert kind in text and str(obj.pk) in text and connection.schema_name in text
    assert "Meins" not in text and "Fremd" not in text


@pytest.mark.parametrize("kind", KINDS)
def test_second_conflict_in_a_row(kind):
    """Ревью HIGH-1: после отказа снова чужая правка — POST со свежим отпечатком снова отказ."""
    obj, data = _conflict(kind)
    page = _post(kind, obj, data).content.decode()
    _foreign(obj, idea="Fremd 2")
    resp = _post(kind, obj, _with_base(dict(data), page))
    assert resp.status_code == 200
    assert _model(kind).objects.get(pk=obj.pk).details["idea"] == "Fremd 2"


# ───────────── правки ревью диффа (красные) ─────────────


def _invalid(kind, data):
    bad = dict(data)
    if kind == "event":
        bad["starts_at"] = "kein Datum"
    else:
        bad["title"] = ""
    return bad


@REVIEW
@pytest.mark.parametrize("kind", KINDS)
def test_invalid_form_keeps_posted_base(kind):
    """HIGH-1: невалидная форма перерисовывается с отпечатками ИЗ POST, а не свежими — иначе
    после исправления поля чужая правка затёрлась бы молча."""
    from apps.core import object_faq

    obj = _make(kind, {"idea": "Alt", "faq": OWN})
    page = _get(kind, obj)
    base = _base_in(page)
    faq_base = object_faq.fingerprint(obj, kind)
    _foreign(obj, idea="Fremd", faq=[{"q": "Fremd?", "a": ""}])
    data = _with_base(_data(kind, obj, idea="Meins", faq_base=faq_base), page)
    resp = _post(kind, obj, _invalid(kind, data))
    assert resp.status_code == 200
    again = resp.content.decode()
    assert _base_in(again) == base
    assert f'value="{faq_base}"' in again
    resp = _post(kind, obj, _with_base(dict(data), again))
    assert resp.status_code == 200  # отказ
    assert _model(kind).objects.get(pk=obj.pk).details["idea"] == "Fremd"


@REVIEW
@pytest.mark.parametrize("kind", KINDS)
def test_conflict_keeps_typed_route_and_layout(kind):
    """HIGH-2: при отказе маршрут тура и шаблон страницы — как набраны, база не меняется."""
    obj, data = _conflict(kind)
    data.update(page_override_present="1", ps_layout="tabs")
    before = _model(kind).objects.get(pk=obj.pk)
    page = _post(kind, obj, data).content.decode()
    assert re.search(r'name="ps_layout" value="tabs" checked', page)
    fresh = _model(kind).objects.get(pk=obj.pk)
    assert fresh.page_override == before.page_override
    if kind == "tour":
        assert 'value="Meine Etappe"' in page
        assert fresh.itinerary == before.itinerary


@REVIEW
@pytest.mark.parametrize("kind", KINDS)
def test_conflict_rows_beyond_limit(kind):
    """MEDIUM а: сохранённые сверх лимита вопросы (данные до среза) при отказе не режутся."""
    from apps.core import object_faq

    n = object_faq.KINDS[kind].max_items + 2
    many = [{"q": f"Frage {i}?", "a": ""} for i in range(n)]
    obj = _make(kind, {"idea": "Alt", "faq": many})
    page = _get(kind, obj)
    _foreign(obj, idea="Fremd")
    data = _with_base(_data(kind, obj, idea="Meins", faq_present="1"), page)
    for i, item in enumerate(many):
        data[f"faq_q_{i}"] = item["q"]
        data[f"faq_a_{i}"] = ""
    out = _post(kind, obj, data).content.decode()
    for item in many:
        assert f'value="{item["q"]}"' in out or f">{item['q']}<" in out, item


@REVIEW
@pytest.mark.parametrize("kind", KINDS)
def test_conflict_with_faq_changed_two_messages(kind):
    """MEDIUM б: вопросы тоже изменены в другом месте — в отказе второе (уже существующее)
    сообщение `object_faq.form_changed_note`."""
    from apps.core import object_faq

    obj, data = _conflict(kind)
    data["faq_base"] = object_faq.fingerprint(obj, kind)
    _foreign(obj, faq=[{"q": "Fremd?", "a": ""}])
    page = _post(kind, obj, data).content.decode()
    assert html.escape(CONFLICT) in page
    assert html.escape(object_faq.form_changed_note()) in page


@REVIEW
@pytest.mark.parametrize("kind", KINDS)
def test_deleted_row_404(kind, monkeypatch):
    """LOW а: строку удалили параллельно (после чтения вьюхи) — 404 до записи, объект не
    воскресает."""
    obj = _make(kind, {"idea": "Alt"})
    page = _get(kind, obj)
    stale = _model(kind).objects.get(pk=obj.pk)
    _model(kind).objects.filter(pk=obj.pk).delete()
    monkeypatch.setattr(views, "get_object_or_404", lambda *a, **k: stale)
    with pytest.raises(Http404):
        _post(kind, obj, _with_base(_data(kind, obj, idea="Meins"), page))
    assert not _model(kind).objects.filter(pk=obj.pk).exists()


@pytest.mark.parametrize("kind", KINDS)
def test_conflict_message_before_form(kind):
    """L5: сообщение отказа — перед `<form>` в DOM, с просьбой выбрать фото заново."""
    obj, data = _conflict(kind)
    page = _post(kind, obj, data).content.decode()
    at = page.find(html.escape(CONFLICT))
    assert at != -1, "нет сообщения отказа"
    assert "Fotos bitte erneut auswählen" in CONFLICT
    assert at < page.find('<form method="post" enctype="multipart/form-data"')
    assert 'role="alert"' in page[max(0, at - 300) : at]


def test_e4_msgids_in_all_po():
    """№16: новая строка E4 во всех пяти каталогах (пишет координатор на верхушке)."""
    for lang in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        have = {(e.msgctxt, e.msgid): e.msgstr for e in po if not e.obsolete}
        for msgid in MSGIDS:
            assert (None, msgid) in have, (lang, msgid)
            if lang != "de":
                assert have[(None, msgid)], (lang, msgid)
