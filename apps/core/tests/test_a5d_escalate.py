# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-5d: «Das funktioniert nicht / ich brauche einen Menschen» → Support (план §4 + §9).

Замки: фраза о человеке/«не работает» на пяти языках → карточка с превью, ничего не
отправлено; отправка — только кнопкой, ровно один тред на задачу (двойной POST), контакты
вычищены, видно, кто отправил; второе обращение за неделю дописывается в тот же тред; лимит;
чужая задача — отказ.
"""

import pytest

from apps.core import assistant_router, assistant_views
from apps.core.tests.test_a4_actions import _html
from apps.core.tests.test_assistant_a2 import (  # noqa: F401 — фикстуры и хелперы
    _ask,
    _clean,
    _req,
    _urlconf,
    _user,
    bakery,
    isolated_ratelimit,
)
from apps.support.models import SupportMessage, SupportThread

pytestmark = pytest.mark.django_db


@pytest.fixture
def ai_off(settings, isolated_ratelimit):
    settings.AI_ENABLED = False
    return settings


def _send(tenant, user, job, text):
    return assistant_views.assistant_escalate(
        _req(tenant, "post", {"text": text}, user=user, drawer=True), job
    )


@pytest.mark.parametrize(
    "phrase",
    [
        "Die Bezahlung funktioniert nicht",
        "Ich brauche einen Menschen",
        "оплата не работает",
        "оплата не працює, потрібна людина",
        "ödeme çalışmıyor",
        "payment is not working",
    ],
)
def test_human_request_routes_to_escalate(ai_off, bakery, phrase):
    assert assistant_router.classify(_req(bakery), phrase) == "escalate"


def test_card_first_nothing_sent(ai_off, bakery):
    user, got = _ask(bakery, "Die Bezahlung funktioniert nicht")
    html = _html(bakery, user, got["job"])
    assert "data-assistant-escalate" in html and "funktioniert nicht" in html
    assert not SupportThread.objects.exists()


def test_send_once_scrubbed_with_author(ai_off, bakery):
    user, got = _ask(bakery, "Die Bezahlung funktioniert nicht")
    text = "Kunde max@example.com, Tel. 0171 2345678 kann nicht zahlen"
    _send(bakery, user, got["job"], text)
    _send(bakery, user, got["job"], text)  # двойной POST
    assert SupportThread.objects.count() == 1
    body = SupportMessage.objects.get().body
    assert "max@example.com" not in body and "2345678" not in body
    assert user.email in body
    assert SupportThread.objects.get().subject.startswith("[Assistent]")
    assert "data-assistant-escalated" in _html(bakery, user, got["job"])


def test_second_request_same_week_joins_thread(ai_off, bakery):
    user, first = _ask(bakery, "Die Bezahlung funktioniert nicht")
    _send(bakery, user, first["job"], "erstes Problem")
    _u, second = _ask(bakery, "Ich brauche einen Menschen", user=user)
    _send(bakery, user, second["job"], "zweites Problem")
    assert SupportThread.objects.count() == 1 and SupportMessage.objects.count() == 2


def test_empty_text_sends_nothing(ai_off, bakery):
    user, got = _ask(bakery, "Ich brauche einen Menschen")
    _send(bakery, user, got["job"], "   ")
    assert not SupportThread.objects.exists()
    _send(bakery, user, got["job"], "jetzt mit Text")  # после отказа — можно снова
    assert SupportThread.objects.count() == 1


def test_rate_limit(ai_off, bakery):
    user = _user()
    for i in range(4):
        _u, got = _ask(bakery, f"Ich brauche einen Menschen {i}", user=user)
        _send(bakery, user, got["job"], f"Problem {i}")
    assert SupportMessage.objects.count() == 3


def test_foreign_job_is_refused(ai_off, bakery):
    user, got = _ask(bakery, "Ich brauche einen Menschen")
    _send(bakery, _user(), got["job"], "fremd")
    assert not SupportThread.objects.exists()
