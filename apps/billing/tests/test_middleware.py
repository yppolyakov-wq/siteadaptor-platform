from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.test import RequestFactory

from apps.billing.middleware import SubscriptionGatingMiddleware
from apps.billing.state_machine import ACTIVE, SUSPENDED, TRIAL_EXPIRED


class _Tenant:
    def __init__(self, status, schema="acme"):
        self.subscription_status = status
        self.schema_name = schema


def _mw():
    return SubscriptionGatingMiddleware(lambda req: HttpResponse("ok"))


def _request(method, path, tenant):
    request = getattr(RequestFactory(), method.lower())(path)
    request.tenant = tenant
    request._messages = FallbackStorage(request)
    return request


def test_gated_post_on_cabinet_is_blocked():
    resp = _mw()(_request("post", "/promotions/create/", _Tenant(SUSPENDED)))
    assert resp.status_code == 302  # redirect (read-only)


def test_gated_get_is_allowed():
    resp = _mw()(_request("get", "/promotions/", _Tenant(TRIAL_EXPIRED)))
    assert resp.status_code == 200


def test_gated_post_on_billing_path_is_allowed():
    resp = _mw()(_request("post", "/dashboard/billing/checkout/", _Tenant(SUSPENDED)))
    assert resp.status_code == 200


def test_active_post_is_allowed():
    resp = _mw()(_request("post", "/promotions/create/", _Tenant(ACTIVE)))
    assert resp.status_code == 200


def test_public_schema_is_not_gated():
    resp = _mw()(_request("post", "/p/123/reserve/", _Tenant(SUSPENDED, schema="public")))
    assert resp.status_code == 200


def test_request_flags_are_set():
    request = _request("get", "/dashboard/", _Tenant(SUSPENDED))
    _mw()(request)
    assert request.subscription_gated is True
    assert request.subscription_status == SUSPENDED
