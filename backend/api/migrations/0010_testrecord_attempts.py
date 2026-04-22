from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_projectmember'),
    ]

    operations = [
        migrations.AddField(
            model_name='testrecord',
            name='attempts',
            field=models.IntegerField(default=1, verbose_name='实际尝试次数'),
        ),
        migrations.AddField(
            model_name='testrecord',
            name='attempt_logs',
            field=models.JSONField(blank=True, default=list, verbose_name='尝试明细'),
        ),
    ]
