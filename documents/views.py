from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.views.generic import CreateView, DetailView, ListView

from accounts.decorators import admin_required

from .forms import CommentForm, DocumentUploadForm, RatingForm
from .models import (
    Category,
    Comment,
    Document,
    DocumentView,
    Download,
    PersonalLibrary,
    Rating,
    Share,
)
from .previews import TEXT_EXTENSIONS, extract_docx_text, get_plain_text


class DocumentListView(ListView):
    model = Document
    template_name = 'documents/document_list.html'
    context_object_name = 'documents'
    paginate_by = 12

    def get_queryset(self):
        qs = super().get_queryset().filter(
            status=Document.Status.APPROVED
        ).select_related('category', 'uploader')
        query = self.request.GET.get('q')
        if query is not None:
            query = query.strip()
            if query:
                for term in query.split():
                    qs = qs.filter(
                        Q(title__icontains=term)
                        | Q(description__icontains=term)
                        | Q(subject__icontains=term)
                        | Q(category__name__icontains=term)
                    )
            else:
                qs = qs.none()
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category__slug=category)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        context['search_empty'] = 'q' in self.request.GET and not self.request.GET['q'].strip()
        return context


class DocumentDetailView(DetailView):
    model = Document
    template_name = 'documents/document_detail.html'
    context_object_name = 'document'

    def get_queryset(self):
        queryset = super().get_queryset().select_related('category', 'uploader')
        if self.request.user.is_authenticated and (
            self.request.user.is_superuser
            or getattr(self.request.user, 'role', None) == 'admin'
        ):
            return queryset
        if self.request.user.is_authenticated:
            return queryset.filter(
                Q(status=Document.Status.APPROVED) | Q(uploader=self.request.user)
            )
        return queryset.filter(status=Document.Status.APPROVED)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        can_view = (
            self.object.visibility == Document.Visibility.PUBLIC
            or request.user.is_authenticated
        )
        if can_view and self.object.status == Document.Status.APPROVED:
            Document.objects.filter(pk=self.object.pk).update(view_count=F('view_count') + 1)
            DocumentView.objects.create(
                document=self.object,
                user=request.user if request.user.is_authenticated else None,
                ip_address=_client_ip(request),
            )
            self.object.refresh_from_db(fields=['view_count'])
        response = super().get(request, *args, **kwargs)
        pending = request.session.get('pending_document_interaction')
        if request.user.is_authenticated and pending and pending.get('document_id') == self.object.pk:
            request.session.pop('pending_document_interaction', None)
            _apply_interaction(request, self.object, pending['action'], pending['value'])
            return redirect(self.object.get_absolute_url())
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_view = (
            self.object.visibility == Document.Visibility.PUBLIC
            or self.request.user.is_authenticated
        )
        context['can_view_content'] = can_view
        context['preview_kind'] = _preview_kind(self.object.file.name)
        context['preview_url'] = reverse('document_preview', args=[self.object.pk])
        if can_view and context['preview_kind'] in ('docx', 'text'):
            try:
                with self.object.file.open('rb') as file_handle:
                    file_content = file_handle.read()
                if context['preview_kind'] == 'docx':
                    context['preview_content'] = extract_docx_text(file_content)
                else:
                    context['preview_content'] = get_plain_text(file_content)
            except (BadZipFile, KeyError, ParseError):
                context['preview_error'] = 'Không thể đọc nội dung tệp này.'
            except UnicodeDecodeError:
                context['preview_error'] = 'Tệp văn bản không sử dụng mã hóa UTF-8.'
            except FileNotFoundError as exc:
                raise Http404('Không tìm thấy tệp tài liệu.') from exc
        context['comments'] = self.object.comments.filter(is_deleted=False).select_related('user')
        context['comment_form'] = CommentForm()
        context['rating_form'] = RatingForm()
        context['user_rating'] = None
        context['is_favorite'] = False
        if self.request.user.is_authenticated:
            context['user_rating'] = self.object.ratings.filter(
                user=self.request.user
            ).first()
            context['is_favorite'] = PersonalLibrary.objects.filter(
                user=self.request.user,
                document=self.object,
                entry_type=PersonalLibrary.EntryType.FAVORITE,
            ).exists()
        return context


class DocumentUploadView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentUploadForm
    template_name = 'documents/document_upload.html'
    success_url = reverse_lazy('document_list')

    def form_valid(self, form):
        new_category = form.cleaned_data.get('new_category')
        if new_category:
            category = Category.objects.filter(name__iexact=new_category).first()
            if category is None:
                base_slug = slugify(new_category)[:120] or 'danh-muc'
                category_slug = base_slug
                suffix = 2
                while Category.objects.filter(slug=category_slug).exists():
                    suffix_text = f'-{suffix}'
                    category_slug = f'{base_slug[:120 - len(suffix_text)]}{suffix_text}'
                    suffix += 1
                category = Category.objects.create(
                    name=new_category,
                    slug=category_slug,
                )
            form.instance.category = category
        form.instance.uploader = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            'Tài liệu đã được tải lên và đang chờ quản trị viên kiểm duyệt.',
        )
        return response


def _client_ip(request):
    return request.META.get('REMOTE_ADDR') or None


def _preview_kind(file_name):
    extension = Path(file_name).suffix.lower()
    if extension == '.pdf':
        return 'pdf'
    if extension == '.docx':
        return 'docx'
    if extension in TEXT_EXTENSIONS:
        return 'text'
    return 'unsupported'


def document_preview(request, pk):
    document_query = Document.objects.select_related('uploader').filter(pk=pk)
    is_admin = request.user.is_authenticated and (
        request.user.is_superuser or getattr(request.user, 'role', None) == 'admin'
    )
    if is_admin:
        document = get_object_or_404(document_query)
    elif request.user.is_authenticated:
        document = get_object_or_404(
            document_query.filter(
                Q(status=Document.Status.APPROVED)
                | Q(uploader=request.user, status=Document.Status.PENDING)
            )
        )
    else:
        document = get_object_or_404(
            document_query, status=Document.Status.APPROVED
        )

    if (
        document.visibility == Document.Visibility.LOGIN
        and not request.user.is_authenticated
    ):
        return redirect(f"{reverse('login')}?next={request.path}")
    if not document.file:
        raise Http404('Tệp tài liệu không tồn tại.')
    if _preview_kind(document.file.name) != 'pdf':
        return redirect(document.get_absolute_url())

    try:
        file_handle = document.file.open('rb')
    except FileNotFoundError as exc:
        raise Http404('Không tìm thấy tệp tài liệu.') from exc
    response = FileResponse(file_handle, content_type='application/pdf')
    response['Content-Disposition'] = 'inline'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _apply_interaction(request, document, action, value):
    if action == 'comment':
        form = CommentForm({'content': value})
        if form.is_valid():
            comment = form.save(commit=False)
            comment.document = document
            comment.user = request.user
            comment.save()
            messages.success(request, 'Bình luận của bạn đã được đăng.')
        else:
            messages.error(request, ' '.join(form.errors.get('content', [])))
        return

    if action == 'rating':
        form = RatingForm({'stars': value})
        if not form.is_valid():
            messages.error(request, 'Vui lòng chọn từ 1 đến 5 sao.')
            return
        try:
            with transaction.atomic():
                Rating.objects.create(
                    document=document,
                    user=request.user,
                    stars=form.cleaned_data['stars'],
                )
            messages.success(request, 'Cảm ơn bạn đã đánh giá tài liệu.')
        except IntegrityError:
            messages.error(
                request,
                'Bạn đã đánh giá tài liệu này trước đó; không thể đánh giá lại.',
            )
        return

    raise Http404('Thao tác không hợp lệ.')


def document_interaction(request, pk):
    document = get_object_or_404(Document, pk=pk, status=Document.Status.APPROVED)
    if request.method != 'POST':
        return redirect(document.get_absolute_url())
    action = request.POST.get('action', '')
    value = request.POST.get('content', '') if action == 'comment' else request.POST.get('stars', '')
    if action not in ('comment', 'rating'):
        raise Http404('Thao tác không hợp lệ.')
    if not request.user.is_authenticated:
        request.session['pending_document_interaction'] = {
            'document_id': document.pk,
            'action': action,
            'value': value,
        }
        return redirect(f"{reverse('login')}?next={document.get_absolute_url()}")
    _apply_interaction(request, document, action, value)
    return redirect(document.get_absolute_url())


@login_required
def edit_comment(request, pk):
    comment = get_object_or_404(Comment.objects.select_related('document'), pk=pk)
    if comment.user_id != request.user.pk:
        raise PermissionDenied
    if comment.is_deleted:
        raise Http404('Bình luận không tồn tại.')
    if request.method == 'POST':
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.is_edited = True
            updated.save()
            messages.success(request, 'Bình luận đã được cập nhật.')
            return redirect(comment.document.get_absolute_url())
    else:
        form = CommentForm(instance=comment)
    return render(
        request,
        'documents/comment_edit.html',
        {'form': form, 'comment': comment},
    )


@login_required
def delete_comment(request, pk):
    comment = get_object_or_404(Comment.objects.select_related('document'), pk=pk)
    if comment.user_id != request.user.pk:
        raise PermissionDenied
    if request.method == 'POST':
        comment.is_deleted = True
        comment.save(update_fields=['is_deleted', 'updated_at'])
        messages.success(request, 'Bình luận đã được xóa.')
    return redirect(comment.document.get_absolute_url())


@login_required
def download_document(request, pk):
    document_query = Document.objects.filter(pk=pk)
    is_admin = request.user.is_superuser or getattr(request.user, 'role', None) == 'admin'
    if is_admin:
        document = get_object_or_404(document_query)
    else:
        document = get_object_or_404(
            document_query.filter(
                Q(status=Document.Status.APPROVED)
                | Q(uploader=request.user, status=Document.Status.PENDING)
            )
        )
    if not document.file:
        raise Http404('Tệp tài liệu không tồn tại.')
    try:
        file_handle = document.file.open('rb')
    except FileNotFoundError as exc:
        raise Http404('Không tìm thấy tệp tài liệu.') from exc

    Download.objects.create(
        document=document,
        user=request.user,
        ip_address=_client_ip(request),
    )
    Document.objects.filter(pk=document.pk).update(
        download_count=F('download_count') + 1
    )
    PersonalLibrary.objects.get_or_create(
        user=request.user,
        document=document,
        entry_type=PersonalLibrary.EntryType.DOWNLOADED,
    )
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=Path(document.file.name).name,
    )


def deny_direct_document_file(request, file_path):
    raise Http404('Tài liệu chỉ được tải qua chức năng có kiểm tra quyền truy cập.')


@login_required
def personal_library(request):
    entries = PersonalLibrary.objects.filter(user=request.user).select_related(
        'document', 'document__category'
    )
    uploaded = Document.objects.filter(uploader=request.user).select_related('category')
    return render(
        request,
        'documents/personal_library.html',
        {
            'favorites': entries.filter(entry_type=PersonalLibrary.EntryType.FAVORITE),
            'downloaded': entries.filter(entry_type=PersonalLibrary.EntryType.DOWNLOADED),
            'uploaded': uploaded,
            'sections': [
                ('Tài liệu yêu thích', entries.filter(
                    entry_type=PersonalLibrary.EntryType.FAVORITE
                )),
                ('Tài liệu đã tải xuống', entries.filter(
                    entry_type=PersonalLibrary.EntryType.DOWNLOADED
                )),
            ],
        },
    )


@login_required
def remove_library_entry(request, entry_id):
    entry = get_object_or_404(PersonalLibrary, pk=entry_id, user=request.user)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Đã xóa tài liệu khỏi thư viện cá nhân.')
    return redirect('personal_library')


@login_required
def toggle_favorite(request, pk):
    document = get_object_or_404(Document, pk=pk, status=Document.Status.APPROVED)
    if request.method == 'POST':
        favorite, created = PersonalLibrary.objects.get_or_create(
            user=request.user,
            document=document,
            entry_type=PersonalLibrary.EntryType.FAVORITE,
        )
        if not created:
            favorite.delete()
            messages.success(request, 'Đã xóa tài liệu khỏi mục yêu thích.')
        else:
            messages.success(request, 'Đã thêm tài liệu vào mục yêu thích.')
    return redirect(document.get_absolute_url())


@login_required
def share_document(request, pk):
    document = get_object_or_404(Document, pk=pk, status=Document.Status.APPROVED)
    if request.method == 'POST':
        platform = request.POST.get('platform', 'copy_link')[:50]
        if platform not in ('copy_link', 'facebook', 'zalo'):
            messages.error(request, 'Nền tảng chia sẻ không hợp lệ.')
            return redirect(document.get_absolute_url())
        share_link = request.build_absolute_uri(document.get_absolute_url())
        Share.objects.create(
            user=request.user,
            document=document,
            platform=platform,
            share_link=share_link,
        )
        return redirect(document.get_absolute_url())
    return redirect(document.get_absolute_url())


@admin_required
def moderation_list(request):
    status = request.GET.get('status', Document.Status.PENDING)
    documents = Document.objects.select_related('category', 'uploader')
    if status in Document.Status.values:
        documents = documents.filter(status=status)
    return render(
        request,
        'documents/moderation_list.html',
        {'documents': documents, 'status_choices': Document.Status.choices, 'current_status': status},
    )


@admin_required
def moderate_document(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status')
        if status not in (Document.Status.APPROVED, Document.Status.REJECTED):
            messages.error(request, 'Trạng thái kiểm duyệt không hợp lệ.')
        else:
            document.status = status
            document.save(update_fields=['status'])
            messages.success(request, 'Trạng thái tài liệu đã được cập nhật.')
    return redirect('document_moderation')
