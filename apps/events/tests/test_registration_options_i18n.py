"""FB-33 стопка 12, срез K («Kindermenü»): варианты select анкеты участника.

Дефект: на витрине (ru/en/tr/uk) варианты «Ernährung», «Erfahrungslevel», «Fahrpraxis»,
«Eigenes Motorrad oder Mietmaschine» шли по-немецки — в `apps/events/registration.py` они
были строками без gettext.

Решение владельца (2026-11-23): вариант — пара `(value, label)`. `value` — прежняя немецкая
строка, одна на всех языках (сохранённые ответы, CSV, ростер и письма её и хранят);
`label` — перевод, виден только в тексте `<option>` формы.
"""

import pathlib
import re
import uuid
from datetime import timedelta

import polib
import pytest
from django.conf import settings
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone, translation
from django.utils.html import escape

from apps.events import participants, public_views, registration, views
from apps.events.models import Event, TicketParticipant
from apps.events.services import book_ticket
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

CTX = "registration option"

# Немецкие значения — как они лежат в сохранённых ответах. Менять нельзя: это данные.
VALUES = {
    "diet": ["Vegetarisch", "Vegan", "Rohkost", "Glutenfrei", "Ayurvedisch", "Kindermenü"],
    "experience": ["Anfänger", "Mittel", "Fortgeschritten"],
    "riding_experience": [
        "Bis 5.000 km",
        "5.000–20.000 km",
        "Über 20.000 km",
        "Offroad-erfahren",
    ],
    "own_bike": ["Mietmaschine", "Eigenes Motorrad"],
}
ALL_VALUES = [v for group in VALUES.values() for v in group]
OTHER_LOCALES = ["en", "tr", "ru", "uk"]


# Строка `<select>` анкеты на странице события ДО среза (шаблон базы beba8b6, язык de).
SELECT_DE_BEFORE = (
    '<select name="reg_diet" class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2.5'
    ' bg-white">\n'
    '                  <option value="">–</option>\n'
    "                  "
    + "".join(f'<option value="{v}">{v}</option>' for v in VALUES["diet"])
    + "\n                </select>"
)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _Tenant:
    stripe_connect_id = ""
    site_config = {}

    def is_module_active(self, name):
        return True


def _event(**kw):
    data = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=20),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 0,
        "capacity": 20,
        "registration_fields": ["diet"],
    }
    data.update(kw)
    return Event.objects.create(**data)


def _detail_html(event, lang):
    request = RequestFactory().get("/")
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.0.7"
    request.tenant = TenantFactory.build()
    with translation.override(lang):
        return public_views.veranstaltung_detail(request, pk=event.pk).content.decode()


def _select(html, name="reg_diet"):
    found = re.search(rf'<select name="{name}".*?</select>', html, re.S)
    assert found, f"нет <select name={name}>"
    return found.group(0)


def _option_text_stripped(select_html):
    """Тот же `<select>` без текста вариантов — всё, кроме подписи, должно совпасть."""
    return re.sub(r"(<option [^>]*>)[^<]*(</option>)", r"\1\2", select_html)


def _guest_page(ticket, lang):
    request = RequestFactory().get("/")
    request.tenant = _Tenant()
    request.session = {}
    request._messages = FallbackStorage(request)
    with translation.override(lang):
        return public_views.veranstaltung_participants(
            request, participants.token(ticket)
        ).content.decode()


def _owner_request():
    from django.contrib.auth import get_user_model

    from apps.core.models import Membership

    request = RequestFactory().get("/dashboard/events/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(enabled_modules=["events"])
    user = get_user_model().objects.create_user(
        username=f"k-{uuid.uuid4().hex[:10]}", password="pw12345678"
    )
    Membership.objects.create(user=user, role="owner")
    request.user = user
    return request


# --- №6, №12: value стабилен -------------------------------------------------
def test_option_value_stable():
    """`value` — немецкая строка на любом языке и обычный `str` (не ленивый перевод)."""
    for lang in ["de", *OTHER_LOCALES]:
        with translation.override(lang):
            for field in registration.FIELDS:
                if field["type"] != "select":
                    continue
                pairs = [tuple(opt) for opt in field["options"]]
                assert all(len(p) == 2 for p in pairs), field["key"]
                values = [value for value, _label in pairs]
                assert values == VALUES[field["key"]], (lang, field["key"])
                assert all(type(v) is str for v in values), field["key"]


def test_select_fields_are_exactly_the_known_four():
    """Новое поле-select без строки в этом замке не появляется молча."""
    selects = [f["key"] for f in registration.FIELDS if f["type"] == "select"]
    assert selects == list(VALUES)


def test_collect_stores_german_value_under_ru():
    with translation.override("ru"):
        out = registration.collect(["diet", "experience"], {"reg_diet": "Kindermenü"})
    assert out == {"diet": "Kindermenü"}


def test_label_is_translated_under_ru():
    with translation.override("ru"):
        labels = {value: str(label) for value, label in registration.FIELDS[3]["options"]}
    assert labels["Kindermenü"] == "Детское меню"
    assert labels["Vegan"] == "Веганское"


# --- №13: форма на витрине ---------------------------------------------------
def test_storefront_form_ru_translates_text_keeps_value():
    html = _select(_detail_html(_event(), "ru"))
    assert '<option value="Kindermenü">Детское меню</option>' in html
    assert '<option value="Vegetarisch">Вегетарианское</option>' in html
    assert ">Kindermenü<" not in html


@pytest.mark.parametrize("lang", OTHER_LOCALES)
def test_storefront_form_no_german_option_text(lang):
    """Ни один вариант ни одного select не остаётся с немецкой подписью, если в каталоге
    языка у него другой перевод (совпадающие написания — «Vegan» — не в счёт)."""
    event = _event(registration_fields=list(VALUES))
    html = _detail_html(event, lang)
    po = polib.pofile(str(_po_path(lang)))
    for key, values in VALUES.items():
        select = _select(html, f"reg_{key}")
        for value in values:
            entry = po.find(value, msgctxt=CTX)
            assert entry is not None, (lang, value)
            want = f'<option value="{value}">{escape(entry.msgstr)}</option>'
            assert want in select, (lang, value)


# --- замер: de байт-в-байт, на ru меняется только текст <option> ---------------
def test_storefront_select_de_byte_identical_to_base():
    assert _select(_detail_html(_event(), "de")) == SELECT_DE_BEFORE


def test_storefront_ru_differs_from_de_only_in_option_text():
    event = _event(registration_fields=list(VALUES))
    de, ru = _detail_html(event, "de"), _detail_html(event, "ru")
    for key in VALUES:
        de_select, ru_select = _select(de, f"reg_{key}"), _select(ru, f"reg_{key}")
        assert de_select != ru_select, key
        assert _option_text_stripped(de_select) == _option_text_stripped(ru_select), key


# --- selected по value: страница участника и карточка билета в кабинете --------
def test_guest_participants_selected_by_value_under_ru():
    ticket = book_ticket(_event(), name="Anna", email="a@t.de", quantity=2, auto_confirm=True)
    TicketParticipant.objects.create(
        ticket=ticket, position=2, name="Ben", answers={"diet": "Kindermenü"}
    )
    html = _guest_page(ticket, "ru")
    second = _select(html, "p2_reg_diet")
    assert '<option value="Kindermenü" selected>Детское меню</option>' in second
    assert second.count(" selected") == 1
    assert " selected" not in _select(html, "p1_reg_diet")


def test_guest_participants_de_byte_identical_options():
    ticket = book_ticket(_event(), name="Anna", email="a@t.de", quantity=1, auto_confirm=True)
    TicketParticipant.objects.create(
        ticket=ticket, position=1, name="Anna", answers={"diet": "Vegan"}
    )
    select = _select(_guest_page(ticket, "de"), "p1_reg_diet")
    expected = "".join(
        f'<option value="{v}"{" selected" if v == "Vegan" else ""}>{v}</option>'
        for v in VALUES["diet"]
    )
    assert expected in select


def test_cabinet_ticket_selected_by_value_under_ru(monkeypatch):
    monkeypatch.setattr("apps.core.roles.is_owner", lambda user: True)
    ticket = book_ticket(_event(), name="Anna", email="a@t.de", quantity=1, auto_confirm=True)
    TicketParticipant.objects.create(
        ticket=ticket, position=1, name="Anna", answers={"diet": "Kindermenü"}
    )
    with translation.override("ru"):
        html = views.ticket_detail(_owner_request(), pk=ticket.pk).content.decode()
    select = _select(html, "p1_reg_diet")
    assert '<option value="Kindermenü" selected>Детское меню</option>' in select
    assert select.count(" selected") == 1


# --- ростер CSV не меняется ----------------------------------------------------
def test_roster_csv_unchanged(monkeypatch):
    """В CSV — немецкое значение ответа на любом языке кабинета; перевода варианта нет."""
    monkeypatch.setattr("apps.core.roles.is_owner", lambda user: True)
    event = _event(registration_fields=["diet", "experience"])
    book_ticket(
        event,
        name="Anna",
        email="a@test.de",
        answers={"diet": "Kindermenü", "experience": "Mittel"},
        auto_confirm=True,
    )
    bodies = {}
    for lang in ["de", "ru"]:
        with translation.override(lang):
            bodies[lang] = views.roster_csv(_owner_request(), pk=event.pk).content.decode(
                "utf-8-sig"
            )
    for lang, body in bodies.items():
        row = body.splitlines()[1]
        assert row.endswith(";Kindermenü;Mittel"), (lang, row)
        assert "Детское меню" not in body and "Средний" not in body, lang
    assert bodies["de"].splitlines()[0].endswith(";Ernährung;Erfahrungslevel")


# --- №16: все пять .po -----------------------------------------------------------
def _po_path(lang):
    return pathlib.Path(settings.BASE_DIR) / "locale" / lang / "LC_MESSAGES" / "django.po"


@pytest.mark.parametrize("lang", ["de", *OTHER_LOCALES])
def test_every_option_in_po_with_context(lang):
    po = polib.pofile(str(_po_path(lang)))
    missing, empty = [], []
    for value in ALL_VALUES:
        hits = [e for e in po if e.msgctxt == CTX and e.msgid == value and not e.obsolete]
        if not hits:
            missing.append(value)
            continue
        assert len(hits) == 1, f"дубль ({CTX}, {value}) в {lang}"
        if not hits[0].msgstr or hits[0].fuzzy:
            empty.append(value)
    assert not missing, f"{lang}: нет записи с msgctxt «{CTX}»: {missing}"
    assert not empty, f"{lang}: пустой или fuzzy перевод: {empty}"


def test_po_has_no_extra_registration_options():
    """В каталоге нет записей контекста, которых нет в реестре (опечатка value, старое имя)."""
    for lang in ["de", *OTHER_LOCALES]:
        po = polib.pofile(str(_po_path(lang)))
        extra = [e.msgid for e in po if e.msgctxt == CTX and e.msgid not in ALL_VALUES]
        assert not extra, (lang, extra)
