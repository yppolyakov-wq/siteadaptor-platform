"""STU-12g (первый срез): `apply_look` — ТОЛЬКО оптика.

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12g): «apply_look — только
оптика (сегодня сбрасывает порядок секций главной; у apply_bundle семантика обратная и
остаётся)». Владелец выбирает кожу — и теряет курированную композицию главной: состав и
порядок секций переписывались раскладкой рекомендованного шаблона архетипа.
"""

import pytest

from apps.tenants import siteconfig, sitetemplates
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _sections(tenant):
    cfg = siteconfig.normalize(tenant.site_config)
    return [(s["key"], s["enabled"]) for s in cfg["sections"]]


def test_apply_look_keeps_the_home_composition():
    """Кожа не трогает ни состав, ни порядок секций главной."""
    tenant = TenantFactory(slug="lksk1", name="LkSk1", business_type="retail")
    # композиция владельца: своя, отличная от раскладки шаблона
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["sections"] = [
        {"key": "faq", "enabled": True},
        {"key": "hero", "enabled": True},
        {"key": "products", "enabled": False},
    ]
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save(update_fields=["site_config"])
    before = _sections(tenant)

    assert sitetemplates.apply_look(tenant, "nacht") is True
    tenant.refresh_from_db()
    assert _sections(tenant) == before, "apply_look — кожа, а не композиция"


def test_apply_look_still_changes_the_skin():
    """…но саму оптику меняет: шрифт/типографика/тема/акцент/карточки."""
    tenant = TenantFactory(slug="lksk2", name="LkSk2", business_type="retail")
    assert sitetemplates.apply_look(tenant, "nacht") is True
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg.get("theme") == "dark", "тёмное семейство включает тёмную тему"
    assert cfg["design"]["look"] == "nacht"
    assert cfg.get("font"), "семейство задаёт шрифт"


def test_apply_bundle_still_owns_the_composition():
    """У сборки семантика ОБРАТНАЯ — она и есть композиция (не ломаем)."""
    tenant = TenantFactory(slug="lksk3", name="LkSk3", business_type="retail")
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["sections"] = [{"key": "faq", "enabled": True}, {"key": "hero", "enabled": False}]
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save(update_fields=["site_config"])
    key = sitetemplates.BUNDLES[0]["key"]
    assert sitetemplates.apply_bundle(tenant, key) is True
    tenant.refresh_from_db()
    assert _sections(tenant) != [("faq", True), ("hero", False)]
