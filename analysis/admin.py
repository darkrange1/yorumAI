from django.contrib import admin

from .models import Analysis


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "url", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "url")
    readonly_fields = ("created_at",)
