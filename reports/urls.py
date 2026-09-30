from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    # UC08 - Báo cáo vi phạm
    # Ví dụ gọi từ trang chi tiết tài liệu: {% url 'reports:report_violation' 'document' document.id %}
    # Ví dụ gọi từ 1 bình luận:            {% url 'reports:report_violation' 'comment' comment.id %}
    path(
        "violation/report/<str:target_type>/<int:target_id>/",
        views.report_violation,
        name="report_violation",
    ),
    # UC09 - Quản lý báo cáo vi phạm (Admin)
    path("violation/manage/", views.violation_report_list, name="violation_report_list"),
    path(
        "violation/manage/<int:pk>/",
        views.violation_report_detail,
        name="violation_report_detail",
    ),
    # UC14 - Thống kê, báo cáo (Admin)
    path("stats/", views.statistics_dashboard, name="statistics_dashboard"),
    path("stats/export/", views.export_statistics_report, name="export_statistics_report"),
    path(
        "stats/history/<int:pk>/download/",
        views.download_statistics_report,
        name="download_statistics_report",
    ),
]
