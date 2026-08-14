from django.contrib import admin

from .models import Category, Document


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'uploader', 'uploaded_at', 'download_count')
    list_filter = ('category', 'uploaded_at')
    search_fields = ('title', 'description')
