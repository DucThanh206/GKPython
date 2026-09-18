from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ViolationReport",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "target_type",
                    models.CharField(
                        choices=[("document", "Tài liệu"), ("comment", "Bình luận")],
                        max_length=20,
                    ),
                ),
                ("target_id", models.PositiveIntegerField(verbose_name="ID đối tượng bị báo cáo")),
                ("reason", models.TextField(verbose_name="Lý do báo cáo")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Chờ xử lý"),
                            ("resolved", "Đã xử lý"),
                            ("rejected", "Từ chối / Giữ nguyên"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("resolution_note", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "handled_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="handled_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="violation_reports_handled",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Admin xử lý",
                    ),
                ),
                (
                    "reporter",
                    models.ForeignKey(
                        db_column="reporter_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="violation_reports_sent",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Người báo cáo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Báo cáo vi phạm",
                "verbose_name_plural": "Báo cáo vi phạm",
                "db_table": "violation_reports",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="StatisticsReport",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "report_type",
                    models.CharField(
                        choices=[
                            ("documents", "Tài liệu"),
                            ("users", "Người dùng"),
                            ("downloads", "Lượt tải"),
                            ("violations", "Vi phạm"),
                            ("overview", "Tổng quan"),
                        ],
                        max_length=20,
                    ),
                ),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("file_path", models.CharField(blank=True, max_length=500, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "admin",
                    models.ForeignKey(
                        db_column="admin_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="statistics_reports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Báo cáo thống kê",
                "verbose_name_plural": "Báo cáo thống kê",
                "db_table": "statistics_reports",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="violationreport",
            index=models.Index(fields=["status"], name="idx_reports_status"),
        ),
        migrations.AddIndex(
            model_name="violationreport",
            index=models.Index(
                fields=["target_type", "target_id"], name="idx_reports_target"
            ),
        ),
        migrations.AddIndex(
            model_name="violationreport",
            index=models.Index(fields=["reporter"], name="idx_reports_reporter"),
        ),
        migrations.AddIndex(
            model_name="statisticsreport",
            index=models.Index(
                fields=["report_type", "period_start", "period_end"],
                name="idx_stats_type_period",
            ),
        ),
    ]
