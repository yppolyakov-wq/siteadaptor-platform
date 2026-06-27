"""Автоподключение кастомных доменов: динамическое доверие хостам (middleware из
таблицы Domain) + авто-подтверждение DNS (Celery beat). Цель — домен, добавленный
в кабинете, работает сам, без ручной правки ALLOWED_HOSTS / клика «Verify»."""

import pytest
from django.test import RequestFactory

from apps.tenants import domains, hosts
from apps.tenants.middleware import CustomDomainHostMiddleware
from apps.tenants.models import CustomDomain, Domain
from apps.tenants.tasks import recheck_pending_custom_domains
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_middleware_trusts_host_from_domain_table(settings):
    settings.ALLOWED_HOSTS = ["siteadaptor.de"]
    tenant = TenantFactory(schema_name="public", slug="md", name="MD")
    Domain.objects.get_or_create(domain="meine-baeckerei.de", defaults={"tenant": tenant})
    hosts.clear_known_hosts()

    seen = {}
    mw = CustomDomainHostMiddleware(lambda r: seen.setdefault("ok", True))
    mw(RequestFactory().get("/", HTTP_HOST="meine-baeckerei.de"))

    assert "meine-baeckerei.de" in settings.ALLOWED_HOSTS  # хост дотрастили на лету
    assert seen.get("ok")  # запрос прошёл дальше


def test_middleware_ignores_unknown_host(settings):
    settings.ALLOWED_HOSTS = ["siteadaptor.de"]
    hosts.clear_known_hosts()
    mw = CustomDomainHostMiddleware(lambda r: "ok")
    mw(RequestFactory().get("/", HTTP_HOST="fremde-domain.example"))
    assert "fremde-domain.example" not in settings.ALLOWED_HOSTS  # чужой хост не трастим


def test_middleware_noop_when_wildcard(settings):
    settings.ALLOWED_HOSTS = ["*"]
    hosts.clear_known_hosts()
    mw = CustomDomainHostMiddleware(lambda r: "ok")
    mw(RequestFactory().get("/", HTTP_HOST="irgendwas.example"))
    assert settings.ALLOWED_HOSTS == ["*"]  # при * ничего не добавляем


def test_known_hosts_cache_invalidated_on_domain_save():
    tenant = TenantFactory(schema_name="public", slug="kh", name="KH")
    hosts.clear_known_hosts()
    hosts.known_hosts()  # прогреть кэш
    # post_save-сигнал (apps.py::ready) сбрасывает кэш — новый домен виден сразу.
    Domain.objects.create(domain="frisch.de", tenant=tenant)
    assert "frisch.de" in hosts.known_hosts()


def test_recheck_activates_pending_domain_when_dns_matches(settings, monkeypatch):
    settings.CUSTOM_DOMAIN_TARGET_IP = "10.0.0.9"
    tenant = TenantFactory(schema_name="public", slug="rc", name="RC")
    cd = CustomDomain.objects.create(domain="auto.example", tenant=tenant)
    assert cd.status == CustomDomain.PENDING
    monkeypatch.setattr(domains, "_resolve_ipv4", lambda d, timeout=5.0: ["10.0.0.9"])

    activated = recheck_pending_custom_domains()

    cd.refresh_from_db()
    assert cd.status == CustomDomain.ACTIVE  # авто-подтверждён без ручного «Verify»
    assert activated == 1
    assert Domain.objects.filter(domain="auto.example", tenant=tenant).exists()  # роутинг создан


def test_recheck_keeps_pending_when_dns_mismatch(settings, monkeypatch):
    settings.CUSTOM_DOMAIN_TARGET_IP = "10.0.0.9"
    tenant = TenantFactory(schema_name="public", slug="rc2", name="RC2")
    cd = CustomDomain.objects.create(domain="notyet.example", tenant=tenant)
    monkeypatch.setattr(domains, "_resolve_ipv4", lambda d, timeout=5.0: ["1.1.1.1"])

    assert recheck_pending_custom_domains() == 0
    cd.refresh_from_db()
    assert cd.status == CustomDomain.PENDING  # DNS не указывает на нас — ждём
