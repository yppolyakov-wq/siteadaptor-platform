import factory
from factory.django import DjangoModelFactory

from apps.tenants.models import Domain, Tenant

#: Схемы тенантов, созданных фабрикой БЕЗ схемы. django-tenants при `save()` уже
#: существующего тенанта создаёт схему, если её нет и `auto_create_schema` стоит
#: (атрибут класса = True). Код, который перечитывает тенанта из БД и сохраняет,
#: получает свежий объект с True — и тест молча гонял все миграции (~90 с).
#: Корневой conftest пропускает create_schema для этих имён (CI-скорость, 2026-11-09).
SCHEMALESS: set[str] = set()


class TenantFactory(DjangoModelFactory):
    """Factory для Tenant.

    По умолчанию НЕ создаёт PostgreSQL-схему (auto_create_schema=False) — это
    нужно только в специфических интеграционных тестах. Чтобы создать схему,
    передай `auto_create_schema=True` при вызове фабрики.
    """

    class Meta:
        model = Tenant

    schema_name = factory.Sequence(lambda n: f"tenant_test_{n}")
    name = factory.Sequence(lambda n: f"Test Tenant {n}")
    slug = factory.Sequence(lambda n: f"test-tenant-{n}")
    business_type = "bakery"
    city = "Hilden"
    country = "DE"
    default_locale = "de"
    enabled_locales = ["de", "en"]
    enabled_modules = ["catalog", "promotions", "publishing"]
    subscription_status = "trial"

    # auto_create_schema — это атрибут экземпляра django-tenants, а НЕ поле
    # модели, поэтому его нельзя передавать в Tenant(**kwargs). Снимаем его из
    # kwargs и выставляем на объекте до save().
    auto_create_schema = False

    @classmethod
    def _build(cls, model_class, *args, **kwargs):
        auto_create_schema = kwargs.pop("auto_create_schema", False)
        obj = super()._build(model_class, *args, **kwargs)
        obj.auto_create_schema = auto_create_schema
        return obj

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        auto_create_schema = kwargs.pop("auto_create_schema", False)
        obj = model_class(*args, **kwargs)
        obj.auto_create_schema = auto_create_schema
        if not auto_create_schema:
            SCHEMALESS.add(obj.schema_name)
        obj.save()
        return obj


class DomainFactory(DjangoModelFactory):
    class Meta:
        model = Domain

    domain = factory.Sequence(lambda n: f"test-tenant-{n}.siteadaptor.de")
    tenant = factory.SubFactory(TenantFactory)
    is_primary = True
