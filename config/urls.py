from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from documents import views as document_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='registration/login.html',
            extra_context={
                'google_oauth_enabled': bool(
                    settings.GOOGLE_OAUTH_CLIENT_ID
                    and settings.GOOGLE_OAUTH_CLIENT_SECRET
                )
            },
        ),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/', include('accounts.urls')),
    path('', include('documents.urls')),
    path("reports/", include("reports.urls")),
    path(
        'media/documents/<path:file_path>',
        document_views.deny_direct_document_file,
        name='deny_direct_document_file',
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
