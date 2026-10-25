"""KA-12 E6.7c: журнал команды чистится через 3 года, прочий журнал не трогается."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.tasks import purge_team_audit

pytestmark = pytest.mark.django_db


def _event(action, days_ago):
    e = AuditEvent.objects.create(action=action, resource_type="membership", resource_id="x")
    AuditEvent.objects.filter(pk=e.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    return e


def test_purges_only_old_team_events():
    old_team = _event("team.perms", 4 * 365)
    fresh_team = _event("team.role", 30)
    old_other = _event("export.crm", 4 * 365)
    purge_team_audit.run() if hasattr(purge_team_audit, "run") else purge_team_audit()
    left = set(AuditEvent.objects.values_list("pk", flat=True))
    assert old_team.pk not in left
    assert {fresh_team.pk, old_other.pk} <= left
