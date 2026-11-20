"""FB-33 M2b-2b C6: демо — свои вопросы FAQ у товара пекарни и номера отеля, блок «FAQ» со
своими вопросами на страницах товаров/номеров; объекты без вопросов блока не показывают."""

import pytest

from apps.core import object_faq
from apps.tenants import demo_fingerprint, demo_kits, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("kit", "host", "kind"),
    [("bakery", "product_detail", "product"), ("hotel", "stay_detail", "stay")],
)
def test_kit_seeds_own_questions_and_the_block(kit, host, kind):
    tenant = TenantFactory(schema_name="public", slug=f"d-{kit}", name="D", business_type=kit)
    assert demo_kits.apply_kit(tenant, kit) is True
    cfg = siteconfig.normalize(tenant.site_config)
    blocks = cfg["page_blocks"][host]
    assert [(b["key"], b["data"]) for b in blocks] == [("faq_ref", {"source": "object"})]
    with_faq = [o for o in object_faq.model(kind).objects.all() if object_faq.items(o, kind)]
    assert len(with_faq) == 1 and len(object_faq.items(with_faq[0], kind)) >= 2


def test_seeder_version_bumped():
    assert demo_fingerprint.SEEDER_VERSION >= 24
