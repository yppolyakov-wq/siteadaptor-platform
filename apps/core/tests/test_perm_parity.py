"""KA-12 E6.7a: эталон паритета прав.

Таблица ниже — СЕГОДНЯШНЕЕ поведение ролевых проверок (до введения реестра прав).
Каждая проверка внутри экранов переведена на ``permissions.has_perm(key)``; тест
требует, чтобы ключ давал ровно прежний ответ для каждой роли. Осознанные изменения
дефолтов (E6.7f) переписывают таблицу явно, с диффом в коммите.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured

from apps.core import permissions, refunds, roles
from apps.core.models import Membership

pytestmark = pytest.mark.django_db

OWN, A, S = Membership.ROLE_OWNER, Membership.ROLE_ADMIN, Membership.ROLE_STAFF
ROLES = (OWN, A, S, "")  # "" — вошёл, но без Membership в этой схеме

OWNER = {OWN}
OWNER_ADMIN = {OWN, A}
ALL = {OWN, A, S}

# Место в коде → (ключ права, у кого сегодня есть доступ).
SITES = {
    # roles.can_edit_policy: booking-правила отмены и чужие заметки, stays-тарифы, price-calendar
    "booking._can_edit_policy": ("preise.edit", OWNER_ADMIN),
    "stays.RATE_EDIT_ACTIONS / can_price / can_edit_prices": ("preise.edit", OWNER_ADMIN),
    "stays.price_calendar._can_edit": ("preise.edit", OWNER_ADMIN),
    # KA-D7: финансовые выгрузки (middleware + кнопки CSV/DATEV)
    "roles.can_export_finance / FINANCE_EXPORT_PREFIXES": ("finanzen.export", OWNER_ADMIN),
    # Gutschrift, Anzahlungsrechnung, полный поиск получателя счёта
    "finance.credit / full_search, deal_card._advance, deal_advance": (
        "finanzen.korrektur",
        OWNER_ADMIN,
    ),
    "refunds.may_refund → apply_action": ("geld.erstatten", OWNER_ADMIN),
    "deal_card._refund_form, deal_refund": ("geld.korrektur", OWNER),
    "status_manager «ohne Erstattung»": ("geld.richtlinie", OWNER),
    "booking._may_close_business, Betriebsferien ganz": ("betriebsferien.ganz", OWNER),
    "events.event_action cancel": ("veranstaltung.absagen", OWNER),
    "publishing.can_manage, platform_bot_*, Telegram-Inhaber, GBP-Öffnungszeiten": (
        "kanaele.edit",
        OWNER,
    ),
    "Stadtportal-Statistik (owner_views, Link, lite)": ("stadtportal.view", OWNER),
    "Kontaktdaten unmaskiert (palette, finance-Kundensuche)": ("kunden.kontakte", OWNER),
    "PII-Exporte (CRM/Verkäufe/Gäste/Roster)": ("kunden.export", OWNER),
    "DSGVO-Anfrage": ("kunden.dsgvo", OWNER),
}

# Ключи, которые сегодня есть у всех ролей кабинета (гейтов ещё нет или они открыты).
OPEN_TODAY = (
    "verkaeufe.view",
    "verkaeufe.edit",
    "verkaeufe.storno",
    "rezeption.edit",
    "geld.rabatt",
    "geld.preis",
    "geld.bezahlt",
    "geld.einloesen",
    "geld.zahlungslink",
    "sortiment.edit",
    "lager.edit",
    "kunden.view",
    "kunden.edit",
    "marketing.edit",
    "nachrichten.edit",
    "website.edit",
    "domains.edit",
    "einstellungen.edit",
    "funktionen.edit",
    "ablaeufe.edit",
    "finanzen.journal",
    "finanzen.edit",
)


def _user(role):
    from uuid import uuid4

    user = get_user_model().objects.create_user(username=f"pp-{role or 'x'}-{uuid4().hex[:6]}")
    if role:
        Membership.objects.create(user=user, role=role)
    return user


@pytest.mark.parametrize("site", sorted(SITES))
@pytest.mark.parametrize("role", ROLES)
def test_site_keeps_todays_access(site, role):
    key, allowed = SITES[site]
    assert permissions.has_perm(_user(role), key) is (role in allowed)


@pytest.mark.parametrize("key", OPEN_TODAY)
@pytest.mark.parametrize("role", ROLES)
def test_open_keys_stay_open(key, role):
    assert permissions.has_perm(_user(role), key) is (role in ALL)


@pytest.mark.parametrize("role", ROLES)
def test_legacy_helpers_match(role):
    """Старые имена — тонкие алиасы к реестру (ответ прежний)."""
    user = _user(role)
    assert roles.can_edit_policy(user) is (role in OWNER_ADMIN)
    assert roles.can_export_finance(user) is (role in OWNER_ADMIN)
    assert refunds.may_refund(user) is (role in OWNER_ADMIN)
    assert roles.is_owner(user) is (role == OWN)


def test_anonymous_has_nothing():
    for key in permissions.PERMS:
        assert permissions.has_perm(AnonymousUser(), key) is False


def test_unknown_key_is_an_error_in_tests():
    with pytest.raises(ImproperlyConfigured):
        permissions.has_perm(_user(OWN), "verkaeufe.vieww")


def test_owner_has_every_key():
    assert permissions.effective(_user(OWN)) == frozenset(permissions.PERMS)


# --- реестр ----------------------------------------------------------------------


def test_registry_shape():
    import re

    for key, perm in permissions.PERMS.items():
        assert re.fullmatch(r"[a-z]+\.[a-z]+", key), key
        assert perm.group in permissions.GROUPS, key
        for req in perm.requires:
            assert req in permissions.PERMS, f"{key} requires {req}"


def test_requires_has_no_cycles():
    def walk(key, seen):
        assert key not in seen, f"цикл: {seen + [key]}"
        for req in permissions.PERMS[key].requires:
            walk(req, seen + [key])

    for key in permissions.PERMS:
        walk(key, [])


def test_presets_are_closed_and_known():
    for role, keys in permissions.PRESETS.items():
        assert keys <= frozenset(permissions.PERMS), role
        assert permissions.for_role(role) == keys, f"{role}: пресет теряет ключи по requires"
    assert permissions.PRESETS[S] <= permissions.PRESETS[A]


def test_frontdesk_contract_for_z5():
    assert "rezeption.edit" in permissions.PERMS
    assert "verkaeufe.storno" in permissions.PERMS


def test_one_query_per_check():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    user = _user(S)
    with CaptureQueriesContext(connection) as ctx:
        permissions.has_perm(user, "preise.edit")
    assert len(ctx.captured_queries) == 1


# --- grep-замок: ролевые проверки только в реестре или для Inhaber-Vorbehalt -----

# Где ``is_owner`` законен: пол (IBAN, импорт с чужого сайта, Impressum лёгкого кабинета),
# middleware/навигация (переходят на права в E6.7b/e) и сам модуль ролей.
IS_OWNER_ALLOWED = {
    "apps/core/roles.py",
    "apps/core/middleware.py",  # E6.7b: process_view по правам вьюхи
    "apps/core/view_perms.py",  # FLOOR — Inhaber-Vorbehalt
    "apps/core/templatetags/cabinet.py",  # cab_is_owner — только для пола (lite-business)
    "apps/core/lite_cabinet.py",  # пункт «Geschäft» (Impressum) — пол
    "apps/core/views.py",  # can_edit_bank (IBAN) — пол
    "apps/orders/views.py",  # IBAN Vorkasse — пол
    "apps/imports/views.py",  # импорт с чужого сайта — пол
}


def test_no_role_checks_outside_registry():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    bad = []
    for path in sorted((root / "apps").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        text = path.read_text()
        if re.search(r"\broles\.is_owner\(|\bimport is_owner\b", text) and (
            rel not in IS_OWNER_ALLOWED
        ):
            bad.append(f"{rel}: is_owner вне пола — используйте permissions.has_perm")
        if re.search(r"role_of\([^)]*\)\s+in\s+\(", text):
            bad.append(f"{rel}: role_of(...) in (...) — используйте permissions.has_perm")
    assert bad == []
