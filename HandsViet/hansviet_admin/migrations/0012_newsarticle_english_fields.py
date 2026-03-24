from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hansviet_admin", "0011_purchase_expiry_reminder_days_sent"),
    ]

    operations = [
        migrations.AddField(
            model_name="newsarticle",
            name="title_en",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="newsarticle",
            name="summary_en",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="newsarticle",
            name="content_en",
            field=models.TextField(blank=True, default=""),
        ),
    ]
