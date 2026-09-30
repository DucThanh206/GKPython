from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.utils import timezone

from documents.models import (
    Category,
    Comment,
    Document,
    Download,
    PersonalLibrary,
    Rating,
)
from reports.models import StatisticsReport, ViolationReport


class Command(BaseCommand):
    help = 'Create repeatable local demo users and sample data for system testing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            required=True,
            help='Password assigned to newly created demo accounts (minimum 10 characters).',
        )

    def handle(self, *args, **options):
        password = options['password']
        if len(password) < 10:
            raise CommandError('The demo password must contain at least 10 characters.')

        User = get_user_model()
        admin, admin_created = User.objects.get_or_create(
            username='demo_admin',
            defaults={
                'email': 'demo-admin@example.test',
                'full_name': 'EduHub Demo Admin',
                'role': User.Role.ADMIN,
                'is_staff': True,
            },
        )
        member, member_created = User.objects.get_or_create(
            username='demo_member',
            defaults={
                'email': 'demo-member@example.test',
                'full_name': 'EduHub Demo Member',
                'role': User.Role.MEMBER,
            },
        )
        for user, created in ((admin, admin_created), (member, member_created)):
            if created:
                user.set_password(password)
                user.save(update_fields=['password'])

        category_specs = (
            ('Toán học', 'toan-hoc'),
            ('Tin học', 'tin-hoc'),
            ('Tiếng Anh', 'tieng-anh'),
        )
        categories = {
            name: Category.objects.get_or_create(name=name, defaults={'slug': slug})[0]
            for name, slug in category_specs
        }

        documents = {}
        document_specs = (
            (
                'Đại số tuyến tính — tài liệu mẫu',
                'Tài liệu công khai để kiểm thử tìm kiếm, xem, tải xuống và đánh giá.',
                'Đại số tuyến tính',
                categories['Toán học'],
                Document.Visibility.PUBLIC,
                Document.Status.APPROVED,
            ),
            (
                'Lập trình Python — chỉ thành viên',
                'Tài liệu yêu cầu đăng nhập để kiểm thử quyền xem và tải xuống.',
                'Lập trình Python',
                categories['Tin học'],
                Document.Visibility.LOGIN,
                Document.Status.APPROVED,
            ),
            (
                'Bài tập tiếng Anh — chờ duyệt',
                'Tài liệu mẫu ở trạng thái chờ quản trị viên kiểm duyệt.',
                'Tiếng Anh',
                categories['Tiếng Anh'],
                Document.Visibility.PUBLIC,
                Document.Status.PENDING,
            ),
        )
        for title, description, subject, category, visibility, status in document_specs:
            document, created = Document.objects.get_or_create(
                title=title,
                uploader=member,
                defaults={
                    'description': description,
                    'subject': subject,
                    'category': category,
                    'visibility': visibility,
                    'status': status,
                },
            )
            if created:
                document.file.save(
                    f'{category.slug}-demo.txt',
                    ContentFile(
                        f'{title}\n\n{description}\n'.encode('utf-8'),
                    ),
                    save=True,
                )
            documents[title] = document

        public_document = documents['Đại số tuyến tính — tài liệu mẫu']
        private_document = documents['Lập trình Python — chỉ thành viên']

        Comment.objects.get_or_create(
            document=public_document,
            user=member,
            defaults={'content': 'Tài liệu mẫu để kiểm thử bình luận.'},
        )
        Rating.objects.get_or_create(
            document=public_document,
            user=member,
            defaults={'stars': 5},
        )

        downloaded_at = timezone.now()
        Download.objects.get_or_create(
            document=public_document,
            user=member,
            defaults={'downloaded_at': downloaded_at, 'ip_address': '127.0.0.1'},
        )
        PersonalLibrary.objects.get_or_create(
            document=public_document,
            user=member,
            entry_type=PersonalLibrary.EntryType.DOWNLOADED,
        )
        PersonalLibrary.objects.get_or_create(
            document=private_document,
            user=member,
            entry_type=PersonalLibrary.EntryType.FAVORITE,
        )

        ViolationReport.objects.get_or_create(
            reporter=member,
            target_type=ViolationReport.TargetType.DOCUMENT,
            target_id=public_document.pk,
            defaults={
                'reason': 'Báo cáo mẫu để kiểm thử quy trình xử lý vi phạm.',
            },
        )
        StatisticsReport.objects.get_or_create(
            admin=admin,
            report_type=StatisticsReport.ReportType.OVERVIEW,
            period_start=timezone.localdate() - timedelta(days=30),
            period_end=timezone.localdate(),
            defaults={'file_path': ''},
        )

        self.stdout.write(self.style.SUCCESS('Demo database records are ready.'))
        self.stdout.write('Admin account: demo_admin')
        self.stdout.write('Member account: demo_member')
        if admin_created or member_created:
            self.stdout.write('The supplied --password was set for newly created demo accounts.')
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Both demo accounts already existed; their passwords were not changed.'
                )
            )
        self.stdout.write('Sample documents: 2 approved and 1 pending moderation.')
