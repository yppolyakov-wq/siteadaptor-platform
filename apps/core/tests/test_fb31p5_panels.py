"""FB-31 P5 R5 (события): разделы детали — строки «Seitenaufbau»: двигаются и скрываются,
свои блоки встают между ними; «Buchung» закреплена; порядок/видимость — на прежнем месте."""

import pytest

from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
B1 = {"key": "text", "id": "b1", "data": {"title": "Zwischen", "body": "x"}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**cfg):
    return TenantFactory(
        business_type="events",
        disabled_modules=list(default_disabled_for("events")),
        site_config=cfg,
    )


def _cfg(tenant):
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


def test_sections_are_rows_and_booking_is_pinned_after_them():
    cfg = siteconfig.normalize({"page_blocks": {"event_detail": [B1]}})
    rows = site_schema.blocks_for(cfg, "event")
    keys = [r["key"] for r in rows]
    assert keys[0] == "for_whom" and "kauf" in keys
    assert keys.index("kauf") == keys.index("certifications") + 1, "Buchung — после разделов"
    assert keys[-1] == "text", "свой блок — хвост, как раньше"
    assert next(r for r in rows if r["key"] == "idea")["label"]


def test_owner_moves_and_hides_sections_and_puts_a_block_between():
    tenant = _tenant(page_blocks={"event_detail": [B1]})
    b = Browser(tenant)
    b.post(seite="event", op="up", ref="idea")  # idea над for_whom
    b.post(seite="event", op="toggle", ref="bring")
    b.post(seite="event", op="move", ref="b1", value="after:idea")
    b.post(seite="event", op="save")
    cfg = _cfg(tenant)
    assert cfg["event_detail"]["order"][:2] == ["idea", "for_whom"]
    assert cfg["event_detail"]["hidden"] == ["bring"]
    rows = cfg["page_blocks"]["event_detail"]
    keys = [r.get("id") or r["key"] for r in rows]
    assert keys.index("b1") == keys.index("idea") + 1
    assert all("enabled" not in r for r in rows if not r.get("id")), "якорь — только позиция"


def test_section_rows_cannot_be_deleted_or_resized():
    tenant = _tenant()
    b = Browser(tenant)
    for op in ("delete", "width", "duplicate"):
        b.post(seite="event", op=op, ref="idea", value="half")
    b.post(seite="event", op="save")
    cfg = _cfg(tenant)
    assert "idea" not in cfg["event_detail"].get("hidden", [])
    assert not (cfg.get("page_blocks") or {}).get("event_detail")
