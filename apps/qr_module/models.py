"""
AKHU AFIVS — QR Code Model
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class QRCode(models.Model):
    """QR code generated after successful verification."""
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('used', _('Used')),
        ('expired', _('Expired')),
        ('revoked', _('Revoked')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant_profile = models.OneToOneField(
        'accounts.ApplicantProfile',
        on_delete=models.CASCADE,
        related_name='qr_code',
    )
    token = models.CharField(
        _('QR Token'),
        max_length=50,
        unique=True,
        help_text='e.g. AKHU2026-000001',
    )
    signed_token = models.TextField(
        _('Signed JWT Token'),
        blank=True,
        help_text='JWT-signed token for tamper detection',
    )
    qr_image = models.ImageField(
        upload_to='qr_codes/%Y/',
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='active',
    )
    scan_count = models.PositiveIntegerField(default=0)
    last_scanned_at = models.DateTimeField(null=True, blank=True)
    last_scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='qr_scans',
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('QR Code')
        verbose_name_plural = _('QR Codes')
        ordering = ['-generated_at']

    def __str__(self):
        return f'{self.token} — {self.status}'
