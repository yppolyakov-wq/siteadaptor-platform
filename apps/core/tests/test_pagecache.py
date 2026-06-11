"""P2.2b: кэш публичной выдачи (apps.core.pagecache).

Хост в каждом тесте уникален (uuid) — ключи в общем Redis не пересекаются ни
между тестами, ни между прогонами (TTL переживает тест).
"""

import uuid

from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.core.pagecache import cache_public_page


def _view_with_counter():
    calls = []

    @cache_public_page
    def view(request):
        calls.append(1)
        return HttpResponse(f"render #{len(calls)}")

    return view, calls


def _get(path="/x/", **extra):
    return RequestFactory().get(path, HTTP_HOST=f"{uuid.uuid4().hex}.test", **extra)


@override_settings(PUBLIC_PAGE_CACHE_TTL=60)
def test_second_hit_served_from_cache():
    view, calls = _view_with_counter()
    req = _get()
    assert view(req).content == b"render #1"
    assert view(req).content == b"render #1"  # тот же HTML, не «render #2»
    assert len(calls) == 1


@override_settings(PUBLIC_PAGE_CACHE_TTL=60)
def test_query_params_bypass_cache():
    view, calls = _view_with_counter()
    host = f"{uuid.uuid4().hex}.test"
    req = RequestFactory().get("/x/", {"cursor": "abc"}, HTTP_HOST=host)
    view(req)
    view(req)
    assert len(calls) == 2  # каждый раз рендер


@override_settings(PUBLIC_PAGE_CACHE_TTL=60)
def test_hosts_are_isolated():
    view, calls = _view_with_counter()
    view(_get())
    view(_get())  # другой хост → другой ключ
    assert len(calls) == 2


@override_settings(PUBLIC_PAGE_CACHE_TTL=60)
def test_language_in_cache_key():
    view, calls = _view_with_counter()
    host = f"{uuid.uuid4().hex}.test"
    req_de = RequestFactory().get("/x/", HTTP_HOST=host)
    req_de.LANGUAGE_CODE = "de"
    req_en = RequestFactory().get("/x/", HTTP_HOST=host)
    req_en.LANGUAGE_CODE = "en"
    view(req_de)
    view(req_en)
    assert len(calls) == 2


@override_settings(PUBLIC_PAGE_CACHE_TTL=0)
def test_ttl_zero_disables_cache():
    view, calls = _view_with_counter()
    req = _get()
    view(req)
    view(req)
    assert len(calls) == 2


@override_settings(PUBLIC_PAGE_CACHE_TTL=60)
def test_non_200_not_cached():
    calls = []

    @cache_public_page
    def view(request):
        calls.append(1)
        return HttpResponse(status=404)

    req = _get()
    view(req)
    view(req)
    assert len(calls) == 2


@override_settings(PUBLIC_PAGE_CACHE_TTL=60)
def test_session_bypasses_cache():
    """Вошедший клиент портала (P2.3) видит персональную страницу, не кэш."""
    from django.contrib.sessions.middleware import SessionMiddleware

    view, calls = _view_with_counter()
    host = f"{uuid.uuid4().hex}.test"
    for _ in range(2):
        req = RequestFactory().get("/x/", HTTP_HOST=host)
        SessionMiddleware(lambda r: None).process_request(req)
        req.session["portal_user_id"] = 1
        view(req)
    assert len(calls) == 2  # оба раза рендер, кэш не использован
