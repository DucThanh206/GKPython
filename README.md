# EduHub - Website chia sẻ tài liệu học tập

Đồ án giữa kì: xây dựng website cho phép người dùng đăng ký, đăng nhập,
tải lên và tải xuống tài liệu học tập theo danh mục môn học, sử dụng Django.

## Cài đặt

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Truy cập http://127.0.0.1:8000

Để tạo dữ liệu mẫu phục vụ kiểm thử cục bộ, chạy lệnh sau sau khi migrate:

```bash
python manage.py seed_demo_data --password "Choose-A-Local-Test-Password"
```

Lệnh tạo thêm tài khoản `demo_admin` và `demo_member`, danh mục, tài liệu mẫu
(công khai, yêu cầu đăng nhập, chờ kiểm duyệt), bình luận, đánh giá, lượt tải,
báo cáo vi phạm và bản ghi thống kê. Lệnh có thể chạy lại mà không nhân đôi dữ
liệu; mật khẩu chỉ được đặt cho tài khoản demo mới tạo và không bị đổi nếu các
tài khoản đã tồn tại. Chỉ dùng dữ liệu/tài khoản demo trong môi trường local.

### Đăng nhập Google OAuth (tùy chọn)

Tạo OAuth 2.0 Web Client trong Google Cloud Console, thêm callback
`http://127.0.0.1:8000/accounts/google/callback/` vào danh sách redirect URI,
sau đó cấu hình `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` và
`GOOGLE_OAUTH_REDIRECT_URI` trong môi trường chạy ứng dụng. Không lưu các giá
trị này vào Git. Khi chưa cấu hình, đăng nhập bằng tên tài khoản/mật khẩu vẫn
hoạt động bình thường. Nếu email Google trùng với tài khoản có sẵn, hãy đăng
nhập tài khoản đó trước rồi liên kết Google tại trang hồ sơ.

## Cấu trúc dự án

```
config/         # Cấu hình chính (settings, urls, wsgi)
documents/      # App quản lý tài liệu (model, view, form)
templates/      # Giao diện HTML
static/         # File tĩnh (CSS/JS)
media/          # Tài liệu người dùng tải lên (không commit lên git)
```

## Tính năng đã có (khởi tạo)

- [x] Đăng ký, đăng nhập/đăng xuất và cập nhật hồ sơ cá nhân
- [x] Tìm kiếm tài liệu theo từng từ khóa trong tiêu đề, mô tả, môn học và danh mục; duyệt theo danh mục
- [x] Đăng tài liệu theo danh mục có sẵn hoặc tạo danh mục mới; kiểm duyệt và phân quyền hiển thị công khai/yêu cầu đăng nhập
- [x] Hiện nội dung PDF, DOCX và các tệp văn bản TXT/Markdown/CSV trên trang chi tiết
- [x] Ghi nhận lượt xem, lượt tải và danh sách tài liệu đã tải xuống
- [x] Bình luận một chiều, sửa/xóa bình luận của chính mình và đánh giá một lần
- [x] Thư viện cá nhân, yêu thích và chia sẻ liên kết
- [x] Quản lý tài khoản, báo cáo vi phạm và thống kê dành cho quản trị viên
- [x] Xuất thống kê PDF và Excel

## Luồng quản trị

Tài khoản mới có vai trò thành viên. Để cấp quyền quản trị viên, đăng nhập vào
Django admin và đổi trường **Vai trò** của tài khoản thành **Quản trị viên**
(hoặc dùng tài khoản superuser). Tài liệu tải lên ở trạng thái chờ duyệt; quản
trị viên duyệt tại trang **Duyệt tài liệu** trên thanh điều hướng.

Sau khi nạp dữ liệu mẫu, đăng nhập bằng `demo_admin` để duyệt tài liệu và xử lý
báo cáo; `demo_member` dùng để thử các luồng thành viên. Cả hai dùng mật khẩu
được truyền vào `seed_demo_data` khi tạo lần đầu.

Tài liệu yêu cầu đăng nhập chỉ cho thành viên xem nội dung/tải xuống sau khi
đăng nhập. Khách có thể xem trước tài liệu công khai nhưng cần đăng nhập để tải.
Bình luận và đánh giá của khách được giữ trong session và gửi tiếp sau khi hoàn
tất đăng nhập. Tệp tải lên giới hạn 25 MiB và nhận PDF, DOC/DOCX, PPT/PPTX,
XLS/XLSX, TXT, Markdown hoặc CSV.

Trang chi tiết nhúng PDF để đọc trực tiếp, trích xuất nội dung đoạn văn/bảng
của DOCX và hiển thị đầy đủ tệp TXT, Markdown, CSV. Định dạng chưa hỗ trợ
preview cần tải về để mở bằng ứng dụng tương ứng.

Các tệp tài liệu không được phục vụ trực tiếp từ đường dẫn media; tải xuống đi
qua endpoint có kiểm tra trạng thái và quyền. Khi triển khai production, không
cấu hình web server để công khai thư mục `media/documents/`.

## Triển khai production

Ứng dụng giữ cấu hình SQLite và email console cho phát triển cục bộ. Production
cần đặt `APP_ENV=production`, `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, `ADMIN_EMAILS`, `MEDIA_ROOT`, `EMAIL_HOST` và thông tin
PostgreSQL (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`; tùy chọn `DB_PORT`).
SMTP có thể cấu hình qua `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
`EMAIL_USE_TLS`/`EMAIL_USE_SSL` và `DEFAULT_FROM_EMAIL`. Xem
[hướng dẫn triển khai trong reports](./reports/README.md#5-cấu-hình-production)
để biết thêm biến môi trường, HTTPS và vận hành sao lưu.
Tạo `DJANGO_SECRET_KEY` bằng `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
và chuyển secret qua secret manager của môi trường triển khai, không ghi vào repo.

Sau khi cài phụ thuộc và cấu hình môi trường, chạy:

```bash
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py purge_expired_statistics_reports
```

Lệnh purge phải được lên lịch chạy hằng ngày. Đặt media/static trên lưu trữ bền
vững, sao lưu cả media và PostgreSQL, giới hạn kích thước request tại reverse
proxy và kiểm tra khôi phục sao lưu trước khi mở dịch vụ.
