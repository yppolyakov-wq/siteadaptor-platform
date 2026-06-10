"""Track B2: форма акции сохраняет флаг Überraschungstüte."""

import pytest

from apps.promotions.forms import PromotionForm
from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db


def test_form_saves_surprise_flag():
    form = PromotionForm(
        data={
            "title_de": "Überraschungstüte",
            "promo_type": Promotion.RESERVATION,
            "max_per_customer": 1,
            "reservation_ttl_hours": 24,
            "strikethrough_old_price": "on",
            "is_surprise": "on",
        }
    )
    assert form.is_valid(), form.errors
    promo = form.save()
    assert promo.is_surprise is True
