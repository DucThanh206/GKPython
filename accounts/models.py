from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model - mở rộng từ AbstractUser để sau này dễ thêm field
    (avatar, bio, số điện thoại...) mà không phải đổi migration giữa chừng."""
    avatar = models.ImageField('Ảnh đại diện', upload_to='avatars/', blank=True, null=True)
    bio = models.TextField('Giới thiệu', blank=True)

    class Meta:
        verbose_name = 'Người dùng'
        verbose_name_plural = 'Người dùng'

    def __str__(self):
        return self.username
