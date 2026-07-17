from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Чистим платформенную админку после admin.autodiscover() (apps.core
        # стоит в INSTALLED_APPS позже django.contrib.admin, поэтому к этому
        # моменту все admin-модули — включая tenant-овые — уже импортированы).
        from apps.core.admin import tidy_platform_admin

        tidy_platform_admin()

        # HIGH-10: штамп схемы в сессию на логине + регистрация security-check'а.
        from apps.core import (
            checks,  # noqa: F401 — регистрирует @register-чек
            session_schema,
        )

        session_schema.connect()
