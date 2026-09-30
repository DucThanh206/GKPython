from django.urls import path

from . import views

urlpatterns = [
    path('', views.DocumentListView.as_view(), name='document_list'),
    path('upload/', views.DocumentUploadView.as_view(), name='document_upload'),
    path('<int:pk>/preview/', views.document_preview, name='document_preview'),
    path('library/', views.personal_library, name='personal_library'),
    path('library/<int:entry_id>/remove/', views.remove_library_entry, name='remove_library_entry'),
    path('moderation/', views.moderation_list, name='document_moderation'),
    path('moderation/<int:pk>/', views.moderate_document, name='moderate_document'),
    path('<int:pk>/download/', views.download_document, name='document_download'),
    path('<int:pk>/interact/', views.document_interaction, name='document_interaction'),
    path('<int:pk>/favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('<int:pk>/share/', views.share_document, name='share_document'),
    path('comments/<int:pk>/edit/', views.edit_comment, name='edit_comment'),
    path('comments/<int:pk>/delete/', views.delete_comment, name='delete_comment'),
    path('<int:pk>/', views.DocumentDetailView.as_view(), name='document_detail'),
]
