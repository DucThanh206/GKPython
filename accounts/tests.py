from django.test import TestCase
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
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
