"""Данные `loyalty/0009`: существующие коды становятся combinable, новые — нет."""

import importlib

import pytest
from django.apps import apps as django_apps

from apps.loyalty.models import Voucher

pytestmark = pytest.mark.django_db


def test_existing_vouchers_become_combinable_new_ones_stay_off():
    old = Voucher.objects.create(code="OLD10", label="x", discount_percent=10)
    assert old.combinable is False
    mod = importlib.import_module("apps.loyalty.migrations.0009_existing_vouchers_combinable")
    mod.mark_existing(django_apps, None)
    old.refresh_from_db()
    assert old.combinable is True
    assert Voucher.objects.create(code="NEW10", label="x").combinable is False
