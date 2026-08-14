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

## Cấu trúc dự án

```
config/         # Cấu hình chính (settings, urls, wsgi)
documents/      # App quản lý tài liệu (model, view, form)
templates/      # Giao diện HTML
static/         # File tĩnh (CSS/JS)
media/          # Tài liệu người dùng tải lên (không commit lên git)
```

## Tính năng đã có (khởi tạo)

- [x] Model `Category`, `Document`
- [x] Đăng nhập / đăng xuất
- [x] Danh sách tài liệu + tìm kiếm theo tiêu đề
- [x] Đăng tài liệu mới (yêu cầu đăng nhập)
- [x] Xem chi tiết & tải xuống tài liệu
- [x] Trang quản trị Django admin

## Việc cần làm tiếp

- [ ] Đăng ký tài khoản (form đăng ký người dùng)
- [ ] Bình luận / đánh giá tài liệu
- [ ] Lọc theo danh mục
- [ ] Đếm lượt tải thực tế khi bấm nút tải
- [ ] Phân quyền (chỉ chủ sở hữu mới sửa/xóa được tài liệu của mình)
