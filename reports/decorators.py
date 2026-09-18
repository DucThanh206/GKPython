"""
Decorator kiểm tra quyền Admin, dùng cho UC09 và UC14 (chỉ Admin mới được
Quản lý báo cáo vi phạm / Thống kê, báo cáo).

Dựa theo cột `users.role` (ENUM 'member', 'admin') trong schemaThuVien.sql.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def admin_required(view_func):
    """Chỉ cho phép user có role == 'admin' truy cập."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        role = getattr(request.user, "role", None)
        is_admin = role == "admin" or request.user.is_superuser
        if not is_admin:
            messages.error(request, "Bạn không có quyền truy cập chức năng này.")
            raise PermissionDenied("Yêu cầu quyền Admin.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def member_required(view_func):
    """Yêu cầu đã đăng nhập (UC08 - 'Điều kiện trước: Đã đăng nhập')."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Vui lòng đăng nhập để sử dụng chức năng này.")
            return redirect("accounts:login")
        return view_func(request, *args, **kwargs)

    return _wrapped
