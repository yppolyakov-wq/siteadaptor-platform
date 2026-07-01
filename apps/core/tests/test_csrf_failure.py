"""Диагностическая 403-страница CSRF (apps.core.csrf.csrf_failure)."""

from django.test import RequestFactory

from apps.core import csrf


def test_csrf_failure_returns_403_with_reason():
    req = RequestFactory().post("/accounts/login/", HTTP_ORIGIN="https://pranasy.siteadaptor.de")
    resp = csrf.csrf_failure(req, reason="Origin checking failed - test")
    assert resp.status_code == 403
    body = resp.content.decode()
    assert "Origin checking failed - test" in body
    assert "pranasy.siteadaptor.de" in body  # Origin-сигнал в диагностике


def test_csrf_failure_reports_cookie_presence():
    rf = RequestFactory()
    # без куки csrftoken
    resp_no = csrf.csrf_failure(rf.post("/x/"), reason="CSRF cookie not set.")
    assert "csrf_cookie_received" in resp_no.content.decode()
    assert "False" in resp_no.content.decode()
    # с кукой
    req = rf.post("/x/")
    req.COOKIES["csrftoken"] = "abc"
    body = csrf.csrf_failure(req, reason="x").content.decode()
    assert "True" in body


def test_csrf_failure_escapes_reason():
    req = RequestFactory().post("/x/")
    body = csrf.csrf_failure(req, reason="<script>alert(1)</script>").content.decode()
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
