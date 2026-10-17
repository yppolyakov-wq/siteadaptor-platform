from django.apps import AppConfig


class ImportsConfig(AppConfig):
    name = "apps.imports"
    label = "imports"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # T-8.27e: задача ИИ регистрируется при старте приложения — её видят и веб,
        # и Celery-воркер (контракт AI-0: регистрация в ready(), не при импорте вьюхи).
        from .site import ai_extract  # noqa: F401
