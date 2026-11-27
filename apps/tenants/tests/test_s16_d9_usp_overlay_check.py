"""FB-33 стопка 16 D9: команда только на чтение `usp_overlay_check` — находит испорченные базы,
не выводит тексты бизнеса и ничего не пишет."""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.tenants.management.commands.usp_overlay_check import scan

CLEAN = {
    "usp_bar": [{"label": "Frisch", "text": "Jeden Tag"}],
    "i18n": {"ru": {"usp_bar": [{"label": "Свежо", "text": "Каждый день"}]}},
}
BROKEN = {
    "usp_bar": [{"label": "Свежо", "text": "Каждый день"}],
    "trust": {"marks": ["Bio"]},
    "history": [{"config": {"i18n": {"ru": {"usp_bar": [{"label": "Свежо"}]}}}}],
}


def test_clean_config_has_no_hits():
    assert scan(CLEAN) == {}


def test_broken_base_is_found_by_history_and_letters():
    hits = scan(BROKEN)
    assert hits[("usp_bar.label", "ru (history)")] == 1
    assert hits[("usp_bar.text", "не немецкий")] == 1
    assert ("trust.marks", "не немецкий") not in hits


@pytest.mark.parametrize("cfg", [None, "x", [], {"trust": "x", "history": "x", "i18n": []}])
def test_odd_shapes_do_not_crash(cfg):
    assert scan(cfg) == {}


@pytest.mark.django_db
def test_command_prints_no_business_text_and_writes_nothing():
    from apps.tenants.models import Tenant
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(site_config=dict(BROKEN))
    before = Tenant.objects.get(pk=t.pk).site_config
    out = StringIO()
    call_command("usp_overlay_check", stdout=out)
    text = out.getvalue()
    assert t.schema_name in text and "usp_bar.label — ru (history): 1" in text
    assert "Свежо" not in text and "Каждый день" not in text
    assert Tenant.objects.get(pk=t.pk).site_config == before
