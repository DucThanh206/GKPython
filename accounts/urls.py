from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('google/login/', views.google_login, name='google_login'),
    path('google/callback/', views.google_oauth_callback, name='google_oauth_callback'),
    path('google/drive/connect/', views.google_drive_connect, name='google_drive_connect'),
    path('google/drive/callback/', views.google_drive_callback, name='google_drive_callback'),
    path('google/drive/disconnect/', views.google_drive_disconnect, name='google_drive_disconnect'),
    path('profile/', views.profile, name='profile'),
    path('manage/', views.account_list, name='account_list'),
    path('manage/<int:pk>/toggle/', views.toggle_account_status, name='toggle_account_status'),
    path('password_change/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password_change_form.html'),
         name='password_change'),

    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='registration/password_change_done.html'),
         name='password_change_done'),
]
