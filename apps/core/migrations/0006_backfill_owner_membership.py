"""Бэкфилл Membership(owner) для легаси-тенантов без строки членства.

До введения fail-closed гейта кабинета (CabinetOwnerAccessMiddleware) владелец без
`Membership` определялся как owner по умолчанию (fail-open). Теперь доступ требует
явную строку. Эта миграция — TENANT-scope (core в TENANT_APPS → выполняется в
КАЖДОЙ схеме тенанта) — заводит по одному Owner на схему: если строк Membership нет,
владельцем считаем самого раннего пользователя схемы (он создаётся первым при
провижининге). Идемпотентно и безопасно на повторный прогон.
"""

from django.conf import settings
from django.db import migrations


def backfill_owner(apps, schema_editor):
    Membership = apps.get_model("core", "Membership")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    if Membership.objects.exists():
        return
    first = User.objects.order_by("date_joined", "id").first()
    if first is not None:
        Membership.objects.create(user=first, role="owner")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_legaldoc"),
    ]

    operations = [
        migrations.RunPython(backfill_owner, migrations.RunPython.noop),
    ]
