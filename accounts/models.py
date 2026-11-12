import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models


def _google_drive_token_cipher():
    key = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(key))


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


class GoogleDriveConnection(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_drive_connection',
    )
    google_email = models.EmailField()
    encrypted_refresh_token = models.TextField()
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_refresh_token(self, refresh_token):
        self.encrypted_refresh_token = _google_drive_token_cipher().encrypt(
            refresh_token.encode('utf-8')
        ).decode('ascii')

    def get_refresh_token(self):
        try:
            return _google_drive_token_cipher().decrypt(
                self.encrypted_refresh_token.encode('ascii')
            ).decode('utf-8')
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise ValueError('Google Drive credential could not be decrypted.') from exc

    def __str__(self):
        return f'{self.user}: {self.google_email}'


class GoogleDriveDocument(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_drive_documents',
    )
    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.CASCADE,
        related_name='google_drive_copies',
    )
    drive_file_id = models.CharField(max_length=255)
    web_view_link = models.URLField(max_length=2048)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'document'],
                name='unique_google_drive_copy_per_user_document',
            )
        ]

    def __str__(self):
        return f'{self.user}: {self.document}'
