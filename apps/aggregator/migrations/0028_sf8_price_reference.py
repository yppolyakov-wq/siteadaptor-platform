# SF-8a (§ 11 PAngV в каталоге города): что за референс у зачёркнутой цены —
# «UVP» производителя или низшая цена 30 дней до акции. SHARED, аддитивная,
# default="" (fast-default PG16, таблица не переписывается).
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("aggregator", "0027_t8_26_variant_terms"),
    ]

    operations = [
        migrations.AddField(
            model_name="aggregatorlisting",
            name="price_reference",
            field=models.CharField(
                blank=True,
                choices=[("", ""), ("uvp", "UVP"), ("lowest30", "Lowest price in the last 30 days")],
                default="",
                max_length=10,
            ),
        ),
    ]
