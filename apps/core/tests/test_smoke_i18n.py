"""Дымовой прогон: ключевые метки кабинета реально переводятся на ru/tr."""

import pytest
from django.utils import translation

pytestmark = pytest.mark.django_db


def test_status_and_registry_labels_translate():
    from apps.orders.models import Order
    from apps.tenants.models import Tenant
    from apps.tenants import siteconfig

    with translation.override("ru"):
        assert str(dict(Order.STATUSES)[Order.STATUS_NEW]) == "Новый" or str(
            dict(Order.STATUSES)[Order.STATUS_NEW]
        ) not in ("New",)
        assert str(dict(Tenant.BUSINESS_TYPES)["bakery"]) == "Пекарня"
        assert str(siteconfig.SECTION_STYLE_LABELS["cards"]) == "Карточки"

    with translation.override("tr"):
        assert str(dict(Tenant.BUSINESS_TYPES)["bakery"]) == "Fırın"
        assert str(siteconfig.SECTION_STYLE_LABELS["cards"]) == "Kartlar"


def test_finder_and_form_labels_translate():
    from apps.core import finder
    from apps.events.forms import EventForm
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(business_type="bakery", disabled_modules=[])
    with translation.override("ru"):
        assert finder.tree_for(tenant)[0]["label"] == "Что ищете? 🥨"
        assert str(EventForm().fields["price_eur"].label) == "Цена за место (€)"
