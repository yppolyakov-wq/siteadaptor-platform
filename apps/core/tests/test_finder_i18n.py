"""I18N-6: пресетное дерево Finder переводится на язык посетителя, кастомное
дерево владельца — нет (это его собственный текст)."""

import pytest
from django.utils import translation

from apps.core import finder
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_preset_tree_is_localized_for_visitor():
    tenant = TenantFactory.build(business_type="bakery", disabled_modules=[])
    with translation.override("en"):
        tree = finder.tree_for(tenant)
    assert tree[0]["label"] == "What are you looking for? 🥨"
    labels = [o["label"] for o in tree[0]["chips"]]
    assert "🥖 Bread & rolls" in labels
    # значения фасета не трогаем — переводится только видимое
    words = [o.get("match", {}).get("words") for o in tree[0]["chips"]]
    assert ["brot", "brötchen", "brezel"] in words


def test_custom_tree_is_not_translated():
    """Владелец написал свои вопросы — gettext их не подменяет."""
    tenant = TenantFactory.build(
        business_type="bakery",
        disabled_modules=[],
        site_config={
            "finder": {
                "enabled": True,
                "questions": [
                    {
                        "key": "q1",
                        "label": "Was suchst du? 🥨",
                        "chips": [{"key": "a", "label": "🥖 Brot & Brötchen", "match": {}}],
                    }
                ],
            }
        },
    )
    with translation.override("en"):
        tree = finder.tree_for(tenant)
    assert tree[0]["label"] == "Was suchst du? 🥨"


def test_preset_tree_raw_for_cabinet_editor():
    """`preset_tree` (кнопка «Branchen-Vorlage laden») отдаёт СЫРОЙ немецкий —
    он попадает в site_config как контент владельца, lazy там недопустим."""
    tenant = TenantFactory.build(business_type="bakery", disabled_modules=[])
    with translation.override("en"):
        raw = finder.preset_tree(tenant)
    assert raw[0]["label"] == "Was suchst du? 🥨"
    assert all(isinstance(o["label"], str) for o in raw[0]["chips"])
