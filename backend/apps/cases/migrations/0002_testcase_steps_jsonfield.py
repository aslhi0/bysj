import json

from django.db import migrations, models


def text_steps_to_json(apps, schema_editor):
    TestCase = apps.get_model('cases', 'TestCase')
    for tc in TestCase.objects.all():
        raw = tc.steps
        text = raw.strip() if isinstance(raw, str) else ''
        if not text:
            tc.steps_data = []
        else:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    tc.steps_data = parsed
                elif isinstance(parsed, dict):
                    tc.steps_data = [parsed]
                else:
                    tc.steps_data = [{'type': 'legacy_text', 'content': text}]
            except (json.JSONDecodeError, TypeError, ValueError):
                tc.steps_data = [{'type': 'legacy_text', 'content': text}]
        tc.save(update_fields=['steps_data'])


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='testcase',
            name='steps_data',
            field=models.JSONField(blank=True, null=True, verbose_name='执行步骤(迁移)'),
        ),
        migrations.RunPython(text_steps_to_json, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='testcase',
            name='steps',
        ),
        migrations.RenameField(
            model_name='testcase',
            old_name='steps_data',
            new_name='steps',
        ),
        migrations.AlterField(
            model_name='testcase',
            name='steps',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='JSON 数组；每项建议含 type（ui|http）、method、url、selector、action 等，供 Selenium/Requests 执行引擎解析。',
                verbose_name='执行步骤',
            ),
        ),
    ]
