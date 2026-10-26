"""KA-12 A-6 (Werkstatt): машина клиента как сущность.

Заявка хранит снимок полей авто (Kennzeichen/HSN/TSN/марка) — их читают смета, PDF и
письма. `Vehicle` — карточка машины у клиента: VIN, первая регистрация, пробег, срок HU,
история заявок. Связь `Job.vehicle_ref` ставит `ensure_vehicle` после создания и правки
заявки; одна машина клиента на номер (сравнение по нормализованному номеру).
"""

import re

from django.db import transaction

#: ISO 3779: 17 знаков, латиница и цифры без I, O, Q (их путают с 1 и 0).
_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


_DASHES = str.maketrans({"\u2013": "-", "\u2014": "-", "\u2212": "-"})


def normalize_plate(value) -> str:
    """«m–ab  12 » → «M-AB 12»: верхний регистр, тире → дефис, одиночные пробелы,
    без пробелов вокруг дефиса. Разделители НЕ выбрасываем: «M-AB 12» и «MA-B 12» —
    разные номера.

    Копия этой функции живёт в миграции `jobs/0024` (миграции не импортируют код
    приложения) — меняя правило, поменяйте и там; совпадение держит замок."""
    text = " ".join((value or "").upper().translate(_DASHES).split())
    text = re.sub(r"\s*-\s*", "-", text).strip("- ")
    return text[:15]


def normalize_vin(value) -> str | None:
    """Пусто → "", корректный VIN → в верхнем регистре, иначе None (ошибка ввода)."""
    vin = "".join((value or "").upper().split())
    if not vin:
        return ""
    return vin if _VIN_RE.match(vin) else None


def ensure_vehicle(job):
    """Связать заявку с машиной её клиента по номеру; номер пуст — связь снять.

    Пустые поля машины дополняются данными заявки (HSN/TSN/марка), заполненные не
    перетираются: карточку машины владелец правит сам. → машина или None."""
    from .models import Job, Vehicle

    plate = normalize_plate(job.vehicle_plate)
    if not plate:
        if job.vehicle_ref_id:
            job.vehicle_ref = None
            job.save(update_fields=["vehicle_ref", "updated_at"])
        return None
    with transaction.atomic():
        old = job.vehicle_ref if job.vehicle_ref_id else None
        if (
            old is not None
            and old.plate != plate
            and not old.jobs.exclude(pk=job.pk).exists()
            and not Vehicle.objects.filter(customer_id=job.customer_id, plate=plate).exists()
        ):
            # Ревью A-6a: исправление опечатки в номере — та же машина (VIN, HU, заметки
            # остаются), а не сирота + вторая карточка с двойным HU-напоминанием.
            old.plate = plate
            old.save(update_fields=["plate", "updated_at"])
        vehicle, _created = Vehicle.objects.get_or_create(customer_id=job.customer_id, plate=plate)
        changed = []
        for src, dst in (
            ("vehicle_hsn", "hsn"),
            ("vehicle_tsn", "tsn"),
            ("vehicle", "make_model"),
        ):
            value = (getattr(job, src) or "").strip()
            if value and not getattr(vehicle, dst):
                setattr(vehicle, dst, value[: Vehicle._meta.get_field(dst).max_length])
                changed.append(dst)
        if changed:
            vehicle.save(update_fields=[*changed, "updated_at"])
        if job.vehicle_ref_id != vehicle.pk:
            Job.objects.filter(pk=job.pk).update(vehicle_ref=vehicle)
            job.vehicle_ref = vehicle
    return vehicle


def record_mileage(job, km) -> bool:
    """Пробег из акта приёмки → заявка и машина. Одометр не убывает: меньшее значение
    машине не записывается (→ False, вызывающая сторона предупреждает)."""
    from .models import Job, Vehicle

    if km is None:
        return True
    Job.objects.filter(pk=job.pk).update(mileage_km=km)
    job.mileage_km = km
    vehicle = job.vehicle_ref if job.vehicle_ref_id else ensure_vehicle(job)
    if vehicle is None:
        return True
    with transaction.atomic():
        current = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
        if current.mileage_km is not None and km < current.mileage_km:
            return False
        if current.mileage_km != km:
            current.mileage_km = km
            current.save(update_fields=["mileage_km", "updated_at"])
    return True
