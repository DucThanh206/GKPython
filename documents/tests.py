import tempfile
from io import BytesIO
from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from reportlab.pdfgen import canvas

from accounts.google_drive import GoogleDriveError
from accounts.models import GoogleDriveConnection, GoogleDriveDocument
from .forms import DocumentUploadForm
from .models import (
    Category,
    Comment,
    Document,
    DocumentView,
    Download,
    PersonalLibrary,
    Rating,
)

User = get_user_model()


def make_pdf(text):
    content = BytesIO()
    pdf = canvas.Canvas(content)
    pdf.drawString(72, 720, text)
    pdf.save()
    return content.getvalue()


class DocumentFlowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_directory = tempfile.TemporaryDirectory()
        cls.settings_override = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.settings_override.enable()
        cls.addClassCleanup(cls.settings_override.disable)
        cls.addClassCleanup(cls.media_directory.cleanup)

    def setUp(self):
        self.user = User.objects.create_user(username='member', password='secret12345')
        self.other_user = User.objects.create_user(
            username='other', password='secret12345'
        )
        self.category = Category.objects.create(name='Toán', slug='toan')
        self.document = Document.objects.create(
            title='Đại số cơ bản',
            description='Tài liệu toán đại số',
            subject='Toán',
            category=self.category,
            file=SimpleUploadedFile('algebra.pdf', b'example document'),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )

    def test_search_and_category_filter_show_only_published_documents(self):
        Document.objects.create(
            title='Tài liệu chờ duyệt',
            file=SimpleUploadedFile('pending.pdf', b'pending'),
            uploader=self.user,
        )
        response = self.client.get(
            reverse('document_list'), {'q': 'đại số', 'category': 'toan'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Đại số cơ bản')
        self.assertNotContains(response, 'Tài liệu chờ duyệt')

    def test_pending_upload_is_hidden_from_library_even_for_uploader(self):
        Document.objects.create(
            title='Tài liệu chưa được duyệt',
            file=SimpleUploadedFile('unreviewed.pdf', b'unreviewed'),
            uploader=self.user,
            status=Document.Status.PENDING,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('document_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.document.title)
        self.assertNotContains(response, 'Tài liệu chưa được duyệt')

    def test_search_matches_partial_non_contiguous_title_terms(self):
        document = Document.objects.create(
            title='Tài liệu tiếng Anh giao tiếp',
            file=SimpleUploadedFile('english.pdf', b'english'),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )

        response = self.client.get(reverse('document_list'), {'q': 'tiếng giao tiếp'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, document.title)

    def test_guest_view_is_recorded_and_private_document_is_gated(self):
        self.client.get(self.document.get_absolute_url())
        self.document.refresh_from_db()
        self.assertEqual(self.document.view_count, 1)
        self.assertEqual(DocumentView.objects.filter(document=self.document).count(), 1)

        self.document.visibility = Document.Visibility.LOGIN
        self.document.save(update_fields=['visibility'])
        response = self.client.get(self.document.get_absolute_url())
        self.assertContains(response, 'Cần đăng nhập')
        self.document.refresh_from_db()
        self.assertEqual(self.document.view_count, 1)

    def test_detail_page_routes_docx_and_text_files_to_google_docs(self):
        document = Document.objects.create(
            title='Word content sample',
            file=SimpleUploadedFile('content.docx', b'docx-content'),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )
        self.client.force_login(self.other_user)

        response = self.client.get(document.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mở bằng Google Docs')
        self.assertContains(response, reverse('document_open', args=[document.pk]))

        text_document = Document.objects.create(
            title='Text content sample',
            file=SimpleUploadedFile('text-sample.txt', b'text-content'),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )
        text_response = self.client.get(text_document.get_absolute_url())
        self.assertContains(text_response, 'Mở bằng Google Docs')

    def test_pdf_open_route_opens_inline_in_browser_for_member_and_admin(self):
        approved_document = Document.objects.create(
            title='Approved PDF',
            file=SimpleUploadedFile('selectable.pdf', make_pdf('PDF content')),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )
        pending_document = Document.objects.create(
            title='Pending PDF',
            file=SimpleUploadedFile('pending-selectable.pdf', make_pdf('Pending content')),
            uploader=self.user,
            status=Document.Status.PENDING,
        )
        admin = User.objects.create_user(
            username='pdf-reviewer',
            password='secret12345',
            role=User.Role.ADMIN,
        )

        self.client.force_login(self.other_user)
        member_response = self.client.get(
            reverse('document_open', args=[approved_document.pk]),
            follow=True,
        )
        self.assertEqual(member_response.status_code, 200)
        self.assertEqual(member_response['Content-Type'], 'application/pdf')
        self.assertEqual(member_response['Content-Disposition'], 'inline')
        member_response.close()

        self.client.force_login(admin)
        admin_response = self.client.get(
            reverse('document_open', args=[pending_document.pk]),
            follow=True,
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response['Content-Type'], 'application/pdf')
        self.assertEqual(admin_response['Content-Disposition'], 'inline')
        admin_response.close()

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
    )
    def test_open_route_imports_each_supported_non_pdf_to_matching_google_app(self):
        connection = GoogleDriveConnection(
            user=self.other_user,
            google_email='drive@example.com',
        )
        connection.set_refresh_token('refresh-token')
        connection.save()
        file_types = {
            '.csv': 'application/vnd.google-apps.spreadsheet',
            '.xls': 'application/vnd.google-apps.spreadsheet',
            '.xlsx': 'application/vnd.google-apps.spreadsheet',
            '.doc': 'application/vnd.google-apps.document',
            '.docx': 'application/vnd.google-apps.document',
            '.md': 'application/vnd.google-apps.document',
            '.txt': 'application/vnd.google-apps.document',
            '.ppt': 'application/vnd.google-apps.presentation',
            '.pptx': 'application/vnd.google-apps.presentation',
        }
        upload_links = [
            (f'drive-id-{index}', f'https://docs.google.com/document/d/{index}/edit')
            for index in range(len(file_types))
        ]
        self.client.force_login(self.other_user)

        with (
            patch('documents.views.refresh_access_token', return_value='access-token'),
            patch('documents.views.get_existing_file_link', return_value=None),
            patch('documents.views.upload_file', side_effect=upload_links) as upload,
        ):
            for index, (extension, target_mime_type) in enumerate(file_types.items()):
                with self.subTest(extension=extension):
                    document = Document.objects.create(
                        title='Workspace import',
                        file=SimpleUploadedFile(
                            f'workspace{extension}',
                            b'document-content',
                        ),
                        uploader=self.user,
                        status=Document.Status.APPROVED,
                    )
                    response = self.client.post(
                        reverse('document_open', args=[document.pk])
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertIn('docs.google.com', response['Location'])
                    self.assertEqual(
                        upload.call_args_list[index].args[1],
                        f'Workspace import{extension}',
                    )
                    self.assertEqual(
                        upload.call_args_list[index].args[3],
                        target_mime_type,
                    )
                    self.assertTrue(
                        GoogleDriveDocument.objects.filter(
                            user=self.other_user,
                            document=document,
                        ).exists()
                    )

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
    )
    def test_open_route_reuses_existing_google_drive_copy(self):
        document = Document.objects.create(
            title='Reused copy',
            file=SimpleUploadedFile('reused.docx', b'document-content'),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )
        connection = GoogleDriveConnection(
            user=self.other_user,
            google_email='drive@example.com',
        )
        connection.set_refresh_token('refresh-token')
        connection.save()
        GoogleDriveDocument.objects.create(
            user=self.other_user,
            document=document,
            drive_file_id='existing-drive-id',
            web_view_link='https://docs.google.com/document/d/existing-drive-id/edit',
        )
        self.client.force_login(self.other_user)

        with (
            patch('documents.views.refresh_access_token', return_value='access-token'),
            patch(
                'documents.views.get_existing_file_link',
                return_value='https://docs.google.com/document/d/existing-drive-id/edit',
            ) as get_link,
            patch('documents.views.upload_file') as upload,
        ):
            response = self.client.post(reverse('document_open', args=[document.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            'https://docs.google.com/document/d/existing-drive-id/edit',
        )
        get_link.assert_called_once_with('access-token', 'existing-drive-id')
        upload.assert_not_called()

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
    )
    def test_workspace_open_shows_actionable_drive_api_configuration_error(self):
        document = Document.objects.create(
            title='Drive API error',
            file=SimpleUploadedFile('api-error.docx', b'document-content'),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )
        connection = GoogleDriveConnection(
            user=self.other_user,
            google_email='drive@example.com',
        )
        connection.set_refresh_token('refresh-token')
        connection.save()
        self.client.force_login(self.other_user)

        with (
            patch('documents.views.refresh_access_token', return_value='access-token'),
            patch('documents.views.get_existing_file_link', return_value=None),
            patch(
                'documents.views.upload_file',
                side_effect=GoogleDriveError(
                    'Drive API is disabled',
                    status_code=403,
                    reason='accessNotConfigured',
                ),
            ),
        ):
            response = self.client.post(
                reverse('document_open', args=[document.pk]),
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Google Drive API chưa được bật')

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
    )
    def test_admin_can_import_pending_office_document_to_google_docs(self):
        document = Document.objects.create(
            title='Pending office review',
            file=SimpleUploadedFile('pending-review.docx', b'document-content'),
            uploader=self.user,
            status=Document.Status.PENDING,
        )
        admin = User.objects.create_user(
            username='workspace-reviewer',
            password='secret12345',
            role=User.Role.ADMIN,
        )
        connection = GoogleDriveConnection(
            user=admin,
            google_email='reviewer@example.com',
        )
        connection.set_refresh_token('refresh-token')
        connection.save()
        self.client.force_login(admin)

        with (
            patch('documents.views.refresh_access_token', return_value='access-token'),
            patch('documents.views.get_existing_file_link', return_value=None),
            patch(
                'documents.views.upload_file',
                return_value=(
                    'pending-drive-id',
                    'https://docs.google.com/document/d/pending-drive-id/edit',
                ),
            ) as upload,
        ):
            response = self.client.post(
                reverse('document_open', args=[document.pk])
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            'https://docs.google.com/document/d/pending-drive-id/edit',
        )
        self.assertEqual(
            upload.call_args.args[3],
            'application/vnd.google-apps.document',
        )

    def test_open_route_requires_a_post_or_oauth_resume_for_workspace_imports(self):
        document = Document.objects.create(
            title='Protected opening action',
            file=SimpleUploadedFile('protected.docx', b'document-content'),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )
        connection = GoogleDriveConnection(
            user=self.other_user,
            google_email='drive@example.com',
        )
        connection.set_refresh_token('refresh-token')
        connection.save()
        self.client.force_login(self.other_user)

        with patch('documents.views.upload_file') as upload:
            response = self.client.get(reverse('document_open', args=[document.pk]))

        self.assertRedirects(response, document.get_absolute_url())
        upload.assert_not_called()

    def test_opening_workspace_document_without_connection_starts_drive_oauth(self):
        document = Document.objects.create(
            title='Connect before opening',
            file=SimpleUploadedFile('connect.docx', b'document-content'),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )
        self.client.force_login(self.other_user)

        response = self.client.post(reverse('document_open', args=[document.pk]))

        self.assertRedirects(
            response,
            f"{reverse('google_drive_connect')}?"
            f"{urlencode({'next': reverse('document_open', args=[document.pk])})}",
            fetch_redirect_response=False,
        )

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
    )
    def test_oauth_resume_opens_workspace_document_once(self):
        document = Document.objects.create(
            title='Resume after Google consent',
            file=SimpleUploadedFile('resume.docx', b'document-content'),
            uploader=self.user,
            status=Document.Status.APPROVED,
        )
        connection = GoogleDriveConnection(
            user=self.other_user,
            google_email='drive@example.com',
        )
        connection.set_refresh_token('refresh-token')
        connection.save()
        self.client.force_login(self.other_user)
        session = self.client.session
        session['google_drive_resume_open_document_id'] = document.pk
        session.save()

        with (
            patch('documents.views.refresh_access_token', return_value='access-token'),
            patch('documents.views.get_existing_file_link', return_value=None),
            patch(
                'documents.views.upload_file',
                return_value=(
                    'resumed-drive-id',
                    'https://docs.google.com/document/d/resumed-drive-id/edit',
                ),
            ),
        ):
            response = self.client.get(reverse('document_open', args=[document.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            'https://docs.google.com/document/d/resumed-drive-id/edit',
        )
        self.assertNotIn('google_drive_resume_open_document_id', self.client.session)

    def test_pdf_preview_is_inline_and_private_preview_requires_login(self):
        response = self.client.get(
            reverse('document_preview', args=[self.document.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(response['Content-Disposition'], 'inline')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        response.close()

        self.document.visibility = Document.Visibility.LOGIN
        self.document.save(update_fields=['visibility'])
        response = self.client.get(reverse('document_preview', args=[self.document.pk]))
        self.assertRedirects(
            response,
            f'/login/?next={reverse("document_preview", args=[self.document.pk])}',
        )

    def test_uploaded_file_cannot_be_fetched_from_public_media_path(self):
        media_url = f'/media/{self.document.file.name}'
        self.assertEqual(self.client.get(media_url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse('document_download', args=[self.document.pk])).status_code,
            302,
        )

    def test_public_document_guest_sees_login_prompt_instead_of_download_link(self):
        response = self.client.get(self.document.get_absolute_url())

        self.assertContains(response, 'Đăng nhập để tải tài liệu')
        self.assertNotContains(
            response,
            reverse('document_download', args=[self.document.pk]),
        )

    def test_upload_rejects_unsupported_extension_and_oversized_file(self):
        self.client.force_login(self.user)
        form_data = {
            'title': 'Tài liệu không hợp lệ',
            'description': '',
            'subject': 'Vật lý',
            'category': self.category.pk,
            'visibility': Document.Visibility.PUBLIC,
        }

        response = self.client.post(
            reverse('document_upload'),
            {
                **form_data,
                'file': SimpleUploadedFile('payload.exe', b'bad'),
            },
        )
        self.assertContains(response, 'Định dạng tệp không được hỗ trợ')
        self.assertFalse(Document.objects.filter(title=form_data['title']).exists())

        with self.settings(MAX_DOCUMENT_UPLOAD_SIZE=3):
            response = self.client.post(
                reverse('document_upload'),
                {
                    **form_data,
                    'file': SimpleUploadedFile('large.pdf', b'four'),
                },
            )
        self.assertContains(response, 'Tệp vượt quá giới hạn')
        self.assertFalse(Document.objects.filter(title=form_data['title']).exists())

    def test_guest_comment_is_restored_after_login(self):
        detail_url = self.document.get_absolute_url()
        response = self.client.post(
            reverse('document_interaction', args=[self.document.pk]),
            {'action': 'comment', 'content': 'Rất hữu ích'},
        )
        self.assertRedirects(response, f'/login/?next={detail_url}')
        self.assertFalse(Comment.objects.exists())

        response = self.client.post(
            f"/login/?next={detail_url}",
            {'username': 'other', 'password': 'secret12345', 'next': detail_url},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, detail_url)
        self.client.get(response.url)
        comment = Comment.objects.get()
        self.assertEqual(comment.content, 'Rất hữu ích')
        self.assertEqual(comment.user, self.other_user)

    def test_rating_can_only_be_submitted_once(self):
        self.client.force_login(self.user)
        url = reverse('document_interaction', args=[self.document.pk])
        self.client.post(url, {'action': 'rating', 'stars': '4'})
        self.client.post(url, {'action': 'rating', 'stars': '2'})
        self.assertEqual(Rating.objects.filter(document=self.document).count(), 1)
        self.assertEqual(self.document.average_rating, 4)

    def test_download_records_event_and_adds_library_entry(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('document_download', args=[self.document.pk]))
        self.assertEqual(response.status_code, 200)
        expected_filename = self.document.file.name.rsplit('/', 1)[-1]
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="{expected_filename}"',
        )
        self.assertEqual(Download.objects.filter(document=self.document).count(), 1)
        self.assertTrue(
            PersonalLibrary.objects.filter(
                user=self.user,
                document=self.document,
                entry_type=PersonalLibrary.EntryType.DOWNLOADED,
            ).exists()
        )
        self.document.refresh_from_db()
        self.assertEqual(self.document.download_count, 1)

    def test_library_entries_can_only_be_removed_by_the_owner(self):
        entry = PersonalLibrary.objects.create(
            user=self.user,
            document=self.document,
            entry_type=PersonalLibrary.EntryType.FAVORITE,
        )
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(reverse('personal_library')).status_code, 200)
        response = self.client.post(
            reverse('remove_library_entry', args=[entry.pk])
        )
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse('remove_library_entry', args=[entry.pk])
        )
        self.assertRedirects(response, reverse('personal_library'))
        self.assertFalse(PersonalLibrary.objects.filter(pk=entry.pk).exists())

    def test_authenticated_member_can_share_and_share_is_logged(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('share_document', args=[self.document.pk]),
            {'platform': 'facebook'},
        )
        self.assertRedirects(response, self.document.get_absolute_url())
        self.assertEqual(self.document.shares.get().platform, 'facebook')

    def test_admin_moderation_page_is_available_to_admin_role(self):
        admin = User.objects.create_user(
            username='administrator', password='secret12345', role=User.Role.ADMIN
        )
        self.client.force_login(admin)
        response = self.client.get(reverse('document_moderation'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kiểm duyệt tài liệu')

    def test_admin_can_open_a_pending_document_for_review(self):
        pending_document = Document.objects.create(
            title='Tài liệu chờ duyệt',
            file=SimpleUploadedFile('pending-review.pdf', b'pending document'),
            uploader=self.user,
            status=Document.Status.PENDING,
        )
        admin = User.objects.create_user(
            username='reviewer', password='secret12345', role=User.Role.ADMIN
        )

        self.client.force_login(admin)
        response = self.client.get(pending_document.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tài liệu đang chờ quản trị viên kiểm duyệt')
        self.assertContains(response, pending_document.title)

    def test_comment_edits_are_limited_to_owner_and_soft_delete(self):
        comment = Comment.objects.create(
            document=self.document, user=self.user, content='Ban đầu'
        )
        self.client.force_login(self.other_user)
        response = self.client.post(
            reverse('edit_comment', args=[comment.pk]), {'content': 'Không phải của tôi'}
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse('edit_comment', args=[comment.pk]), {'content': 'Đã cập nhật'}
        )
        self.assertRedirects(response, self.document.get_absolute_url())
        comment.refresh_from_db()
        self.assertEqual(comment.content, 'Đã cập nhật')
        self.assertTrue(comment.is_edited)

        self.client.post(reverse('delete_comment', args=[comment.pk]))
        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)

    def test_upload_waits_for_moderation(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('document_upload'),
            {
                'title': 'Tài liệu mới',
                'description': '',
                'subject': 'Vật lý',
                'category': self.category.pk,
                'visibility': Document.Visibility.PUBLIC,
                'file': SimpleUploadedFile('physics.pdf', b'physics'),
            },
        )
        self.assertRedirects(response, reverse('document_list'))
        uploaded = Document.objects.get(title='Tài liệu mới')
        self.assertEqual(uploaded.status, Document.Status.PENDING)

    def test_upload_can_create_a_new_category(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('document_upload'),
            {
                'title': 'English notes',
                'description': '',
                'subject': 'English',
                'category': DocumentUploadForm.NEW_CATEGORY_VALUE,
                'new_category': 'Tiếng Anh',
                'visibility': Document.Visibility.PUBLIC,
                'file': SimpleUploadedFile('english-notes.pdf', b'english notes'),
            },
        )

        self.assertRedirects(response, reverse('document_list'))
        uploaded = Document.objects.get(title='English notes')
        self.assertEqual(uploaded.category.name, 'Tiếng Anh')
        self.assertEqual(uploaded.category.slug, 'tieng-anh')
        self.assertNotEqual(uploaded.category.name, 'Tạo danh mục mới')

    def test_category_creation_option_is_part_of_category_selector(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('document_upload'))

        self.assertContains(response, 'Danh mục')
        self.assertContains(response, 'Tạo danh mục mới')
        self.assertContains(response, 'emptyCategoryOption.hidden = true')
        self.assertNotContains(response, '---------')
        self.assertNotContains(response, 'Maksimum')
        self.assertContains(response, 'id="new-category-field"')
        self.assertNotContains(response, 'Hoặc thêm danh mục mới')


class DemoDatabaseCommandTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_directory = tempfile.TemporaryDirectory()
        cls.settings_override = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.settings_override.enable()
        cls.addClassCleanup(cls.settings_override.disable)
        cls.addClassCleanup(cls.media_directory.cleanup)

    def test_seed_command_is_idempotent(self):
        call_command('seed_demo_data', password='EduHubTest2026!')
        call_command('seed_demo_data', password='EduHubTest2026!')

        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Category.objects.count(), 3)
        self.assertEqual(Document.objects.count(), 3)
        self.assertEqual(Comment.objects.count(), 1)
        self.assertEqual(Rating.objects.count(), 1)
        self.assertEqual(Download.objects.count(), 1)
        self.assertEqual(PersonalLibrary.objects.count(), 2)

    def test_seed_command_requires_reasonable_password(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo_data', password='short')
