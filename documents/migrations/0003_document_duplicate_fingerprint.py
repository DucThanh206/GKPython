import hashlib
import logging
from pathlib import PurePosixPath

from django.db import migrations, models

logger = logging.getLogger(__name__)


def backfill_document_fingerprints(apps, schema_editor):
    Document = apps.get_model('documents', 'Document')
    pending_updates = []

    for document in Document.objects.exclude(file='').iterator(chunk_size=100):
        try:
            with document.file.storage.open(document.file.name, 'rb') as source:
                digest = hashlib.sha256()
                file_size = 0
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    digest.update(chunk)
        except FileNotFoundError:
            logger.warning(
                'Skipping fingerprint for Document %s because file %s is missing.',
                document.pk,
                document.file.name,
            )
            continue

        document.original_filename = PurePosixPath(document.file.name).name
        document.file_size = file_size
        document.file_sha256 = digest.hexdigest()
        pending_updates.append(document)

        if len(pending_updates) == 100:
            Document.objects.bulk_update(
                pending_updates,
                ['original_filename', 'file_size', 'file_sha256'],
            )
            pending_updates.clear()

    if pending_updates:
        Document.objects.bulk_update(
            pending_updates,
            ['original_filename', 'file_size', 'file_sha256'],
        )


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0002_comment_documentview_download_personallibrary_rating_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='file_sha256',
            field=models.CharField(blank=True, max_length=64, verbose_name='Dấu vân tay nội dung'),
        ),
        migrations.AddField(
            model_name='document',
            name='file_size',
            field=models.PositiveBigIntegerField(blank=True, null=True, verbose_name='Kích thước tệp'),
        ),
        migrations.AddField(
            model_name='document',
            name='original_filename',
            field=models.CharField(blank=True, db_index=True, max_length=255, verbose_name='Tên tệp gốc'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['file_size', 'file_sha256'], name='doc_size_sha256_idx'),
        ),
        migrations.RunPython(
            backfill_document_fingerprints,
            migrations.RunPython.noop,
        ),
    ]
