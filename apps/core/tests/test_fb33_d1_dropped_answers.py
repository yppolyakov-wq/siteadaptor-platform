"""FB-33 D1: ответ на удалённый или изменённый вопрос корзины и заявки не пропадает молча.

План — `docs/fb33-stack13-plan-2026-11-24.md` §2 D1 и правки ревью §10 (H5, M1, M7, M8).
Решение владельца (вариант A): ответ на вопрос, удалённый между показом формы и отправкой,
хранится в снимке сделки строкой `stale="removed"` (подпись «Entfernte Frage» — при показе),
ответ выбора вне текущих вариантов — `stale="changed"` с подписью вопроса и пометкой
«(nicht mehr in der Liste)». Подпись из POST не берётся. Номер `q<n>` хранится, только если
бизнес его выдавал (`n <= next_id`). В лог INFO идут только id и число — без значений (ПДн).
Показ — единый `form_answers.rows`: карточка, письмо владельцу, KDS, ЛК, PDF заявки.
"""

import logging
import uuid
from decimal import Decimal
from pathlib import Path

import polib
import pytest
from django.http import QueryDict
from django.template.loader import render_to_string
from django.utils import translation

from apps.catalog.tests.factories import ProductFactory
from apps.core import deal_card, form_answers
from apps.core.tests.test_fb33_m2i2_before import _quote_text, quote_job
from apps.core.tests.test_fb33_m2i_before import _post_anfrage

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
LOGGER = "apps.core.form_answers"

QUESTIONS = [
    {"id": "q1", "type": "text", "label": "Allergien"},
    {"id": "q3", "type": "choice", "label": "Besteck", "options": ["Ja", "Nein"]},
]
#: q2 был у бизнеса и удалён (номер выдан: next_id = 3)
NEXT_ID = 3

SECRET = "Erdnuss-Allergie-geheim"


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _ff(form, questions=QUESTIONS, next_id=NEXT_ID):
    entry = {"custom": questions}
    if next_id:
        entry["next_id"] = next_id
    return {"form_fields": {form: entry}}


def _checkout(data, cfg):
    from apps.orders import public_views
    from apps.orders.models import Order
    from apps.orders.tests.test_payment_methods import _pub_req
    from apps.tenants.tests.factories import TenantFactory

    product = ProductFactory(base_price=Decimal("10.00"))
    request = _pub_req(
        {"name": "Kim", **data},
        tenant=TenantFactory.build(site_config=cfg),
        session={"cart": {str(product.pk): 1}},
    )
    public_views.checkout(request)
    return Order.objects.get().custom_answers


def _anfrage(data, cfg):
    from apps.jobs.models import Job

    _post_anfrage({"title": "Fest", "name": "A", "phone": "1", **data}, cfg)
    return Job.objects.get().custom_answers


DEALS = {"checkout": _checkout, "anfrage": _anfrage}


def _records(caplog):
    return [r for r in caplog.records if r.name == LOGGER]


def _post(data):
    q = QueryDict(mutable=True)
    for key, value in data.items():
        q[key] = value
    return q


# --- лог: какие ответы не легли в снимок как ответы ------------------------------------------


@pytest.mark.parametrize("form", sorted(DEALS))
def test_removed_question_answer_logged(form, caplog):
    """Вопрос удалён между GET и POST — сделка создана, в логе INFO его id."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    DEALS[form]({"q1": "Nüsse", "q2": "Bitte ohne Zwiebeln"}, _ff(form))
    lines = [r.getMessage() for r in _records(caplog) if r.levelno == logging.INFO]
    assert lines and "q2" in lines[-1], lines


def test_dropped_ids_exact():
    """`q1` задан, пришли `q1` и `q10` — лишний только `q10`; служебные поля и временные
    `n1` не считаются; пустые значения — не ответ."""
    post = _post(
        {
            "q1": "x",
            "q10": "y",
            "q11": "  ",
            "name": "Kim",
            "email": "k@example.com",
            "csrfmiddlewaretoken": "t",
            "website": "spam",
            "n1": "draft",
            "q0": "zero",
        }
    )
    assert form_answers.dropped(QUESTIONS[:1], post) == ["q10"]


def test_changed_choice_logged(caplog):
    """Вариант удалён — ответ не идёт обычным ответом, id в логе."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    snap = form_answers.answers_for_deal(
        QUESTIONS, _post({"q3": "Vielleicht"}), kind="order", next_id=NEXT_ID
    )
    assert snap["q3"].get("stale") == "changed"
    assert "q3" in _records(caplog)[-1].getMessage()


def test_broken_number_logged_not_stored(caplog):
    """Битое число — ошибка ввода гостя, не правка владельца: не хранится, только лог."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    questions = [{"id": "q1", "type": "number", "label": "Personen"}]
    snap = form_answers.answers_for_deal(questions, _post({"q1": "zwei"}), kind="order", next_id=1)
    assert snap == {}
    assert "q1" in _records(caplog)[-1].getMessage()


def test_log_has_no_answer_values(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    form_answers.answers_for_deal(
        QUESTIONS,
        _post({"q2": SECRET, "q3": SECRET + "x", "q1": SECRET + "y"}),
        kind="job",
        next_id=NEXT_ID,
    )
    records = _records(caplog)
    assert records
    for record in records:
        assert SECRET not in record.getMessage()
        assert SECRET not in repr(record.args)


def test_orphan_log_id_is_ascii_fullmatch(caplog):
    """`q5\\n` и не-ASCII цифры — не id: не хранятся и в лог не попадают."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    post = _post({"q2\n": "a", "q２": "b", "Q2": "c", " q2": "d"})
    assert form_answers.dropped(QUESTIONS, post) == []
    assert form_answers.answers_for_deal(QUESTIONS, post, kind="order", next_id=9) == {}
    assert not _records(caplog)


# --- решение A: хранится с пометкой ------------------------------------------------------------


@pytest.mark.parametrize("form", sorted(DEALS))
def test_removed_question_answer_stored(form):
    snap = DEALS[form]({"q1": "Nüsse", "q2": "Bitte ohne Zwiebeln"}, _ff(form))
    assert snap["q2"] == {
        "label": "",
        "value": "Bitte ohne Zwiebeln",
        "type": "text",
        "stale": "removed",
    }
    with translation.override("de"):
        assert ("Entfernte Frage", "Bitte ohne Zwiebeln") in form_answers.rows(snap)


def test_changed_choice_stored():
    snap = form_answers.answers_for_deal(
        QUESTIONS, _post({"q3": "Vielleicht"}), kind="order", next_id=NEXT_ID
    )
    assert snap == {
        "q3": {"label": "Besteck", "value": "Vielleicht", "type": "text", "stale": "changed"}
    }
    with translation.override("de"):
        assert form_answers.rows(snap) == [("Besteck", "Vielleicht (nicht mehr in der Liste)")]


def test_stale_capped_and_trimmed():
    post = _post({f"q{n}": "x" * 1000 for n in range(10, 40)})
    snap = form_answers.answers_for_deal(QUESTIONS[:1], post, kind="order", next_id=100)
    assert len(snap) == form_answers.STALE_MAX
    assert all(len(item["value"]) == form_answers.LABEL_MAX * 2 for item in snap.values())


def test_orphan_not_stored_when_tenant_never_had_questions():
    snap = form_answers.answers_for_deal([], _post({"q1": "x"}), kind="order", next_id=0)
    assert snap == {}


def test_orphan_not_stored_above_next_id():
    snap = form_answers.answers_for_deal(
        QUESTIONS, _post({"q2": "a", "q4": "b"}), kind="order", next_id=NEXT_ID
    )
    assert set(snap) == {"q2"}


def test_stale_removed_row_rendered_by_rows():
    """Пустая подпись у строки `removed` — не мусор: ветка `stale` раньше проверки подписи."""
    snap = {"q2": {"label": "", "value": "Text", "type": "text", "stale": "removed"}}
    with translation.override("de"):
        assert form_answers.rows(snap) == [("Entfernte Frage", "Text")]
    with translation.override("ru"):
        ((label, value),) = form_answers.rows(snap)
    assert label != "Entfernte Frage" and value == "Text"


def test_old_snapshots_render_same():
    """Снимки без `stale` рисуются как раньше; пустая подпись без признака — пропуск."""
    old = {
        "q1": {"label": "Anlass", "value": "Hochzeit"},
        "q2": {"label": "", "value": "x"},
        "q3": {"label": "Vegetarisch", "value": True, "type": "bool"},
    }
    with translation.override("de"):
        assert form_answers.rows(old) == [("Anlass", "Hochzeit"), ("Vegetarisch", "Ja")]


STALE = {
    "q1": {"label": "Allergien", "value": "Nüsse", "type": "text"},
    "q2": {"label": "", "value": "Ohne Zwiebeln", "type": "text", "stale": "removed"},
    "q3": {"label": "Besteck", "value": "Vielleicht", "type": "text", "stale": "changed"},
}


def test_stale_shown_everywhere(monkeypatch):
    """Карточка, письмо владельцу, KDS, ЛК и PDF заявки — через `rows`, второго пути нет."""
    from apps.account import account_data
    from apps.jobs import notifications as job_notifications
    from apps.orders import notifications, services, views
    from apps.orders.models import Order
    from apps.orders.tests.test_kitchen import _req as _cab_req
    from apps.promotions.models import Customer

    order = services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}), 1)],
        name="Kim",
        email=f"k-{uuid.uuid4().hex[:6]}@example.com",
    )
    Order.objects.filter(pk=order.pk).update(custom_answers=dict(STALE))
    order.refresh_from_db()
    with translation.override("de"):
        card = views.order_detail(
            _cab_req(path=f"/dashboard/orders/{order.pk}/"), pk=order.pk
        ).content.decode()
        kds = views.kitchen_board(_cab_req()).content.decode()
        account = account_data._orders(Customer.objects.get(pk=order.customer_id))
        sent = []
        monkeypatch.setattr(notifications, "notify", lambda **kw: sent.append(kw))
        monkeypatch.setattr(notifications, "_owner_email", lambda tenant: "owner@example.com")
        monkeypatch.setattr(notifications, "channel_enabled", lambda *a: True)
        notifications.enqueue_order_email(order, "created")
        owner = {m["type"]: m for m in sent}["order_created_owner"]["body"]

        job = quote_job(custom_answers=dict(STALE))
        job_mail = render_to_string(
            "emails/job_new.txt",
            {
                "job": job,
                "customer": job.customer,
                "custom_answers": job_notifications._owner_answers(job),
            },
        )
        pdf = _quote_text(job)
    for html in (card, kds):
        assert "Entfernte Frage" in html and "Ohne Zwiebeln" in html
        assert "Vielleicht (nicht mehr in der Liste)" in html
    assert ("Entfernte Frage", "Ohne Zwiebeln") in account["items"][0]["answers"]
    for text in (owner, job_mail):
        assert "Entfernte Frage: Ohne Zwiebeln" in text
        assert "Besteck: Vielleicht (nicht mehr in der Liste)" in text
    assert "Entfernte Frage" in pdf and "Ohne Zwiebeln" in pdf
    assert deal_card._custom_answers(order) == form_answers.rows(STALE)


def test_deal_answers_one_path(monkeypatch):
    """Корзина и заявка строят снимок одной функцией: подмена видна в обоих."""
    marker = {"q9": {"label": "M", "value": "m", "type": "text"}}
    calls = []

    def fake(questions, post, *, kind, next_id, prefix=""):
        calls.append((kind, next_id))
        return dict(marker)

    monkeypatch.setattr(form_answers, "answers_for_deal", fake)
    assert _checkout({"q1": "a"}, _ff("checkout")) == marker
    from apps.jobs.models import Job
    from apps.orders.models import Order

    Order.objects.all().delete()
    Job.objects.all().delete()
    assert _anfrage({"q1": "a"}, _ff("anfrage")) == marker
    assert calls == [("order", NEXT_ID), ("job", NEXT_ID)]


MSGIDS = [("form answer", "Entfernte Frage"), ("form answer", "(nicht mehr in der Liste)")]


def test_d1_msgids_in_all_po():
    for lang in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        entries = [e for e in po if not e.obsolete]
        pairs = [(e.msgctxt, e.msgid) for e in entries]
        assert len(pairs) == len(set(pairs)), lang
        have = {(e.msgctxt, e.msgid): e.msgstr for e in entries}
        for pair in MSGIDS:
            assert pair in have, (lang, pair)
            if lang != "de":
                assert have[pair] and have[pair] != pair[1], (lang, pair)


# --- ревью диффа (план §10.4) -----------------------------------------------------------------
#: замки правок ревью — снимаются своими коммитами
REVIEW = pytest.mark.xfail(strict=True, reason="FB-33 D1 §10.4: до правки")


@REVIEW
@pytest.mark.parametrize(
    "raw, want",
    [
        (7, 7),
        ("7", 7),
        (None, 0),
        ("x", 0),
        (-3, 0),
        (10**9, form_answers.ID_MAX),
        (float("inf"), 0),
    ],
)
def test_next_id_reader(raw, want, caplog):
    """Тонкий читатель номера: тот же зажим, что `normalize`; мусор — 0 и WARNING."""
    from apps.core import form_spec

    site = {"form_fields": {"checkout": {"next_id": raw}}}
    with caplog.at_level(logging.WARNING, logger="apps.core.form_spec"):
        assert form_spec.next_id(site, "checkout") == want
    if raw in ("x", float("inf")):
        assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert form_spec.next_id({}, "anfrage") == 0


@REVIEW
def test_views_read_next_id_through_form_spec(monkeypatch):
    """Корзина и заявка берут номер у `form_spec.next_id`, не через `edit_state`."""
    from apps.core import form_spec

    seen = []
    monkeypatch.setattr(form_spec, "next_id", lambda site, form: seen.append(form) or 2)
    monkeypatch.setattr(
        form_spec, "edit_state", lambda *a, **kw: pytest.fail("edit_state на публичном POST")
    )
    snap = _checkout({"q2": "weg"}, _ff("checkout"))
    assert snap["q2"]["stale"] == "removed"
    from apps.orders.models import Order

    Order.objects.all().delete()
    assert _anfrage({"q2": "weg"}, _ff("anfrage"))["q2"]["stale"] == "removed"
    assert seen == ["checkout", "anfrage"]


@REVIEW
@pytest.mark.parametrize("form", sorted(DEALS))
def test_orphan_not_stored_when_form_has_no_questions(form):
    """Вопросов в форме нет (все удалены) — осиротевший ответ не хранится, как бы ни был
    велик сохранённый номер."""
    snap = DEALS[form]({"q1": "x"}, {"form_fields": {form: {"next_id": 5}}})
    assert snap == {}


@REVIEW
def test_bool_false_not_logged(caplog):
    """Снятая галочка (`0/off/no/false`) — не потерянный ответ."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    questions = [{"id": "q4", "type": "bool", "label": "Geschenk"}]
    for raw in ("0", "off", "no", "false", "OFF"):
        assert form_answers.dropped(questions, _post({"q4": raw})) == []
    form_answers.answers_for_deal(questions, _post({"q4": "0"}), kind="order", next_id=4)
    assert not _records(caplog)


@REVIEW
def test_lost_answers_warn_with_schema(caplog):
    """Сохранено меньше потерянного — WARNING со схемой; названы потерянные id; без значений."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    post = _post({f"q{n}": SECRET for n in range(2, 13)})  # 11 осиротевших
    snap = form_answers.answers_for_deal(QUESTIONS[:1], post, kind="order", next_id=100)
    assert len(snap) == form_answers.STALE_MAX
    (record,) = _records(caplog)
    message = record.getMessage()
    assert record.levelno == logging.WARNING and "schema=" in message
    assert "q12" in message and SECRET not in message


@REVIEW
def test_everything_kept_logs_info(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    form_answers.answers_for_deal(QUESTIONS, _post({"q2": "a"}), kind="order", next_id=NEXT_ID)
    (record,) = _records(caplog)
    assert record.levelno == logging.INFO and "schema=" in record.getMessage()
