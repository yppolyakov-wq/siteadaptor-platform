"""Чистка платформенной админки (public-схема).

Django admin живёт только на public (config/urls_public). Сторонние библиотеки
(dj-stripe, celery, allauth-социалки, sites…) регистрируют десятки моделей — для
платформенного админа это шум. Плюс TENANT-приложения (catalog/promotions)
регистрируют свои модели, но их таблиц в public-схеме нет — такие разделы
ломаются при открытии. Снимаем и то, и другое с регистрации, оставляя только
полезные SHARED-модели (Tenants/Domains, Aggregator, Support, Secrets, Audit,
Webhooks, Users/Groups). Курируемый сайдбар — UNFOLD["SIDEBAR"] в settings.

Важно про порядок: autodiscover импортирует admin-модули в порядке INSTALLED_APPS,
а apps.core идёт ПОЗЖЕ catalog/promotions невозможно — наоборот, раньше. Поэтому
снятие с регистрации нельзя делать на уровне импорта этого модуля (tenant-админки
ещё не зарегистрированы). Вызываем `tidy_platform_admin()` из CoreConfig.ready(),
который отрабатывает уже ПОСЛЕ admin.autodiscover().
"""

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib import admin

# Сторонний шум — библиотеки, чьи модели платформенному админу не нужны.
_HIDE_APP_LABELS = {
    "djstripe",
    "django_celery_beat",
    "django_celery_results",
    "socialaccount",
    "authtoken",
}
# Точечные модели (app_label, model_name) — оставшийся шум.
_HIDE_MODELS = {
    ("account", "emailaddress"),
    ("sites", "site"),
}


def _tenant_only_labels() -> set[str]:
    """Ярлыки приложений, живущих только в схемах тенантов.

    P0-5 (аудит 2026-09-03 §9.3): раньше здесь был чёрный СПИСОК ярлыков
    (`catalog`, `promotions`), и `loyalty` в него не попал — LoyaltyCard с
    данными клиентов бизнеса стоял в платформенной админке. Таблиц в public у
    таких моделей нет, раздел падал, а не отдавал данные, но это защита по
    случайности. Теперь — правило по `settings.TENANT_ONLY_APPS`: любое новое
    tenant-приложение снимается автоматически. Сопоставляем по `AppConfig.name`
    (путь пакета), а не по label: label у приложения может отличаться от имени.
    """
    names = set(getattr(settings, "TENANT_ONLY_APPS", ()))
    return {cfg.label for cfg in django_apps.get_app_configs() if cfg.name in names}


def tidy_platform_admin():
    """Снять с регистрации шумные/несовместимые модели. Идемпотентно."""
    hidden_labels = _HIDE_APP_LABELS | _tenant_only_labels()
    for model in list(admin.site._registry):
        meta = model._meta
        if meta.app_label in hidden_labels or (meta.app_label, meta.model_name) in _HIDE_MODELS:
            try:
                admin.site.unregister(model)
            except admin.sites.NotRegistered:
                pass

    admin.site.site_header = "SiteAdaptor — Platform admin"
    admin.site.site_title = "SiteAdaptor admin"
    admin.site.index_title = "Platform"
