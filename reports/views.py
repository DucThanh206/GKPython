"""
Views cho UC08, UC09, UC14.

UC08 - Báo cáo vi phạm            -> report_violation
UC09 - Quản lý báo cáo vi phạm     -> violation_report_list, violation_report_detail
UC14 - Thống kê, báo cáo           -> statistics_dashboard, export_statistics_report
"""

from datetime import date, timedelta

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.mail import mail_admins
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import admin_required, member_required
from .forms import (
    ExportReportForm,
    StatisticsFilterForm,
    ViolationHandleForm,
    ViolationReportForm,
)
from .models import StatisticsReport, ViolationReport

User = get_user_model()


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
        form = ViolationReportForm(request.POST, initial=initial)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.target_type = target_type
            report.target_id = target_id
            try:
                report.full_clean()
            except Exception as exc:  # đối tượng bị báo cáo không tồn tại
                messages.error(request, "; ".join(sum(exc.message_dict.values(), [])) if hasattr(exc, "message_dict") else str(exc))
                return render(request, "reports/report_form.html", {"form": form})

            report.save()
            _notify_admins_new_report(report)  # B5
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
        mail_admins(subject, message, fail_silently=True)
    except Exception:
        # Không để lỗi gửi mail làm hỏng luồng báo cáo chính.
        pass


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
            _notify_reporter_result(report, action)  # B5
            messages.success(
                request,
                f"Đã xử lý báo cáo #{report.id}: {ViolationReport.get_action_label(action)}.",
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
        return
    subject = f"Kết quả xử lý báo cáo vi phạm #{report.id}"
    message = (
        f"Báo cáo của bạn với {report.get_target_type_display()} #{report.target_id} "
        f"đã được xử lý.\nKết quả: {ViolationReport.get_action_label(action)}.\n"
        f"Ghi chú: {report.resolution_note or '(không có)'}"
    )
    try:
        from django.core.mail import send_mail

        send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            [report.reporter.email],
            fail_silently=True,
        )
    except Exception:
        pass


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
        },
    )


def _build_statistics(report_type, period_start, period_end):
    """B3 - Truy vấn CSDL theo loại thống kê đã chọn.

    Dùng ORM tương đương các view SQL đã tạo sẵn trong schema:
    v_document_stats, v_violation_stats, v_daily_activity.
    Nếu app 'documents' chưa tồn tại trong project hiện tại (đang phát
    triển độc lập từng phần), hàm sẽ trả về dữ liệu rỗng/None thay vì lỗi.
    """
    date_range = Q(created_at__date__gte=period_start, created_at__date__lte=period_end)
    result = {"report_type": report_type}

    # ---- Người dùng: luôn khả dụng vì User thuộc app accounts ----
    if report_type in (StatisticsReport.ReportType.USERS, StatisticsReport.ReportType.OVERVIEW):
        result["total_users"] = User.objects.count()
        result["new_users"] = User.objects.filter(date_range).count() if hasattr(User, "created_at") else None

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
                created_at__date__gte=period_start, created_at__date__lte=period_end
            )
            result["document_total"] = Document.objects.count()
            result["document_new"] = doc_qs.count()
            result["document_by_status"] = list(
                Document.objects.values("status").annotate(total=Count("id")).order_by("status")
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

    # Ghi lịch sử xuất báo cáo vào bảng statistics_reports (B5)
    StatisticsReport.objects.create(
        admin=request.user,
        report_type=report_type,
        period_start=period_start,
        period_end=period_end,
        file_path=f"exports/{file_name}",
    )

    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    return response


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
            ws.append([key, ""])
            for row in value:
                ws.append(["", str(row)])
        else:
            ws.append([key, value])

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
            p.drawString(50, y, f"{key}:")
            y -= 18
            for row in value:
                p.drawString(70, y, f"- {row}")
                y -= 16
        else:
            p.drawString(50, y, f"{key}: {value}")
            y -= 18

    p.showPage()
    p.save()
    buffer.seek(0)
    return HttpResponse(buffer.read(), content_type="application/pdf")
