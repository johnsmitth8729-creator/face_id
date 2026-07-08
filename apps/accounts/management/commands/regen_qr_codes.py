"""
Management command: Regenerate QR codes for all locked applicants.
Usage: python manage.py regen_qr_codes [--force]
"""
from django.core.management.base import BaseCommand
from apps.accounts.models import ApplicantProfile
from apps.qr_module.models import QRCode
from apps.qr_module.generator import generate_qr_code


class Command(BaseCommand):
    help = "Regenerate QR codes for all verified/locked applicants with current domain settings"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing QR codes and regenerate (default: skip existing)",
        )

    def handle(self, *args, **options):
        force = options["force"]
        profiles = ApplicantProfile.objects.filter(is_locked=True)
        total = profiles.count()
        self.stdout.write(f"Found {total} verified applicant(s).")

        regenerated = 0
        skipped = 0

        for profile in profiles:
            existing = QRCode.objects.filter(applicant_profile=profile).first()

            if existing and force:
                if existing.qr_image:
                    try:
                        existing.qr_image.delete(save=False)
                    except Exception:
                        pass
                existing.delete()
                existing = None

            if existing and not force:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(f"  Skipped (exists): {profile.full_name} ({profile.admission_id})")
                )
                continue

            try:
                qr = generate_qr_code(profile)
                regenerated += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  Generated: {profile.full_name} -- Token: {qr.token}")
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  FAILED for {profile.full_name}: {e}"))

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Done. Generated: {regenerated}, Skipped: {skipped}, Total: {total}")
        )
