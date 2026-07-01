"""UA3-1 (решение 2): резолвер основного действия детали услуги (booking|request).

Приоритет: поле Service.primary_action (UA4-3) → tenant.site_config['primary_service_cta']
→ дефолт booking. 'request' валиден только при активном jobs.
"""

from types import SimpleNamespace

from apps.core.archetypes import primary_service_action


class _Tenant:
    def __init__(self, cfg=None, jobs=True):
        self.site_config = cfg or {}
        self._jobs = jobs

    def is_module_active(self, key):
        return key == "jobs" and self._jobs


def _svc(primary_action=None):
    return SimpleNamespace(primary_action=primary_action)


def test_default_is_booking():
    assert primary_service_action(_svc(), _Tenant()) == "booking"


def test_tenant_config_request_when_jobs_active():
    t = _Tenant(cfg={"primary_service_cta": "request"})
    assert primary_service_action(_svc(), t) == "request"


def test_request_falls_back_to_booking_without_jobs():
    t = _Tenant(cfg={"primary_service_cta": "request"}, jobs=False)
    assert primary_service_action(_svc(), t) == "booking"


def test_service_field_overrides_tenant_config():
    t = _Tenant(cfg={"primary_service_cta": "request"})
    assert primary_service_action(_svc("booking"), t) == "booking"  # поле приоритетнее


def test_service_field_request():
    assert primary_service_action(_svc("request"), _Tenant()) == "request"


def test_invalid_config_value_defaults_booking():
    assert primary_service_action(_svc(), _Tenant(cfg={"primary_service_cta": "x"})) == "booking"


def test_non_dict_site_config_is_safe():
    t = _Tenant()
    t.site_config = None
    assert primary_service_action(_svc(), t) == "booking"
