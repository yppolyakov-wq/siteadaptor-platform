"""FB-33 M2i-2: свои вопросы формы заявки — рендер, ответы, показ, DSGVO.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i». Без вопросов форма, письмо и PDF
байт-в-байт прежние (снимки `test_fb33_m2i_before`, `test_fb33_m2i2_before`).
"""

import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from django.template.loader import render_to_string
from django.utils import translation

from apps.core import deal_card, form_answers
from apps.core.tests.test_fb33_m2i2_before import _quote_text, quote_job
from apps.core.tests.test_fb33_m2i_before import (
    _anfrage_request,
    _post_anfrage,
    anfrage_html,
    band_html,
)

pytestmark = pytest.mark.django_db

QUESTIONS = [
    {"id": "q1", "type": "choice", "label": "Anlass", "options": ["Hochzeit", "Firmenfeier"]},
    {"id": "q2", "type": "number", "label": "Budget", "mode": "req"},
    {"id": "q3", "type": "bool", "label": "Vegetarisch"},
    {"id": "q4", "type": "date", "label": "Probetermin"},
    {"id": "q5", "type": "textarea", "label": "Wünsche"},
    {"id": "q6", "type": "text", "label": "Firma"},
]


def _cfg(questions=QUESTIONS):
    return {"form_fields": {"anfrage": {"custom": questions, "next_id": 6}}}


def test_form_draws_every_question_type():
    with translation.override("de"):
        html = anfrage_html(_cfg())
    assert '<select id="id_q1" name="q1"' in html and '<option value="Hochzeit">' in html
    assert 'name="q2" type="number" step="any" required' in html
    # ревью a11y M2i-5: «*» скрыт от скринридера, вслух — «(Pflichtfeld)»
    assert (
        'Budget<span aria-hidden="true"> *</span><span class="sr-only"> (Pflichtfeld)</span>'
        in html
    )
    assert '<input type="checkbox" name="q3" value="1">' in html
    assert 'name="q4" type="date"' in html
    assert '<textarea id="id_q5" name="q5"' in html
    assert 'name="q6" type="text"' in html


def test_answers_are_stored_as_a_snapshot_with_the_label():
    from apps.jobs.models import Job

    data = {"title": "Fest", "name": "A", "phone": "1", "q1": "Hochzeit", "q2": "1500"}
    data.update({"q3": "on", "q4": "2027-03-01", "q5": "Bitte\nscharf", "q9": "fremd"})
    _post_anfrage(data, _cfg())
    job = Job.objects.get()
    assert job.custom_answers == {
        "q1": {"label": "Anlass", "value": "Hochzeit", "type": "choice"},
        "q2": {"label": "Budget", "value": 1500, "type": "number"},
        "q3": {"label": "Vegetarisch", "value": True, "type": "bool"},
        "q4": {"label": "Probetermin", "value": "2027-03-01", "type": "date"},
        "q5": {"label": "Wünsche", "value": "Bitte\nscharf", "type": "textarea"},
    }


def test_required_question_and_choice_outside_options():
    from django.contrib.messages import get_messages

    from apps.jobs import public_views
    from apps.jobs.models import Job

    with translation.override("de"):
        req = _anfrage_request({"title": "F", "name": "A", "phone": "1", "q2": "viel"}, _cfg())
        public_views.anfrage(req)
        text = " ".join(str(m) for m in get_messages(req))
    assert not Job.objects.exists() and "Budget" in text
    _post_anfrage({"title": "F", "name": "A", "phone": "1", "q2": "5", "q1": "Party"}, _cfg())
    assert "q1" not in Job.objects.get().custom_answers  # не из списка владельца — прочь


def test_band_draws_required_text_questions_or_sends_to_the_full_form():
    with translation.override("de"):
        html = band_html(_cfg())
    assert 'name="q2" required' in html and "Budget *" in html
    choice_req = [{"id": "q1", "type": "choice", "label": "A", "options": ["x"], "mode": "req"}]
    with translation.override("de"):
        html = band_html(_cfg(choice_req))
    assert "<form" not in html and 'href="/anfrage/"' in html


def test_old_deals_and_deals_without_answers_show_nothing():
    job = quote_job()
    assert job.custom_answers == {}
    assert deal_card._custom_answers(job) == []
    assert form_answers.rows(None) == [] and form_answers.rows({"x": "y"}) == []


def test_card_email_and_pdf_show_the_answers():
    from apps.jobs import notifications

    job = quote_job(
        custom_answers={
            "q1": {"label": "Anlass", "value": "Hochzeit"},
            "q3": {"label": "Vegetarisch", "value": True},
            "q4": {"label": "Probetermin", "value": "2027-03-01", "type": "date"},
        }
    )
    with translation.override("de"):
        rows = deal_card._custom_answers(job)
        assert rows == [
            ("Anlass", "Hochzeit"),
            ("Vegetarisch", "Ja"),
            ("Probetermin", "01.03.2027"),
        ]
        ctx = {
            "job": job,
            "customer": job.customer,
            "custom_answers": notifications._owner_answers(job),
        }
        mail = render_to_string("emails/job_new.txt", ctx)
        assert "Anlass: Hochzeit\nVegetarisch: Ja\n" in mail
        text = _quote_text(job)
    assert "Anlass: Hochzeit" in text and "Probetermin: DATE" in text  # даты снимок нормализует


def test_card_template_lists_the_answers():
    tpl = Path(__file__).resolve().parents[3] / "templates" / "jobs" / "detail.html"
    assert "{% if deal_custom_answers %}" in tpl.read_text()


# --- DSGVO, вебхуки, правка заказа --------------------------------------------------


def test_erasure_clears_the_answers_of_jobs_and_orders():
    from apps.crm import dsgvo
    from apps.jobs.models import Job
    from apps.orders.models import Order
    from apps.promotions.models import Customer

    customer = Customer.objects.create(name="Erika", email="erika@example.com")
    job = quote_job(custom_answers={"q1": {"label": "Anlass", "value": "Hochzeit"}})
    Job.objects.filter(pk=job.pk).update(customer=customer, status="declined")
    order = Order.objects.create(
        customer=customer,
        reference_code=f"O-{uuid.uuid4().hex[:6]}",
        status="picked_up",
        payment_state="paid",
        total=Decimal("1.00"),
        custom_answers={"q1": {"label": "Allergie", "value": "Nüsse"}},
    )
    exported = dsgvo.export_json(customer)
    # выгрузка субъекта (Art. 15/20) — ответы читаемо, подпись и значение, не маской
    assert '"label": "Anlass"' in exported and '"value": "Hochzeit"' in exported
    assert '"value": "Nüsse"' in exported and '"custom_answers": "***"' not in exported
    dsgvo.erase_customer(customer)
    job.refresh_from_db()
    order.refresh_from_db()
    assert job.custom_answers == {} and order.custom_answers == {}


def test_every_encrypted_json_field_of_deals_is_in_the_erasure_map():
    """Замок: зашифрованное JSON-поле сделки (ответы клиента) обязано стираться по DSGVO."""
    from django.apps import apps as django_apps

    from apps.crm import dsgvo
    from apps.secrets.fields import EncryptedJSONField

    missing = []
    for model in django_apps.get_models():
        label = model._meta.label
        if label not in dsgvo.ERASURE_POLICY:
            continue
        action, arg = dsgvo.ERASURE_POLICY[label]
        if action not in ("clear",):
            continue
        for field in model._meta.concrete_fields:
            if isinstance(field, EncryptedJSONField) and field.name not in arg:
                missing.append(f"{label}.{field.name}")
    assert missing == []


def test_answers_never_leave_through_webhooks_or_search():
    """Решение владельца: ответы — карточка, письмо, PDF, выгрузка DSGVO; не вебхуки и не поиск."""
    root = Path(__file__).resolve().parents[3] / "apps"
    allowed = {
        "account/account_data.py",
        "core/form_answers.py",
        "core/form_spec.py",
        "core/deal_card.py",
        "crm/dsgvo.py",
        "jobs/models.py",
        "jobs/services.py",
        "jobs/public_views.py",
        "jobs/notifications.py",
        "jobs/pdf.py",
        "orders/models.py",
        # FB-33 M2i-34: снимок ответов корзины — вьюха оформления и сервис заказа
        "orders/public_views.py",
        "orders/services.py",
    }
    readers = set()
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in f"/{rel}" or "/migrations/" in f"/{rel}":
            continue
        if re.search(r"\bcustom_answers\b", path.read_text(encoding="utf-8")):
            readers.add(rel)
    assert readers <= allowed, sorted(readers - allowed)
    assert not any(r.startswith(("integrations/", "aggregator/")) for r in readers)
    # обобщённая сериализация (model_to_dict/serialize) сделок вынесла бы ответы мимо замка
    generic = re.compile(r"\bmodel_to_dict\(|serializers\.serialize\(")
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(("jobs/", "orders/", "integrations/", "aggregator/", "api/")):
            if "/tests/" not in f"/{rel}" and generic.search(path.read_text(encoding="utf-8")):
                raise AssertionError(f"обобщённая сериализация сделки: {rel}")


def test_order_editing_keeps_the_answers():
    from apps.orders import editing
    from apps.orders.models import Order
    from apps.promotions.models import Customer

    order = Order.objects.create(
        customer=Customer.objects.create(name="K"),
        reference_code=f"O-{uuid.uuid4().hex[:6]}",
        total=Decimal("10.00"),
        custom_answers={"q1": {"label": "Allergie", "value": "Nüsse"}},
    )
    editing.set_discount(order, cents=100, allow_closed=True)
    editing.update_customer(order, name="K2")
    editing.recalc_total(order)
    order.refresh_from_db()
    assert order.custom_answers == {"q1": {"label": "Allergie", "value": "Nüsse"}}


# --- ревью M2i-2 ----------------------------------------------------------------------


def test_the_customer_sees_own_answers_in_the_account():
    from django.template.loader import render_to_string

    from apps.account import account_data
    from apps.jobs.models import Job
    from apps.promotions.models import Customer

    customer = Customer.objects.create(name="Erika", email="erika@example.com")
    job = quote_job(custom_answers={"q1": {"label": "Anlass", "value": "Hochzeit & Taufe"}})
    Job.objects.filter(pk=job.pk).update(customer=customer)
    section = account_data._jobs(customer)
    assert section["items"][0]["answers"] == [("Anlass", "Hochzeit & Taufe")]
    html = render_to_string("konto/home.html", {"customer": customer, "sections": [section]})
    assert "data-custom-answers" in html and "Hochzeit &amp; Taufe" in html


def test_numbers_must_be_finite():
    questions = [{"id": "q1", "type": "number", "label": "N", "mode": "req"}]
    for raw in ("nan", "inf", "-Infinity", "1e400"):
        answers = form_answers.collect(questions, {"q1": raw})
        assert answers == {} and form_answers.validate(questions, answers) == ["q1"]


def test_owner_mail_is_plain_text_without_html_escaping():
    job = quote_job(custom_answers={"q1": {"label": "Firma", "value": "Müller & Söhne <GmbH>"}})
    ctx = {"job": job, "customer": job.customer, "custom_answers": deal_card._custom_answers(job)}
    mail = render_to_string("emails/job_new.txt", ctx)
    assert "Firma: Müller & Söhne <GmbH>" in mail and "&amp;" not in mail


def test_long_answers_wrap_in_the_pdf_and_move_to_the_next_page():
    from io import BytesIO

    from pypdf import PdfReader

    from apps.jobs.pdf import build_quote_pdf
    from apps.tenants.tests.factories import TenantFactory

    long_text = " ".join(f"Wort{i}" for i in range(60)) + " ENDE"
    job = quote_job(custom_answers={"q1": {"label": "Wünsche", "value": long_text}})
    with translation.override("de"):
        text = _quote_text(job)
    assert "ENDE" in text  # перенесено, не обрезано
    huge = " ".join(f"W{i}" for i in range(400))
    many = {f"q{i}": {"label": f"Frage {i}", "value": huge} for i in range(1, 11)}
    job = quote_job(custom_answers=many)
    with translation.override("de"):
        pdf = build_quote_pdf(job, TenantFactory.build(name="X"))
        reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 2  # ответы не налезают на таблицу — новая страница
    full = "\n".join(p.extract_text() or "" for p in reader.pages)
    assert "…" in full and "Gesamt" in full


def test_many_answers_and_many_lines_keep_totals_on_the_page():
    """Ревью M2i-2: 10 ответов + 20 позиций — итоги и Hinweise не уходят за низ листа."""
    from io import BytesIO

    from pypdf import PdfReader

    from apps.jobs import services
    from apps.jobs.pdf import build_quote_pdf
    from apps.tenants.tests.factories import TenantFactory

    many = {f"q{i}": {"label": f"Frage {i}", "value": "kurz"} for i in range(1, 11)}
    job = quote_job(custom_answers=many)
    lines = [{"text": f"Position {i}", "qty": 1, "unit_price": "10.00"} for i in range(20)]
    services.set_lines(job, lines)
    with translation.override("de"):
        reader = PdfReader(BytesIO(build_quote_pdf(job, TenantFactory.build(name="X"))))
    last = reader.pages[-1].extract_text() or ""
    full = "\n".join(p.extract_text() or "" for p in reader.pages)
    assert "Position 19" in full and "Gesamt" in last
    assert "unverbindliches Angebot" in last


def test_old_snapshots_without_type_show_as_text_and_yes_has_context():
    old = {"q1": {"label": "Datum", "value": "2027-03-01"}, "q2": {"label": "J", "value": True}}
    with translation.override("ru"):
        assert form_answers.rows(old) == [("Datum", "2027-03-01"), ("J", "Да")]


def test_number_inputs_accept_decimals():
    q = [{"id": "q1", "type": "number", "label": "Budget", "mode": "req"}]
    with translation.override("de"):
        full, band = anfrage_html(_cfg(q)), band_html(_cfg(q))
    assert 'type="number" step="any" required' in full
    assert 'type="number" step="any" name="q1" required' in band
