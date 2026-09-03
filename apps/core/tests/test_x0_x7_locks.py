"""X0+X7 (план cabinet-cleanup-2026-08-19): хотфиксы навигации + предохранители.

X0: owner-only табы прячутся у сотрудников · «Full view» → Verkäufe · карточка
непрочитанных на marketing-home · гейт якоря Marketing (замки в test_sidebar_st4b).

X7: два инвариант-замка против возврата «каши»:
- состав якорей сайдбара ЗАМОРОЖЕН (мораторий владельца, минимум квартал) —
  менять только осознанной правкой этого теста с записью в build-log;
- каждый новый беспараметрный экран кабинета обязан попасть в реестр
  навигации/палитру ЛИБО быть осознанно внесён в EXPECTED_UNLISTED ниже.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.template import Context, Template

from apps.core import nav_registry
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- X7.1: замок состава якорей (мораторий) ----------------------------------


def test_sidebar_anchor_composition_is_frozen():
    """Состав/порядок якорей — под мораторием (решение владельца 2026-08-19,
    план cabinet-cleanup §0.4): рынок держит 6–9 фиксированных пунктов, наши
    9 перекроек за 7 недель — главный источник «каши». Изменение якорей =
    осознанная правка ЭТОГО замка + запись в build-log."""
    assert [(a.url_name, a.nav_key, a.icon) for a in nav_registry.ANCHORS] == [
        ("dashboard", "dashboard", "🏠"),
        ("verkaeufe", "board", "🗂️"),
        ("sellable-manage", "sellables", "📦"),
        ("marketing-home", "promotions", "📣"),
        ("site-home", "site", "✏️"),
        # SR-5: якорь ведёт на обзор (nav_key прежний — подсветка цела)
        ("einstellungen-home", "settings", "⚙️"),
    ]


# --- X7.3: замок «новый экран обязан быть в навигации» ------------------------

# Беспараметрные url кабинета, ОСОЗНАННО отсутствующие в реестре/палитре.
# Категории: [POST] — приёмники форм/действий, не страницы; [302] — легаси-
# редиректы (W10-6/W11-5); [X2] — легаси-поверхности, план X2 (снос);
# [X4] — экраны-сироты, план X4 (получат вход в навигацию/палитру);
# [OK] — самостоятельный хром (мастер) или служебные JSON.
EXPECTED_UNLISTED = frozenset(
    {
        # [POST] приёмники и action-роуты
        "billing-checkout",
        "billing-payments-callback",
        "billing-payments-connect",
        "billing-payments-methods",
        "booking:booking-create",
        "booking:service-inline-edit",
        "booking:service-photo-edit",
        "catalog:category-create",
        "catalog:category-inline-edit",
        "catalog:combo-create",
        "catalog:product-create",
        "catalog:product-inline-edit",
        "catalog:product-photo-edit",
        "catalog:products-merge",
        "channel-config",
        # POST-only приёмник панели «Anfrage-Formular» (её UI живёт на «Abläufe»
        # с X2c). Был ошибочно классифицирован как экран и попал в палитру —
        # серверный обход вскрыл 405 при клике из Ctrl+K.
        "jobs:anfrage-form-settings",
        "channel-toggle",
        "crm:company-create",
        "crm:customer-create",
        "crm:customer-export",
        "domain-add",
        "events:create",
        "events:event-inline-edit",
        "events:event-photo-edit",
        "events:teacher-create",
        # ERP-4: DATEV-выгрузка расходов — CSV-скачивание, вход кнопкой на Ausgaben.
        "finance:expenses-datev",
        "finance:export-csv",
        "finance:export-datev",
        "promotions:promotion-create",
        "promotions:promotion-inline-edit",
        "promotions:promotion-photo-edit",
        "promotions:voucher-redeem",
        "set-cabinet-lang",
        "set-presence",
        # DL-13 C3: POST-only targeted-write режима страницы акций (панель в списке акций).
        "promotions:promotion-page-mode",
        "site-cblock-photo-edit",
        "site-inline-edit",
        "site-preview-draft",
        # STU-3: JSON-виды охвата настройки («для всех / только здесь») — служебные
        # запросы Студии из её же панели, отдельного экрана у них нет.
        "site-scope-save",
        "site-scope-state",
        "site-share-preview",
        "stays:reports-export",
        "stays:stay-create",
        "stays:stay-inline-edit",
        "stays:stay-photo-edit",
        "telegram-connect",
        "telegram-disconnect",
        "verkaeufe-view",
        "sortiment-view",  # SR-1: POST-сеттер вида Kacheln/Liste (кнопки на Sortiment)
        # [302] легаси-редиректы с GET-carry
        "booking:calendar",
        "catalog:product-list",  # SR-1: страница товаров умерла → 302 на Sortiment
        "orders:order-list",
        "site",
        "stays:calendar",
        "stays:today",
        "board",  # X2b: легаси-доска снесена → 302 на Verkäufe
        "jobs:list",  # VF-10: пункт «Aufträge» ведёт прямо на verkaeufe?tab=job;
        # сам URL остался легаси-редиректом X2c для старых ссылок
        "billing-portal",  # редирект в Stripe-портал, не экран
        # [POST] приёмник панели колонок (её UI живёт на «Abläufe»)
        "board-settings",
        "orders:kitchen-board",  # HTMX-партиал поллинга KDS
        # [DOC] генераторы печатных документов (вход — кнопка родного экрана)
        "promotions:shop-poster",
        # [＋] формы создания: вход — кнопка «＋» поверхности продаж
        "stays:stay-new",
        "jobs:new",  # X2c: ручная заявка (приёмник POST схлопнутого списка)
        # [OK] служебное
        "inbox:unread-count",  # JSON-счётчик бейджа
        "palette-search",  # X8: JSON-поиск палитры (не страница)
        "setup",  # мастер — собственный хром (_base_setup)
        "site-menu",  # области Studio: вход из рейки билдера, не из сайдбара
        "site-pages",
        "site-preview",
        "site-sections",
    }
)

# X2a: «willkommen/» жил ВНЕ этих префиксов — замок его не видел, и удаление
# маршрута прошло бы мимо инварианта. Добавлен, чтобы класс ловился впредь.
_CABINET_PREFIXES = ("dashboard/", "catalog/", "promotions/", "imports/", "crm/", "willkommen/")


def _cabinet_screen_names():
    from django.urls import get_resolver
    from django.urls.resolvers import URLPattern, URLResolver

    def walk(resolver, prefix="", ns=""):
        for p in resolver.url_patterns:
            if isinstance(p, URLResolver):
                yield from walk(
                    p, prefix + str(p.pattern), ns + (p.namespace + ":" if p.namespace else "")
                )
            elif isinstance(p, URLPattern) and p.name:
                full = prefix + str(p.pattern)
                if not full.startswith(_CABINET_PREFIXES):
                    continue
                if p.pattern.converters or "(" in full or "<" in full:
                    continue
                yield ns + p.name

    return set(walk(get_resolver("config.urls_tenant")))


def test_every_cabinet_screen_listed_or_consciously_excluded():
    """Инвариант X7.3 (принцип §5.5 исследования 2026-08-18): экран без входа из
    навигации = класс дефектов «сирота», с которого начинается Битрикс-каша.
    Новый беспараметрный url кабинета обязан либо попасть в nav_registry
    (палитра/табы), либо быть ОСОЗНАННО добавлен в EXPECTED_UNLISTED с
    категорией. Экраны категории [X4] уходят из списка волной X4."""
    inventory = _cabinet_screen_names()
    listed = {e["url_name"] for e in nav_registry.palette_entries()} | {
        a.url_name for a in nav_registry.ANCHORS
    }
    unlisted = inventory - listed
    assert unlisted == set(EXPECTED_UNLISTED), (
        f"новые не в реестре: {sorted(unlisted - EXPECTED_UNLISTED)}; "
        f"устарели в EXPECTED_UNLISTED: {sorted(EXPECTED_UNLISTED - unlisted)}"
    )


# --- X0: owner-only табы прячутся у сотрудников -------------------------------


def _req_with_role(tenant, role):
    user = get_user_model().objects.create_user(
        username=f"u-{uuid4().hex[:8]}", email=f"{uuid4().hex[:8]}@t.de", password="pw12345678"
    )
    Membership.objects.create(user=user, role=role)
    return SimpleNamespace(tenant=tenant, user=user)


def _settings_menu(tenant, user):
    """R7-1: состав раздела «Einstellungen» так, как его видит этот пользователь
    (таб-бары сняты — единственная поверхность меню)."""
    from apps.core import modules

    section = next(it for it in modules.sidebar_nav(tenant, user) if it["nav_key"] == "settings")
    return [str(c["label"]) for c in section["children"]]


def test_owner_only_entries_hidden_for_staff():
    """X0 (переписан под R7-1): owner-гейт переехал из снесённого тега в
    подменю сайдбара — сотруднику мёртвые экраны (403) не показываем."""
    t = TenantFactory(slug=f"x0-{uuid4().hex[:6]}", name="X0")
    req = _req_with_role(t, Membership.ROLE_STAFF)
    kids = _settings_menu(t, req.user)
    for lbl in ("Team & Zugriff", "Abo & Rechnung", "Recht & Steuern"):
        assert lbl not in kids, lbl
    assert "Mein Geschäft" in kids


def test_owner_only_entries_visible_for_owner_and_failopen_without_user():
    t = TenantFactory(slug=f"x0o-{uuid4().hex[:6]}", name="X0o")
    req = _req_with_role(t, Membership.ROLE_OWNER)
    kids = _settings_menu(t, req.user)
    assert "Team & Zugriff" in kids and "Abo & Rechnung" in kids
    # fail-open: без user (простые рендеры/тесты) показываем всё — доступ
    # держит middleware, скрытие остаётся чистым UX-слоем.
    assert "Team & Zugriff" in _settings_menu(t, None)


def test_owner_only_hidden_in_palette_for_staff():
    t = TenantFactory(slug=f"x0p-{uuid4().hex[:6]}", name="X0p")
    html = Template("{% load cabinet %}{% nav_palette %}").render(
        Context({"request": _req_with_role(t, Membership.ROLE_STAFF)})
    )
    assert "Team &amp; Zugriff" not in html
    # «Sprachen» — не-owner запись settings-хаба, остаётся видимой
    # (якорь «Einstellungen» дедупит запись «Mein Geschäft» по url_name).
    assert "Sprachen" in html


# --- X0: карточка непрочитанных на marketing-home -----------------------------


def test_marketing_home_shows_unread_card():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views as core_views
    from apps.inbox.models import Conversation

    t = TenantFactory(slug=f"x0m-{uuid4().hex[:6]}", name="X0m", business_type="friseur")
    Conversation.objects.create(subject="Frage", unread_for_staff=True)
    req = RequestFactory().get("/dashboard/marketing/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = t
    req.user = get_user_model().objects.create_user(
        username=f"m-{uuid4().hex[:8]}", email=f"m-{uuid4().hex[:8]}@t.de", password="pw12345678"
    )
    html = core_views.marketing_home(req).content.decode()
    assert "ungelesen" in html
    assert "/dashboard/inbox/" in html


# --- X2b: снос легаси-доски не ломает главную у events/jobs-архетипов ---------


def test_home_entry_never_points_to_removed_board():
    """Риск №1 разведки X2: `orders_view._view_url` звался С ГЛАВНОЙ и возвращал
    reverse("board"); после сноса маршрута это дало бы 500 у архетипов, чей
    primary-модуль не booking/stays/catalog (события/заявки/туры). Замок держит
    инвариант: вход всегда резолвится и ведёт на единую страницу продаж."""
    from django.urls import reverse

    from apps.core import orders_view as ov

    for bt in ("events", "handwerker", "tour_operator", "werkstatt", "other"):
        t = TenantFactory(slug=f"x2b-{bt[:6]}-{uuid4().hex[:4]}", name="X2b", business_type=bt)
        assert ov.entry_url_name(t) == "verkaeufe"
        assert reverse(ov.entry_url_name(t)) == "/dashboard/verkaeufe/"
