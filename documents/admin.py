from django.contrib import admin

from .models import Category, Comment, Document, Download, PersonalLibrary, Rating


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'uploader', 'status', 'uploaded_at', 'download_count')
    list_filter = ('status', 'category', 'uploaded_at')
    search_fields = ('title', 'description')


admin.site.register((Comment, Rating, Download, PersonalLibrary))
