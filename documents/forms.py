from pathlib import Path

from django import forms
from django.conf import settings

from .models import Category, Comment, Document, Rating


class DocumentUploadForm(forms.ModelForm):
    NEW_CATEGORY_VALUE = '__new__'
    new_category = forms.CharField(
        label='',
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Nhập tên danh mục mới',
                'aria-label': 'Tên danh mục mới',
            }
        ),
    )
    category = forms.ChoiceField(
        label='Danh mục',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_category'}),
    )

    ALLOWED_EXTENSIONS = {
        '.csv', '.doc', '.docx', '.md', '.pdf', '.ppt', '.pptx',
        '.txt', '.xls', '.xlsx',
    }

    class Meta:
        model = Document
        fields = ['title', 'description', 'subject', 'category', 'visibility', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'subject': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(
                attrs={'class': 'form-select', 'id': 'id_category'}
            ),
            'visibility': forms.Select(attrs={'class': 'form-select'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].choices = [
            ('', ''),
            (self.NEW_CATEGORY_VALUE, 'Tạo danh mục mới'),
            *Category.objects.values_list('pk', 'name'),
        ]
        self.fields['file'].help_text = (
            'Định dạng cho phép: ' + ', '.join(sorted(self.ALLOWED_EXTENSIONS))
        )

    def clean_category(self):
        category_id = self.cleaned_data['category']
        if not category_id or category_id == self.NEW_CATEGORY_VALUE:
            return None
        try:
            return Category.objects.get(pk=category_id)
        except Category.DoesNotExist as exc:
            raise forms.ValidationError('Danh mục đã chọn không tồn tại.') from exc

    def clean_new_category(self):
        return self.cleaned_data['new_category'].strip()

    def clean(self):
        cleaned_data = super().clean()
        category_choice = self.data.get(self.add_prefix('category'))
        new_category = cleaned_data.get('new_category')
        if category_choice == self.NEW_CATEGORY_VALUE and not new_category:
            self.add_error('new_category', 'Vui lòng nhập tên danh mục mới.')
        elif category_choice != self.NEW_CATEGORY_VALUE and new_category:
            self.add_error(
                'new_category',
                'Để tạo danh mục mới, vui lòng chọn mục tương ứng trong danh sách Danh mục.',
            )
        return cleaned_data

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        extension = Path(uploaded_file.name).suffix.lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            allowed = ', '.join(sorted(self.ALLOWED_EXTENSIONS))
            raise forms.ValidationError(
                f'Định dạng tệp không được hỗ trợ. Định dạng cho phép: {allowed}.'
            )
        if uploaded_file.size > settings.MAX_DOCUMENT_UPLOAD_SIZE:
            maximum_mb = settings.MAX_DOCUMENT_UPLOAD_SIZE // (1024 * 1024)
            raise forms.ValidationError(
                f'Tệp vượt quá giới hạn {maximum_mb} MB.'
            )
        return uploaded_file


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3, 'maxlength': 5000}
            )
        }


class RatingForm(forms.ModelForm):
    class Meta:
        model = Rating
        fields = ['stars']
        widgets = {'stars': forms.RadioSelect(choices=[(n, f'{n} sao') for n in range(1, 6)])}

    def clean_stars(self):
        stars = self.cleaned_data['stars']
        if not 1 <= stars <= 5:
            raise forms.ValidationError('Vui lòng chọn từ 1 đến 5 sao.')
        return stars
