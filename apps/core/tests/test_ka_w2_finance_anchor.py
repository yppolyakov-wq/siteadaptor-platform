"""KA-12 Волна 2 · батч 3a: условный якорь «Finanzen» и группы подменю.

План — docs/ka-12-w2-batch3-plan-2026-10-24.md. Решение владельца (KA-4 В-1…В-6):
седьмой якорь «Finanzen» — только при модуле finance или analytics (мораторий X7 снят
ровно для него); без них его пункты живут группой «Zahlen & Finanzen» в Einstellungen.
"""

from uuid import uuid4

import pytest
from django.template import Context, Template

from apps.core import modules, nav_registry
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

BUSINESS_TYPES = [code for code, _label in Tenant.BUSINESS_TYPES]


def _tenant(business_type="bakery", enable=()):
    off = [m for m in modules.default_disabled_for(business_type) if m not in enable]
    return TenantFactory(
        slug=f"fa-{business_type[:7]}-{uuid4().hex[:4]}",
        business_type=business_type,
        disabled_modules=off,
    )


def _items(tenant):
    return {it["nav_key"]: it for it in modules.sidebar_nav(tenant)}


def _sidebar_anchor(tenant, nav):
    from types import SimpleNamespace

    return Template("{% load cabinet %}{% sidebar_anchor %}").render(
        Context({"nav": nav, "request": SimpleNamespace(tenant=tenant, user=None)})
    )


def test_only_finance_anchor_is_conditional():
    conditional = [a.nav_key for a in nav_registry.ANCHORS if a.modules_any]
    assert conditional == ["finance"]


@pytest.mark.parametrize("business_type", BUSINESS_TYPES)
def test_finance_anchor_hidden_by_default(business_type):
    """finance и analytics выключены по умолчанию у всех типов → якоря нет, «Zahlungen»
    живёт группой «Zahlen & Finanzen» в Einstellungen, подсветка — Einstellungen."""
    tenant = _tenant(business_type)
    items = _items(tenant)
    assert "finance" not in items
    sett = items["settings"]["children"]
    pay = next(c for c in sett if c["url_name"] == "payments-page")
    assert pay["group"] == "finanzen"
    assert _sidebar_anchor(tenant, "zahlungen").strip() == "settings"


def test_finance_anchor_shown_with_analytics():
    tenant = _tenant("bakery", enable=("analytics",))
    items = _items(tenant)
    fin = items["finance"]
    names = [c["url_name"] for c in fin["children"]]
    assert "promotions:analytics" in names and "payments-page" in names
    # finance-модуль выключен — журнала нет, цель раздела — первый видимый экран
    assert "finance:journal" not in names
    assert fin["target"] == "promotions:analytics"
    assert "payments-page" not in [c["url_name"] for c in items["settings"]["children"]]
    assert _sidebar_anchor(tenant, "zahlungen").strip() == "finance"


def test_finance_anchor_shown_with_finance():
    tenant = _tenant("bakery", enable=("finance",))
    fin = _items(tenant)["finance"]
    names = [c["url_name"] for c in fin["children"]]
    assert names[:2] == ["payments-page", "finance:journal"] or "finance:journal" in names
    assert {"finance:invoices", "finance:offene", "finance:bank"} <= set(names)
    assert fin["target"] == "finance:journal"
    headers = [c["header"] for c in fin["children"] if c.get("header")]
    assert [str(h) for h in headers] == ["Überblick", "Buchhaltung"]


def test_finance_entries_leave_verkaeufe():
    tenant = _tenant("bakery", enable=("finance", "analytics"))
    verk = {c["url_name"] for c in _items(tenant)["board"]["children"]}
    assert not verk & {"payments-page", "promotions:analytics", "finance:journal"}


def test_every_grouped_hub_entry_has_known_group():
    for hub, groups in nav_registry.SUBMENU_GROUPS.items():
        known = {key for key, _label in groups}
        for e in nav_registry.ENTRIES:
            if e.hub == hub and not e.palette_only:
                assert e.group in known, f"{hub}:{e.url_name} без группы ({e.group!r})"


def test_settings_submenu_has_group_headers():
    tenant = _tenant("hotel")
    sett = _items(tenant)["settings"]["children"]
    headers = [str(c["header"]) for c in sett if c.get("header")]
    assert headers[0] == "Geschäft"
    assert "Zimmer" in headers and "System" in headers
    # группы идут блоками: одна группа не встречается дважды
    seen, prev = [], None
    for c in sett:
        g = c.get("group") or ""
        if g != prev:
            assert g not in seen, f"группа {g} разорвана"
            seen.append(g)
            prev = g


def test_sidebar_renders_subheaders():
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open, _user

    tenant = _tenant("hotel")
    user = _user(Membership.ROLE_OWNER)
    body = _open("/dashboard/einstellungen/", tenant, user).content.decode()
    assert "data-nav-subhead" in body


def test_finance_anchor_not_in_palette_when_hidden():
    from types import SimpleNamespace

    tenant = _tenant("bakery")
    html = Template("{% load cabinet %}{% nav_palette %}").render(
        Context({"request": SimpleNamespace(tenant=tenant, user=None)})
    )
    assert "/dashboard/finance/" not in html


def test_staff_never_gets_owner_only_finance_link():
    """Ревью 3a: банк — owner-only; цель раздела учитывает роль (без 403-ссылок)."""
    from django.urls import reverse

    from apps.core import roles
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _user

    tenant = _tenant("bakery", enable=("finance", "analytics"))
    staff = _user(Membership.ROLE_STAFF)
    items = {it["nav_key"]: it for it in modules.sidebar_nav(tenant, staff)}
    fin = items["finance"]
    urls = [fin["target"]] + [c["url_name"] for c in fin["children"]]
    assert "finance:bank" not in urls
    for name in urls:
        assert roles.required_role_for_path(reverse(name)) != roles.ROLE_OWNER_ONLY, name


# --- 3b: Marketing & Kunden, лендинги → 302 ------------------------------------


def _owner_open(path, tenant, data=None):
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open, _user

    return _open(path, tenant, _user(Membership.ROLE_OWNER), data=data)


def test_marketing_home_redirects_to_first_active_screen_with_get():
    tenant = _tenant("bakery")
    resp = _owner_open("/dashboard/marketing/", tenant, data={"q": "x"})
    assert resp.status_code == 302
    anchor = next(a for a in nav_registry.ANCHORS if a.nav_key == "promotions")
    from django.urls import reverse

    assert resp["Location"] == reverse(nav_registry.anchor_target(anchor, tenant)) + "?q=x"


def test_anchor_target_first_active():
    anchor = next(a for a in nav_registry.ANCHORS if a.nav_key == "promotions")
    with_inbox = _tenant("bakery")
    assert nav_registry.anchor_target(anchor, with_inbox) == "inbox:list"
    no_inbox = _tenant("bakery")
    no_inbox.disabled_modules = list(no_inbox.disabled_modules) + ["inbox"]
    assert nav_registry.anchor_target(anchor, no_inbox) == "promotions:promotion-list"


def test_integrations_home_redirects_to_channels_page():
    tenant = _tenant("bakery")
    resp = _owner_open("/dashboard/integrationen/", tenant, data={"a": "1"})
    assert resp.status_code == 302
    from django.urls import reverse

    assert resp["Location"] == reverse("notifications-settings") + "?a=1"


def test_connection_cards_live_on_channels_page():
    tenant = _tenant("hotel")
    body = _owner_open("/dashboard/settings/notifications/", tenant).content.decode()
    assert "data-connections" in body and 'id="verbindungen"' in body
    assert "/dashboard/domains/" in body  # карточка «Eigene Domain»


def test_marketing_submenu_grouped_with_inbox_first():
    tenant = _tenant("bakery")
    mk = _items(tenant)["promotions"]
    assert mk["target"] == "inbox:list"
    first = mk["children"][0]
    assert first["url_name"] == "inbox:list" and first.get("badge") == "inbox"
    headers = [str(c["header"]) for c in mk["children"] if c.get("header")]
    assert headers == ["Kunden", "Aktionen", "Reichweite"][: len(headers)]
    assert "telegram-settings" not in [c["url_name"] for c in mk["children"]]


def test_anchor_target_never_points_to_redirect_stub():
    """Ревью батча 3: без inbox/promotions/reviews/crm раздел Marketing остаётся виден
    (блог/рассылка), а цель не может быть самой заглушкой marketing-home — петля 302."""
    anchor = next(a for a in nav_registry.ANCHORS if a.nav_key == "promotions")
    t = _tenant(enable=("blog", "newsletter"))
    t.disabled_modules = list(t.disabled_modules) + ["inbox", "promotions", "reviews", "crm"]
    t.save(update_fields=["disabled_modules"])
    target = nav_registry.anchor_target(anchor, t)
    assert target != "marketing-home"
    for it in modules.sidebar_nav(t):
        assert it["target"] != "marketing-home"
        assert all(c["url_name"] != "marketing-home" for c in it["children"])
