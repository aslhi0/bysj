from django.db import models
from django.conf import settings

class Project(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='projects', verbose_name='所属用户')
    name = models.CharField('项目名称', max_length=100)
    description = models.TextField('项目描述', blank=True)
    webhook_url = models.URLField('Webhook地址', blank=True, help_text='如钉钉/企微群机器人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '测试项目'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class EnvConfig(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='envs', verbose_name='所属项目')
    name = models.CharField('环境名称', max_length=50)
    base_url = models.URLField('基础URL', blank=True)
    db_config = models.JSONField('数据库配置', default=dict, help_text='{"host": "...", "port": 3306, "user": "...", "password": "...", "database": "..."}', blank=True)
    variables = models.JSONField('环境变量', default=dict, help_text='如数据库连接、Token等')
    is_default = models.BooleanField('是否默认', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '环境配置'
        verbose_name_plural = verbose_name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            EnvConfig.objects.filter(project=self.project).exclude(id=self.id).update(is_default=False)

class TestCase(models.Model):
    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('active', '启用'),
        ('archived', '归档'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='cases', verbose_name='所属项目')
    title = models.CharField('用例标题', max_length=200)
    steps = models.JSONField('测试步骤', default=list)
    variables = models.JSONField('变量池', default=dict)
    tags = models.JSONField('标签', default=list, blank=True)
    setup_sql = models.TextField('前置SQL', blank=True, help_text='测试前执行的数据准备脚本')
    teardown_sql = models.TextField('后置SQL', blank=True, help_text='测试后执行的数据清理脚本')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '测试用例'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']

    def __str__(self):
        return self.title

class TestCaseVersion(models.Model):
    case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='versions', verbose_name='所属用例')
    version = models.IntegerField('版本号')
    snapshot = models.JSONField('快照', default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='case_versions', verbose_name='创建人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '用例版本'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['case', 'version'], name='uniq_case_version'),
        ]

class TestSuite(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='suites', verbose_name='所属项目')
    name = models.CharField('套件名称', max_length=100)
    description = models.TextField('套件描述', blank=True)
    variables = models.JSONField('套件变量', default=dict)
    ordered_case_ids = models.JSONField('用例顺序', default=list)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '测试套件'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class TestRecord(models.Model):
    case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='records', verbose_name='所属用例')
    status = models.CharField('执行结果', max_length=20, default='running')
    result_log = models.TextField('执行日志', blank=True)
    step_results = models.JSONField('步骤详情', default=list, blank=True)
    screenshot = models.ImageField('失败截图', upload_to='screenshots/%Y/%m/%d/', blank=True, null=True)
    elapsed_time = models.FloatField('耗时(s)', default=0.0)
    created_at = models.DateTimeField('执行时间', auto_now_add=True)

    class Meta:
        verbose_name = '用例执行记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

class SuiteRun(models.Model):
    suite = models.ForeignKey(TestSuite, on_delete=models.CASCADE, related_name='runs', verbose_name='所属套件')
    summary = models.JSONField('执行汇总', default=dict)
    stop_on_failure = models.BooleanField('遇败即停', default=False)
    results = models.JSONField('详细结果', default=list)
    created_at = models.DateTimeField('执行时间', auto_now_add=True)

    class Meta:
        verbose_name = '套件执行批次'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

class PerfRecord(models.Model):
    case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='perf_records', verbose_name='所属用例')
    users = models.IntegerField('并发用户数')
    spawn_rate = models.IntegerField('每秒启动数')
    duration = models.CharField('持续时长', max_length=20)
    status = models.CharField('状态', max_length=20, default='running')
    csv_prefix = models.CharField('结果文件前缀', max_length=100, blank=True)
    created_at = models.DateTimeField('执行时间', auto_now_add=True)

    class Meta:
        verbose_name = '性能测试记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
