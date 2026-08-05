"""W7a (аудит кабинета 2026-08-05): замки на save-пути настроек.

1. normalize() пропускает операционные ключи site_config, которые пишут ДРУГИЕ
   экраны кабинета (notify/склад/read-hook'и) — сохранение билдера/SEO их не теряет.
2. «Benachrichtigungen» мержит матрицу клиента — выбор временно выключенных
   модулей переживает Save.
3. settings_view пишет только свои поля (update_fields) — параллельная запись
   site_config не затирается снимком формы.
4. Мастер (_post_company) не обнуляет контакты, которых нет в POST.
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import setup_steps, views
from apps.tenants.models import Tenant
from apps.tenants.siteconfig import normalize
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _req(path, method="get", data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant or TenantFactory(business_type="restaurant")
    return req


# --- 1. normalize passthrough -------------------------------------------------
def test_normalize_preserves_operational_keys():
    cfg = normalize(
        {
            "notify": {"customer": {"order:ready": {"email": False}}, "owner_chat_id": "9"},
            "low_stock_threshold": 3,
            "lots_enabled": True,
            "wishlist": False,
            "primary_service_cta": "request",
        }
    )
    assert cfg["notify"]["owner_chat_id"] == "9"
    assert cfg["notify"]["customer"]["order:ready"] == {"email": False}
    assert cfg["low_stock_threshold"] == 3
    assert cfg["lots_enabled"] is True
    assert cfg["wishlist"] is False
    assert cfg["primary_service_cta"] == "request"


def test_normalize_does_not_materialize_absent_operational_keys():
    cfg = normalize({})
    for key in ("notify", "low_stock_threshold", "lots_enabled", "wishlist", "primary_service_cta"):
        assert key not in cfg


def test_normalize_drops_wrong_typed_operational_keys():
    cfg = normalize(
        {
            "notify": ["not-a-dict"],
            "low_stock_threshold": True,  # bool — не порог
            "lots_enabled": "yes",
            "primary_service_cta": "hack",
        }
    )
    for key in ("notify", "low_stock_threshold", "lots_enabled", "primary_service_cta"):
        assert key not in cfg


def test_seo_save_path_preserves_notify_and_stock_keys():
    # Реальный normalize-писатель (site-seo): раньше Save стирал notify/склад.
    tenant = TenantFactory(business_type="restaurant")
    tenant.site_config = {
        "notify": {"owner_chat_id": "42"},
        "low_stock_threshold": 7,
        "lots_enabled": True,
    }
    tenant.save(update_fields=["site_config"])
    resp = views.seo_settings_view(_req("/dashboard/site/seo/", "post", {}, tenant=tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["notify"] == {"owner_chat_id": "42"}
    assert tenant.site_config["low_stock_threshold"] == 7
    assert tenant.site_config["lots_enabled"] is True


# --- 2. Benachrichtigungen: мерж вместо замены --------------------------------
def test_notifications_save_keeps_prefs_of_disabled_modules():
    tenant = TenantFactory(business_type="restaurant", disabled_modules=["events"])
    tenant.site_config = {
        "notify": {"customer": {"ticket:confirmed": {"email": False, "telegram": False}}}
    }
    tenant.save(update_fields=["site_config"])
    views.notifications_settings(
        _req(
            "/dashboard/settings/notifications/",
            "post",
            {"c-order-ready-email": "on"},
            tenant=tenant,
        )
    )
    tenant.refresh_from_db()
    customer = tenant.site_config["notify"]["customer"]
    # Выбор по выключенному модулю events (домен ticket) пережил Save.
    assert customer["ticket:confirmed"] == {"email": False, "telegram": False}
    assert customer["order:ready"] == {"email": True, "telegram": False}


# --- 3. settings_view: targeted-write -----------------------------------------
def test_settings_save_does_not_clobber_parallel_site_config_write():
    tenant = TenantFactory(business_type="restaurant")
    req = _req("/dashboard/settings/", "post", {"name": "Neu GmbH"}, tenant=tenant)
    # Параллельный писатель (Telegram-вебхук/черновик билдера) успел после
    # загрузки формы: инстанс request.tenant этой записи не видит.
    Tenant.objects.filter(pk=tenant.pk).update(site_config={"notify": {"owner_chat_id": "7"}})
    resp = views.settings_view(req)
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.name == "Neu GmbH"
    assert tenant.site_config == {"notify": {"owner_chat_id": "7"}}


# --- 4. мастер: presence-guard контактов --------------------------------------
def test_setup_company_missing_fields_do_not_wipe():
    tenant = TenantFactory(business_type="restaurant")
    tenant.address = "Altstr. 1"
    tenant.contact_phone = "+49 1"
    tenant.save(update_fields=["address", "contact_phone"])
    req = _req("/dashboard/setup/", "post", {"name": "X", "city": "Hilden"}, tenant=tenant)
    setup_steps._post_company(req)
    tenant.refresh_from_db()
    assert tenant.address == "Altstr. 1"  # поля не было в POST — цело
    assert tenant.contact_phone == "+49 1"
    assert tenant.city == "Hilden"


def test_setup_company_present_empty_field_clears():
    tenant = TenantFactory(business_type="restaurant")
    tenant.address = "Altstr. 1"
    tenant.save(update_fields=["address"])
    req = _req("/dashboard/setup/", "post", {"name": "X", "address": ""}, tenant=tenant)
    setup_steps._post_company(req)
    tenant.refresh_from_db()
    assert tenant.address == ""  # явное пустое значение — осознанная очистка
