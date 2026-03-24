from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hansviet_admin", "0006_newsarticle_ai_source_newsarticle_is_auto_generated_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="newsarticle",
            name="view_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]

