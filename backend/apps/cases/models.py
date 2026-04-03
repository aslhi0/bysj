from django.db import models

from apps.projects.models import Project


def default_test_steps():
    return []


def default_variables():
    return {}


class TestCase(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        ACTIVE = 'active', '启用'
        ARCHIVED = 'archived', '归档'

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='cases',
        verbose_name='所属项目',
    )
    title = models.CharField('用例标题', max_length=300)
    steps = models.JSONField(
        '执行步骤',
        default=default_test_steps,
        blank=True,
        help_text='JSON 数组；type:http 走 requests，type:ui 走 Selenium（action: open/click/input/wait_visible/sleep 等），可与 HTTP 步骤混排。',
    )
    variables = models.JSONField(
        '全局变量池',
        default=default_variables,
        blank=True,
        help_text='键值对；步骤中可使用 {{key}} 占位符。执行时与 POST /run/ 传入的 variables 合并（请求体覆盖同名键）。',
    )
    status = models.CharField(
        '状态',
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = '测试用例'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title


class TestSuite(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='suites',
        verbose_name='所属项目',
    )
    name = models.CharField('套件名称', max_length=200)
    description = models.TextField('描述', blank=True)
    variables = models.JSONField(
        '套件变量',
        default=default_variables,
        blank=True,
        help_text='执行套件时并入变量池（在用例 variables 之后、请求体 variables 之前覆盖）。',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '测试套件'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class SuiteCase(models.Model):
    suite = models.ForeignKey(
        TestSuite,
        on_delete=models.CASCADE,
        related_name='suite_cases',
        verbose_name='套件',
    )
    testcase = models.ForeignKey(
        TestCase,
        on_delete=models.CASCADE,
        related_name='suite_memberships',
        verbose_name='用例',
    )
    order = models.PositiveIntegerField('顺序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '套件用例'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.suite_id}:{self.testcase_id}'


def default_suite_run_summary():
    return {}


def default_suite_run_results():
    return []


class SuiteRun(models.Model):
    """一次套件同步批量执行的快照，便于历史追溯与论文「执行记录」描述。"""

    suite = models.ForeignKey(
        TestSuite,
        on_delete=models.CASCADE,
        related_name='suite_runs',
        verbose_name='套件',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    stop_on_failure = models.BooleanField('遇败即停', default=False)
    summary = models.JSONField(
        '汇总',
        default=default_suite_run_summary,
        blank=True,
        help_text='如 {"total","passed","failed"}',
    )
    results = models.JSONField(
        '明细',
        default=default_suite_run_results,
        blank=True,
        help_text='每条含 case_id、case_title、record_id、status、elapsed_time',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = '套件执行记录'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'SuiteRun #{self.pk} suite={self.suite_id}'
