"""T-8.30f: заполнить OwnerTelegramLink.user_pk из зеркала site_config["notify"].

Только если зеркало принадлежит ЭТОЙ связи (общий бот, тот же чат) и метка — целое > 0;
иначе NULL (не угадываем). Право владельца здесь не проверяется (Membership — в схемах
бизнесов): это делает код при каждом чтении.
"""

from django.db import migrations


def forward(apps, schema_editor):
    Link = apps.get_model("platform_bot", "OwnerTelegramLink")
    for link in Link.objects.filter(is_active=True, user_pk__isnull=True).select_related(
        "tenant"
    ):
        cfg = link.tenant.site_config if isinstance(link.tenant.site_config, dict) else {}
        node = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
        if node.get("owner_bot") != "platform":
            continue
        if str(node.get("owner_chat_id") or "") != str(link.tg_user_id):
            continue
        pk = node.get("owner_user_pk")
        if isinstance(pk, bool) or not isinstance(pk, int) or pk <= 0:
            continue
        Link.objects.filter(pk=link.pk).update(user_pk=pk)


class Migration(migrations.Migration):
    dependencies = [("platform_bot", "0003_ownertelegramlink_user_pk")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
