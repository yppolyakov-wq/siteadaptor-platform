"""KA-12 E8.8 (KA-4 §7): мобильный таб-бар полного кабинета — Übersicht · Verkäufe · ＋ ·
Nachrichten (без чата — Sortiment) · Mehr, подписи под иконками. Лёгкий кабинет не тронут."""

from uuid import uuid4

import pytest

from apps.core import modules, sales_page
from apps.core.context import _cabinet_tabbar
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(business_type, disabled=None):
    off = modules.default_disabled_for(business_type) if disabled is None else disabled
    return TenantFactory(
        slug=f"tb-{business_type[:6]}-{uuid4().hex[:4]}",
        business_type=business_type,
        disabled_modules=list(off),
    )


def _bar(tenant):
    return _cabinet_tabbar(tenant, modules.sidebar_nav(tenant))


def test_order_is_overview_sales_plus_messages():
    t = _tenant("friseur")
    if not t.is_module_active("inbox"):
        t.disabled_modules = [m for m in t.disabled_modules if m != "inbox"]
        t.save(update_fields=["disabled_modules"])
    bar = _bar(t)
    keys = [b["nav_key"] for b in bar]
    assert keys[:2] == ["dashboard", "board"]
    assert keys[2] == "plus" and bar[2]["url"] == sales_page.tabbar_create_target(t)
    assert keys[3] == "inbox" and bar[3]["badge"] == "inbox"
    assert all(str(b["label"]) for b in bar)


def test_without_inbox_fourth_is_sortiment():
    t = _tenant("bakery")
    t.disabled_modules = list(t.disabled_modules) + ["inbox"]
    t.save(update_fields=["disabled_modules"])
    keys = [b["nav_key"] for b in _bar(t)]
    assert "inbox" not in keys and keys[-1] == "sellables"


def test_plus_target_by_direction():
    hotel = _tenant("hotel")
    assert sales_page.tabbar_create_target(hotel).endswith("/dashboard/stays/neu/") or (
        "stay" in sales_page.tabbar_create_target(hotel)
    )
    shop = _tenant("shop")
    # заказы формы создания не имеют → быстрая акция (если акции включены), иначе без «＋»
    want = "/promotions/schnell/" if shop.is_module_active("promotions") else ""
    assert sales_page.tabbar_create_target(shop) == want


def test_template_has_labels_and_plus():
    from pathlib import Path

    src = Path("templates/tenant/_base_dashboard.html").read_text()
    assert "data-tabbar-create" in src and 'trans "Mehr"' in src
    assert 'id="ic-nav-plus"' in Path("templates/tenant/_icons.html").read_text()
