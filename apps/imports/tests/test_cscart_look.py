"""M21.5: вид перенесённого магазина — фото целиком, крупный логотип, подвал колонками;
правки владельца при повторном импорте не перетираются."""

import pytest

from apps.imports import cscart
from apps.imports.tests.test_cscart import _site_with_home


@pytest.mark.django_db
def test_design_sets_whole_photos_logo_and_footer_columns_only_once():
    from apps.tenants import siteconfig
    from apps.tenants.tests.factories import TenantFactory

    site = _site_with_home()
    tenant = TenantFactory(schema_name="public")
    tenant.site_config = {}
    cscart.apply_design(tenant, site, with_images=False)
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    sd = cfg["site_defaults"]
    assert sd["media_places"]["product"] == {"ratio": "1-1", "fit": "contain"}
    assert sd["media_places"]["detail"] == {"ratio": "1-1", "fit": "contain"}
    assert sd["logo_size"] == "l"
    labels = [c["label"] for c in cfg["menus"]["footer"]["columns"]]
    assert labels == ["Mein Konto", "Kundendienst", "Über uns"]

    raw = dict(tenant.site_config)
    raw["site_defaults"] = {**raw["site_defaults"], "logo_size": "xl"}
    tenant.site_config = raw
    tenant.save(update_fields=["site_config"])
    cscart.apply_design(tenant, site, with_images=False)
    tenant.refresh_from_db()
    assert siteconfig.normalize(tenant.site_config)["site_defaults"]["logo_size"] == "xl"


def test_detail_place_changes_only_ratio_not_width():
    from apps.core import media_places

    css = media_places.css({"detail": {"ratio": "round", "fit": "contain"}})
    assert '[data-sf-place="detail"]' in css and "aspect-ratio:1 / 1" in css
    assert "width:62%" not in css and "width:auto" not in css  # лента 88 % на телефоне цела
    assert "object-fit:contain" in css
