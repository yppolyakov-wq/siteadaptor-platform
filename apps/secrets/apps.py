from django.apps import AppConfig


class SecretsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.secrets"

    def ready(self):
        from . import checks  # noqa: F401 — регистрирует deploy-check
