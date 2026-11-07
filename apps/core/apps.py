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

        # STU-19c: the setup helper registers its AI task at import (the Celery worker
        # and the AI admin list must know it without importing a view first).
        # T-8.30: любой вход снимает ограничение сессии Telegram Mini App.
        from apps.core import (
            assistant_ai,  # noqa: F401 — AIS A-2 «KI fragen»
            assistant_ai_actions,  # noqa: F401 — AIS A-4e «KI-Aktionen»
            i18n_translate,  # noqa: F401 — AIS-5 «Übersetzen»
            offer_pdf,  # noqa: F401 — AIS-4 «PDF der Speisekarte»
            offer_photo,  # noqa: F401 — AIS W4-4 «Foto der Speisekarte»
            setup_assistant,  # noqa: F401
            text_draft,  # noqa: F401 — AIS-7 «Text vorschlagen»
            tg_login,
        )

        tg_login.connect()

        # KA-12 E10: изменение членства сбрасывает мемо прав/членства на объекте user.
        from django.db.models.signals import post_delete, post_save

        from apps.core.models import Membership
        from apps.core.permissions import bump_generation

        post_save.connect(bump_generation, sender=Membership, dispatch_uid="core_member_gen_s")
        post_delete.connect(bump_generation, sender=Membership, dispatch_uid="core_member_gen_d")
