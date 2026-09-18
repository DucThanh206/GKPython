from django.contrib import admin

from .models import StatisticsReport, ViolationReport


@admin.register(ViolationReport)
class ViolationReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "target_type",
        "target_id",
        "reporter",
        "status",
        "handled_by",
        "created_at",
        "resolved_at",
    )
    list_filter = ("status", "target_type")
    search_fields = ("reason", "reporter__email", "reporter__full_name")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


@admin.register(StatisticsReport)
class StatisticsReportAdmin(admin.ModelAdmin):
    list_display = ("id", "report_type", "period_start", "period_end", "admin", "created_at")
    list_filter = ("report_type",)
    date_hierarchy = "created_at"
