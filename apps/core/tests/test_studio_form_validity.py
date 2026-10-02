"""Save Студии не должен молча блокироваться валидацией браузера (класс X-ревью).

Стенд LB-2 (2026-10-02) поймал: на демо aktionsmarkt кнопка Save ничего не делала —
Chrome отменял отправку формы («An invalid form control with name='order_contact' is
not focusable»). Поле позиции фикс-секции было `max="20"`, а секций в реестре уже 25
(+ C-блоки на главной до 30), поэтому у последних секций позиция 21+ — недопустимое
значение. Скрытое поле владелец даже не видит, а форма не уходит.

Замок класса: ни одно числовое поле формы конструктора не нарушает собственных `min`/
`max` — ни на главной, ни на странице с блоками.
"""

import itertools
import re
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _text(i):
    return {"key": "text", "id": f"t{i}", "enabled": True, "data": {"title": f"T{i}"}}


def _builder(tenant, page="/"):
    from apps.core import views

    req = RequestFactory().get("/dashboard/site/home/", {"page": page})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return views.home_builder_view(req).content.decode()


def _out_of_range(body):
    bad = []
    for tag in re.findall(r"<input\b[^>]*>", body):
        if 'type="number"' not in tag:
            continue
        value = re.search(r'\bvalue="(-?\d+)"', tag)
        if not value:
            continue
        name = (re.search(r'\bname="([^"]+)"', tag) or [None, "?"])[1]
        low = re.search(r'\bmin="(-?\d+)"', tag)
        high = re.search(r'\bmax="(-?\d+)"', tag)
        v = int(value.group(1))
        if (low and v < int(low.group(1))) or (high and v > int(high.group(1))):
            bad.append((name, v, low and low.group(1), high and high.group(1)))
    return bad


def test_no_number_field_of_the_builder_breaks_its_own_range():
    blocks = [_text(i) for i in range(30)]  # кап блоков главной
    t = TenantFactory(slug=f"fv{next(_N)}", name="Fv")
    t.site_config = {"sections": blocks, "page_blocks": {"promos": blocks[:20]}}
    t.save(update_fields=["site_config"])
    assert not _out_of_range(_builder(t)), _out_of_range(_builder(t))
    assert not _out_of_range(_builder(t, "/aktionen/"))
