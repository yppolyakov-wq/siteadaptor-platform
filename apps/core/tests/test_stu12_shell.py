"""STU-12a — Студия без рейки: верхняя строка с «Seite ▾» и «Design des Shops →»,
одна колонка справа, открытая по умолчанию на настройках открытой страницы.

ТЗ: docs/stu12-studio-simplification-plan-2026-09-09.md §2/12a. Замки написаны ДО
кода и красны без правок; ids колонки (`#bld-editor-pane`, `#bld-block-popup`,
`#bld-panel-toggle`, `#home-prev-frame`, `#bld-root`) обязаны пережить волну —
на них держатся замки старого билдера.
"""

import pathlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.core import views
from apps.core.design_page import design_view
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TEMPLATE = pathlib.Path("templates/tenant/site_home.html")


def _req(method, path, tenant, data=None, real_user=False):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    if real_user:
        o = uuid4().hex[:8]
        req.user = get_user_model().objects.create_user(
            username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
        )
    else:
        req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _html(tenant, path="/dashboard/site/home/"):
    resp = views.home_builder_view(_req("get", path, tenant))
    assert resp.status_code == 200
    return resp.content.decode()


# ── снос ──────────────────────────────────────────────────────────────────────
def test_left_rail_page_strip_and_area_tabs_are_gone():
    """Решение владельца 2026-09-09 (1): у рейки не осталось функций — всё
    открывается кликом по канве, «+» и «Seite ▾». Лента страниц (3A) и
    вкладки панели (вторая навигация) — туда же."""
    html = _html(TenantFactory())
    for gone in (
        'id="st-rail"',
        'id="st-pages"',
        'id="bld-area-tabs"',
        "data-st-level=",
        "bld-rail-btn",
    ):
        assert gone not in html, gone


def test_topbar_duplicates_are_gone_but_shell_ids_survive():
    """⚙️ Vorlage / ☰ Menü / 🧱 Blöcke дублировали рейку и области; 🔍 Kompakt
    переезжает в шапку колонки (12b). Каркас колонки и канвы — те же ids."""
    html = _html(TenantFactory())
    for gone in (
        'id="bld-drawer-toggle"',
        'id="bld-menu-btn"',
        'id="bld-blocks-btn"',
        'id="bld-compact-btn"',
    ):
        assert gone not in html, gone
    for keep in (
        'id="bld-root"',
        'id="bld-editor-pane"',
        'id="bld-block-popup"',
        'id="bld-panel-toggle"',
        'id="home-prev-frame"',
        'id="bld-inserter"',
        ">Studio</span>",
    ):
        assert keep in html, keep


# ── «Seite ▾» (3A) ────────────────────────────────────────────────────────────
def test_page_switcher_lists_cart_checkout_and_promo_groups():
    """«Seite ▾» — единственный путь к страницам, до которых кликом по канве не дойти:
    Warenkorb и страницы групп акций (`?gruppe=`, STU-7).

    STU-14: пункт «Kasse» СНЯТ — `storefront-checkout` это POST-приёмник корзины
    (@require_POST), страницы по этому адресу нет и переход из Студии давал 405.
    Замок теперь стережёт обратное: чтобы её не вернули в список.
    """
    tenant = TenantFactory()
    PromotionFactory(group="Räumung", status="active")
    PromotionFactory(group="Entwurf-Gruppe", status="draft")
    html = _html(tenant)
    assert 'id="st-page-menu"' in html and 'id="st-page-name"' in html
    assert f'data-st-page="{reverse("storefront-cart")}"' in html
    assert f'data-st-page="{reverse("storefront-checkout")}"' not in html
    assert 'data-st-page="/aktionen/?gruppe=R%C3%A4umung"' in html
    assert "Entwurf-Gruppe" not in html, "черновики акций страницы не образуют"
    # группы списка: клик-достижимые отдельно от «только отсюда»
    assert 'data-st-section="here"' in html and 'data-st-section="site"' in html
    assert 'data-st-section="groups"' in html


def test_page_switcher_uses_the_same_navigation_as_the_old_strip():
    """Клик по пункту = `?page=` (тот же санитайзер `_safe_preview_page`, STU-7):
    страница группы акций уезжает вместе с параметром."""
    body = TEMPLATE.read_text()
    i = body.index('id="st-page-menu"')
    js = body[body.index("st-page-menu", i + 20) :]
    assert '"?page=" + encodeURIComponent(' in js


# ── «Design des Shops →» (1B) ─────────────────────────────────────────────────
def test_design_link_carries_return_path_and_design_page_shows_back_link():
    tenant = TenantFactory()
    html = _html(tenant, "/dashboard/site/home/?page=/sortiment/")
    assert 'id="st-design-link"' in html
    assert f'href="{reverse("design")}?next=' in html
    back = "/dashboard/site/home/?page=/sortiment/"
    resp = design_view(_req("get", reverse("design"), tenant, {"next": back}, real_user=True))
    page = resp.content.decode()
    assert f'href="{back}"' in page and "Zurück ins Studio" in page


@pytest.mark.parametrize(
    "bad",
    [
        "https://evil.example/",
        "//evil.example/x",
        "/dashboard/orders/",
        "/dashboard/site/home/\\evil",
    ],
)
def test_design_back_link_rejects_foreign_targets(bad):
    """Возврат только в Студию: чужой путь/хост/схема → ссылки нет (класс T-6)."""
    tenant = TenantFactory()
    resp = design_view(_req("get", reverse("design"), tenant, {"next": bad}, real_user=True))
    page = resp.content.decode()
    assert "Zurück ins Studio" not in page
    assert "evil" not in page


# ── колонка по умолчанию ──────────────────────────────────────────────────────
def test_panel_opens_by_default_on_the_current_page_area():
    """Без рейки единственный вход в настройки страницы — сама колонка: при входе
    она ОТКРЫТА на `stuPageArea()` (sections на главной / page иначе), а не
    свёрнута (W1 «канва-first» пересмотрен решением владельца). Восстановление
    области из localStorage (`sf_cur_area`) больше не нужно."""
    body = TEMPLATE.read_text()
    assert "function stuDefaultOpen()" in body
    i = body.index("function syncFrameState(frame)")
    sync = body[i : body.index("\n  }\n", i)]
    assert "applyStuPageScope();" in sync and "stuDefaultOpen();" in sync
    assert sync.index("applyStuPageScope();") < sync.index("stuDefaultOpen();")
    assert "sf_cur_area" not in body


def test_panel_titles_no_longer_depend_on_area_tabs():
    """Заголовок колонки брался с кнопки вкладки — вкладок нет, подпись обязана
    называть охват: страница = «Diese Seite: ‹тип›»."""
    body = TEMPLATE.read_text()
    assert "function panelTitleFor(" in body
    assert "STU_LABELS[curStuPage]" in body[body.index("function panelTitleFor(") :][:1200]


def test_mobile_has_a_page_settings_button():
    """< lg рейки не было и раньше, а теперь нет и ☰/⚙️ — единственный вход в
    настройки страницы на телефоне: «⚙» в верхней строке (F7A, часть 1)."""
    html = _html(TenantFactory())
    assert 'id="st-page-btn"' in html
