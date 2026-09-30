from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not (
            request.user.is_superuser
            or getattr(request.user, 'role', None) == 'admin'
        ):
            raise PermissionDenied('Yêu cầu quyền quản trị viên.')
        return view_func(request, *args, **kwargs)

    return wrapped
