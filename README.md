# EduHub - Website chia sẻ tài liệu học tập
Đồ án giữa kì: website chia sẻ tài liệu học tập theo danh mục môn học, xây dựng bằng Django. Người dùng có thể đăng ký, đăng nhập, tải tài liệu lên và tải tài liệu về.

## Database

Khi chạy local, ứng dụng mặc định dùng SQLite tại `db.sqlite3`. Database, media và dữ liệu catalog không được đóng gói trong Git; sau khi clone, hãy migrate và tạo dữ liệu mẫu hoặc nhập catalog theo hướng dẫn bên dưới. Lệnh nhập catalog tạo tài liệu TXT chứa metadata (tác giả, nhà xuất bản, giấy phép và liên kết tới tài nguyên gốc), không tải bản sách gốc về.

## Cài đặt

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Truy cập http://127.0.0.1:8000

### Tạo dữ liệu mẫu

Để tạo tài khoản `demo_admin`, `demo_member` cùng tài liệu và bản ghi mẫu phục vụ
kiểm thử các luồng chính, chạy sau khi migrate:

```bash
python manage.py seed_demo_data --password "Choose-A-Local-Test-Password"
```

Mật khẩu phải có ít nhất 10 ký tự và chỉ được đặt khi tài khoản demo mới được
tạo; lệnh không đổi mật khẩu tài khoản đã tồn tại.

### Nhập catalog Open Textbook Library

Lấy bản CSV từ [Open Textbook Library Discovery](https://open.umn.edu/opentextbooks/discovery)
và đặt tại `data/open_textbook_library.csv` (hoặc truyền đường dẫn khác bằng
`--csv`). Sau khi migrate, chạy:

```bash
python manage.py import_open_textbooks --password "Choose-A-Local-Test-Password"
```

Lệnh tạo `demo_admin`, các tài khoản `demo_member1` đến `demo_member5` và tài liệu
TXT từ metadata catalog. Dùng `--limit 100` để chỉ nhập tối đa 100 bản ghi.
Mật khẩu demo phải có ít nhất 10 ký tự và chỉ được đặt cho tài khoản mới tạo;
hãy giữ CSV, database và media ở local hoặc trong kho lưu trữ phù hợp, không đưa
thông tin đăng nhập hay dữ liệu nhạy cảm lên Git.

### Dùng PostgreSQL Render hiện có khi chạy local

Để ứng dụng local dùng PostgreSQL thay vì `db.sqlite3`, cấu hình các biến sau
trong file `.env`. Lấy thông tin từ **External Database URL** của PostgreSQL trên Render:

```text
DB_ENGINE=django.db.backends.postgresql
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=5432
```

`config/settings.py` tự đọc `.env`; khi các biến này có mặt, lệnh quản trị và
ứng dụng Django sẽ dùng PostgreSQL. Chạy `python manage.py migrate` nếu còn
migration chưa áp dụng, rồi `python manage.py runserver`. Cấu hình này không
tự chuyển dữ liệu từ `db.sqlite3` sang PostgreSQL; xem hướng dẫn
[PostgreSQL và DBeaver](./sql/POSTGRESQL_DBEAVER.md) nếu cần chuyển dữ liệu.

## Cấu trúc dự án

```
accounts/       # Tài khoản, hồ sơ và xác thực
config/         # Cấu hình chính (settings, urls, wsgi)
documents/      # Tài liệu, danh mục và kiểm duyệt
reports/        # Báo cáo vi phạm và thống kê
templates/      # Giao diện HTML
data/           # CSV catalog cục bộ (không bắt buộc)
media/          # Tệp tài liệu và báo cáo phát sinh
sql/            # Hướng dẫn PostgreSQL/DBeaver và schema tham khảo
```

## Tính năng

- [x] Đăng ký, đăng nhập/đăng xuất và cập nhật hồ sơ cá nhân
- [x] Đăng nhập Google tùy chọn và liên kết tài khoản Google từ hồ sơ
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
báo cáo; `demo_member` dùng để thử các luồng thành viên. Khi nhập catalog, các
tài khoản `demo_member1` đến `demo_member5` được tạo để làm người đăng tài liệu.
Mật khẩu được truyền qua `--password` chỉ áp dụng cho tài khoản mới tạo; lệnh
không đặt lại mật khẩu của tài khoản đã có.

### Đăng nhập Google (tùy chọn)

Tạo OAuth 2.0 Web Client trong Google Cloud Console, thêm callback
`http://127.0.0.1:8000/accounts/google/callback/` vào danh sách redirect URI,
sau đó cấu hình `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` và
`GOOGLE_OAUTH_REDIRECT_URI` trong môi trường chạy ứng dụng. Không lưu các giá
trị này vào Git. Khi chưa cấu hình, đăng nhập bằng tên tài khoản/mật khẩu vẫn
hoạt động bình thường. Nếu email Google trùng với tài khoản có sẵn, hãy đăng
nhập tài khoản đó trước rồi liên kết Google tại trang hồ sơ.

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
PostgreSQL (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`; tùy chọn `DB_PORT`,
mặc định `5432`). Production mặc định dùng PostgreSQL; local mặc định vẫn dùng
SQLite. Xem [hướng dẫn PostgreSQL và DBeaver](./sql/POSTGRESQL_DBEAVER.md) để
kết nối và chuyển dữ liệu SQLite hiện có.
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