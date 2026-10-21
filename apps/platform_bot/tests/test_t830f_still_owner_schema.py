"""T-8.30f-0: still_owner читает Membership в схеме бизнеса, а не там, где его позвали.

В проде apps.core — только TENANT_APPS: в public таблицы core_membership нет, и вызов из
вебхука общего бота (/profil, «🔑» входа) падал ProgrammingError. В тестах все приложения
SHARED, поэтому ловим схему, в которой выполнился запрос.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from apps.core.models import Membership
from apps.platform_bot import links
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_still_owner_queries_tenant_schema(monkeypatch):
    t = TenantFactory(schema_name="so_schema", slug="so-schema", name="X")
    user = get_user_model().objects.create_user(username="so", password="pw12345678")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    t.site_config = {"notify": {"owner_user_pk": user.pk}}
    seen = []
    real = Membership.objects.filter

    def spy(*a, **kw):
        seen.append(connection.schema_name)
        return real(*a, **kw)

    monkeypatch.setattr(Membership.objects, "filter", spy)
    links.still_owner(t)
    assert "so_schema" in seen
