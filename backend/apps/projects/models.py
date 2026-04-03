from django.db import models


class Project(models.Model):
    name = models.CharField('项目名称', max_length=200)
    description = models.TextField('描述', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '测试项目'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name
