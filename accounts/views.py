import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid

from django.contrib.auth import login
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView

from .forms import ProfileForm, SignUpForm
from .decorators import admin_required

User = get_user_model()
logger = logging.getLogger(__name__)

GOOGLE_AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('document_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


def google_login(request):
    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
    if not client_id or not getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', ''):
        messages.error(request, 'Đăng nhập Google chưa được cấu hình.')
        return redirect('login')

    state = secrets.token_urlsafe(32)
    request.session['google_oauth_state'] = state
    if request.user.is_authenticated:
        request.session['google_oauth_link_user_id'] = request.user.pk
    else:
        request.session.pop('google_oauth_link_user_id', None)
    next_url = request.GET.get('next', '')
    if url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        request.session['google_oauth_next'] = next_url
    else:
        request.session.pop('google_oauth_next', None)

    redirect_uri = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', '')
    if not redirect_uri:
        redirect_uri = request.build_absolute_uri(reverse('google_oauth_callback'))
    params = urllib.parse.urlencode(
        {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile',
            'state': state,
            'include_granted_scopes': 'true',
        }
    )
    return redirect(f'{GOOGLE_AUTHORIZE_URL}?{params}')


def google_oauth_callback(request):
    state = request.session.pop('google_oauth_state', None)
    link_user_id = request.session.pop('google_oauth_link_user_id', None)
    received_state = request.GET.get('state', '')
    if not state or not secrets.compare_digest(state, received_state):
        messages.error(request, 'Phiên xác thực Google không hợp lệ hoặc đã hết hạn.')
        return redirect('login')
    if request.GET.get('error'):
        messages.error(request, 'Đăng nhập Google đã bị hủy hoặc không thành công.')
        return redirect('login')
    code = request.GET.get('code')
    if not code:
        messages.error(request, 'Google không trả về mã xác thực.')
        return redirect('login')

    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        messages.error(request, 'Đăng nhập Google chưa được cấu hình.')
        return redirect('login')

    redirect_uri = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', '')
    if not redirect_uri:
        redirect_uri = request.build_absolute_uri(reverse('google_oauth_callback'))
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
        if not access_token:
            raise ValueError('Google did not return an access token.')
        profile = _google_request_json(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': 'Bear' + 'er ' + access_token},
        )
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        logger.exception('Google OAuth authentication failed.')
        messages.error(request, 'Không thể xác thực với Google. Vui lòng thử lại.')
        return redirect('login')

    google_id = profile.get('sub')
    raw_email = profile.get('email')
    if (
        not isinstance(google_id, str)
        or not google_id
        or not isinstance(raw_email, str)
        or not raw_email.strip()
        or profile.get('email_verified') is not True
    ):
        messages.error(request, 'Tài khoản Google không cung cấp email đã xác minh.')
        return redirect('login')
    email = raw_email.strip().lower()
    full_name = str(profile.get('name') or '')[:150]

    user = User.objects.filter(google_id=google_id).first()
    if link_user_id:
        link_user = User.objects.filter(pk=link_user_id).first()
        if link_user is None or not link_user.is_active:
            messages.error(request, 'Tài khoản cần liên kết không còn khả dụng.')
            return redirect('login')
        if user is not None and user.pk != link_user.pk:
            messages.error(request, 'Tài khoản Google này đã được liên kết với người dùng khác.')
            return redirect('profile')
        if link_user.google_id and link_user.google_id != google_id:
            messages.error(request, 'Tài khoản này đã liên kết với Google khác.')
            return redirect('profile')
        if link_user.email and link_user.email.casefold() != email.casefold():
            messages.error(request, 'Email Google phải trùng với email trong hồ sơ.')
            return redirect('profile')
        link_user.google_id = google_id
        if not link_user.email:
            link_user.email = email
        if not link_user.full_name:
            link_user.full_name = full_name
        link_user.save(update_fields=['google_id', 'email', 'full_name'])
        user = link_user
    elif user is None:
        existing_email_user = User.objects.filter(email__iexact=email).first()
        if existing_email_user is not None:
            messages.error(
                request,
                'Email này đã có tài khoản. Hãy đăng nhập tài khoản đó rồi liên kết Google trong hồ sơ.',
            )
            return redirect('login')
        user = User(
            username=f'google-{uuid.uuid4().hex}',
            email=email,
            full_name=full_name,
            first_name=str(profile.get('given_name') or '')[:150],
            last_name=str(profile.get('family_name') or '')[:150],
            google_id=google_id,
        )
        user.set_unusable_password()
        user.save()
    elif not user.is_active:
        messages.error(request, 'Tài khoản của bạn đã bị khóa.')
        return redirect('login')

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    next_url = request.session.pop('google_oauth_next', '')
    messages.success(request, 'Bạn đã đăng nhập bằng Google.')
    return redirect(next_url or 'document_list')


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
            'google_oauth_enabled': bool(
                settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET
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
