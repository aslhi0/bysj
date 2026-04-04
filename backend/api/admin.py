from django.contrib import admin
from .models import Project, EnvConfig, TestCase, TestSuite, TestRecord, SuiteRun, PerfRecord, TestCaseVersion

admin.site.register(Project)
admin.site.register(EnvConfig)
admin.site.register(TestCase)
admin.site.register(TestSuite)
admin.site.register(TestRecord)
admin.site.register(SuiteRun)
admin.site.register(PerfRecord)
admin.site.register(TestCaseVersion)
