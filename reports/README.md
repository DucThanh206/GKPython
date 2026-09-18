# App `reports` — UC08, UC09, UC14

App Django này hiện thực đầy đủ 3 use case được giao:

| Use case | Chức năng | View | URL name |
|---|---|---|---|
| UC08 | Báo cáo vi phạm | `report_violation` | `reports:report_violation` |
| UC09 | Quản lý báo cáo vi phạm | `violation_report_list`, `violation_report_detail` | `reports:violation_report_list`, `reports:violation_report_detail` |
| UC14 | Thống kê, báo cáo | `statistics_dashboard`, `export_statistics_report` | `reports:statistics_dashboard`, `reports:export_statistics_report` |

## 1. Cài đặt vào project

1. Copy thư mục `reports/` vào thư mục gốc project (ngang hàng với `accounts/`, `documents/`).
2. Trong `config/settings.py`:
   ```python
   INSTALLED_APPS = [
       ...
       "accounts",
       "documents",
       "reports",
   ]
   ```
3. Trong `config/urls.py`:
   ```python
   urlpatterns = [
       ...
       path("reports/", include("reports.urls")),
   ]
   ```
4. Cấu hình email admin (dùng để UC08 "gửi thông báo cho Admin"):
   ```python
   ADMINS = [("Admin", "admin@example.com")]
   DEFAULT_FROM_EMAIL = "no-reply@thuvien.com"
   # Dev: in email ra console thay vì gửi thật
   EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
   ```

## 2. Phụ thuộc vào app khác (quan trọng)

- `settings.AUTH_USER_MODEL` phải trỏ tới model User của app `accounts`
  (map bảng `users` — có cột `role` ENUM('member','admin') dùng để phân quyền Admin trong `decorators.py`).
- Model `Document` và `Comment` được tham chiếu **lỏng** qua
  `django.apps.apps.get_model("documents", "Document"/"Comment")` — nếu app
  `documents` của bạn cùng nhóm chưa sẵn sàng, các chức năng liên quan (xem
  chi tiết đối tượng bị báo cáo, gỡ tài liệu vi phạm, thống kê tài liệu/lượt
  tải) sẽ tự động trả về "không có dữ liệu" thay vì lỗi crash — bạn có thể
  phát triển độc lập và tích hợp sau.
- Cần base template `templates/base.html` (đã có sẵn theo cấu trúc project) với các block `title`, `content`.

## 3. Database

- Bảng `violation_reports` và `statistics_reports` đã có sẵn trong
  `schemaThuVien.sql`. Migration `0001_initial.py` được viết để **khớp
  chính xác** với schema đó (tên bảng, tên cột, index).
- Nếu bạn chạy `schemaThuVien.sql` để tạo bảng trước, hãy đánh dấu migration
  là đã áp dụng mà không chạy SQL tạo bảng lại:
  ```bash
  python manage.py migrate reports --fake-initial
  ```
- Nếu để Django tự tạo bảng qua migration (không chạy phần `CREATE TABLE
  violation_reports/statistics_reports` trong file .sql), chạy bình thường:
  ```bash
  python manage.py migrate reports
  ```

## 4. Cài thêm thư viện xuất báo cáo (UC14)

```bash
pip install openpyxl reportlab
```
Thêm vào `requirements.txt`:
```
openpyxl>=3.1
reportlab>=4.0
```

## 5. Cách gọi UC08 từ trang tài liệu / bình luận (do teammate phụ trách `documents` tích hợp)

```html
<!-- Trong template chi tiết tài liệu -->
<a href="{% url 'reports:report_violation' 'document' document.id %}" class="btn btn-outline-danger">
  Báo cáo vi phạm
</a>

<!-- Trong template bình luận -->
<a href="{% url 'reports:report_violation' 'comment' comment.id %}" class="btn btn-sm btn-link text-danger">
  Báo cáo
</a>
```

## 6. Điểm khớp với đặc tả (UseCase_UC08_UC09_UC14.docx)

- **UC08**: mỗi bước B1–B6 trong luồng sự kiện chính đều có comment tương
  ứng trực tiếp trong `views.report_violation`.
- **UC09**: 3 hành động "xóa / giữ / cảnh báo" ở Bước 3 được hiện thực trong
  `ViolationReport.apply_action()`. Vì bảng `violation_reports` không có cột
  riêng lưu hành động, hành động được ghi vào `resolution_note` và ánh xạ
  sang `status` (`resolved`/`rejected`).
- **UC14**: `report_type` khớp đúng ENUM `documents/users/downloads/violations/overview`
  của cột `statistics_reports.report_type`. Xuất báo cáo hỗ trợ cả Excel
  (`openpyxl`) và PDF (`reportlab`) đúng như đặc tả "Tạo file báo cáo (PDF/Excel)".

## 7. Việc còn cần làm khi merge vào file .docx chung

- Đổi số thứ tự mục/hình từ placeholder (2.3.9, 2.3.10, 2.3.15) sang số thật
  theo thứ tự cuối cùng của nhóm.
- Đối chiếu lại phần "loại thống kê" trong UC14 (`_build_statistics()`) với
  đúng những chỉ số mà `documents` app của nhóm thực sự có (view_count,
  download_count, ...) trước khi chốt bản đặc tả.
