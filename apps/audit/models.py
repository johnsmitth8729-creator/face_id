"""
AKHU AFIVS — Audit Log Model
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class AuditLog(models.Model):
    """Records all system activities for security compliance."""
    ACTION_CATEGORIES = [
        ('auth', _('Authentication')),
        ('verification', _('Verification')),
        ('admin', _('Administration')),
        ('supervisor', _('Supervisor')),
        ('data', _('Data Management')),
        ('security', _('Security')),
        ('system', _('System')),
        ('report', _('Reports')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    username_snapshot = models.CharField(max_length=150, blank=True)
    user_role_snapshot = models.CharField(max_length=20, blank=True)

    category = models.CharField(max_length=20, choices=ACTION_CATEGORIES, default='system')
    action = models.CharField(_('Action'), max_length=200)
    description = models.TextField(_('Description'), blank=True)

    # Request details
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    method = models.CharField(max_length=10, blank=True)
    path = models.CharField(max_length=500, blank=True)

    # Additional context
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    extra_data = models.JSONField(default=dict, blank=True)

    # Status
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('Audit Log')
        verbose_name_plural = _('Audit Logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['category', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
        ]

    def __str__(self):
        return f'[{self.category}] {self.action} — {self.username_snapshot} — {self.timestamp:%Y-%m-%d %H:%M}'
