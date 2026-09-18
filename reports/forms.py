from datetime import date, timedelta

from django import forms

from .models import StatisticsReport, ViolationReport


class ViolationReportForm(forms.ModelForm):
    """UC08 - Form nhập lý do báo cáo (Bước 2 trong luồng sự kiện chính).

    `target_type` và `target_id` được truyền sẵn từ view (view chọn đối
    tượng cần báo cáo: tài liệu hoặc bình luận) nên chỉ hiển thị ẩn,
    người dùng chỉ cần nhập `reason`.
    """

    class Meta:
        model = ViolationReport
        fields = ["target_type", "target_id", "reason"]
        widgets = {
            "target_type": forms.HiddenInput(),
            "target_id": forms.HiddenInput(),
            "reason": forms.Textarea(
                attrs={
                    "rows": 5,
                    "maxlength": 1000,
                    "placeholder": "Mô tả nội dung/vi phạm bạn muốn báo cáo...",
                    "class": "form-control",
                }
            ),
        }
        labels = {"reason": "Lý do báo cáo"}

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if len(reason) < 10:
            raise forms.ValidationError(
                "Vui lòng mô tả lý do báo cáo chi tiết hơn (tối thiểu 10 ký tự)."
            )
        return reason


class ViolationHandleForm(forms.Form):
    """UC09 - Form Admin xử lý báo cáo (Bước 3: xóa / giữ / cảnh báo)."""

    action = forms.ChoiceField(
        choices=ViolationReport.Action.choices,
        widget=forms.RadioSelect,
        label="Quyết định xử lý",
    )
    note = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        required=False,
        label="Ghi chú xử lý (tùy chọn)",
    )


class StatisticsFilterForm(forms.Form):
    """UC14 - Chọn loại thống kê & khoảng thời gian (Bước 2)."""

    REPORT_TYPE_CHOICES = StatisticsReport.ReportType.choices

    report_type = forms.ChoiceField(
        choices=REPORT_TYPE_CHOICES,
        initial=StatisticsReport.ReportType.OVERVIEW,
        label="Loại thống kê",
    )
    period_start = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Từ ngày",
    )
    period_end = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Đến ngày",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            # Mặc định: 30 ngày gần nhất
            today = date.today()
            self.fields["period_start"].initial = today - timedelta(days=30)
            self.fields["period_end"].initial = today

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("period_start"), cleaned.get("period_end")
        if start and end and start > end:
            raise forms.ValidationError("'Từ ngày' phải trước hoặc bằng 'Đến ngày'.")
        return cleaned


class ExportReportForm(forms.Form):
    """UC14 - Tùy chọn 'Xuất báo cáo' (Bước 3, nhánh tùy chọn)."""

    FORMAT_CHOICES = (
        ("xlsx", "Excel (.xlsx)"),
        ("pdf", "PDF (.pdf)"),
    )

    report_type = forms.ChoiceField(choices=StatisticsReport.ReportType.choices)
    period_start = forms.DateField(widget=forms.HiddenInput())
    period_end = forms.DateField(widget=forms.HiddenInput())
    file_format = forms.ChoiceField(choices=FORMAT_CHOICES, initial="xlsx")
