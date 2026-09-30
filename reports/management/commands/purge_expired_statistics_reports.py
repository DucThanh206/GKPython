import logging
from datetime import timedelta

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from reports.models import (
    STATISTICS_REPORT_RETENTION_DAYS,
    StatisticsReport,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete exported statistics reports older than the retention period."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=STATISTICS_REPORT_RETENTION_DAYS)
        expired_reports = StatisticsReport.objects.filter(created_at__lte=cutoff)
        deleted_count = 0

        for report in expired_reports.iterator():
            try:
                if report.file_path:
                    default_storage.delete(report.file_path)
                with transaction.atomic():
                    report.delete()
            except OSError as exc:
                logger.exception(
                    "Could not remove expired statistics report %s", report.pk
                )
                raise CommandError(
                    f"Could not remove expired report {report.pk}; it remains in history."
                ) from exc
            deleted_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Deleted {deleted_count} expired report(s).")
        )
