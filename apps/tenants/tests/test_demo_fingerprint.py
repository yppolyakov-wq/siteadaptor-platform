"""T-10 D-2: пересев только изменённых демо (отпечаток кита)."""

import dataclasses

import pytest
from django.core.management import call_command
from django.utils import translation

from apps.tenants import demo_fingerprint, demo_kits
from apps.tenants.management.commands import seed_demo_tenants
from apps.tenants.tests.factories import TenantFactory

KEY = "bakery"


def test_fingerprint_stable_across_languages():
    kit = demo_kits.KITS[KEY]
    with translation.override("ru"):
        ru = demo_fingerprint.kit_fingerprint(kit)
    with translation.override("de"):
        de = demo_fingerprint.kit_fingerprint(kit)
    assert ru == de


def test_fingerprint_changes_with_spec_and_own_translation(monkeypatch):
    kit = demo_kits.KITS[KEY]
    base = demo_fingerprint.kit_fingerprint(kit)
    assert demo_fingerprint.kit_fingerprint(dataclasses.replace(kit, label="Anders")) != base
    from apps.tenants import demo_i18n

    en = dict(demo_i18n._map("en"))
    monkeypatch.setitem(demo_i18n._MAPS, "en", {**en, kit.label: "Changed translation"})
    assert demo_fingerprint.kit_fingerprint(kit) != base
    # Чужая строка в словаре отпечаток этого кита не трогает.
    monkeypatch.setitem(demo_i18n._MAPS, "en", {**en, "zz unrelated string": "x"})
    assert demo_fingerprint.kit_fingerprint(kit) == base


def test_normalize_keeps_fingerprint():
    from apps.tenants.siteconfig import normalize

    stored = {"key": KEY, "fp": "abc", "seeded_at": "2026-10-20T00:00:00"}
    assert normalize({"demo_kit": stored})["demo_kit"] == stored
    assert "demo_kit" not in normalize({})


@pytest.fixture
def seeded(monkeypatch):
    calls = []

    def fake_seed(self, key, options):
        calls.append((key, options["recreate"]))
        return True

    monkeypatch.setattr(seed_demo_tenants.Command, "_seed_one", fake_seed)
    return calls


@pytest.mark.django_db
def test_changed_seeds_missing_and_changed_skips_equal(seeded):
    slug = demo_kits.KITS[KEY].subdomain or f"{KEY}-demo"
    tenant = TenantFactory(slug=slug, is_demo=True)
    fp = demo_fingerprint.kit_fingerprint(demo_kits.KITS[KEY])

    demo_fingerprint.stamp(tenant, KEY, fp)
    call_command("seed_demo_tenants", "--kit", KEY, "--changed")
    assert seeded == []  # отпечаток совпал — пропуск

    demo_fingerprint.stamp(tenant, KEY, "old")
    call_command("seed_demo_tenants", "--kit", KEY, "--changed")
    assert seeded == [(KEY, True)]  # изменён — пересоздать

    seeded.clear()
    call_command("seed_demo_tenants", "--kit", "cafe", "--changed")
    assert seeded == [("cafe", True)]  # демо нет — создать


@pytest.mark.django_db
def test_stamp_writes_fingerprint_without_seeding(seeded):
    slug = demo_kits.KITS[KEY].subdomain or f"{KEY}-demo"
    tenant = TenantFactory(slug=slug, is_demo=True, site_config={"theme": "dark"})
    call_command("seed_demo_tenants", "--kit", KEY, "--stamp")
    tenant.refresh_from_db()
    assert seeded == []
    assert demo_fingerprint.stored(tenant) == demo_fingerprint.kit_fingerprint(demo_kits.KITS[KEY])
    assert tenant.site_config["theme"] == "dark"  # остальной конфиг цел


@pytest.mark.django_db
def test_stamp_skips_non_demo_tenant(seeded):
    slug = demo_kits.KITS[KEY].subdomain or f"{KEY}-demo"
    tenant = TenantFactory(slug=slug, is_demo=False)
    call_command("seed_demo_tenants", "--kit", KEY, "--stamp")
    tenant.refresh_from_db()
    assert demo_fingerprint.stored(tenant) == ""
