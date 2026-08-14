from django.conf import settings
from django.db import models
from django.urls import reverse


class Category(models.Model):
    """Danh mục môn học / chủ đề tài liệu, ví dụ: Toán, CNTT, Tiếng Anh..."""
    name = models.CharField('Tên danh mục', max_length=100, unique=True)
    slug = models.SlugField('Slug', max_length=120, unique=True)

    class Meta:
        verbose_name = 'Danh mục'
        verbose_name_plural = 'Danh mục'
        ordering = ['name']

    def __str__(self):
        return self.name


class Document(models.Model):
    """Một tài liệu học tập do người dùng chia sẻ."""
    title = models.CharField('Tiêu đề', max_length=255)
    description = models.TextField('Mô tả', blank=True)
    file = models.FileField('Tệp tài liệu', upload_to='documents/%Y/%m/')
    category = models.ForeignKey(
        Category, verbose_name='Danh mục',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documents',
    )
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='Người đăng',
        on_delete=models.CASCADE, related_name='documents',
    )
    uploaded_at = models.DateTimeField('Ngày đăng', auto_now_add=True)
    download_count = models.PositiveIntegerField('Lượt tải', default=0)

    class Meta:
        verbose_name = 'Tài liệu'
        verbose_name_plural = 'Tài liệu'
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('document_detail', kwargs={'pk': self.pk})
