from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Thông tin bổ sung', {'fields': ('avatar', 'bio')}),
    )
    list_display = ('username', 'email', 'is_staff', 'is_active', 'date_joined')
