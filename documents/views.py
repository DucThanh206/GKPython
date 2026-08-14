from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView

from .forms import DocumentUploadForm
from .models import Document


class DocumentListView(ListView):
    model = Document
    template_name = 'documents/document_list.html'
    context_object_name = 'documents'
    paginate_by = 12

    def get_queryset(self):
        qs = super().get_queryset().select_related('category', 'uploader')
        query = self.request.GET.get('q')
        if query:
            qs = qs.filter(title__icontains=query)
        return qs


class DocumentDetailView(DetailView):
    model = Document
    template_name = 'documents/document_detail.html'
    context_object_name = 'document'


class DocumentUploadView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentUploadForm
    template_name = 'documents/document_upload.html'
    success_url = reverse_lazy('document_list')

    def form_valid(self, form):
        form.instance.uploader = self.request.user
        return super().form_valid(form)
