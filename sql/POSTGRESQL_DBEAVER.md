# Dùng PostgreSQL trên Render với DBeaver

DBeaver kết nối tới PostgreSQL trên Render để xem và quản lý dữ liệu. Cấu trúc
bảng của ứng dụng được quản lý bằng Django migrations, không tạo bảng thủ công.

## Kết nối DBeaver

Tạo kết nối PostgreSQL trong DBeaver bằng thông tin External Database URL trên
Render:

- Host: `DB_HOST`
- Port: `DB_PORT` (thường là `5432`)
- Database: `DB_NAME`
- Username: `DB_USER`
- Password: `DB_PASSWORD`
- SSL: `require`

Không lưu thông tin đăng nhập vào Git. DBeaver chạy trên máy cá nhân cần dùng External hostname; ứng dụng chạy trên Render nên dùng Internal Database URL.

## Cấu hình ứng dụng

Đặt các biến sau trong `.env` khi chạy cục bộ hoặc trong Environment của dịch vụ Render:

```text
DB_ENGINE=django.db.backends.postgresql
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=5432
```

Sau khi cài phụ thuộc, tạo/cập nhật bảng và tài khoản quản trị:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

Trên Render, cơ sở dữ liệu PostgreSQL được tạo sẵn; không cần chạy
`sql/schemaThuVien.sql`. Dùng DBeaver để xem dữ liệu sau khi chạy migrations.
