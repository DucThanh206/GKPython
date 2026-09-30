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
   # Development mặc định in email ra console; production dùng SMTP qua biến môi trường.
   ```

## 2. Phụ thuộc vào app khác (quan trọng)

- `settings.AUTH_USER_MODEL` phải trỏ tới model User của app `accounts`
  (map bảng `users` — có cột `role` ENUM('member','admin') dùng để phân quyền Admin trong `decorators.py`).
- Model `Document` và `Comment` được tra cứu qua registry Django để tránh
  import vòng. Các luồng báo cáo, kiểm duyệt và thống kê đã được nối với app
  `documents` trong project.
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

## 4. Xuất báo cáo (UC14)

Các thư viện `openpyxl` và `reportlab` đã được khai báo trong
`requirements.txt`; cài đặt chúng cùng các phụ thuộc khác bằng
`pip install -r requirements.txt`.

Các tệp xuất được lưu riêng trong `MEDIA_ROOT/exports/`, chỉ Admin tạo báo cáo
mới có thể tải lại. Bản xuất hết hạn sau 90 ngày. Lên lịch chạy lệnh sau mỗi
ngày để xóa tệp và bản ghi đã hết hạn:

```bash
python manage.py purge_expired_statistics_reports
```

Lưu ý: thư mục media cần nằm trên persistent storage được sao lưu; không phục vụ
`media/` trực tiếp qua web server.

## 5. Cấu hình production

Production bắt buộc đặt `APP_ENV=production`, `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, `MEDIA_ROOT`, `EMAIL_HOST` và `ADMIN_EMAILS` (danh sách
email phân tách bằng dấu phẩy). `DJANGO_DEBUG` phải là
`false`. Cơ sở dữ liệu dùng PostgreSQL và cần các biến `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST` (có thể đặt `DB_PORT`, mặc định `5432`). Email SMTP
hỗ trợ `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`,
`EMAIL_USE_SSL` và `DEFAULT_FROM_EMAIL`. Không lưu bí mật trong Git.

Ví dụ chuỗi triển khai sau khi cấu hình môi trường và cài `requirements.txt`:

```bash
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
```

Đặt `STATIC_ROOT` và `MEDIA_ROOT` lên volumes bền vững/được sao lưu; cấu hình
reverse proxy giới hạn request body tối đa theo `MAX_DOCUMENT_UPLOAD_SIZE`
(mặc định 25 MiB) cùng phần overhead multipart. Giới hạn ứng dụng cho phép
PDF, DOC/DOCX, PPT/PPTX, XLS/XLSX, TXT, Markdown và CSV. Bật TLS ở reverse
proxy và thiết lập `DJANGO_CSRF_TRUSTED_ORIGINS` cho các origin HTTPS của hệ
thống. Sao lưu và thử khôi phục cả PostgreSQL lẫn media trước phát hành.
Reverse proxy phải ghi đè `X-Forwarded-Proto` bằng scheme thực của kết nối;
không để client bên ngoài tự gửi giá trị header này tới ứng dụng.

## 6. UC08 đã tích hợp trong trang tài liệu và bình luận

Người dùng đã đăng nhập có thể chọn **Báo cáo vi phạm** trên tài liệu hoặc
**Báo cáo** trên bình luận. Tài khoản quản trị viên xử lý báo cáo tại trang
quản lý báo cáo.

## 7. Điểm khớp với đặc tả (UseCase_UC08_UC09_UC14.docx)

- **UC08**: mỗi bước B1–B6 trong luồng sự kiện chính đều có comment tương
  ứng trực tiếp trong `views.report_violation`.
- **UC09**: 3 hành động "xóa / giữ / cảnh báo" ở Bước 3 được hiện thực trong
  `ViolationReport.apply_action()`. Vì bảng `violation_reports` không có cột
  riêng lưu hành động, hành động được ghi vào `resolution_note` và ánh xạ
  sang `status` (`resolved`/`rejected`).
- **UC14**: `report_type` khớp đúng ENUM `documents/users/downloads/violations/overview`
  của cột `statistics_reports.report_type`. Xuất báo cáo hỗ trợ cả Excel
  (`openpyxl`) và PDF (`reportlab`) đúng như đặc tả "Tạo file báo cáo (PDF/Excel)".

## 8. Hoàn thiện đặc tả nhóm

- Đổi số thứ tự mục/hình từ placeholder (2.3.9, 2.3.10, 2.3.15) sang số thật
  theo thứ tự cuối cùng của nhóm.
- Đối chiếu lại phần "loại thống kê" trong UC14 (`_build_statistics()`) với
  các chỉ số cuối cùng nhóm muốn đưa vào bản đặc tả.
