from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('google/login/', views.google_login, name='google_login'),
    path('google/callback/', views.google_oauth_callback, name='google_oauth_callback'),
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
