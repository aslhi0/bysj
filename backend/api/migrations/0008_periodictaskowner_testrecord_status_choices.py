from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_testcaseversion'),
        ('django_celery_beat', '0018_improve_crontab_helptext'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 为 TestRecord.status 添加 choices（不影响数据库列类型，无需数据迁移）
        migrations.AlterField(
            model_name='testrecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('running', '执行中'),
                    ('success', '成功'),
                    ('failed', '失败'),
                    ('error', '异常'),
                ],
                default='running',
                max_length=20,
                verbose_name='执行结果',
            ),
        ),
        # 新增 PeriodicTaskOwner 表
        migrations.CreateModel(
            name='PeriodicTaskOwner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('owner', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='owned_periodic_tasks',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='归属用户',
                )),
                ('periodic_task', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='owner_record',
                    to='django_celery_beat.periodictask',
                    verbose_name='定时任务',
                )),
            ],
            options={
                'verbose_name': '定时任务归属',
                'verbose_name_plural': '定时任务归属',
            },
        ),
    ]
