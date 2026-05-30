"""Чистка платформенной админки (public-схема).

Сторонние библиотеки (dj-stripe, celery, allauth-социалки, sites…) регистрируют
десятки моделей — для платформенного админа это шум. Снимаем их с регистрации,
оставляя только полезное: Tenants/Domains, Audit, Webhooks, Users/Groups.

Тут только unregister; полезные модели регистрируются в своих admin.py.
"""

from django.contrib import admin

# Приложения, чьи модели целиком убираем из админки.
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


def _cleanup_admin():
    for model in list(admin.site._registry):
        meta = model._meta
        if (
            meta.app_label in _HIDE_APP_LABELS
            or (
                meta.app_label,
                meta.model_name,
            )
            in _HIDE_MODELS
        ):
            try:
                admin.site.unregister(model)
            except admin.sites.NotRegistered:
                pass


_cleanup_admin()

admin.site.site_header = "SiteAdaptor — Platform admin"
admin.site.site_title = "SiteAdaptor admin"
admin.site.index_title = "Platform"
