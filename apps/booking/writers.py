"""AIS A-4a: писатель «создать услугу» — тот же путь, что экран «＋ Leistung»."""

from __future__ import annotations

from apps.catalog.writers import WriteError


def create_service(tenant, fields: dict):
    from . import views

    data = {k: ("" if v is None else str(v)) for k, v in (fields or {}).items()}
    errors = views._service_new_errors(data)
    service = None if errors else views.service_from_data(data, tenant)
    if service is None:
        raise WriteError(errors or {"name": "required"})
    service.save()
    return service
