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

    class Status(models.TextChoices):
        PENDING = 'pending', 'Chờ duyệt'
        APPROVED = 'approved', 'Đã duyệt'
        REJECTED = 'rejected', 'Đã gỡ'

    class Visibility(models.TextChoices):
        PUBLIC = 'public', 'Công khai'
        LOGIN = 'require_login', 'Yêu cầu đăng nhập'

    title = models.CharField('Tiêu đề', max_length=255)
    description = models.TextField('Mô tả', blank=True)
    file = models.FileField('Tệp tài liệu', upload_to='documents/%Y/%m/')
    subject = models.CharField('Môn học / chủ đề', max_length=150, blank=True)
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
    view_count = models.PositiveIntegerField('Lượt xem', default=0)
    visibility = models.CharField(
        'Chế độ hiển thị',
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    status = models.CharField(
        'Trạng thái kiểm duyệt',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    class Meta:
        verbose_name = 'Tài liệu'
        verbose_name_plural = 'Tài liệu'
        ordering = ['-uploaded_at']
        indexes = [models.Index(fields=['status', 'uploaded_at'])]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('document_detail', kwargs={'pk': self.pk})

    @property
    def average_rating(self):
        result = self.ratings.aggregate(average=models.Avg('stars'))
        return result['average'] or 0


class Comment(models.Model):
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='comments'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments'
    )
    content = models.TextField('Bình luận')
    is_edited = models.BooleanField('Đã chỉnh sửa', default=False)
    is_deleted = models.BooleanField('Đã xóa', default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user}: {self.content[:50]}'


class Rating(models.Model):
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='ratings'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ratings'
    )
    stars = models.PositiveSmallIntegerField('Số sao')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'user'], name='unique_rating_per_user_document'
            ),
            models.CheckConstraint(
                condition=models.Q(stars__gte=1, stars__lte=5),
                name='rating_stars_between_1_and_5',
            ),
        ]

    def __str__(self):
        return f'{self.stars}/5 — {self.document}'


class Download(models.Model):
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='downloads'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_downloads',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    downloaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-downloaded_at']
        indexes = [models.Index(fields=['document', 'downloaded_at'])]


class DocumentView(models.Model):
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='views'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_views',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)


class PersonalLibrary(models.Model):
    class EntryType(models.TextChoices):
        DOWNLOADED = 'downloaded', 'Đã tải xuống'
        FAVORITE = 'favorite', 'Yêu thích'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='library_entries'
    )
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='library_entries'
    )
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'document', 'entry_type'],
                name='unique_library_entry_per_user_document_type',
            )
        ]
        ordering = ['-created_at']


class Share(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shares'
    )
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='shares'
    )
    platform = models.CharField(max_length=50)
    share_link = models.URLField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
