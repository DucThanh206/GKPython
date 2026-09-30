import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from documents.models import Document

from .models import (
    STATISTICS_REPORT_RETENTION_DAYS,
    StatisticsReport,
    ViolationReport,
)

User = get_user_model()


class ViolationAndStatisticsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_directory = tempfile.TemporaryDirectory()
        cls.settings_override = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.settings_override.enable()
        cls.addClassCleanup(cls.settings_override.disable)
        cls.addClassCleanup(cls.media_directory.cleanup)

    def setUp(self):
        self.member = User.objects.create_user(
            username='member',
            password='secret12345',
            email='member@example.com',
        )
        self.admin = User.objects.create_user(
            username='admin',
            password='secret12345',
            email='admin@example.com',
            role=User.Role.ADMIN,
        )
        self.document = Document.objects.create(
            title='Study notes',
            file=SimpleUploadedFile('notes.pdf', b'notes'),
            uploader=self.member,
            status=Document.Status.APPROVED,
        )

    def test_member_can_report_document_and_admin_can_resolve_report(self):
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(
                reverse(
                    'reports:report_violation',
                    args=['document', self.document.pk],
                )
            ).status_code,
            200,
        )
        response = self.client.post(
            reverse(
                'reports:report_violation',
                args=['document', self.document.pk],
            ),
            {'reason': 'This file contains copied material.'},
        )
        report = ViolationReport.objects.get()
        self.assertRedirects(response, self.document.get_absolute_url())
        self.assertEqual(report.status, ViolationReport.Status.PENDING)

        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse('reports:violation_report_list')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse('reports:violation_report_detail', args=[report.pk])
            ).status_code,
            200,
        )
        response = self.client.post(
            reverse('reports:violation_report_detail', args=[report.pk]),
            {'action': ViolationReport.Action.DELETE, 'note': 'Removed after review'},
        )
        self.assertRedirects(response, reverse('reports:violation_report_list'))
        report.refresh_from_db()
        self.document.refresh_from_db()
        self.assertEqual(report.status, ViolationReport.Status.RESOLVED)
        self.assertEqual(self.document.status, Document.Status.REJECTED)
        self.assertEqual(report.handled_by, self.admin)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_warning_emails_content_owner_and_audits_action(self):
        report = ViolationReport.objects.create(
            reporter=self.admin,
            target_type=ViolationReport.TargetType.DOCUMENT,
            target_id=self.document.pk,
            reason='Contains prohibited material.',
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('reports:violation_report_detail', args=[report.pk]),
            {'action': ViolationReport.Action.WARN, 'note': 'Please review the rules.'},
        )

        self.assertRedirects(response, reverse('reports:violation_report_list'))
        report.refresh_from_db()
        self.assertEqual(report.status, ViolationReport.Status.RESOLVED)
        self.assertEqual(report.handled_by, self.admin)
        self.assertIn('Cảnh báo người vi phạm', report.resolution_note)
        self.assertIn('Please review the rules.', report.resolution_note)
        self.assertIsNotNone(report.resolved_at)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('member@example.com', mail.outbox[0].to + mail.outbox[1].to)

    def test_member_cannot_access_admin_report_management(self):
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse('reports:violation_report_list')).status_code,
            403,
        )

    def test_admin_dashboard_and_excel_export_use_real_document_fields(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reports:statistics_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['data']['document_total'], 1)

        response = self.client.get(
            reverse('reports:export_statistics_report'),
            {
                'report_type': StatisticsReport.ReportType.DOCUMENTS,
                'period_start': '2026-01-01',
                'period_end': '2026-12-31',
                'file_format': 'xlsx',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        report = StatisticsReport.objects.get()
        self.assertTrue(default_storage.exists(report.file_path))
        self.assertTrue(report.file_path.startswith('exports/'))
        self.assertEqual(
            report.expires_at,
            report.created_at + timedelta(days=STATISTICS_REPORT_RETENTION_DAYS),
        )

        download = self.client.get(
            reverse('reports:download_statistics_report', args=[report.pk])
        )
        self.assertEqual(download.status_code, 200)
        self.assertIn('attachment;', download['Content-Disposition'])
        self.assertTrue(b''.join(download.streaming_content))
        download.close()

        other_admin = User.objects.create_user(
            username='other-admin',
            password='secret12345',
            role=User.Role.ADMIN,
        )
        self.client.force_login(other_admin)
        self.assertEqual(
            self.client.get(
                reverse('reports:download_statistics_report', args=[report.pk])
            ).status_code,
            404,
        )

    def test_expired_exports_are_removed_with_their_history(self):
        from django.core.files.base import ContentFile

        report = StatisticsReport.objects.create(
            admin=self.admin,
            report_type=StatisticsReport.ReportType.OVERVIEW,
            period_start=timezone.localdate(),
            period_end=timezone.localdate(),
        )
        report.file_path = default_storage.save(
            f'exports/{report.pk}/expired.xlsx',
            ContentFile(b'expired report'),
        )
        report.save(update_fields=['file_path'])
        StatisticsReport.objects.filter(pk=report.pk).update(
            created_at=timezone.now()
            - timedelta(days=STATISTICS_REPORT_RETENTION_DAYS + 1)
        )

        call_command('purge_expired_statistics_reports')

        self.assertFalse(StatisticsReport.objects.filter(pk=report.pk).exists())
        self.assertFalse(default_storage.exists(report.file_path))

    def test_statistics_marks_lifetime_and_period_values_separately(self):
        Document.objects.filter(pk=self.document.pk).update(
            uploaded_at=timezone.make_aware(
                timezone.datetime(2000, 1, 1)
            )
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('reports:statistics_dashboard'),
            {
                'report_type': StatisticsReport.ReportType.DOCUMENTS,
                'period_start': '2026-01-01',
                'period_end': '2026-12-31',
            },
        )

        self.assertEqual(response.context['data']['document_total'], 1)
        self.assertEqual(response.context['data']['document_new'], 0)
        self.assertEqual(response.context['data']['document_by_status_period'], [])

    def test_dashboard_formats_status_breakdowns_as_labels_and_counts(self):
        Document.objects.create(
            title='Pending notes',
            file=SimpleUploadedFile('pending.pdf', b'pending'),
            uploader=self.member,
            status=Document.Status.PENDING,
        )
        ViolationReport.objects.create(
            reporter=self.member,
            target_type=ViolationReport.TargetType.DOCUMENT,
            target_id=self.document.pk,
            reason='Reported in the selected period.',
            status=ViolationReport.Status.RESOLVED,
        )
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('reports:statistics_dashboard'),
            {
                'report_type': StatisticsReport.ReportType.OVERVIEW,
                'period_start': '2026-01-01',
                'period_end': '2026-12-31',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Đã xử lý')
        self.assertContains(response, 'Đã duyệt')
        self.assertContains(response, 'Chờ duyệt')
        self.assertContains(response, 'status-count')
        self.assertNotContains(response, "'status':")
        self.assertEqual(
            response.context['status_breakdowns']['violation_by_status'][0],
            {'label': 'Đã xử lý', 'status': 'resolved', 'total': 1},
        )
