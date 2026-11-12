import csv
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from documents.models import Category, Document


class Command(BaseCommand):
    help = "Import real Open Textbook Library catalog records as EduHub documents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default=str(Path("data") / "open_textbook_library.csv"),
            help="Path to the Open Textbook Library CSV export.",
        )
        parser.add_argument(
            "--password", required=True,
            help="Password assigned to the local demo accounts (minimum 10 characters).",
        )
        parser.add_argument(
            "--limit", type=int, default=0,
            help="Maximum number of records to import; 0 imports the full catalog.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        if len(password) < 10:
            raise CommandError("The demo password must contain at least 10 characters.")
        csv_path = Path(options["csv"])
        if not csv_path.is_file():
            raise CommandError(f"CSV file not found: {csv_path}")

        User = get_user_model()
        admin, admin_created = User.objects.get_or_create(
            username="demo_admin",
            defaults={
                "email": "demo-admin@example.test",
                "full_name": "EduHub Demo Admin",
                "role": User.Role.ADMIN,
                "is_staff": True,
            },
        )
        if admin_created:
            admin.set_password(password)
            admin.save(update_fields=["password"])

        members = []
        for number in range(1, 6):
            member, created = User.objects.get_or_create(
                username=f"demo_member{number}",
                defaults={
                    "email": f"demo-member{number}@example.test",
                    "full_name": f"EduHub Demo Member {number}",
                    "role": User.Role.MEMBER,
                },
            )
            if created:
                member.set_password(password)
                member.save(update_fields=["password"])
            members.append(member)

        imported = 0
        created_count = 0
        with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            rows = csv.DictReader(source)
            for row in rows:
                if options["limit"] and imported >= options["limit"]:
                    break
                title = (row.get("Title") or "").strip()
                catalog_url = (row.get("Library URL") or "").strip()
                if not title or not catalog_url:
                    continue

                otl_id = (row.get("Otl id") or "").strip()
                subject = (row.get("Subject 1") or "Open Textbooks").strip()
                category_name = subject.split(" - ", 1)[0].strip()[:100] or "Open Textbooks"
                slug = slugify(category_name)[:105] or "open-textbooks"
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={"slug": f"{slug}-{otl_id or imported}"[:120]},
                )

                document_title = f"{title[:220]} [OTL #{otl_id}]"
                uploader = members[imported % len(members)]
                document, created = Document.objects.get_or_create(
                    title=document_title,
                    uploader=uploader,
                    defaults={
                        "description": (row.get("Description") or "")[:4000],
                        "subject": subject[:150],
                        "category": category,
                        "visibility": (
                            Document.Visibility.LOGIN
                            if imported % 5 == 1
                            else Document.Visibility.PUBLIC
                        ),
                        "status": (
                            Document.Status.PENDING
                            if imported % 40 == 39
                            else Document.Status.APPROVED
                        ),
                    },
                )
                if created:
                    created_count += 1
                    details = [
                        title,
                        "Open Textbook Library catalog record",
                        f"Catalog ID: {otl_id}",
                        f"Authors / contributors: {row.get('Contributors', '').strip()}",
                        f"Publisher: {row.get('Publisher', '').strip()}",
                        f"Copyright year: {row.get('Copyright year', '').strip()}",
                        f"License: {row.get('License', '').strip()}",
                        f"ISBN-13: {row.get('ISBN13', '').strip()}",
                        f"Subject: {subject}",
                        f"Catalog: {catalog_url}",
                        "Available resources:",
                    ]
                    for index in range(1, 7):
                        resource_type = (row.get(f"Type {index}") or "").strip()
                        resource_url = (row.get(f"URL {index}") or "").strip()
                        if resource_url:
                            details.append(f"- {resource_type or 'Resource'}: {resource_url}")
                    details.extend([
                        "",
                        "This TXT file contains catalog metadata and links to the original resource.",
                        "The original content and its license remain with the listed publisher/author.",
                    ])
                    safe_name = slugify(title)[:70] or f"book-{otl_id}"
                    document.file.save(
                        f"{safe_name}-otl-{otl_id}.txt",
                        ContentFile("\n".join(details).encode("utf-8")),
                        save=True,
                    )
                imported += 1

        self.stdout.write(self.style.SUCCESS(
            f"Catalog processed: {imported}; new documents: {created_count}; "
            f"categories: {Category.objects.count()}; users: {User.objects.count()}."
        ))
        self.stdout.write("Login: demo_admin or demo_member1 through demo_member5")
