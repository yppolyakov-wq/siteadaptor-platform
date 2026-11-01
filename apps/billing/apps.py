from django.apps import AppConfig


class BillingConfig(AppConfig):
    name = "apps.billing"
    label = "billing"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import checks  # noqa: F401 — регистрирует deploy-check SEC-D2
