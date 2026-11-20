"""FB-33 M2i-5 C3: разметка вкладки «Felder» и превью черновика на витрине.

Замки: группа «Nicht fragen · Optional · Pflicht» на каждое незакреплённое поле (fieldset/legend),
закреплённые — 🔒 без переключателя; свои вопросы с подписями для скринридера; «+ Frage» нет при
10 вопросах; подписи и варианты — только автоэкранированием (форма витрины, окно, карточка
сделки, письмо, PDF, `autorepair_ld`); превью `?preview=1&aufbau=anfrage` показывает черновик;
журнал без значений ответов; старые заявки — по снимку.
"""

import copy
import logging
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.test import RequestFactory
from django.utils import translation

from apps.core import deal_card, form_answers
from apps.core.tests import test_fb31p5_detail_golden as _p5
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m2i5_before import CUSTOM
from apps.core.tests.test_fb33_m2i5_draft import WOPEN, _edit, _tenant

pytestmark = pytest.mark.django_db
frozen_now = _p5.frozen_now

XSS = "<script>alert(1)</script>"
ATTR = '"><img src=x onerror=alert(1)>'
EVIL = {
    "anfrage": {"fields": ["event_type"], "event_types": [XSS]},
    "form_fields": {
        "anfrage": {
            "mode": {"event_type": "req"},
            "labels": {"phone": XSS, "email": ATTR},
            "custom": [
                {"id": "q1", "type": "text", "label": ATTR},
                {"id": "q2", "type": "choice", "label": XSS, "options": [XSS, ATTR]},
            ],
            "next_id": 2,
        }
    },
}


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _clean(html):
    assert "<script>alert" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html


def _window(cfg=None, business_type="catering"):
    b = Browser(_tenant(cfg, business_type))
    with translation.override("de"):
        return b, b.get("?seite=anfrage&block=form&tab=felder")


def _part(html):
    start = html.index("data-form-felder")
    return html[start : html.index("</form>", start)]


def test_mode_groups_and_pinned_fields():
    _b, html = _window()
    part = _part(html)
    assert re.search(r'<fieldset[^>]*data-form-field="phone"', part)
    group = part[part.index('data-form-field="phone"') :]
    group = group[: group.index("</fieldset>")]
    assert re.search(r"<legend[^>]*>Telefon</legend>", group)
    radios = re.findall(r'<input type="radio" name="f_mode_phone" value="(\w+)"( checked)?>', group)
    assert [v for v, _c in radios] == ["off", "opt", "req"]
    assert [v for v, c in radios if c] == ["req"]  # CUSTOM: телефон обязателен
    for text in ("Nicht fragen", "Optional", "Pflicht"):
        assert text in group
    for pinned in ("title", "name"):
        assert f'data-form-field="{pinned}"' in part
        assert f'name="f_mode_{pinned}"' not in part
    assert part.count("immer Pflicht") == 2 and "🔒" in part


def test_questions_have_screen_reader_labels_and_actions():
    _b, html = _window()
    part = _part(html)
    assert [m for m in re.findall(r'data-form-question="(q\d+)"', part)] == ["q1", "q2", "q4"]
    assert 'value="up:q1"' not in part and 'value="down:q4"' not in part  # края
    assert 'value="up:q2"' in part and 'value="down:q2"' in part and 'value="del:q4"' in part
    assert "„Raum“ nach oben" in part and "„Raum“ nach unten" in part
    assert 'for="ff-q-q2-label"' in part and 'id="ff-q-q2-label"' in part
    assert "data-form-add" in part and "data-form-preset" in part  # кейтеринг — пресет есть
    # Enter в поле — первая кнопка формы = «Übernehmen» (не «Nach oben»), вне Tab, с именем
    first = re.search(r"<button[^>]*>[^<]*</button>", part).group(0)
    assert 'name="f_do"' not in first and 'name="f_commit_new"' in first
    # FB-33 M3-5a (ревью a11y): как у прочих sr-only кнопок «по умолчанию» — aria-hidden
    assert 'tabindex="-1"' in first and 'aria-hidden="true"' in first and "Übernehmen" in first
    assert 'aria-describedby="ff-q-q2-options-hint"' in part


def test_no_preset_button_without_industry_template():
    _b, html = _window(business_type="handwerker")
    assert "data-form-preset" not in _part(html)


def test_add_is_hidden_at_ten_questions():
    entry = copy.deepcopy(CUSTOM["form_fields"]["anfrage"])
    entry["custom"] = [{"id": f"q{i}", "type": "text", "label": f"F{i}"} for i in range(1, 11)]
    entry["next_id"] = 10
    _b, html = _window({"form_fields": {"anfrage": entry}})
    part = _part(html)
    assert "data-form-add" not in part and "data-form-full" in part


def test_event_hint_when_type_without_options():
    _b, html = _window({"anfrage": {"fields": ["event_type"]}})
    part = _part(html)
    assert "data-form-event-hint" in part
    assert 'aria-describedby="ff-event-types-hint ff-event-types-warn"' in part
    assert "die Liste bleibt auch sonst gespeichert" in part  # подсказка = поведение (H1)
    _b, html = _window()
    assert "data-form-event-hint" not in _part(html)


def test_window_escapes_labels_and_options():
    _b, html = _window(EVIL)
    _clean(_part(html))


def test_storefront_form_and_modal_escape_labels_and_options():
    from apps.core.tests.test_fb33_m2i5_before import anfrage_html, modal_html

    with translation.override("de"):
        _clean(anfrage_html(EVIL))
        _clean(modal_html(EVIL))
        page = anfrage_html({**EVIL, "jobs_vehicle": True})
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    assert ld and "alert" not in ld.group(1)  # autorepair_ld — данные бизнеса, не подписи


def test_card_mail_and_pdf_keep_labels_as_text():
    from pathlib import Path

    from django.template import Context, Template
    from django.template.loader import render_to_string

    from apps.core.tests.test_fb33_m2i2_before import _quote_text, quote_job

    job = quote_job(custom_answers={"q1": {"label": XSS, "value": ATTR}})
    rows = deal_card._custom_answers(job)
    assert rows == [(XSS, ATTR)]
    # карточка — тот же цикл, что в jobs/detail.html (автоэкранирование, без |safe)
    src = (Path(__file__).resolve().parents[3] / "templates/jobs/detail.html").read_text()
    loop = re.search(r"\{% for label, value in deal_custom_answers %\}.*?\{% endfor %\}", src)
    assert loop and "|safe" not in loop.group(0)
    html = Template(loop.group(0)).render(Context({"deal_custom_answers": rows}))
    _clean(html)
    mail = render_to_string(
        "emails/job_new.txt", {"job": job, "customer": job.customer, "custom_answers": rows}
    )
    assert f"{XSS}: {ATTR}" in mail  # письмо — простой текст (HTML-версии нет)
    text = _quote_text(job)
    assert "alert(1)" in text  # PDF рисует как текст


def _preview_request(b, query):
    req = RequestFactory().get("/anfrage/" + query)
    req.META["REMOTE_ADDR"] = "10.1.2.3"
    req.session = b.session
    MessageMiddleware(lambda r: None).process_request(req)
    from apps.core.models import Membership

    user = get_user_model().objects.create_user(username=f"pv-{uuid.uuid4().hex[:6]}")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    req.user = user
    b.tenant.refresh_from_db()
    req.tenant = b.tenant
    return req


def test_preview_shows_draft_storefront_shows_saved():
    from apps.jobs import public_views

    b = Browser(_tenant())
    _edit(b, do="add", new_label="Allergien", mode_photos="off")
    with translation.override("de"):
        shown = public_views.anfrage(_preview_request(b, "?preview=1&aufbau=anfrage"))
        saved = public_views.anfrage(_preview_request(b, ""))
    assert "Allergien" in shown.content.decode() and 'name="photos"' not in shown.content.decode()
    assert "Allergien" not in saved.content.decode() and 'name="photos"' in saved.content.decode()


def test_saved_form_shows_the_question_after_speichern():
    from apps.core.tests.test_fb33_m2i5_before import anfrage_html

    b = Browser(_tenant())
    _edit(b, do="add", new_label="Allergien")
    b.post(seite="anfrage", ref="form", op="window_done", wopen=WOPEN)
    b.post(seite="anfrage", op="save")
    b.tenant.refresh_from_db()
    with translation.override("de"):
        html = anfrage_html(b.tenant.site_config)
    assert 'name="q6"' in html and "Allergien" in html


def test_old_jobs_render_answers_from_their_snapshot():
    """Вопрос удалили, переименовали, сменили тип — старая заявка показывает снимок."""
    from apps.core.tests.test_fb33_m2i2_before import quote_job

    snap = form_answers.snapshot(
        CUSTOM["form_fields"]["anfrage"]["custom"], {"q1": "500", "q2": "Saal", "q4": True}
    )
    job = quote_job(custom_answers=snap)
    b = Browser(_tenant())
    _edit(b, do="del:q2")
    _edit(b, q_q1_label="Preisrahmen", q_q1_type="number", q_q4_label="Vegan", q_q4_type="text")
    b.post(seite="anfrage", op="save")
    with translation.override("de"):
        assert deal_card._custom_answers(job) == [
            ("Budget", "500"),
            ("Raum", "Saal"),
            ("Vegan?", "Ja"),
        ]


def test_logs_carry_no_answer_values(caplog):
    from apps.core.tests.test_fb33_m2i_before import _post_anfrage

    caplog.set_level(logging.DEBUG)
    secret = "GEHEIM-4711"
    data = {"title": "Fest", "name": "A", "phone": "1", "q1": secret, "q2": "Saal"}
    _post_anfrage(data, CUSTOM)
    b = Browser(_tenant())
    _edit(b, q_q1_label=secret, q_q1_type="text")
    assert secret not in caplog.text
