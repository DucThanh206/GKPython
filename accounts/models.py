from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model used by member and administrator flows."""

    class Role(models.TextChoices):
        MEMBER = 'member', 'Thành viên'
        ADMIN = 'admin', 'Quản trị viên'

    avatar = models.ImageField('Ảnh đại diện', upload_to='avatars/', blank=True, null=True)
    bio = models.TextField('Giới thiệu', blank=True)
    full_name = models.CharField('Họ và tên', max_length=150, blank=True)
    school = models.CharField('Trường / Khoa', max_length=255, blank=True)
    role = models.CharField(
        'Vai trò', max_length=10, choices=Role.choices, default=Role.MEMBER
    )
    google_id = models.CharField(
        'Google ID', max_length=64, unique=True, null=True, blank=True
    )

    class Meta:
        verbose_name = 'Người dùng'
        verbose_name_plural = 'Người dùng'

    def __str__(self):
        return self.username
