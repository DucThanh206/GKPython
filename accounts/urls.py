from django.urls import path

from . import views

urlpatterns = [
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('google/login/', views.google_login, name='google_login'),
    path('google/callback/', views.google_oauth_callback, name='google_oauth_callback'),
    path('profile/', views.profile, name='profile'),
    path('manage/', views.account_list, name='account_list'),
    path('manage/<int:pk>/toggle/', views.toggle_account_status, name='toggle_account_status'),
]
