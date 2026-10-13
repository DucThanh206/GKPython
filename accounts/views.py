import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.contrib.auth import login
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView

from .forms import ProfileForm, SignUpForm
from .decorators import admin_required
from .models import GoogleDriveConnection, GoogleDriveDocument

User = get_user_model()
logger = logging.getLogger(__name__)

GOOGLE_AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'
GOOGLE_DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.file'


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('document_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


@login_required
def google_drive_connect(request):
    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        messages.error(request, 'Kết nối Google Drive chưa được cấu hình.')
        return redirect('profile')

    next_url = request.GET.get('next', '')
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = reverse('profile')
    state = secrets.token_urlsafe(32)
    request.session['google_drive_oauth_state'] = state
    request.session['google_drive_next'] = next_url

    redirect_uri = getattr(settings, 'GOOGLE_DRIVE_REDIRECT_URI', '')
    if not redirect_uri:
        redirect_uri = request.build_absolute_uri(reverse('google_drive_callback'))
    params = urllib.parse.urlencode(
        {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': f'openid email profile {GOOGLE_DRIVE_SCOPE}',
            'state': state,
            'include_granted_scopes': 'true',
            'access_type': 'offline',
            'prompt': 'consent select_account',
        }
    )
    return redirect(f'{GOOGLE_AUTHORIZE_URL}?{params}')


@login_required
def google_drive_callback(request):
    state = request.session.pop('google_drive_oauth_state', None)
    next_url = request.session.pop('google_drive_next', reverse('profile'))
    received_state = request.GET.get('state', '')
    if not state or not secrets.compare_digest(state, received_state):
        messages.error(request, 'Phiên kết nối Google Drive không hợp lệ hoặc đã hết hạn.')
        return redirect('profile')
    if request.GET.get('error'):
        messages.error(request, 'Kết nối Google Drive đã bị hủy hoặc không thành công.')
        return redirect(next_url)

    code = request.GET.get('code')
    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '')
    if not code or not client_id or not client_secret:
        messages.error(request, 'Google không trả về mã xác thực hợp lệ.')
        return redirect(next_url)

    redirect_uri = getattr(settings, 'GOOGLE_DRIVE_REDIRECT_URI', '')
    if not redirect_uri:
        redirect_uri = request.build_absolute_uri(reverse('google_drive_callback'))
    try:
        token_data = _google_request_json(
            GOOGLE_TOKEN_URL,
            method='POST',
            form_data={
                'code': code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            },
        )
        access_token = token_data.get('access_token')
        if not isinstance(access_token, str) or not access_token:
            raise ValueError('Google did not return an access token.')
        profile = _google_request_json(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
        )
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        logger.exception('Google Drive OAuth connection failed.')
        messages.error(request, 'Không thể kết nối tài khoản với Google Drive.')
        return redirect(next_url)

    email = profile.get('email')
    if (
        not isinstance(email, str)
        or not email.strip()
        or profile.get('email_verified') is not True
    ):
        messages.error(request, 'Google Drive cần tài khoản Google có email đã xác minh.')
        return redirect(next_url)

    connection = GoogleDriveConnection.objects.filter(user=request.user).first()
    refresh_token = token_data.get('refresh_token')
    if isinstance(refresh_token, str) and refresh_token:
        if connection is None:
            connection = GoogleDriveConnection(user=request.user)
        connection.set_refresh_token(refresh_token)
    elif connection and connection.google_email.casefold() != email.strip().casefold():
        messages.error(request, 'Google không cấp quyền làm mới token. Vui lòng kết nối lại.')
        return redirect(next_url)
    elif connection is None:
        messages.error(request, 'Google không cấp quyền làm mới token. Vui lòng kết nối lại.')
        return redirect(next_url)
    connection.google_email = email.strip().lower()
    connection.save()
    try:
        next_match = resolve(urllib.parse.urlsplit(next_url).path)
    except Resolver404:
        next_match = None
    if next_match and next_match.url_name == 'document_open':
        request.session['google_drive_resume_open_document_id'] = int(
            next_match.kwargs['pk']
        )
    messages.success(request, f'Đã kết nối Google Drive ({connection.google_email}).')
    return redirect(next_url)


@login_required
def google_drive_disconnect(request):
    if request.method == 'POST':
        GoogleDriveDocument.objects.filter(user=request.user).delete()
        GoogleDriveConnection.objects.filter(user=request.user).delete()
        messages.success(request, 'Đã hủy liên kết Google Drive trên EduHub.')
    return redirect('profile')


def _google_request_json(url, *, method='GET', form_data=None, headers=None):
    request_headers = headers or {}
    data = None
    if form_data is not None:
        data = urllib.parse.urlencode(form_data).encode('utf-8')
        request_headers['Content-Type'] = 'application/x-www-form-urlencoded'
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read().decode('utf-8'))
    if not isinstance(result, dict):
        raise ValueError('Google returned an invalid response.')
    return result


@login_required
def profile(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cập nhật hồ sơ thành công.')
            return redirect('profile')
    else:
        form = ProfileForm(instance=request.user)
    return render(
        request,
        'accounts/profile.html',
        {
            'form': form,
            'google_drive_enabled': bool(
                settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET
            ),
            'google_drive_connection': getattr(
                request.user, 'google_drive_connection', None
            ),
        },
    )


@admin_required
def account_list(request):
    users = User.objects.order_by('username')
    return render(request, 'accounts/account_list.html', {'users': users})


@admin_required
def toggle_account_status(request, pk):
    if request.method != 'POST':
        return redirect('account_list')
    account = get_object_or_404(User, pk=pk)
    if account.pk == request.user.pk:
        messages.error(request, 'Bạn không thể khóa tài khoản của chính mình.')
    else:
        account.is_active = not account.is_active
        account.save(update_fields=['is_active'])
        messages.success(request, 'Trạng thái tài khoản đã được cập nhật.')
    return redirect('account_list')
