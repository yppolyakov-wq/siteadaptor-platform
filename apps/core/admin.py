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

from django.contrib import admin

# Приложения, чьи модели целиком убираем из админки.
_HIDE_APP_LABELS = {
    "djstripe",
    "django_celery_beat",
    "django_celery_results",
    "socialaccount",
    "authtoken",
    # TENANT-приложения: таблиц нет в public-схеме → разделы ломаются.
    "catalog",
    "promotions",
}
# Точечные модели (app_label, model_name) — оставшийся шум.
_HIDE_MODELS = {
    ("account", "emailaddress"),
    ("sites", "site"),
}


def tidy_platform_admin():
    """Снять с регистрации шумные/несовместимые модели. Идемпотентно."""
    for model in list(admin.site._registry):
        meta = model._meta
        if meta.app_label in _HIDE_APP_LABELS or (meta.app_label, meta.model_name) in _HIDE_MODELS:
            try:
                admin.site.unregister(model)
            except admin.sites.NotRegistered:
                pass

    admin.site.site_header = "SiteAdaptor — Platform admin"
    admin.site.site_title = "SiteAdaptor admin"
    admin.site.index_title = "Platform"
