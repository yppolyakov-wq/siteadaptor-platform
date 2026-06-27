from django.apps import AppConfig


class TenantsConfig(AppConfig):
    name = "apps.tenants"
    label = "tenants"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Автоподключение доменов: сбрасываем кэш известных хостов при изменении
        # Domain, чтобы свежедобавленный/подтверждённый домен трастился сразу.
        from django.db.models.signals import post_delete, post_save

        from .hosts import clear_known_hosts
        from .models import Domain

        post_save.connect(clear_known_hosts, sender=Domain, dispatch_uid="tenants_known_hosts_save")
        post_delete.connect(
            clear_known_hosts, sender=Domain, dispatch_uid="tenants_known_hosts_delete"
        )
