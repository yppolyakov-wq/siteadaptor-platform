from django.apps import AppConfig


class CollectionsConfig(AppConfig):
    """UB3-2: подборки (коллекции) продаваемых сущностей — TENANT-приложение.

    Метка `collections` уникальна в реестре Django-приложений; со stdlib-модулем
    `collections` конфликтов нет (абсолютные импорты `apps.collections`)."""

    name = "apps.collections"
    label = "collections"
