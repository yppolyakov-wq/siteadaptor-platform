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


# --- ревью диффа (план §10.4) -----------------------------------------------------------------
#: замки правок ревью — снимаются своими коммитами
REVIEW = pytest.mark.xfail(strict=True, reason="FB-33 D2 §10.4: до правки")
PARTIAL = ROOT / "templates/orders/_kitchen_board.html"


def _more(html):
    """Строка переполнения `[data-kds-more]` (любая разметка) — внутренний HTML или None."""
    match = re.search(r"<p[^>]*data-kds-more[^>]*>(.*?)</p>", html, re.S)
    return match.group(1) if match else None


def _sales_url():
    return reverse("verkaeufe") + "?tab=order&view=liste"


@REVIEW
def test_overflow_line_is_not_a_live_region():
    """a11y HIGH: доска пересоздаётся поллингом каждые 8 с — live region внутри неё
    пересоздавался бы и объявлялся заново; строка — обычный абзац."""
    source = PARTIAL.read_text(encoding="utf-8")
    assert 'role="status"' not in source and "aria-live" not in source
    _orders(LIMIT + 1)
    html = _board()
    assert _more(html) is not None and 'role="status"' not in html


@REVIEW
def test_focus_targets_have_stable_ids():
    """a11y HIGH: htmx возвращает фокус после замены `outerHTML` по `id` — у кнопок действия
    и у ссылки он постоянный."""
    _orders(LIMIT + 1)
    html = _board()
    shown = list(Order.objects.order_by("created_at")[:LIMIT])
    for order in shown[:3]:
        assert f'id="kds-act-{order.pk}"' in html
    assert len(re.findall(r'id="kds-act-', html)) == LIMIT
    assert 'id="kds-more-link"' in _more(html)


@REVIEW
def test_link_named_open_list_and_count_is_text():
    """Имя ссылки — «Bestellliste öffnen»; число — текстом перед ссылкой, не в ней."""
    _orders(LIMIT + 2)
    more = _more(_board())
    link = re.search(r"<a ([^>]*)>(.*?)</a>", more, re.S)
    assert link and " ".join(link.group(2).split()) == "Bestellliste öffnen"
    assert "underline" in link.group(1) and "min-h-[44px]" in link.group(1)
    before = more[: link.start()]
    assert "2 weitere offene Bestellungen" in before


@REVIEW
def test_link_targets_the_sales_screen():
    """MEDIUM: цель — экран «Verkäufe» (вкладка заказов, список), не легаси с 302."""
    _orders(LIMIT + 1)
    link = re.search(r'<a [^>]*href="([^"]+)"', _more(_board()))
    assert link and link.group(1).replace("&amp;", "&") == _sales_url()


@REVIEW
def test_closed_link_explains(monkeypatch):
    """Право на KDS есть, на «Verkäufe» нет — ссылки нет, строка поясняет почему."""
    from apps.core import view_perms
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _user

    monkeypatch.setitem(
        view_perms.RULES, "verkaeufe", view_perms.Rule("kunden.view", "kunden.edit")
    )
    staff = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=staff).update(
        permissions={"add": ["verkaeufe.view"], "remove": ["kunden.view", "kunden.edit"]}
    )
    staff = get_user_model().objects.get(pk=staff.pk)
    _orders(LIMIT + 1)
    more = _more(_board(_req(user=staff)))
    assert more is not None and "<a " not in more
    assert "Die Bestellliste ist für Ihr Konto nicht freigegeben." in more


@REVIEW
def test_new_orders_beyond_the_limit_are_named():
    """MEDIUM: 48 принятых и один новый за потолком — строка называет «davon 1 neu»."""
    _orders(LIMIT + 1)
    newest = Order.objects.order_by("-created_at").first()
    Order.objects.exclude(pk=newest.pk).update(status=Order.STATUS_CONFIRMED)
    more = _more(_board())
    assert more is not None and "davon 1 neu" in more


@REVIEW
def test_no_new_count_when_hidden_are_confirmed():
    _orders(LIMIT + 1)
    newest = Order.objects.order_by("-created_at").first()
    Order.objects.filter(pk=newest.pk).update(status=Order.STATUS_CONFIRMED)
    more = _more(_board())
    assert more is not None and "neu" not in more and "Bestellliste öffnen" in more


REVIEW_MSGIDS = [
    (
        "%(counter)s weitere offene Bestellung wird hier nicht angezeigt",
        "%(counter)s weitere offene Bestellungen werden hier nicht angezeigt",
    ),
    ("davon %(counter)s neu", "davon %(counter)s neu"),
    ("Bestellliste öffnen", None),
    ("Die Bestellliste ist für Ihr Konto nicht freigegeben.", None),
]


@REVIEW
def test_d2_review_msgids_in_all_po():
    """Новые строки — во всех пяти каталогах; старая строка «… — in der Bestellliste» снята."""
    for lang in ("de", "en", "tr", "ru", "uk"):
        po = polib.pofile(str(ROOT / f"locale/{lang}/LC_MESSAGES/django.po"))
        entries = {(e.msgctxt, e.msgid): e for e in po if not e.obsolete}
        assert (None, MSGID) not in entries, lang
        for msgid, plural in REVIEW_MSGIDS:
            entry = entries.get((None, msgid))
            assert entry is not None, (lang, msgid)
            if plural:
                assert entry.msgid_plural == plural, (lang, msgid)
                forms = list(entry.msgstr_plural.values())
                assert forms and all("%(counter)s" in f for f in forms), (lang, msgid)
            elif lang != "de":
                assert entry.msgstr and entry.msgstr != msgid, (lang, msgid)
