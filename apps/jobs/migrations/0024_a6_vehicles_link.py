"""KA-12 A-6: старые заявки с номером → карточка машины клиента.

Отдельно от схемы (0023): данные не держат блокировку DDL. Идемпотентно — повторный
прогон и прогон по уже связанным заявкам ничего не дублирует. Нормализация номера —
КОПИЯ `apps.jobs.vehicles.normalize_plate` (миграции не импортируют код приложения;
совпадение держит замок test_a6_vehicles)."""

import re

from django.db import migrations

_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-"})


def normalize_plate(value) -> str:
    text = " ".join((value or "").upper().translate(_DASHES).split())
    text = re.sub(r"\s*-\s*", "-", text).strip("- ")
    return text[:15]


def link_vehicles(apps, schema_editor):
    Job = apps.get_model("jobs", "Job")
    Vehicle = apps.get_model("jobs", "Vehicle")
    cache = {}
    pending = (
        Job.objects.filter(vehicle_ref__isnull=True)
        .exclude(vehicle_plate="")
        .order_by("pk")
        .only("pk", "customer_id", "vehicle_plate", "vehicle", "vehicle_hsn", "vehicle_tsn")
    )
    for job in pending.iterator(chunk_size=500):
        plate = normalize_plate(job.vehicle_plate)
        if not plate or not job.customer_id:
            continue  # мусор вроде «-» машиной не становится
        key = (job.customer_id, plate)
        vehicle = cache.get(key)
        if vehicle is None:
            vehicle, _created = Vehicle.objects.get_or_create(
                customer_id=job.customer_id,
                plate=plate,
                defaults={
                    "hsn": (job.vehicle_hsn or "")[:4],
                    "tsn": (job.vehicle_tsn or "")[:3],
                    "make_model": (job.vehicle or "")[:120],
                },
            )
            cache[key] = vehicle
        Job.objects.filter(pk=job.pk).update(vehicle_ref=vehicle)


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0023_a6_vehicles"),
    ]

    operations = [
        migrations.RunPython(link_vehicles, migrations.RunPython.noop),
    ]
