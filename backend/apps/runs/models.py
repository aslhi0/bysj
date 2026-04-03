from django.db import models

from apps.cases.models import TestCase


class TestRecord(models.Model):
    class Status(models.TextChoices):
        RUNNING = 'running', '执行中'
        SUCCESS = 'success', '成功'
        FAILED = 'failed', '失败'

    testcase = models.ForeignKey(
        TestCase,
        on_delete=models.CASCADE,
        related_name='records',
        verbose_name='测试用例',
    )
    status = models.CharField(
        '状态',
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    result_log = models.TextField('执行日志', blank=True)
    elapsed_time = models.FloatField(
        '耗时(秒)',
        default=0,
        help_text='整次执行总耗时',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '执行记录'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.testcase_id} #{self.pk} {self.status}'
