from django.apps import AppConfig


class AIConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    label = "ai"
    verbose_name = "KI"

    def ready(self):
        from . import checks  # noqa: F401 — регистрирует system checks ai.*
