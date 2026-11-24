"""FB-33 D2: кухонная доска (KDS) показывает не больше `KDS_MAX_ORDERS` заказов.

План — `docs/fb33-stack13-plan-2026-11-24.md` §2 D2, §4 и правка ревью §10.1 M6. Выборка
режется на `KDS_MAX_ORDERS + 1` (лишний — признак «есть ещё»); ответы на свои вопросы
расшифровываются только у показанных; порядок прежний — старые сверху. При переполнении
внутри `#kds-board` (поллинг заменяет его целиком) — заметная строка `role="status"` с числом
скрытых заказов (лёгкий `count` только при переполнении) и обычной ссылкой на список заказов,
если он открыт этому пользователю здесь (одна проверка — `nav_registry.screen_closed`).
"""

import re
import uuid
from pathlib import Path

import polib
import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone, translation

from apps.catalog.tests.factories import ProductFactory
from apps.core import form_answers
from apps.orders import services, views
from apps.orders.models import Order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


ROOT = Path(__file__).resolve().parents[3]
LIMIT = 48


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    """Ресторан с модулем заказов (KDS — экран гастро-типов, `nav_registry.KITCHEN_TYPES`)."""
    return TenantFactory.build(business_type="restaurant", disabled_modules=[])


def _req(user=None, tenant=None):
    request = RequestFactory().get("/dashboard/orders/kitchen/board/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if user is None:
        owner = uuid.uuid4().hex[:8]
        user = get_user_model().objects.create_user(
            username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
        )
    request.user = user
    request.tenant = tenant or _tenant()
    return request


def _orders(n):
    """`n` активных заказов, созданных по порядку (старые — первые)."""
    product = ProductFactory(name={"de": "Brot"})
    start = timezone.now() - timezone.timedelta(hours=2)
    made = []
    for i in range(n):
        order = services.create_order(items=[(product, 1)], name=f"K{i}")
        Order.objects.filter(pk=order.pk).update(
            created_at=start + timezone.timedelta(minutes=i),
            custom_answers={"q1": {"label": "Allergien", "value": f"A{i}"}},
        )
        made.append(order.reference_code)
    return made


def _board(request=None):
    with translation.override("de"):
        return views.kitchen_board(request or _req()).content.decode()


def _status(html):
    match = re.search(r'<p[^>]*role="status"[^>]*data-kds-more[^>]*>(.*?)</p>', html, re.S)
    return match


def test_board_limited():
    codes = _orders(LIMIT + 2)
    html = _board()
    shown = [c for c in codes if c in html]
    assert len(shown) == LIMIT and views.KDS_MAX_ORDERS == LIMIT
    assert _status(html)


def test_fifo_kept():
    codes = _orders(LIMIT + 1)
    html = _board()
    assert codes[0] in html and codes[-1] not in html
    positions = [html.index(c) for c in codes[:LIMIT]]
    assert positions == sorted(positions)


def test_answers_decrypted_only_for_shown(monkeypatch):
    _orders(LIMIT + 3)
    calls = []
    real = form_answers.rows

    def counting(stored):
        calls.append(1)
        return real(stored)

    monkeypatch.setattr(form_answers, "rows", counting)
    _board()
    assert len(calls) == LIMIT


def test_overflow_shows_count_and_warning_style():
    _orders(LIMIT + 3)
    html = _board()
    status = _status(html)
    assert status, html[-600:]
    assert "3 weitere offene Bestellungen" in status.group(1)
    tag = status.group(0)[: status.group(0).index(">") + 1]
    assert "bg-amber-100" in tag and "border-amber-400" in tag
    # строка — внутри доски, которую поллинг заменяет целиком
    board = html[html.index('id="kds-board"') :]
    assert "data-kds-more" in board


def test_no_status_without_overflow():
    """Без переполнения — ни строки, ни лишнего запроса (вывод прежний)."""
    _orders(3)
    html = _board()
    assert "data-kds-more" not in html and 'role="status"' not in html


def test_more_link_is_plain_link_named_by_text():
    _orders(LIMIT + 1)
    html = _board()
    status = _status(html)
    assert status
    link = re.search(r'<a href="([^"]+)"([^>]*)>(.*?)</a>', status.group(1), re.S)
    assert link and link.group(1) == reverse("orders:order-list")
    assert "aria-label" not in link.group(2) and "hx-" not in link.group(2)
    text = " ".join(link.group(3).split())
    assert text == "1 weitere offene Bestellung — in der Bestellliste"


def _staff_without_sales():
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _user

    staff = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=staff).update(
        permissions={"add": [], "remove": ["verkaeufe.view", "verkaeufe.edit"]}
    )
    return get_user_model().objects.get(pk=staff.pk)


@pytest.mark.parametrize("closed", ["perm", "package"])
def test_more_link_needs_list_access(closed, monkeypatch):
    _orders(LIMIT + 2)
    if closed == "package":
        from apps.core import packages

        real = packages.view_allowed
        monkeypatch.setattr(
            packages,
            "view_allowed",
            lambda tenant, name: False if name == "orders:order-list" else real(tenant, name),
        )
        request = _req()
    else:
        request = _req(user=_staff_without_sales())
    html = _board(request)
    status = _status(html)
    assert status and "2 weitere offene Bestellungen" in status.group(1)
    assert "<a " not in status.group(1)


def test_kitchen_page_and_action_use_the_same_limit():
    codes = _orders(LIMIT + 1)
    request = _req()
    with translation.override("de"):
        page = views.kitchen(request).content.decode()
    assert codes[-1] not in page and _status(page)
    post = RequestFactory().post(
        f"/dashboard/orders/kitchen/{uuid.uuid4()}/action/", {"action": "noop"}
    )
    post.user, post.tenant, post.session = request.user, request.tenant, request.session
    order = Order.objects.order_by("created_at").first()
    with translation.override("de"):
        after = views.kitchen_action(post, pk=order.pk).content.decode()
    assert codes[-1] not in after and _status(after)


MSGID = "%(counter)s weitere offene Bestellung — in der Bestellliste"
PLURAL = "%(counter)s weitere offene Bestellungen — in der Bestellliste"


def test_d2_msgids_in_all_po():
    for lang in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        entries = [e for e in po if not e.obsolete]
        pairs = [(e.msgctxt, e.msgid) for e in entries]
        assert len(pairs) == len(set(pairs)), lang
        entry = next((e for e in entries if e.msgid == MSGID), None)
        assert entry is not None and entry.msgid_plural == PLURAL, lang
        forms = [v for _k, v in sorted(entry.msgstr_plural.items())]
        assert forms and all("%(counter)s" in f for f in forms), (lang, forms)
        if lang != "de":
            assert forms[0] != MSGID, lang
