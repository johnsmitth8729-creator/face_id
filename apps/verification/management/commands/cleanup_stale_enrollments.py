"""
Management command: cleanup_stale_enrollments

Removes temporary biometric data from incomplete enrollment sessions that are
older than a configurable retention period.

Usage:
    python manage.py cleanup_stale_enrollments
    python manage.py cleanup_stale_enrollments --retention-hours 24
    python manage.py cleanup_stale_enrollments --dry-run
    python manage.py cleanup_stale_enrollments --retention-hours 24 --dry-run

Schedule examples (cron / Celery beat):
    # Every night at 02:00
    0 2 * * * /path/to/venv/bin/python manage.py cleanup_stale_enrollments

    # Every 6 hours
    0 */6 * * * /path/to/venv/bin/python manage.py cleanup_stale_enrollments --retention-hours 24
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Remove temporary biometric data (selfie_embedding, selfie images) '
        'from enrollment sessions that are incomplete and older than '
        '--retention-hours (default: 48). VERIFIED sessions are never touched.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--retention-hours',
            type=int,
            default=48,
            metavar='HOURS',
            help=(
                'Remove biometric data from incomplete sessions older than '
                'this many hours. Default: 48.'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help=(
                'Preview which sessions would be cleaned without making '
                'any changes to the database or storage.'
            ),
        )

    def handle(self, *args, **options):
        retention_hours = options['retention_hours']
        dry_run = options['dry_run']

        from apps.verification.models import VerificationSession, VerificationStatus
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(hours=retention_hours)

        stale_sessions = VerificationSession.objects.filter(
            started_at__lt=cutoff,
        ).exclude(
            status=VerificationStatus.VERIFIED
        ).select_related('user')

        total = stale_sessions.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                f'No stale incomplete sessions found (retention={retention_hours}h).'
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[DRY RUN] Would clean {total} session(s) older than {retention_hours}h:'
            ))
            for session in stale_sessions:
                passport = self._passport(session)
                self.stdout.write(
                    f'  session={session.id} passport={passport} '
                    f'status={session.status} started={session.started_at.isoformat()}'
                )
            self.stdout.write(self.style.WARNING(
                '[DRY RUN] No changes were made. Remove --dry-run to execute.'
            ))
            return

        # ── Live run ─────────────────────────────────────────────────────────
        from apps.verification.cleanup import cleanup_incomplete_enrollment

        cleaned = 0
        skipped = 0
        errors = 0

        self.stdout.write(
            f'Cleaning {total} stale session(s) older than {retention_hours}h ...'
        )

        for session in stale_sessions:
            passport = self._passport(session)
            audit = cleanup_incomplete_enrollment(
                session,
                reason=f'retention_policy_{retention_hours}h',
                performed_by='system:cleanup_stale_enrollments',
            )
            result = audit['cleanup_result']
            if result == 'cleaned':
                cleaned += 1
                self.stdout.write(
                    f'  [CLEANED] session={session.id} passport={passport} '
                    f'files_removed={audit["files_removed"]}'
                )
            elif result == 'skipped_verified':
                skipped += 1
                self.stdout.write(self.style.WARNING(
                    f'  [SKIP/VERIFIED] session={session.id} passport={passport}'
                ))
            elif result == 'no_profile':
                self.stdout.write(
                    f'  [NO_PROFILE] session={session.id} passport={passport}'
                )
            elif result == 'error':
                errors += 1
                self.stdout.write(self.style.ERROR(
                    f'  [ERROR] session={session.id} passport={passport}'
                ))

        # ── Summary ───────────────────────────────────────────────────────────
        summary = (
            f'\nRetention cleanup complete | '
            f'retention={retention_hours}h cutoff={cutoff.isoformat()} | '
            f'scanned={total} cleaned={cleaned} skipped_verified={skipped} errors={errors}'
        )
        if errors:
            self.stdout.write(self.style.ERROR(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))

        logger.info(
            "cleanup_stale_enrollments command | retention_hours=%d cutoff=%s "
            "scanned=%d cleaned=%d skipped_verified=%d errors=%d",
            retention_hours, cutoff.isoformat(), total, cleaned, skipped, errors
        )

    @staticmethod
    def _passport(session) -> str:
        """Best-effort passport number extraction for display only."""
        try:
            return session.user.applicant_profile.passport_number
        except Exception:
            try:
                return f'user_id={session.user_id}'
            except Exception:
                return 'unknown'
