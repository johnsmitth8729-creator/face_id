"""
AKHU AFIVS — Verification Models
VerificationSession, FaceProfile, VerificationLog, LivenessChallenge
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class VerificationStatus(models.TextChoices):
    PENDING = 'pending', _('Pending')
    IN_PROGRESS = 'in_progress', _('In Progress')
    VERIFIED = 'verified', _('Verified')
    REVIEW_REQUIRED = 'review_required', _('Review Required')
    REJECTED = 'rejected', _('Rejected')


class VerificationType(models.TextChoices):
    INITIAL = 'initial', _('Initial Verification')
    EXAM_DAY = 'exam_day', _('Examination Day')
    RE_VERIFICATION = 're_verification', _('Re-Verification')


class VerificationStep(models.IntegerChoices):
    PERSONAL_INFO = 1, _('Personal Information')
    DOCUMENT_UPLOAD = 2, _('Document Upload')
    FACE_CAPTURE = 3, _('Face Capture')
    LIVENESS = 4, _('Liveness Detection')
    FACE_MATCHING = 5, _('Face Matching')
    COMPLETED = 6, _('Completed')


class VerificationSession(models.Model):
    """Tracks the 6-step verification wizard progress."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='verification_sessions',
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=255, blank=True)  # for anonymous sessions
    current_step = models.IntegerField(
        choices=VerificationStep.choices,
        default=VerificationStep.PERSONAL_INFO,
    )
    status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.IN_PROGRESS,
    )
    verification_type = models.CharField(
        max_length=20,
        choices=VerificationType.choices,
        default=VerificationType.INITIAL,
    )

    # Step completion flags
    step_personal_info_done = models.BooleanField(default=False)
    step_document_done = models.BooleanField(default=False)
    step_face_capture_done = models.BooleanField(default=False)
    step_liveness_done = models.BooleanField(default=False)
    step_matching_done = models.BooleanField(default=False)

    # Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=50, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Verification Session')
        verbose_name_plural = _('Verification Sessions')
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status'], name='vsession_status_idx'),
            models.Index(fields=['user', 'status'], name='vsession_user_status_idx'),
            models.Index(fields=['session_key'], name='vsession_session_key_idx'),
            models.Index(fields=['expires_at'], name='vsession_expires_idx'),
        ]

    def __str__(self):
        return f'Session {self.id} — Step {self.current_step} — {self.status}'

    @property
    def progress_percentage(self):
        return int((self.current_step / 6) * 100)


class FaceProfile(models.Model):
    """Stores facial data and match results for an applicant."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        VerificationSession,
        on_delete=models.CASCADE,
        related_name='face_profile',
    )

    # Live selfie
    selfie_image = models.ImageField(
        upload_to='selfies/%Y/%m/',
        null=True,
        blank=True,
    )
    selfie_image_hash = models.CharField(max_length=64, blank=True)

    selfie_left = models.ImageField(
        upload_to='liveness/%Y/%m/',
        null=True,
        blank=True,
    )
    selfie_right = models.ImageField(
        upload_to='liveness/%Y/%m/',
        null=True,
        blank=True,
    )
    selfie_up = models.ImageField(
        upload_to='liveness/%Y/%m/',
        null=True,
        blank=True,
    )

    # Face embeddings (stored as JSON list of floats)
    selfie_embedding = models.JSONField(null=True, blank=True)

    # Verification results
    similarity_score = models.FloatField(null=True, blank=True)  # 0.0 - 1.0
    match_percentage = models.FloatField(null=True, blank=True)  # 0 - 100
    status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )

    # Anti-spoofing
    liveness_passed = models.BooleanField(null=True, blank=True)
    anti_spoof_score = models.FloatField(null=True, blank=True)
    anti_spoof_result = models.CharField(max_length=20, blank=True)  # 'real' or 'spoof'

    # Admin review
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_profiles',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Face Profile')
        verbose_name_plural = _('Face Profiles')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status'], name='faceprofile_status_idx'),
            models.Index(fields=['session', 'status'], name='faceprofile_session_status_idx'),
        ]

    def __str__(self):
        return f'FaceProfile — {self.status} — {self.match_percentage}%'

    @property
    def status_display_class(self):
        """Bootstrap color class for status."""
        mapping = {
            'verified': 'success',
            'review_required': 'warning',
            'rejected': 'danger',
            'pending': 'secondary',
            'in_progress': 'info',
        }
        return mapping.get(self.status, 'secondary')


class LivenessChallenge(models.Model):
    """Records liveness challenges issued and completed."""
    CHALLENGE_TYPES = [
        ('blink', _('Blink')),
        ('look_left', _('Look Left')),
        ('look_right', _('Look Right')),
        ('look_up', _('Look Up')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        VerificationSession,
        on_delete=models.CASCADE,
        related_name='liveness_challenges',
    )
    challenge_type = models.CharField(max_length=20, choices=CHALLENGE_TYPES)
    order = models.PositiveSmallIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    confidence = models.FloatField(null=True, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Liveness Challenge')
        verbose_name_plural = _('Liveness Challenges')
        ordering = ['order']

    def __str__(self):
        return f'{self.challenge_type} — {"✓" if self.is_completed else "✗"}'


class VerificationLog(models.Model):
    """Audit trail for every verification attempt."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        VerificationSession,
        on_delete=models.CASCADE,
        related_name='logs',
        null=True,
        blank=True,
    )
    applicant_profile = models.ForeignKey(
        'accounts.ApplicantProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verification_logs',
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supervised_verifications',
    )
    verification_type = models.CharField(
        max_length=20,
        choices=VerificationType.choices,
    )
    result = models.CharField(max_length=20, choices=VerificationStatus.choices)
    score = models.FloatField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_info = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    verified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Verification Log')
        verbose_name_plural = _('Verification Logs')
        ordering = ['-verified_at']
        indexes = [
            models.Index(fields=['verified_at'], name='vlog_verified_at_idx'),
            models.Index(fields=['applicant_profile', 'verification_type'], name='vlog_profile_type_idx'),
            models.Index(fields=['verification_type', 'result'], name='vlog_type_result_idx'),
        ]

    def __str__(self):
        return f'{self.verification_type} — {self.result} — {self.verified_at:%Y-%m-%d %H:%M}'
