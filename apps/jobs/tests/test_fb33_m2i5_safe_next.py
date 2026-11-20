"""FB-33 M2i-5 (security-reviewer M3): возврат `next` после старой панели «Anfrage-Formular».

Самодельная проверка `startswith("/") and not startswith("//")` пропускала `/\\evil.com`
(браузер читает «\\» как «/» → `//evil.com`, открытый редирект). Теперь — единая проверка
проекта `owner_login.safe_next` (pitfalls §3); то же у `inbox._safe_next`.
"""

import pytest
from django.test import RequestFactory
from django.urls import reverse

BAD = ("/\\evil.com", "//evil.com", "https://evil.com", "/\t/evil.com", "\\\\evil.com", "")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _post(nxt):
    return RequestFactory().post("/x/", {"next": nxt})


def _offsite(url: str) -> bool:
    return not url.startswith("/") or url.startswith("//") or "\\" in url


@pytest.mark.parametrize("nxt", BAD)
def test_jobs_next_refuses_foreign_hosts(nxt):
    from apps.jobs import views

    assert views._safe_next(_post(nxt)) == reverse("ablaeufe")


def test_jobs_next_encoded_backslash_stays_local():
    """`/%5Cevil.com` браузер не декодирует в хост — это путь своего сайта."""
    from apps.jobs import views

    got = views._safe_next(_post("/%5Cevil.com"))
    assert not _offsite(got)


def test_jobs_next_keeps_local_path():
    from apps.jobs import views

    assert views._safe_next(_post("/dashboard/ablaeufe/?kind=job")) == (
        "/dashboard/ablaeufe/?kind=job"
    )


@pytest.mark.parametrize("nxt", BAD)
def test_inbox_next_refuses_foreign_hosts(nxt):
    from apps.inbox import views

    assert views._safe_next(_post(nxt)) == ""


def test_inbox_next_keeps_local_path():
    from apps.inbox import views

    assert views._safe_next(_post("/dashboard/inbox/?x=1")) == "/dashboard/inbox/?x=1"
