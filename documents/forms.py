from django import forms

from .models import Document


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'description', 'category', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
