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
        from .models import Domain, Tenant

        post_save.connect(clear_known_hosts, sender=Domain, dispatch_uid="tenants_known_hosts_save")
        post_delete.connect(
            clear_known_hosts, sender=Domain, dispatch_uid="tenants_known_hosts_delete"
        )
        # SE-5a: при публикации (сохранении site_config) сбрасываем кэш витрины тенанта.
        # Срабатывает только когда save() передал site_config в update_fields — т.е. на
        # явных правках конфига витрины (редактор/настройки), не на любом save() тенанта.
        post_save.connect(
            _bump_storefront_cache_on_config_save,
            sender=Tenant,
            dispatch_uid="tenants_storefront_cache_bust",
        )


def _bump_storefront_cache_on_config_save(sender, instance, update_fields, **kwargs):
    """SE-5a: сброс кэша витрины при сохранении site_config (см. ready())."""
    if update_fields and "site_config" in update_fields:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(instance.schema_name)
