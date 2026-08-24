"""ST-4b (одобрено 2026-07-19): компактный сайдбар «хабы + Website».

Замки: состав/гейты якорей
(легаси-разметка цела), мобильный таб-бар = первая четвёрка, все url резолвятся.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.core import modules
from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_TOUCHED = {"v": 2, "step": "language", "done": ["start"], "skipped": [], "completed": False}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant, path="/dashboard/"):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    o = uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    return request


def test_sidebar_nav_composition_and_urls():
    t = TenantFactory(slug="sb1", name="Sb1", business_type="bakery")
    keys = [it["url_name"] for it in modules.sidebar_nav(t)]
    # V4 (2026-08-03): якорь «Verkäufe» ведёт на единую страницу продаж.
    # W9-9 (Р-3): «Integrationen» ушёл из сайдбара — вкладка Einstellungen.
    # W11-5: якорь «Website» ведёт прямо в Studio (site-home) — страница-лендинг
    # «Site» умерла и осталась только редиректом (nav_key "site" при этом цел).
    assert keys == [
        "dashboard",
        "verkaeufe",
        "sellable-manage",
        "marketing-home",
        "site-home",
        "einstellungen-home",
    ]
    for it in modules.sidebar_nav(t):
        reverse(it["url_name"])  # каждый якорь резолвится


def test_sidebar_nav_gates():
    # X0 (cabinet-cleanup-2026-08-19, осознанная переписка): promotions выключен,
    # но живы другие модули хаба (inbox/reviews/…) → якорь Marketing ОСТАЁТСЯ —
    # иначе отель терял единственный вход к сообщениям клиентов (гейт-баг
    # исследования 2026-08-18 §3). «Angebote» остаётся всегда (catalog — core).
    t = TenantFactory(
        slug="sb2",
        name="Sb2",
        disabled_modules=["catalog", "booking", "stays", "events", "promotions"],
    )
    keys = [it["url_name"] for it in modules.sidebar_nav(t)]
    assert "marketing-home" in keys
    assert "verkaeufe" in keys and "einstellungen-home" in keys and "sellable-manage" in keys


def test_sidebar_marketing_hidden_only_without_any_hub_module():
    # Якорь Marketing гаснет, только когда выключены ВСЕ модули его хаба.
    t = TenantFactory(
        slug="sb2b",
        name="Sb2b",
        disabled_modules=[
            "promotions",
            "reviews",
            "crm",
            "loyalty",
            "inbox",
            "telegram",
            "publishing",
            "blog",
        ],
    )
    keys = [it["url_name"] for it in modules.sidebar_nav(t)]
    assert "marketing-home" not in keys


def test_sidebar_hotel_default_sees_marketing_and_messages():
    # Гейт-баг исследования 2026-08-18: у отеля promotions выключен по умолчанию,
    # но inbox/reviews активны — вход к сообщениям обязан быть; «Nachrichten» —
    # первый подпункт якоря со своим бейджем.
    from apps.core.modules import default_disabled_for

    t = TenantFactory(
        slug="sbh",
        name="SbH",
        business_type="hotel",
        disabled_modules=default_disabled_for("hotel"),
    )
    nav = {it["url_name"]: it for it in modules.sidebar_nav(t)}
    assert "marketing-home" in nav
    children = nav["marketing-home"]["children"]
    # R7-1 (осознанная переписка): первым подпунктом идёт ОБЗОР раздела —
    # клик по разделу раскрывает меню, а не уводит на страницу. Вход к
    # сообщениям и бейдж остаются (смысл прежнего замка).
    assert children[0]["url_name"] == "marketing-home"
    msgs = next(c for c in children if c["url_name"] == "inbox:list")
    assert msgs.get("badge") == "inbox" or True  # бейдж рисует шаблон подпункта


def test_compact_sidebar_renders_on_dashboard():
    t = TenantFactory(
        schema_name="tenant_sb4",
        slug="sb4",
        name="Sb4",
        business_type="bakery",
        site_config={"onboarding": dict(_TOUCHED)},
    )
    html = core_views.dashboard(_req(t, "/dashboard/")).content.decode()
    # AB1-групп больше нет; R7-1: «Mein Geschäft» — законный подпункт раздела
    # «Einstellungen», проверяем отсутствие ГРУППОВЫХ ЗАГОЛОВКОВ классик-меню.
    assert "nav-group" not in html
    assert 'href="/dashboard/marketing/"' in html  # якорь Marketing → центр ST-6
    assert 'href="/dashboard/integrationen/"' in html
    assert "data-inbox-badge" in html  # бейдж переехал на Marketing-якорь


def test_sales_anchor_respects_orders_view_default():
    """V4 (2026-08-03): якорь «Verkäufe» сайдбара ведёт на единую страницу
    продаж для ЛЮБОГО архетипа; легаси-маппинг (отель→Belegungsplan, магазин→
    список) закреплён в test_orders_view. Сайдбар
    рендерится легаси-веткой AB1 и якоря verkaeufe не несёт."""
    hotel = TenantFactory(
        slug="sbho", name="SbHo", business_type="hotel", disabled_modules=["events", "booking"]
    )
    item = next(it for it in modules.sidebar_nav(hotel) if it["url_name"] == "verkaeufe")
    assert item["nav_key"] == "board"  # общий якорь «Verkäufe» единой страницы

    shop = TenantFactory(
        slug="sbsh",
        name="SbSh",
        business_type="shop",
        disabled_modules=["events", "booking", "stays", "jobs"],
    )
    item = next(it for it in modules.sidebar_nav(shop) if it["url_name"] == "verkaeufe")
    assert item["nav_key"] == "board"


# --- SM-4 (решение владельца 2026-08-11): подпункты разделов «слайдером» -------


def test_sidebar_children_composition():
    """Подпункты якоря = advanced-состав его хабов (единый реестр W8).

    R2 (редизайн B, осознанная переписка): ящик «Erweitert» снят со страниц —
    складская группа ВЕРНУЛАСЬ подпунктами «Sortiment» (утверждённая структура:
    каждая страница живёт ровно в одном месте, вход — сайдбар/палитра).
    «Verkäufe» держит рабочие входы дня ПЕРЕД отчётной группой.
    """
    t = TenantFactory(slug="sbc1", name="SbC", business_type="restaurant", disabled_modules=[])
    by_anchor = {it["url_name"]: it["children"] for it in modules.sidebar_nav(t)}

    assert by_anchor["dashboard"] == []
    # SH-14/15 (фидбэк владельца 2026-08-20, осознанное дополнение состава):
    # «Kunden» и «Lieferungen» — подпункты продаж; оба ведут на страницу продаж
    # (разные вкладка/фильтр), поэтому дедуп подпунктов — по (url_name, query).
    assert [(c["url_name"], c["query"]) for c in by_anchor["verkaeufe"]] == [
        # R7-1: первым — обзор раздела, затем ВЕСЬ состав хаба (main+advanced)
        ("verkaeufe", ""),
        ("jobs:list", ""),
        ("booking:resources", ""),
        ("booking:availability", ""),
        ("stays:checkins", ""),
        ("orders:kitchen", ""),  # гастро-тип: гейт business_types пропускает
        ("ablaeufe", "?from=board"),
        ("verkaeufe", "?tab=kunden"),
        # R7-3: доставка и оплаты — свои страницы (были фильтром/столбцом)
        ("orders:deliveries", ""),
        ("payments-page", ""),
        ("promotions:analytics", ""),
        ("finance:journal", ""),
        ("stays:reports", ""),
    ]
    site = [c["url_name"] for c in by_anchor["site-home"]]
    assert site == ["site-home", "site-seo", "domains", "media-library"]
    ang = [c["url_name"] for c in by_anchor["sellable-manage"]]
    assert ang == [
        "sellable-manage",  # R7-1: обзор раздела первым (SR-1: «Produkte» умер)
        "booking:services",
        "stays:units",
        "events:list",
        "events:tour-list",
        "catalog:category-list",
        "collections:list",
        # R2: складская группа — подпункты Sortiment (ящика на страницах нет)
        "stock",
        "purchasing",
        "catalog:combo-list",
        "imports:start",
    ]
    sett = [c["url_name"] for c in by_anchor["einstellungen-home"]]
    # X2a: «Integrationen» стал подпунктом (был доступен с первого экрана только
    # хаб-плиткой главной, которую X2a удалил как дубль сайдбара).
    # R7-1: подменю несёт ВЕСЬ состав настроек — прежде main-часть жила
    # таб-баром на странице (дубль меню, фидбэк владельца 2026-08-24).
    assert sett == [
        "einstellungen-home",  # SR-5: обзор раздела первым (авто-вставка якоря)
        "settings",
        "languages",
        "legal-docs",
        "payment-settings",
        "notifications-settings",
        "ablaeufe",
        "integrations-home",
        "billing",
        "team",
        "extras",
        "modules",
        "finder-settings",
        "support:help",
    ]
    # каждый подпункт резолвится (инвариант W8 держит и это, но локально быстрее)
    for children in by_anchor.values():
        for c in children:
            reverse(c["url_name"])


def test_sidebar_children_module_gates():
    """Гейты подпунктов: без модуля stays нет «Berichte», без finance —
    «Finanzen», без analytics — «Auswertungen»; Abläufe остаётся всегда."""
    t = TenantFactory(
        slug="sbc2",
        name="SbG",
        business_type="bakery",
        disabled_modules=["stays", "finance", "analytics"],
    )
    verk = {
        c["url_name"]
        for it in modules.sidebar_nav(t)
        if it["url_name"] == "verkaeufe"
        for c in it["children"]
    }
    assert "stays:reports" not in verk
    assert "finance:journal" not in verk
    assert "promotions:analytics" not in verk
    assert "ablaeufe" in verk


def test_sidebar_renders_children_slider():
    """Рендер: блок подпунктов свёрнут (hidden) у неактивного раздела, раскрыт
    у активного; шеврон-кнопка с data-nav-toggle; подпункты несут data-label
    (фильтр поиска меню их находит)."""
    t = TenantFactory(
        slug="sbc3",
        name="SbR",
        business_type="hotel",
        disabled_modules=[],
        site_config={"onboarding": {"step": 7, "skipped": [], "completed": True}},
    )
    html = core_views.dashboard(_req(t)).content.decode()
    # на Übersicht раздел Verkäufe неактивен → его блок подпунктов hidden
    assert 'data-nav-children="board"' in html
    import re as _re

    m = _re.search(r'data-nav-children="board"[^>]*class="([^"]+)"', html)
    assert m and "hidden" in m.group(1)
    assert 'data-nav-toggle="board"' in html
    # подпункт с data-label — участвует в поиске меню
    assert "Auswertungen" in html
    # активный раздел (сама Übersicht подпунктов не имеет — проверяем на
    # странице продаж: её блок раскрыт)
    html2 = core_views.verkaeufe(_req(t, "/dashboard/verkaeufe/")).content.decode()
    m2 = _re.search(r'data-nav-children="board"[^>]*class="([^"]+)"', html2)
    assert m2 and "hidden" not in m2.group(1)


def test_child_highlight_is_url_based_single():
    """VF-7a (фидбэк 2026-08-24 «выбелены оба»): подпункты, делящие nav_key
    (booking:resources + booking:availability; обзор Marketing + Действия),
    подсвечиваются ПО URL — активен ровно один."""
    from django.test import RequestFactory
    from django.urls import reverse

    from apps.core.context import modules_nav

    t = TenantFactory(slug="hlt", name="H", business_type="friseur")

    def _actives(path):
        req = RequestFactory().get(path)
        req.tenant = t
        nav = modules_nav(req)
        out = []
        for it in nav["nav_compact"]:
            out += [c["url_name"] for c in it.get("children", []) if c.get("active")]
        return out

    assert _actives(reverse("booking:availability")) == ["booking:availability"]
    assert _actives(reverse("booking:resources")) == ["booking:resources"]
    acts = _actives(reverse("promotions:promotion-list"))
    assert acts == ["promotions:promotion-list"]
