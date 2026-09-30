"""
Models cho app `reports`.

Ánh xạ đúng 2 bảng trong schemaThuVien.sql:
    - violation_reports   -> ViolationReport   (dùng cho UC08, UC09)
    - statistics_reports  -> StatisticsReport  (dùng cho UC14)

Lưu ý (đã ghi trong schema):
    - `target_type` / `target_id` là khóa đa hình (document hoặc comment),
      KHÔNG có FK cứng ở tầng CSDL -> phải tự kiểm tra tính hợp lệ và xử lý
      cascade ở tầng ứng dụng (xem hàm get_target()/clean()).
    - `documents.Document` và `documents.Comment` thuộc app khác (app
      `documents` do bạn cùng nhóm phụ trách). Ở đây chỉ tham chiếu bằng
      string reference ("app_label.Model") để tránh phụ thuộc import cứng.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from datetime import timedelta

from django.utils import timezone

STATISTICS_REPORT_RETENTION_DAYS = 90


class ViolationReport(models.Model):
    """UC08 - Báo cáo vi phạm / UC09 - Quản lý báo cáo vi phạm."""

    class TargetType(models.TextChoices):
        DOCUMENT = "document", "Tài liệu"
        COMMENT = "comment", "Bình luận"

    class Status(models.TextChoices):
        PENDING = "pending", "Chờ xử lý"
        RESOLVED = "resolved", "Đã xử lý"
        REJECTED = "rejected", "Từ chối / Giữ nguyên"

    class Action(models.TextChoices):
        """Hành động Admin chọn ở UC09 (Bước 3: xóa / giữ / cảnh báo).

        Không có cột riêng trong schema -> được ghi lại trong resolution_note,
        đồng thời map sang Status ở phía trên.
        """
        DELETE = "delete", "Gỡ bỏ nội dung vi phạm"
        KEEP = "keep", "Giữ nguyên (báo cáo không hợp lệ)"
        WARN = "warn", "Cảnh báo người vi phạm"

    id = models.AutoField(primary_key=True)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="violation_reports_sent",
        db_column="reporter_id",
        verbose_name="Người báo cáo",
    )
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    target_id = models.PositiveIntegerField(verbose_name="ID đối tượng bị báo cáo")
    reason = models.TextField(verbose_name="Lý do báo cáo")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="violation_reports_handled",
        db_column="handled_by",
        verbose_name="Admin xử lý",
    )
    resolution_note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "violation_reports"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="idx_reports_status"),
            models.Index(fields=["target_type", "target_id"], name="idx_reports_target"),
            models.Index(fields=["reporter"], name="idx_reports_reporter"),
        ]
        verbose_name = "Báo cáo vi phạm"
        verbose_name_plural = "Báo cáo vi phạm"

    def __str__(self):
        return f"[{self.get_status_display()}] {self.get_target_type_display()} #{self.target_id}"

    # ------------------------------------------------------------------
    # UC08 - hỗ trợ nghiệp vụ
    # ------------------------------------------------------------------
    def clean(self):
        """Kiểm tra target_id có tồn tại thật hay không (vì không có FK cứng)."""
        target = self.get_target()
        if target is None:
            raise ValidationError(
                f"{self.get_target_type_display()} #{self.target_id} không tồn tại."
            )

    def get_target(self):
        """Trả về đối tượng thật sự bị báo cáo (Document hoặc Comment)."""
        from django.apps import apps

        try:
            if self.target_type == self.TargetType.DOCUMENT:
                Document = apps.get_model("documents", "Document")
                return Document.objects.filter(pk=self.target_id).first()
            if self.target_type == self.TargetType.COMMENT:
                Comment = apps.get_model("documents", "Comment")
                return Comment.objects.filter(pk=self.target_id).first()
        except LookupError:
            # App 'documents' chưa được cài đặt trong dự án hiện tại.
            return None
        return None

    # ------------------------------------------------------------------
    # UC09 - hỗ trợ nghiệp vụ
    # ------------------------------------------------------------------
    def apply_action(self, action: str, admin_user, note: str = ""):
        """Admin xử lý báo cáo: xóa / giữ / cảnh báo (UC09 bước 3-5).

        - delete -> gỡ tài liệu/bình luận vi phạm, status = resolved
        - warn   -> cảnh báo người vi phạm (không xóa nội dung), status = resolved
        - keep   -> giữ nguyên, báo cáo không hợp lệ, status = rejected
        """
        if action not in self.Action.values:
            raise ValidationError("Hành động xử lý không hợp lệ.")

        target = self.get_target()

        if action == self.Action.DELETE:
            if target is not None and self.target_type == self.TargetType.DOCUMENT and hasattr(target, "status"):
                target.status = "rejected"
                target.save(update_fields=["status"])
            elif target is not None and self.target_type == self.TargetType.COMMENT and hasattr(target, "is_deleted"):
                target.is_deleted = True
                target.save(update_fields=["is_deleted"])
            self.status = self.Status.RESOLVED
        elif action == self.Action.WARN:
            self.status = self.Status.RESOLVED
        elif action == self.Action.KEEP:
            self.status = self.Status.REJECTED

        self.handled_by = admin_user
        self.resolution_note = f"[{self.get_action_label(action)}] {note}".strip()
        self.resolved_at = timezone.now()
        self.save(update_fields=[
            "status", "handled_by", "resolution_note", "resolved_at",
        ])
        return self

    @classmethod
    def get_action_label(cls, action: str) -> str:
        return dict(cls.Action.choices).get(action, action)


class StatisticsReport(models.Model):
    """UC14 - Thống kê, báo cáo (lịch sử các file báo cáo Admin đã xuất)."""

    class ReportType(models.TextChoices):
        DOCUMENTS = "documents", "Tài liệu"
        USERS = "users", "Người dùng"
        DOWNLOADS = "downloads", "Lượt tải"
        VIOLATIONS = "violations", "Vi phạm"
        OVERVIEW = "overview", "Tổng quan"

    id = models.AutoField(primary_key=True)
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="statistics_reports",
        db_column="admin_id",
    )
    report_type = models.CharField(max_length=20, choices=ReportType.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    file_path = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "statistics_reports"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["report_type", "period_start", "period_end"],
                name="idx_stats_type_period",
            ),
        ]
        verbose_name = "Báo cáo thống kê"
        verbose_name_plural = "Báo cáo thống kê"

    def __str__(self):
        return f"{self.get_report_type_display()} ({self.period_start} - {self.period_end})"

    @property
    def expires_at(self):
        return self.created_at + timedelta(days=STATISTICS_REPORT_RETENTION_DAYS)
