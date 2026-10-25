"""KA-12 E6.4: демо салона показывает неявки и рецептуру мастера «как в жизни»."""

import pytest

from apps.tenants import demo_kits
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_friseur_kit_seeds_no_shows_and_treatment_notes():
    from apps.booking import no_shows
    from apps.booking.models import Booking
    from apps.crm.models import CustomerNote
    from apps.promotions.models import Customer

    tenant = TenantFactory(schema_name="public", slug="fr", name="F", business_type="friseur")
    assert demo_kits.apply_kit(tenant, "friseur") is True
    tobias = Customer.objects.get(email="tobias.wendt@example.com")
    assert no_shows.summary(tobias)["n"] == 2
    upcoming = Booking.objects.filter(customer=tobias, status__in=("pending", "confirmed"))
    assert upcoming.exists(), "будущий визит, на котором виден бейдж"
    claudia = Customer.objects.get(email="claudia.brandt@example.com")
    notes = CustomerNote.objects.filter(customer=claudia, kind=CustomerNote.KIND_SERVICE)
    assert notes.count() == 2 and all(n.booking_id and n.service_id for n in notes)
