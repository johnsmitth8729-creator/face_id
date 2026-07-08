"""
AKHU AFIVS — Biometric Data Cleanup

Reusable helpers for removing temporary biometric data from unfinished,
expired, rejected, or review_required enrollment sessions.

Rules:
  - Only PENDING / non-verified FaceProfile records are cleaned.
  - VERIFIED profiles are NEVER touched.
  - File storage is explicitly deleted (Django CASCADE only removes DB rows;
    media files on disk remain unless FieldFile.delete() is called).
  - Logs: session_id, passport_no, timestamp, reason, performed_by,
    cleanup_result. Never logs images or embedding values.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Fields that hold biometric media files on FaceProfile
_BIOMETRIC_FILE_FIELDS = (
    'selfie_image',
    'selfie_left',
    'selfie_right',
    'selfie_up',
)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def cleanup_incomplete_enrollment(
    session,
    reason: str = 'unspecified',
    performed_by: str = 'system',
) -> dict:
    """
    Remove all biometric data from a single unfinished enrollment session.

    Only cleans records whose FaceProfile.status is NOT 'verified'.
    VERIFIED applicants are never affected.

    Args:
        session:      VerificationSession instance to clean up.
        reason:       Why cleanup is being triggered.
                      E.g. 'session_expired', 'new_enrollment', 'admin_reset',
                           'retention_policy', 'enrollment_cancelled'.
        performed_by: Who triggered the cleanup ('system', 'admin:<username>').

    Returns:
        Structured audit dict:
        {
            'session_id':      str,
            'passport_no':     str,
            'timestamp':       ISO-8601 string,
            'reason':          str,
            'performed_by':    str,
            'cleanup_result':  'cleaned' | 'skipped_verified' | 'no_profile' | 'error',
            'files_removed':   int,
        }
    """
    from apps.verification.models import FaceProfile, VerificationStatus

    passport_no = _get_passport_no(session)
    session_id = str(session.id)
    timestamp = timezone.now().isoformat()

    base_audit = {
        'session_id': session_id,
        'passport_no': passport_no,
        'timestamp': timestamp,
        'reason': reason,
        'performed_by': performed_by,
    }

    # ── No profile at all ────────────────────────────────────────────────────
    try:
        face_profile = FaceProfile.objects.get(session=session)
    except FaceProfile.DoesNotExist:
        audit = {**base_audit, 'cleanup_result': 'no_profile', 'files_removed': 0}
        logger.info(
            "Biometric cleanup | session=%s passport=%s reason=%s performed_by=%s "
            "result=no_profile",
            session_id, passport_no, reason, performed_by
        )
        return audit

    # ── Guard: VERIFIED profiles are untouchable ─────────────────────────────
    if face_profile.status == VerificationStatus.VERIFIED:
        audit = {**base_audit, 'cleanup_result': 'skipped_verified', 'files_removed': 0}
        logger.info(
            "Biometric cleanup | session=%s passport=%s reason=%s performed_by=%s "
            "result=skipped_verified (PROTECTED)",
            session_id, passport_no, reason, performed_by
        )
        return audit

    # ── Delete biometric media files ─────────────────────────────────────────
    files_removed = _delete_biometric_files(
        face_profile, session_id, passport_no, reason, performed_by
    )

    # ── Clear embedding + metadata from DB ───────────────────────────────────
    try:
        face_profile.selfie_embedding = None
        face_profile.anti_spoof_score = None
        face_profile.anti_spoof_result = ''
        face_profile.save(update_fields=[
            'selfie_embedding',
            'anti_spoof_score',
            'anti_spoof_result',
        ])
        cleanup_result = 'cleaned'
    except Exception as db_err:
        cleanup_result = 'error'
        logger.error(
            "Biometric cleanup DB error | session=%s passport=%s reason=%s error=%s",
            session_id, passport_no, reason, db_err
        )

    audit = {
        **base_audit,
        'cleanup_result': cleanup_result,
        'files_removed': files_removed,
    }
    logger.info(
        "Biometric cleanup | session=%s passport=%s timestamp=%s reason=%s "
        "performed_by=%s result=%s files_removed=%d",
        session_id, passport_no, timestamp, reason, performed_by,
        cleanup_result, files_removed
    )
    return audit


def cleanup_all_incomplete_for_user(
    user,
    reason: str = 'new_enrollment',
    performed_by: str = 'system',
) -> list:
    """
    Remove biometric data from ALL unfinished enrollment sessions for a user.

    Called when a new enrollment starts so that no stale temporary templates
    remain from previous incomplete sessions.

    Args:
        user:         CustomUser instance whose previous sessions should be cleaned.
        reason:       Reason string forwarded to cleanup_incomplete_enrollment.
        performed_by: Actor string forwarded to cleanup_incomplete_enrollment.

    Returns:
        List of audit dicts, one per session that was processed.
    """
    from apps.verification.models import VerificationSession, VerificationStatus

    sessions = VerificationSession.objects.filter(
        user=user,
    ).exclude(
        status=VerificationStatus.VERIFIED
    )

    audits = []
    for session in sessions:
        audit = cleanup_incomplete_enrollment(session, reason=reason, performed_by=performed_by)
        audits.append(audit)

    cleaned = sum(1 for a in audits if a['cleanup_result'] == 'cleaned')
    if cleaned:
        logger.info(
            "Biometric bulk cleanup | user=%s cleaned=%d total_sessions=%d reason=%s performed_by=%s",
            user.username, cleaned, len(audits), reason, performed_by
        )
    return audits


def cleanup_stale_enrollments(
    retention_hours: int = 48,
    performed_by: str = 'system:retention_policy',
) -> list:
    """
    Remove biometric data from any incomplete enrollment session that is older
    than `retention_hours` hours.

    Targets statuses: pending, in_progress, rejected, review_required.
    VERIFIED sessions are never touched.

    Args:
        retention_hours: Age threshold in hours. Default 48.
        performed_by:    Actor string for audit logs.

    Returns:
        List of audit dicts.
    """
    from apps.verification.models import VerificationSession, VerificationStatus

    cutoff = timezone.now() - timedelta(hours=retention_hours)

    stale_sessions = VerificationSession.objects.filter(
        started_at__lt=cutoff,
    ).exclude(
        status=VerificationStatus.VERIFIED
    ).select_related('user')

    audits = []
    for session in stale_sessions:
        audit = cleanup_incomplete_enrollment(
            session,
            reason=f'retention_policy_{retention_hours}h',
            performed_by=performed_by,
        )
        audits.append(audit)

    cleaned = sum(1 for a in audits if a['cleanup_result'] == 'cleaned')
    logger.info(
        "Retention cleanup | cutoff=%s retention_hours=%d "
        "sessions_scanned=%d cleaned=%d performed_by=%s",
        cutoff.isoformat(), retention_hours, len(audits), cleaned, performed_by
    )
    return audits


# ──────────────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_passport_no(session) -> str:
    """Return passport number for logging. Never raises."""
    try:
        return session.user.applicant_profile.passport_number
    except Exception:
        try:
            return f'user_id={session.user_id}'
        except Exception:
            return 'unknown'


def _delete_biometric_files(
    face_profile,
    session_id: str,
    passport_no: str,
    reason: str,
    performed_by: str,
) -> int:
    """
    Delete all biometric media files for a FaceProfile.

    Returns the number of files successfully deleted.
    File deletion failures are warned but never propagated.
    """
    deleted = 0
    for field_name in _BIOMETRIC_FILE_FIELDS:
        field_file = getattr(face_profile, field_name, None)
        if field_file and field_file.name:
            try:
                field_file.delete(save=False)
                deleted += 1
                logger.info(
                    "Biometric file removed | field=%s session=%s passport=%s "
                    "reason=%s performed_by=%s",
                    field_name, session_id, passport_no, reason, performed_by
                )
            except Exception as exc:
                logger.warning(
                    "Biometric file delete failed | field=%s session=%s passport=%s "
                    "reason=%s performed_by=%s error=%s",
                    field_name, session_id, passport_no, reason, performed_by, exc
                )
    return deleted
