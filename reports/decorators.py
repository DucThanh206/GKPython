"""
Decorator kiểm tra quyền Admin, dùng cho UC09 và UC14 (chỉ Admin mới được
Quản lý báo cáo vi phạm / Thống kê, báo cáo).

Dựa theo cột `users.role` (ENUM 'member', 'admin') trong schemaThuVien.sql.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from accounts.decorators import admin_required


def member_required(view_func):
    """Yêu cầu đã đăng nhập (UC08 - 'Điều kiện trước: Đã đăng nhập')."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Vui lòng đăng nhập để sử dụng chức năng này.")
            return redirect("login")
        return view_func(request, *args, **kwargs)

    return _wrapped
