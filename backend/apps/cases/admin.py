from django.contrib import admin

from .models import SuiteCase, SuiteRun, TestCase, TestSuite


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'status', 'updated_at')
    list_filter = ('status', 'project')
    search_fields = ('title',)


class SuiteCaseInline(admin.TabularInline):
    model = SuiteCase
    extra = 0
    ordering = ('order',)


@admin.register(TestSuite)
class TestSuiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'created_at')
    list_filter = ('project',)
    inlines = [SuiteCaseInline]


@admin.register(SuiteRun)
class SuiteRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'suite', 'created_at', 'stop_on_failure')
    list_filter = ('suite',)
    readonly_fields = ('suite', 'created_at', 'stop_on_failure', 'summary', 'results')
