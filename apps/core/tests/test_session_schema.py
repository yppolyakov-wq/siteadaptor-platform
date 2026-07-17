"""HIGH-10: привязка сессии к схеме логина (signal + middleware + check)."""

from importlib import import_module

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.checks import session_cookie_domain_not_set
from apps.core.middleware import SessionSchemaGuardMiddleware
from apps.core.session_schema import SESSION_SCHEMA_KEY, stamp_session_schema

pytestmark = pytest.mark.django_db

_UNSET = object()


def _user(name="u1"):
    return get_user_model().objects.create_user(
        username=name, email=f"{name}@t.de", password="pw12345678"
    )


def _session():
    return import_module(settings.SESSION_ENGINE).SessionStore()


def _call(user, stamped=_UNSET):
    req = RequestFactory().get("/dashboard/")
    req.session = _session()
    if stamped is not _UNSET:
        req.session[SESSION_SCHEMA_KEY] = stamped
    req.user = user
    SessionSchemaGuardMiddleware(lambda r: HttpResponse("ok"))(req)
    return req


def test_signal_stamps_current_schema():
    req = RequestFactory().get("/")
    req.session = _session()
    stamp_session_schema(None, request=req, user=_user())
    assert req.session[SESSION_SCHEMA_KEY] == connection.schema_name


def test_mismatched_schema_logs_out():
    req = _call(_user("owner"), stamped="some_other_schema")
    assert req.user.is_authenticated is False  # сессия из чужой схемы сброшена


def test_matching_schema_passes():
    req = _call(_user("owner2"), stamped=connection.schema_name)
    assert req.user.is_authenticated is True


def test_absent_stamp_is_legacy_grace():
    req = _call(_user("owner3"))  # без штампа — легаси-сессия не сбрасывается
    assert req.user.is_authenticated is True


def test_anonymous_untouched():
    req = _call(AnonymousUser(), stamped="whatever")
    assert req.user.is_authenticated is False


def test_check_flags_session_cookie_domain(settings):
    settings.SESSION_COOKIE_DOMAIN = None
    assert session_cookie_domain_not_set(None) == []
    settings.SESSION_COOKIE_DOMAIN = ".siteadaptor.de"
    errs = session_cookie_domain_not_set(None)
    assert len(errs) == 1 and errs[0].id == "core.E001"
