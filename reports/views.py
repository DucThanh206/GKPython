"""
Views cho UC08, UC09, UC14.

UC08 - Báo cáo vi phạm            -> report_violation
UC09 - Quản lý báo cáo vi phạm     -> violation_report_list, violation_report_detail
UC14 - Thống kê, báo cáo           -> statistics_dashboard, export_statistics_report
"""

from datetime import date, timedelta
import logging
import smtplib
from pathlib import PurePosixPath

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import mail_admins
from django.db import DatabaseError
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import admin_required, member_required
from .forms import (
    ExportReportForm,
    StatisticsFilterForm,
    ViolationHandleForm,
    ViolationReportForm,
)
from .models import (
    STATISTICS_REPORT_RETENTION_DAYS,
    StatisticsReport,
    ViolationReport,
)

User = get_user_model()
logger = logging.getLogger(__name__)


# =========================================================================
# UC08 - BÁO CÁO VI PHẠM
# =========================================================================
@member_required
def report_violation(request, target_type, target_id):
    """
    Luồng sự kiện chính UC08:
        B1. Chọn chức năng "Báo cáo vi phạm"  -> GET (hiện form)
        B2. Hệ thống hiển thị form nhập lý do -> render form
        B3. Nhập lý do, gửi báo cáo            -> POST
        B4. Lưu báo cáo vào CSDL               -> form.save()
        B5. Gửi thông báo cho Admin            -> _notify_admins_new_report()
        B6. Hiển thị "Đã gửi báo cáo"          -> messages.success + redirect
    """
    if target_type not in ViolationReport.TargetType.values:
        raise Http404("Loại đối tượng báo cáo không hợp lệ.")

    initial = {"target_type": target_type, "target_id": target_id}

    if request.method == "POST":
        form_data = request.POST.copy()
        form_data.update(initial)
        form = ViolationReportForm(form_data, initial=initial)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.target_type = target_type
            report.target_id = target_id
            try:
                report.full_clean()
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
                return render(request, "reports/report_form.html", {"form": form})

            report.save()
            if not _notify_admins_new_report(report):  # B5
                messages.warning(
                    request,
                    'Báo cáo đã được lưu nhưng email thông báo cho Admin không gửi được.',
                )
            messages.success(request, "Đã gửi báo cáo. Cảm ơn bạn đã phản ánh!")  # B6
            return redirect(_get_target_redirect_url(report))
    else:
        form = ViolationReportForm(initial=initial)

    return render(
        request,
        "reports/report_form.html",
        {"form": form, "target_type": target_type, "target_id": target_id},
    )


def _notify_admins_new_report(report: ViolationReport):
    """UC08 B4 - Gửi thông báo cho Admin khi có báo cáo mới."""
    subject = f"[Báo cáo vi phạm mới] {report.get_target_type_display()} #{report.target_id}"
    message = (
        f"Người báo cáo: {report.reporter}\n"
        f"Đối tượng: {report.get_target_type_display()} #{report.target_id}\n"
        f"Lý do: {report.reason}\n"
        f"Thời gian: {report.created_at:%d/%m/%Y %H:%M}\n"
    )
    try:
        sent_count = mail_admins(subject, message)
    except (OSError, smtplib.SMTPException, ValueError):
        logger.exception("Could not email administrators about violation report %s", report.pk)
        return False
    if sent_count != 1:
        logger.error("No administrator email was sent for violation report %s", report.pk)
        return False
    return True


def _get_target_redirect_url(report: ViolationReport):
    """Điều hướng người dùng quay lại trang tài liệu/bình luận sau khi báo cáo."""
    target = report.get_target()
    if report.target_type == ViolationReport.TargetType.DOCUMENT and target is not None:
        return getattr(target, "get_absolute_url", lambda: "/")()
    # Bình luận: quay về trang tài liệu chứa bình luận đó (nếu xác định được)
    if target is not None and hasattr(target, "document_id"):
        try:
            Document = apps.get_model("documents", "Document")
            doc = Document.objects.filter(pk=target.document_id).first()
            if doc is not None:
                return getattr(doc, "get_absolute_url", lambda: "/")()
        except LookupError:
            pass
    return "/"


# =========================================================================
# UC09 - QUẢN LÝ BÁO CÁO VI PHẠM
# =========================================================================
@admin_required
def violation_report_list(request):
    """
    B1. Admin mở danh sách báo cáo -> GET
    B2. Hiển thị báo cáo chờ xử lý -> queryset lọc theo status (mặc định pending)
    """
    status = request.GET.get("status", ViolationReport.Status.PENDING)
    reports = ViolationReport.objects.select_related("reporter", "handled_by")

    if status in ViolationReport.Status.values:
        reports = reports.filter(status=status)

    counts = ViolationReport.objects.values("status").annotate(total=Count("id"))
    status_counts = {row["status"]: row["total"] for row in counts}

    return render(
        request,
        "reports/violation_list.html",
        {
            "reports": reports,
            "current_status": status,
            "status_choices": ViolationReport.Status.choices,
            "status_counts": status_counts,
        },
    )


@admin_required
def violation_report_detail(request, pk):
    """
    B2. Chọn một báo cáo               -> GET
    B3. Hiển thị chi tiết               -> render (kèm target)
    (Bước 3 luồng chính) Quyết định xử lý (xóa, giữ, cảnh báo) -> POST
    B4. Cập nhật trạng thái báo cáo     -> report.apply_action()
    B5. Thông báo kết quả cho người báo cáo -> _notify_reporter_result()
    """
    report = get_object_or_404(
        ViolationReport.objects.select_related("reporter", "handled_by"), pk=pk
    )
    target = report.get_target()

    if request.method == "POST":
        form = ViolationHandleForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data["action"]
            note = form.cleaned_data["note"]
            report.apply_action(action=action, admin_user=request.user, note=note)
            notification_sent = _notify_reporter_result(report, action)  # B5
            owner_notified = True
            if action == ViolationReport.Action.WARN:
                owner_notified = _notify_content_owner(report)
            messages.success(
                request,
                f"Đã xử lý báo cáo #{report.id}: {ViolationReport.get_action_label(action)}.",
            )
            if not notification_sent:
                messages.warning(
                    request,
                    'Báo cáo đã được xử lý nhưng email thông báo cho người báo cáo không gửi được.',
                )
            if action == ViolationReport.Action.WARN and not owner_notified:
                messages.warning(
                    request,
                    'Đã lưu lịch sử cảnh báo nhưng email cho người đăng không gửi được hoặc tài khoản chưa có email.',
                )
            return redirect("reports:violation_report_list")
    else:
        form = ViolationHandleForm()

    return render(
        request,
        "reports/violation_detail.html",
        {"report": report, "target": target, "form": form},
    )


def _notify_reporter_result(report: ViolationReport, action: str):
    """UC09 B5 - Thông báo kết quả xử lý cho người đã gửi báo cáo."""
    if not getattr(report.reporter, "email", None):
        return False
    subject = f"Kết quả xử lý báo cáo vi phạm #{report.id}"
    message = (
        f"Báo cáo của bạn với {report.get_target_type_display()} #{report.target_id} "
        f"đã được xử lý.\nKết quả: {ViolationReport.get_action_label(action)}.\n"
        f"Ghi chú: {report.resolution_note or '(không có)'}"
    )
    try:
        from django.core.mail import send_mail

        sent_count = send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            [report.reporter.email],
        )
    except (OSError, smtplib.SMTPException, ValueError):
        logger.exception("Could not email reporter about violation report %s", report.pk)
        return False
    return sent_count == 1


def _notify_content_owner(report: ViolationReport):
    """Email the uploader/commenter; the report row records who warned them and why."""
    target = report.get_target()
    if target is None:
        return False
    owner = (
        getattr(target, "uploader", None)
        if report.target_type == ViolationReport.TargetType.DOCUMENT
        else getattr(target, "user", None)
    )
    email = getattr(owner, "email", None)
    if not email:
        return False

    try:
        from django.core.mail import send_mail

        sent_count = send_mail(
            f"Cảnh báo về nội dung bạn đã đăng (báo cáo #{report.pk})",
            (
                f"Nội dung {report.get_target_type_display()} #{report.target_id} "
                "đã bị quản trị viên cảnh báo sau khi xem xét báo cáo.\n"
                f"Lý do báo cáo: {report.reason}\n"
                f"Ghi chú xử lý: {report.resolution_note or '(không có)'}"
            ),
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
    except (OSError, smtplib.SMTPException, ValueError):
        logger.exception("Could not email content owner about warning %s", report.pk)
        return False
    return sent_count == 1


# =========================================================================
# UC14 - THỐNG KÊ, BÁO CÁO
# =========================================================================
@admin_required
def statistics_dashboard(request):
    """
    B1. Chọn chức năng "Thống kê, báo cáo"          -> GET
    B2. Hiển thị các loại thống kê                   -> form.report_type choices
    B2. Chọn loại thống kê & khoảng thời gian        -> GET params
    B3. Truy vấn dữ liệu từ CSDL                     -> _build_statistics()
    B4. Hiển thị biểu đồ / số liệu thống kê          -> render + context
    B3(opt). Chọn "Xuất báo cáo"                     -> form xuất (export_statistics_report)
    """
    form = StatisticsFilterForm(request.GET or None)

    if form.is_valid():
        report_type = form.cleaned_data["report_type"]
        period_start = form.cleaned_data["period_start"]
        period_end = form.cleaned_data["period_end"]
    else:
        report_type = StatisticsReport.ReportType.OVERVIEW
        period_start = date.today() - timedelta(days=30)
        period_end = date.today()

    data = _build_statistics(report_type, period_start, period_end)

    export_form = ExportReportForm(
        initial={
            "report_type": report_type,
            "period_start": period_start,
            "period_end": period_end,
        }
    )
    export_history = list(
        StatisticsReport.objects.filter(
            admin=request.user,
            created_at__gt=timezone.now()
            - timedelta(days=STATISTICS_REPORT_RETENTION_DAYS),
        ).order_by("-created_at")[:20]
    )
    for report in export_history:
        try:
            report.download_available = bool(
                report.file_path and default_storage.exists(report.file_path)
            )
        except OSError:
            logger.exception(
                "Could not check exported statistics report %s", report.pk
            )
            report.download_available = False

    status_breakdowns = _format_status_breakdowns(data)
    return render(
        request,
        "reports/admin_dashboard.html",
        {
            "filter_form": form,
            "export_form": export_form,
            "report_type": report_type,
            "period_start": period_start,
            "period_end": period_end,
            "data": data,
            "export_history": export_history,
            "statistic_labels": {
                key: _statistic_label(key) for key in data if key != "report_type"
            },
            "status_breakdown_keys": tuple(status_breakdowns),
            "status_breakdowns": status_breakdowns,
        },
    )


def _format_status_breakdowns(data):
    """Translate grouped status values into presentation-ready labels and counts."""
    choices_by_key = {}
    try:
        Document = apps.get_model("documents", "Document")
        choices_by_key.update({
            "document_by_status": Document.Status.choices,
            "document_by_status_period": Document.Status.choices,
        })
    except LookupError:
        pass
    choices_by_key["violation_by_status"] = ViolationReport.Status.choices

    return {
        key: [
            {
                "label": dict(choices_by_key[key]).get(row["status"], row["status"]),
                "status": row["status"],
                "total": row["total"],
            }
            for row in data.get(key, [])
        ]
        for key in choices_by_key
        if key in data
    }


def _build_statistics(report_type, period_start, period_end):
    """B3 - Truy vấn CSDL theo loại thống kê đã chọn.

    Dùng ORM tương đương các view SQL đã tạo sẵn trong schema:
    v_document_stats, v_violation_stats, v_daily_activity.
    Nếu app 'documents' chưa tồn tại trong project hiện tại (đang phát
    triển độc lập từng phần), hàm sẽ trả về dữ liệu rỗng/None thay vì lỗi.
    """
    result = {"report_type": report_type}

    # ---- Người dùng: luôn khả dụng vì User thuộc app accounts ----
    if report_type in (StatisticsReport.ReportType.USERS, StatisticsReport.ReportType.OVERVIEW):
        result["total_users"] = User.objects.count()
        result["new_users"] = User.objects.filter(
            date_joined__date__gte=period_start, date_joined__date__lte=period_end
        ).count()

    # ---- Vi phạm: luôn khả dụng vì ViolationReport thuộc app reports ----
    if report_type in (StatisticsReport.ReportType.VIOLATIONS, StatisticsReport.ReportType.OVERVIEW):
        qs = ViolationReport.objects.filter(
            created_at__date__gte=period_start, created_at__date__lte=period_end
        )
        result["violation_total"] = qs.count()
        result["violation_by_status"] = list(
            qs.values("status").annotate(total=Count("id")).order_by("status")
        )

    # ---- Tài liệu / Lượt tải: phụ thuộc app 'documents' ----
    if report_type in (
        StatisticsReport.ReportType.DOCUMENTS,
        StatisticsReport.ReportType.DOWNLOADS,
        StatisticsReport.ReportType.OVERVIEW,
    ):
        try:
            Document = apps.get_model("documents", "Document")
            doc_qs = Document.objects.filter(
                uploaded_at__date__gte=period_start, uploaded_at__date__lte=period_end
            )
            result["document_total"] = Document.objects.count()
            result["document_new"] = doc_qs.count()
            result["document_by_status"] = list(
                Document.objects.values("status").annotate(total=Count("id")).order_by("status")
            )
            result["document_by_status_period"] = list(
                doc_qs.values("status")
                .annotate(total=Count("id"))
                .order_by("status")
            )
        except LookupError:
            result["document_total"] = None

        try:
            Download = apps.get_model("documents", "Download")
            result["download_total"] = Download.objects.filter(
                downloaded_at__date__gte=period_start, downloaded_at__date__lte=period_end
            ).count()
        except LookupError:
            result["download_total"] = None

    return result


@admin_required
def export_statistics_report(request):
    """
    B3 (tùy chọn) "Xuất báo cáo"
    B5. Tạo file báo cáo (PDF/Excel), lưu vào statistics_reports, cho tải xuống.
    """
    form = ExportReportForm(request.GET or None)
    if not form.is_valid():
        messages.error(request, "Thông tin xuất báo cáo không hợp lệ.")
        return redirect("reports:statistics_dashboard")

    report_type = form.cleaned_data["report_type"]
    period_start = form.cleaned_data["period_start"]
    period_end = form.cleaned_data["period_end"]
    file_format = form.cleaned_data["file_format"]

    data = _build_statistics(report_type, period_start, period_end)

    if file_format == "xlsx":
        response = _export_xlsx(report_type, period_start, period_end, data)
        file_name = f"baocao_{report_type}_{period_start}_{period_end}.xlsx"
    else:
        response = _export_pdf(report_type, period_start, period_end, data)
        file_name = f"baocao_{report_type}_{period_start}_{period_end}.pdf"

    report = None
    stored_name = None
    try:
        report = StatisticsReport.objects.create(
            admin=request.user,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
        )
        stored_name = default_storage.save(
            f"exports/{report.pk}/{file_name}",
            ContentFile(response.content),
        )
        report.file_path = stored_name
        report.save(update_fields=["file_path"])
    except (OSError, DatabaseError):
        logger.exception("Could not persist exported statistics report")
        if stored_name:
            default_storage.delete(stored_name)
        if report is not None:
            report.delete()
        messages.error(
            request,
            "Không thể lưu bản xuất vào kho tệp. Báo cáo chưa được tạo; vui lòng thử lại.",
        )
        return redirect("reports:statistics_dashboard")

    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    return response


@admin_required
def download_statistics_report(request, pk):
    report = get_object_or_404(StatisticsReport, pk=pk, admin=request.user)
    if timezone.now() >= report.expires_at:
        raise Http404("Bản xuất báo cáo đã hết hạn.")
    if not report.file_path:
        raise Http404("Không tìm thấy tệp báo cáo.")
    path = PurePosixPath(report.file_path)
    if (
        path.is_absolute()
        or not path.parts
        or path.parts[0] != "exports"
        or any(part in (".", "..") for part in path.parts)
    ):
        raise Http404("Đường dẫn tệp báo cáo không hợp lệ.")
    try:
        file_handle = default_storage.open(report.file_path, "rb")
    except (FileNotFoundError, OSError) as exc:
        logger.exception("Stored statistics report %s is unavailable", report.pk)
        raise Http404("Không tìm thấy tệp báo cáo.") from exc
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=path.name,
    )


def _export_xlsx(report_type, period_start, period_end, data):
    """Xuất báo cáo dạng Excel bằng openpyxl."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Báo cáo"

    ws.append([f"Báo cáo: {report_type}"])
    ws.append([f"Khoảng thời gian: {period_start} - {period_end}"])
    ws.append([f"Xuất lúc: {timezone.now():%d/%m/%Y %H:%M}"])
    ws.append([])
    ws.append(["Chỉ số", "Giá trị"])

    for key, value in data.items():
        if key == "report_type":
            continue
        if isinstance(value, list):
            ws.append([_statistic_label(key), ""])
            for row in value:
                ws.append(["", str(row)])
        else:
            ws.append([_statistic_label(key), value])

    from io import BytesIO

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _export_pdf(report_type, period_start, period_end, data):
    """Xuất báo cáo dạng PDF bằng reportlab."""
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, y, f"Báo cáo thống kê: {report_type}")
    y -= 25
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"Khoảng thời gian: {period_start} - {period_end}")
    y -= 20
    p.drawString(50, y, f"Xuất lúc: {timezone.now():%d/%m/%Y %H:%M}")
    y -= 30

    for key, value in data.items():
        if key == "report_type":
            continue
        if y < 60:
            p.showPage()
            y = height - 50
            p.setFont("Helvetica", 11)
        if isinstance(value, list):
            p.drawString(50, y, f"{_statistic_label(key)}:")
            y -= 18
            for row in value:
                p.drawString(70, y, f"- {row}")
                y -= 16
        else:
            p.drawString(50, y, f"{_statistic_label(key)}: {value}")
            y -= 18

    p.showPage()
    p.save()
    buffer.seek(0)
    return HttpResponse(buffer.read(), content_type="application/pdf")


def _statistic_label(key):
    labels = {
        "total_users": "Tổng người dùng (toàn thời gian)",
        "new_users": "Người dùng mới (trong kỳ)",
        "violation_total": "Báo cáo vi phạm (trong kỳ)",
        "violation_by_status": "Phân bố trạng thái báo cáo (trong kỳ)",
        "document_total": "Tổng tài liệu (toàn thời gian)",
        "document_new": "Tài liệu mới (trong kỳ)",
        "document_by_status": "Trạng thái tài liệu (toàn thời gian)",
        "document_by_status_period": "Trạng thái tài liệu (tài liệu tạo trong kỳ)",
        "download_total": "Lượt tải (trong kỳ)",
    }
    return labels.get(key, key.replace("_", " ").title())
