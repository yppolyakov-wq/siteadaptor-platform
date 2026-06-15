"""Backfill StayBooking.total_cents для существующих броней (A5a).

До A5a итог считался как price_cents × ночи (флэт). Проставляем то же значение,
чтобы старые брони показывали корректный total и finance не сбоил."""

from django.db import migrations


def backfill(apps, schema_editor):
    StayBooking = apps.get_model("stays", "StayBooking")
    for booking in StayBooking.objects.filter(total_cents=0):
        nights = (booking.departure - booking.arrival).days
        total = booking.price_cents * max(nights, 0)
        if total:
            booking.total_cents = total
            booking.save(update_fields=["total_cents"])


class Migration(migrations.Migration):
    dependencies = [
        ("stays", "0002_staybooking_total_cents_stayunit_weekend_price_cents_and_more"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
