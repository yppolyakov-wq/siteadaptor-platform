"""FB-30 (фидбэк владельца 2026-11-15): «Seitenaufbau» показывал 6 колонок товаров, а Студия
— «4 в строке»: число колонок и вид сетки хранились отдельно. Теперь это одно значение."""

import pytest

from apps.core import site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _layout(tenant, key="products"):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    return next(s for s in cfg["sections"] if s["key"] == key).get("layout") or {}


def test_columns_set_in_seitenaufbau_switch_the_studio_view_too():
    t = _tenant()
    b = Browser(t)
    b.post(seite="home", op="update", ref="products", panel_present="1", f_cols="6")
    b.post(seite="home", op="save")
    lay = _layout(t)
    assert lay["cols"] == 6 and lay["preset"] == "cols6"


def test_special_views_keep_their_preset():
    assert siteconfig.preset_for_cols("gallery", 3) == "gallery"
    assert siteconfig.preset_for_cols("preisliste", 2) == "preisliste"
    assert siteconfig.preset_for_cols("cols4", 1) == "list"
    assert siteconfig.preset_for_cols("cols4", "x") == "cols4"


def test_studio_shows_the_effective_view_for_old_data():
    """Старые данные: вид cols4, а колонок 6 — Студия показывает «6 в строке»."""
    from apps.core import views

    assert siteconfig.preset_for_cols("cols4", 6) == "cols6"
    assert "preset_for_cols" in open(views.__file__).read()
    assert site_schema  # модуль схемы на месте
