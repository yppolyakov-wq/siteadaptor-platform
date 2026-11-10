"""NT-A1 (Р-NT4): подписки-поиски из ОДНОГО условия «категория / признак / марка» → свои виды.

До NT такие подписки жили как вид «query» (sha256 набора). Теперь у них отдельный вид, и центр
подписок видит их как отмеченные пункты. Дубль (житель уже подписан на ту же цель новым видом)
сливается: остаётся одна строка с более ранней датой согласия (Art. 7 DSGVO); частота и
портал — у оставшейся строки (её житель выбирал позже, через новый вид). Идемпотентно:
повторный прогон ничего не находит. Обратный ход — noop (строки нового вида остаются валидными).
"""

from django.db import migrations


def _target(pairs, cc):
    if not isinstance(pairs, list) or len(pairs) != 1:
        return None
    item = pairs[0]
    if not isinstance(item, (list, tuple)) or len(item) != 2:
        return None
    name, value = str(item[0]), str(item[1]).strip()
    if name == "kat" and cc.category(value) and not cc.section(value):
        return "category", value
    if name == "merkmal" and cc.tag_label(value):
        return "tag", value
    if name == "marke":
        from apps.aggregator.search import clean_brand

        key = clean_brand(value).casefold()  # = follow.brand_key
        return ("brand", key) if key else None
    return None


def forward(apps, schema_editor):
    from apps.core import city_categories as cc

    FollowSubscription = apps.get_model("aggregator", "FollowSubscription")
    for sub in FollowSubscription.objects.filter(target_kind="query").order_by("pk"):
        pairs = (sub.query or {}).get("p") if isinstance(sub.query, dict) else None
        target = _target(pairs, cc)
        if target is None:
            continue
        kind, key = target
        twin = (
            FollowSubscription.objects.filter(
                user_id=sub.user_id,
                target_kind=kind,
                target_key=key,
                city=sub.city,
                channel=sub.channel,
            )
            .exclude(pk=sub.pk)
            .first()
        )
        if twin is not None:
            if sub.confirmed_at and sub.confirmed_at < twin.confirmed_at:
                twin.confirmed_at = sub.confirmed_at
                twin.source_host = sub.source_host or twin.source_host
                twin.save(update_fields=["confirmed_at", "source_host"])
            sub.delete()
            continue
        sub.target_kind = kind
        sub.target_key = key
        sub.query = {}
        sub.save(update_fields=["target_kind", "target_key", "query"])


class Migration(migrations.Migration):
    dependencies = [("aggregator", "0040_nt_follow_kinds")]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
