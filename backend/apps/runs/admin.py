from django.contrib import admin

from .models import TestRecord


@admin.register(TestRecord)
class TestRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'testcase', 'status', 'elapsed_time', 'created_at')
    list_filter = ('status',)
    search_fields = ('testcase__title', 'result_log')
