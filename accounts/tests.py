from io import BytesIO
from tempfile import TemporaryDirectory

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from unittest.mock import patch

User = get_user_model()


class AccountFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='secret12345', role=User.Role.ADMIN
        )
        self.member = User.objects.create_user(username='member', password='secret12345')

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

    def test_profile_uploads_and_previews_avatar_image(self):
        image_buffer = BytesIO()
        Image.new('RGB', (1, 1), color='blue').save(image_buffer, format='PNG')
        image = SimpleUploadedFile(
            'avatar.png', image_buffer.getvalue(), content_type='image/png'
        )
        self.client.force_login(self.member)

        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    reverse('profile'),
                    {
                        'full_name': 'Nguyễn An',
                        'email': 'an@example.com',
                        'school': '',
                        'bio': '',
                        'avatar': image,
                    },
                )
                self.assertRedirects(response, reverse('profile'))

                self.member.refresh_from_db()
                self.assertTrue(self.member.avatar.name.startswith('avatars/'))
                response = self.client.get(reverse('profile'))

        self.assertContains(response, f'<img id="avatar-preview"')
        self.assertContains(response, self.member.avatar.url)
        self.assertNotContains(response, 'Currently:')

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

    def test_admin_cannot_lock_or_unlock_another_admin(self):
        another_admin = User.objects.create_user(
            username='another-admin',
            password='secret12345',
            role=User.Role.ADMIN,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('account_list'))
        self.assertNotContains(response, 'Tên đăng nhập: another-admin')
        self.assertContains(response, 'Không thể khóa quản trị viên')
        self.assertNotContains(response, reverse(
            'toggle_account_status', args=[another_admin.pk]
        ))

        response = self.client.post(
            reverse('toggle_account_status', args=[another_admin.pk])
        )
        self.assertRedirects(response, reverse('account_list'))
        another_admin.refresh_from_db()
        self.assertTrue(another_admin.is_active)

        another_admin.is_active = False
        another_admin.save(update_fields=['is_active'])
        self.client.post(reverse('toggle_account_status', args=[another_admin.pk]))
        another_admin.refresh_from_db()
        self.assertFalse(another_admin.is_active)

    def test_account_list_uses_profile_name_and_shows_superuser_as_admin(self):
        self.member.username = 'demo_member01'
        self.member.full_name = 'Doan Minh Tri'
        self.member.save(update_fields=['username', 'full_name'])
        superuser_member_role = User.objects.create_user(
            username='admin_01',
            email='admin01@example.com',
            password='secret12345',
            role=User.Role.MEMBER,
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('account_list'))

        self.assertContains(response, 'Doan Minh Tri')
        self.assertNotContains(response, 'Tên đăng nhập: demo_member01')
        self.assertEqual(response.content.decode().count('Quản trị viên'), 2)
        self.assertNotContains(
            response, reverse('toggle_account_status', args=[superuser_member_role.pk])
        )

        self.client.post(
            reverse('toggle_account_status', args=[superuser_member_role.pk])
        )
        superuser_member_role.refresh_from_db()
        self.assertTrue(superuser_member_role.is_active)

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
        GOOGLE_OAUTH_REDIRECT_URI='http://testserver/accounts/google/callback/',
    )
    @patch(
        'accounts.views._google_request_json',
        side_effect=[
            {'access_token': 'token'},
            {
                'sub': 'google-user-1',
                'email': 'google@example.com',
                'email_verified': True,
                'name': 'Google Member',
                'given_name': 'Google',
                'family_name': 'Member',
            },
        ],
    )
    def test_google_callback_creates_and_authenticates_verified_account(self, google_request):
        session = self.client.session
        session['google_oauth_state'] = 'expected-state'
        session.save()
        response = self.client.get(
            reverse('google_oauth_callback'),
            {'state': 'expected-state', 'code': 'authorization-code'},
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email='google@example.com')
        self.assertEqual(user.google_id, 'google-user-1')
        self.assertEqual(user.role, User.Role.MEMBER)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(google_request.call_count, 2)
        auth_header = google_request.call_args_list[1].kwargs['headers']['Authorization']
        self.assertEqual(auth_header, 'Bear' + 'er token')

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
    )
    def test_google_callback_rejects_invalid_state(self):
        response = self.client.get(
            reverse('google_oauth_callback'),
            {'state': 'wrong-state', 'code': 'authorization-code'},
        )
        self.assertRedirects(response, reverse('login'))
        self.assertFalse(User.objects.filter(username__startswith='google-').exists())

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
        GOOGLE_OAUTH_REDIRECT_URI='http://testserver/accounts/google/callback/',
    )
    @patch(
        'accounts.views._google_request_json',
        side_effect=[
            {'access_token': 'token'},
            {
                'sub': 'member-google-id',
                'email': 'member@example.com',
                'email_verified': True,
                'name': 'Member',
            },
        ],
    )
    def test_authenticated_member_can_link_matching_google_account(self, google_request):
        self.member.email = 'member@example.com'
        self.member.save(update_fields=['email'])
        self.client.force_login(self.member)
        self.client.get(reverse('google_login'))
        state = self.client.session['google_oauth_state']

        response = self.client.get(
            reverse('google_oauth_callback'),
            {'state': state, 'code': 'authorization-code'},
        )
        self.assertRedirects(response, reverse('document_list'))
        self.member.refresh_from_db()
        self.assertEqual(self.member.google_id, 'member-google-id')
        self.assertEqual(google_request.call_count, 2)

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
        GOOGLE_OAUTH_REDIRECT_URI='http://testserver/accounts/google/callback/',
    )
    @patch(
        'accounts.views._google_request_json',
        side_effect=[
            {'access_token': 'token'},
            {
                'sub': 'locked-google-user',
                'email': 'member@example.com',
                'email_verified': True,
                'name': 'Member',
            },
        ],
    )
    def test_google_login_does_not_bypass_account_lock(self, google_request):
        self.member.email = 'member@example.com'
        self.member.is_active = False
        self.member.save(update_fields=['email', 'is_active'])
        session = self.client.session
        session['google_oauth_state'] = 'expected-state'
        session.save()

        response = self.client.get(
            reverse('google_oauth_callback'),
            {'state': 'expected-state', 'code': 'authorization-code'},
        )
        self.assertRedirects(response, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(google_request.call_count, 2)
        self.member.refresh_from_db()
        self.assertIsNone(self.member.google_id)

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID='client-id',
        GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
        GOOGLE_OAUTH_REDIRECT_URI='http://testserver/accounts/google/callback/',
    )
    @patch(
        'accounts.views._google_request_json',
        side_effect=[
            {'access_token': 'token'},
            {
                'sub': 'unlinked-google-user',
                'email': 'member@example.com',
                'email_verified': True,
                'name': 'Member',
            },
        ],
    )
    def test_google_does_not_automatically_take_over_existing_email(self, google_request):
        self.member.email = 'member@example.com'
        self.member.save(update_fields=['email'])
        session = self.client.session
        session['google_oauth_state'] = 'expected-state'
        session.save()

        response = self.client.get(
            reverse('google_oauth_callback'),
            {'state': 'expected-state', 'code': 'authorization-code'},
        )
        self.assertRedirects(response, reverse('login'))
        self.assertIsNone(User.objects.get(pk=self.member.pk).google_id)
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(google_request.call_count, 2)
