import urllib.error
from io import BytesIO
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from unittest.mock import MagicMock, patch

from .google_drive import (
    GoogleDriveError,
    _google_view_link,
    _request_json,
    upload_file,
)
from .models import GoogleDriveConnection

User = get_user_model()


class AccountFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='secret12345', role=User.Role.ADMIN
        )
        self.member = User.objects.create_user(username='member', password='secret12345')

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
        GOOGLE_DRIVE_REDIRECT_URI='http://testserver/accounts/google/drive/callback/',
    )
    def test_google_drive_connect_requests_offline_drive_file_access(self):
        self.client.force_login(self.member)

        response = self.client.get(
            reverse('google_drive_connect'),
            {'next': reverse('document_open', args=[12])},
        )

        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlparse(response['Location']).query)
        self.assertIn('https://www.googleapis.com/auth/drive.file', params['scope'][0])
        self.assertEqual(params['access_type'], ['offline'])
        self.assertEqual(
            params['redirect_uri'],
            ['http://testserver/accounts/google/drive/callback/'],
        )
        self.assertEqual(self.client.session['google_drive_next'], reverse('document_open', args=[12]))

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
        GOOGLE_DRIVE_REDIRECT_URI='http://testserver/accounts/google/drive/callback/',
    )
    @patch(
        'accounts.views._google_request_json',
        side_effect=[
            {'access_token': 'access-token', 'refresh_token': 'refresh-token'},
            {
                'email': 'drive-member@example.com',
                'email_verified': True,
            },
        ],
    )
    def test_google_drive_callback_saves_encrypted_refresh_token(self, google_request):
        self.client.force_login(self.member)
        session = self.client.session
        session['google_drive_oauth_state'] = 'expected-state'
        session['google_drive_next'] = reverse('document_open', args=[12])
        session.save()

        response = self.client.get(
            reverse('google_drive_callback'),
            {'state': 'expected-state', 'code': 'authorization-code'},
        )

        self.assertRedirects(
            response,
            reverse('document_open', args=[12]),
            fetch_redirect_response=False,
        )
        connection = GoogleDriveConnection.objects.get(user=self.member)
        self.assertEqual(connection.google_email, 'drive-member@example.com')
        self.assertNotEqual(connection.encrypted_refresh_token, 'refresh-token')
        self.assertEqual(connection.get_refresh_token(), 'refresh-token')
        self.assertEqual(
            self.client.session['google_drive_resume_open_document_id'],
            12,
        )
        self.assertEqual(google_request.call_count, 2)

    def test_user_can_disconnect_google_drive(self):
        connection = GoogleDriveConnection(user=self.member, google_email='drive@example.com')
        connection.set_refresh_token('refresh-token')
        connection.save()
        self.client.force_login(self.member)

        response = self.client.post(reverse('google_drive_disconnect'))

        self.assertRedirects(response, reverse('profile'))
        self.assertFalse(GoogleDriveConnection.objects.filter(user=self.member).exists())

    def test_google_drive_upload_uses_resumable_conversion(self):
        initiation_response = MagicMock()
        initiation_response.__enter__.return_value.headers.get.return_value = (
            'https://www.googleapis.com/upload/drive/v3/files?upload_id=one-time-id'
        )
        upload_response = MagicMock()
        upload_response.__enter__.return_value.read.return_value = (
            b'{"id":"drive-id","webViewLink":"https://docs.google.com/document/d/drive-id/edit"}'
        )

        with patch(
            'accounts.google_drive.urllib.request.urlopen',
            side_effect=[initiation_response, upload_response],
        ) as urlopen:
            result = upload_file(
                'access-token',
                'Converted document',
                'application/msword',
                'application/vnd.google-apps.document',
                b'office-content',
            )

        self.assertEqual(
            result,
            (
                'drive-id',
                'https://docs.google.com/document/d/drive-id/edit',
            ),
        )
        initiation_request = urlopen.call_args_list[0].args[0]
        upload_request = urlopen.call_args_list[1].args[0]
        self.assertEqual(initiation_request.get_method(), 'POST')
        self.assertEqual(
            initiation_request.get_header('X-upload-content-type'),
            'application/msword',
        )
        self.assertEqual(upload_request.get_method(), 'PUT')
        self.assertEqual(upload_request.data, b'office-content')

    def test_google_drive_open_link_rejects_untrusted_hosts(self):
        with self.assertRaises(GoogleDriveError):
            _google_view_link('https://attacker.example/document')

    def test_google_drive_api_errors_keep_status_and_reason(self):
        error_response = urllib.error.HTTPError(
            'https://www.googleapis.com/drive/v3/files',
            403,
            'Forbidden',
            {},
            BytesIO(
                b'{"error":{"code":403,"message":"Drive API is disabled",'
                b'"errors":[{"reason":"accessNotConfigured"}],'
                b'"status":"PERMISSION_DENIED"}}'
            ),
        )

        with (
            patch(
                'accounts.google_drive.urllib.request.urlopen',
                side_effect=error_response,
            ),
            self.assertRaises(GoogleDriveError) as raised,
        ):
            _request_json(
                Request('https://www.googleapis.com/drive/v3/files')
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.reason, 'accessNotConfigured')

    def test_profile_is_login_protected_and_updates_user(self):
        response = self.client.get(reverse('profile'))
        self.assertRedirects(response, f"/login/?next={reverse('profile')}")

        self.client.force_login(self.member)
        response = self.client.post(
            reverse('profile'),
            {
                'full_name': 'Nguyễn An',
                'email': 'an@example.com',
                'school': 'Đại học',
                'bio': 'Xin chào',
            },
        )
        self.assertRedirects(response, reverse('profile'))
        self.member.refresh_from_db()
        self.assertEqual(self.member.full_name, 'Nguyễn An')
        self.assertEqual(self.member.email, 'an@example.com')
        self.assertEqual(self.client.get(reverse('profile')).status_code, 200)

    def test_admin_can_lock_other_users_but_member_cannot_access(self):
        response = self.client.get(reverse('account_list'))
        self.assertRedirects(response, f"/login/?next={reverse('account_list')}")

        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('account_list')).status_code, 403)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('account_list')).status_code, 200)
        response = self.client.post(
            reverse('toggle_account_status', args=[self.member.pk])
        )
        self.assertRedirects(response, reverse('account_list'))
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)

    def test_google_sign_in_is_removed_for_members_and_admins(self):
        login_response = self.client.get(reverse('login'))
        self.assertEqual(login_response.status_code, 200)
        self.assertNotContains(login_response, 'accounts/google/login/')

        admin_login_response = self.client.get('/admin/login/')
        self.assertEqual(admin_login_response.status_code, 200)
        self.assertNotContains(admin_login_response, 'accounts/google/login/')

        self.assertEqual(self.client.get('/accounts/google/login/').status_code, 404)
        self.assertEqual(self.client.get('/accounts/google/callback/').status_code, 404)
